"""
全局上下文管理器
用于在 fixture 和用例之间传递接口依赖数据

解决的核心问题：
    接口自动化测试中，用例之间有数据依赖。例如：
    - 注册接口 → 返回 user_id
    - 登录接口 → 需要 user_id，返回 token
    - 下单接口 → 需要 token

    如果用 pytest fixture 的 return 值传递，会导致 fixture 之间强耦合。
    Context 提供了一个"公共黑板"，任何 fixture/用例都可以往上写、从上面读，
    实现松耦合的数据共享。

使用示例：
    # fixture 中写入
    @pytest.fixture(scope="session")
    def register_user(auth_http, ctx):
        resp = auth_http.post("/api/register", json={"username": "test"})
        ctx.set("user_id", resp.json()["data"]["id"])      # 写入

    # 另一个 fixture 或用例中读取
    def test_get_profile(auth_http, ctx):
        user_id = ctx.get_or_fail("user_id")               # 读取
        resp = auth_http.get(f"/api/users/{user_id}")
        assert resp.status_code == 200
"""

import threading


class Context:
    """
    线程安全的共享字典（全局上下文）。

    设计要点：
    1. 线程安全 —— 用 threading.Lock 保护读写操作
       （pytest-xdist 多线程 / 未来并发执行时不会数据竞争）
    2. 单例模式 —— 模块底部创建唯一实例 ctx，所有地方 import 同一个
    3. 简单的 KV 存储 —— 本质上就是一个加了锁的 dict 包装器

    生命周期：
        session 开始 → ctx 为空
        fixture 执行 → 逐步往 ctx 里 set 数据
        用例执行     → 从 ctx 里 get 数据
        session 结束 → ctx.clear() 清空（可选）
    """

    def __init__(self):
        # 内部存储字典，所有共享数据都存在这里
        # 外部不应直接访问 _data，应通过 set/get 方法操作
        self._data = {}

        # 线程锁，保证多线程环境下读写安全
        # 场景：如果将来用 pytest-xdist 并行执行，多个线程可能同时读写 _data
        # 不加锁 → 可能出现数据丢失或读到不一致的状态
        self._lock = threading.Lock()

    # ============================================================
    # 写入方法
    # ============================================================

    def set(self, key, value):
        """
        存入一个键值对

        Args:
            key:   字符串键名，建议用有意义的名字如 "user_id", "token", "order_id"
            value: 任意 Python 对象（str, int, dict, list 等）

        Example:
            ctx.set("token", "eyJhbGciOiJIUzI1NiJ9...")
            ctx.set("user_id", 10086)
        """
        with self._lock:
            # with 语句自动加锁/解锁，即使发生异常也能正确释放锁
            self._data[key] = value

    def set_many(self, mapping: dict):
        """
        批量存入多个键值对（原子操作）

        原子性：要么全部写入成功，要么都不写入（在锁保护下一次性 update）

        Args:
            mapping: 字典，key-value 对

        Example:
            ctx.set_many({
                "user_id": 10086,
                "username": "test_user",
                "role": "admin"
            })
        """
        with self._lock:
            self._data.update(mapping)

    # ============================================================
    # 读取方法
    # ============================================================

    def get(self, key, default=None):
        """
        安全取值 —— 不存在时返回默认值，不报错

        适用于：可选数据，没有也不影响测试继续执行

        Args:
            key:     要取的键名
            default: 键不存在时的返回值，默认 None

        Returns:
            对应的值，或 default

        Example:
            nickname = ctx.get("nickname", "匿名用户")
            # 如果没人 set 过 "nickname"，返回 "匿名用户" 而不是报错
        """
        # 注意：get 是读操作，dict.get() 本身是原子的（CPython GIL 保护）
        # 严格来说这里不需要加锁，但为了语义一致性也可以加
        # 当前实现没加锁，性能更好，在 CPython 下也是安全的
        return self._data.get(key, default)

    def get_or_fail(self, key):
        """
        强制取值 —— 不存在时直接抛出 KeyError

        适用于：前置依赖数据，如果没有说明测试流程有问题，应该立即失败
        比 get() 更安全，能快速暴露 fixture 执行顺序问题

        Args:
            key: 要取的键名

        Returns:
            对应的值

        Raises:
            KeyError: 键不存在时抛出，错误信息会提示当前已有的 keys，方便排查

        Example:
            token = ctx.get_or_fail("token")
            # 如果 login fixture 没跑过，这里会立刻报错：
            # KeyError: ❌ Context 中找不到 'token'，请检查对应的 fixture 是否已执行。
            #           当前已有 keys: ['user_id', 'username']
        """
        if key not in self._data:
            raise KeyError(
                f"❌ Context 中找不到 '{key}'，"
                f"请检查对应的 fixture 是否已执行。"
                f"当前已有 keys: {list(self._data.keys())}"
                # 列出当前所有 keys，帮助开发者快速定位是哪个 fixture 漏了
            )
        return self._data[key]

    # ============================================================
    # 工具方法
    # ============================================================

    def has(self, key):
        """
        检查某个 key 是否存在

        适用于：条件判断，比如"如果已经登录了就跳过登录步骤"

        Example:
            if not ctx.has("token"):
                # 执行登录...
                ctx.set("token", new_token)
        """
        return key in self._data

    def keys(self):
        """
        返回当前所有 key 的列表（快照）

        返回 list 而非 dict_keys 视图，避免遍历过程中 _data 被修改导致异常

        Example:
            print(ctx.keys())  # ['user_id', 'token', 'order_id']
        """
        return list(self._data.keys())

    def clear(self):
        """
        清空所有数据

        调用时机：
        - session 结束时（teardown）
        - 需要重置状态时（比如切换测试账号）

        注意：加锁保证清空操作的原子性
        """
        with self._lock:
            self._data.clear()

    def dump(self):
        """
        调试用：返回当前所有数据的副本（浅拷贝）

        用途：
        - 在日志中打印当前上下文状态
        - 在 Allure 报告中附加上下文快照
        - 排查"为什么取不到某个值"的问题

        Returns:
            dict: 当前 _data 的副本

        Example:
            log.info(f"当前上下文: {ctx.dump()}")
            # 输出：当前上下文: {'user_id': 10086, 'token': 'eyJ...'}
        """
        return dict(self._data)

    def __repr__(self):
        """
        自定义打印表示

        在交互式调试或日志中看到 ctx 对象时，显示当前有哪些 keys
        而不是默认的 <Context object at 0x7f...>

        Example:
            print(ctx)  # <Context keys=['user_id', 'token']>
        """
        return f"<Context keys={self.keys()}>"


# ============================================================
# 全局单例实例
# ============================================================
# Python 模块只会被 import 一次（sys.modules 缓存），
# 所以这行代码只会执行一次，整个进程只有一个 Context 实例。
#
# 所有文件通过 from common.context import ctx 拿到的都是同一个对象。
# 这就是 Python 中最简单的单例模式实现。
#
# 使用方式：
#   from common.context import ctx
#   ctx.set("token", "xxx")        # 在 fixture 中写入
#   token = ctx.get_or_fail("token")  # 在用例中读取
ctx = Context()

'''
pytest session 开始
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  fixture: register_user                               │
│  resp = http.post("/api/register", ...)               │
│  ctx.set("user_id", 10086)          ──写入──→  _data  │
└──────────────────────────────────────────────────────┘
    │                                          │
    ▼                                          │  _data = {"user_id": 10086}
┌──────────────────────────────────────────────────────┐
│  fixture: login                                       │
│  uid = ctx.get_or_fail("user_id")   ←──读取──  _data  │
│  resp = http.post("/api/login", ...)                  │
│  ctx.set("token", "eyJ...")         ──写入──→  _data  │
└──────────────────────────────────────────────────────┘
    │                                          │
    ▼                                          │  _data = {"user_id": 10086,
    │                                          │           "token": "eyJ..."}
┌──────────────────────────────────────────────────────┐
│  test_create_order (测试用例)                          │
│  token = ctx.get_or_fail("token")   ←──读取──  _data  │
│  resp = http.post("/api/orders",                      │
│                   headers={"Authorization": token})   │
│  ctx.set("order_id", 99001)         ──写入──→  _data  │
└──────────────────────────────────────────────────────┘
    │                                          │
    ▼                                          │  _data = {"user_id": 10086,
    │                                          │           "token": "eyJ...",
┌──────────────────────────────────────────────────────┐  "order_id": 99001}
│  test_query_order (测试用例)                           │
│  oid = ctx.get_or_fail("order_id")  ←──读取──  _data  │
│  resp = http.get(f"/api/orders/{oid}")                │
│  assert resp.json()["data"]["status"] == "created"    │
└──────────────────────────────────────────────────────┘
    │
    ▼
pytest session 结束 → ctx.clear()
'''

'''
线程 A (fixture)                线程 B (用例)
    │                               │
    ├─ ctx.set("token", "abc")      │
    │   🔒 加锁                     │
    │   _data["token"] = "abc"      │
    │   🔓 解锁                     │
    │                               ├─ ctx.get("token")
    │                               │   → "abc" ✅ 读到完整值
    │                               │
    ├─ ctx.set("token", "xyz")      ├─ ctx.set("order_id", 1)
    │   🔒 加锁                     │   🔒 等待锁...
    │   _data["token"] = "xyz"      │   ...
    │   🔓 解锁                     │   🔒 获得锁
    │                               │   _data["order_id"] = 1
    │                               │   🔓 解锁
    │                               │
    不会出现 _data 处于半写入状态的情况
'''