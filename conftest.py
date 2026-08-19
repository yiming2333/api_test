# ============================================================
# 根目录 conftest.py —— pytest 全局 Fixture 与钩子配置
# ============================================================
#
# 📌 conftest.py 是 pytest 的特殊文件，无需 import 即自动生效
#    放在根目录 → 对所有测试模块全局生效
#    放在子目录 → 仅对该子目录及下级生效
#
# 本文件职责：
#   1. 注册命令行参数（--env）
#   2. 提供全局共享 fixture（db, http, context）
#   3. 测试结束后自动清理数据库脏数据

import pytest
from common.http_client import HttpClient  # 封装的 HTTP 客户端
from common.yaml_handler import get_config  # YAML 配置读取器
from common.context import ctx  # 全局上下文（共享数据黑板）
from utils.db import db as db_client  # 数据库客户端实例
from common.logger import log  # 统一日志


# ============================================================
# Fixture: db —— 全局数据库客户端
# ============================================================

@pytest.fixture(scope="session")
def db():
    """
    全局数据库客户端，session 级别复用

    scope="session" 的含义：
        整个 pytest 运行期间只创建一次，所有测试模块/用例共享同一个实例
        避免每个用例都重新连接数据库（开销大）

    yield vs return:
        这里用 yield 而非 return，是因为 yield 后面的代码会在 session 结束时执行
        （虽然当前没有 teardown 逻辑，但保持与 clean_test_data 一致的风格）

    Usage:
        def test_xxx(db):
            result = db.execute("SELECT * FROM users WHERE id=1")
    """
    yield db_client


# ============================================================
# 钩子: pytest_addoption —— 注册自定义命令行参数
# ============================================================

def pytest_addoption(parser):
    """
    pytest 内置钩子函数，用于注册自定义命令行参数

    注册后可以通过以下方式传入环境：
        pytest --env=dev          → 使用 config/dev.yaml
        pytest --env=prod         → 使用 config/prod.yaml
        pytest                    → 不传则默认 dev

    Args:
        parser: pytest 的参数解析器对象

    ⚠️ 注意：此函数名必须严格为 pytest_addoption，pytest 通过名字自动识别调用
    """
    parser.addoption(
        "--env",  # 命令行参数名
        default="dev",  # 不传时的默认值
        help="运行环境: dev/prod"  # pytest --help 中显示的说明文字
    )


# ============================================================
# Fixture: env_name —— 获取当前运行环境名称
# ============================================================

@pytest.fixture(scope="session")
def env_name(request):
    """
    从命令行参数中提取环境名称

    request 是 pytest 内置的特殊 fixture，提供对当前测试上下文的访问：
        - request.config       → pytest 配置对象
        - request.config.getoption("--env") → 获取 --env 参数的值

    scope="session": 整个会话只解析一次

    Returns:
        str: 环境名称，如 "dev", "prod"

    Usage:
        def test_xxx(env_name):
            print(f"当前环境: {env_name}")  # → "dev"
    """
    return request.config.getoption("--env")


# ============================================================
# Fixture: http —— 全局 HTTP 客户端（无 Token）
# ============================================================

@pytest.fixture(scope="session")
def http(env_name):
    """
    创建全局 HTTP 客户端实例（不带 Token）

    依赖链：http ← env_name ← --env 命令行参数

    工作流程：
        1. 根据 env_name 读取对应的 YAML 配置（如 config/dev.yaml）
        2. 从配置中提取 base_url 和 timeout
        3. 创建 HttpClient 实例
        4. session 级别复用，所有用例共享同一个 Session（TCP 连接复用）

    适用场景：
        - 登录接口（不需要 Token）
        - 注册接口
        - 公开接口

    如果需要带 Token 的客户端，应在具体测试模块的 conftest 中
    基于 http + login_token 再创建一个 auth_http fixture

    Args:
        env_name: 由上面的 env_name fixture 注入的环境名称

    Returns:
        HttpClient: 配置好的 HTTP 客户端实例
    """
    # 读取对应环境的配置文件
    # 例如 env_name="dev" → 读取 config/dev.yaml
    cfg = get_config(env_name)

    # 创建 HTTP 客户端
    # base_url: API 根地址，如 "http://127.0.0.1:5000"
    # timeout: 请求超时秒数，配置中没有则默认 10s
    client = HttpClient(
        base_url=cfg["base_url"],
        timeout=cfg.get("timeout", 10)
    )
    return client


# ============================================================
# Fixture: context —— 全局上下文（带自动清理）
# ============================================================

@pytest.fixture(scope="session")
def context():
    """
    提供全局上下文对象，并在 session 结束时自动清空

    yield 的两阶段语义：
        ┌─ yield 之前 ─→ setup 阶段（此处无额外初始化）
        │  yield ctx   ─→ 将 ctx 注入到使用该 fixture 的用例/fixture 中
        └─ yield 之后 ─→ teardown 阶段（session 结束时执行 ctx.clear()）

    为什么要清空？
        防止上一次 pytest 运行的残留数据影响下一次运行
        （虽然每次 pytest 都是新进程，ctx 天然为空，但作为防御性编程保留）

    Usage:
        def test_xxx(context):
            context.set("order_id", 12345)
            oid = context.get_or_fail("order_id")

        # 或者直接用全局单例（效果相同）：
        from common.context import ctx
        ctx.set("order_id", 12345)
    """
    yield ctx
    # ↓↓↓ session 结束时执行 ↓↓↓
    ctx.clear()
    log.info("🧹 Context 已清空")


# ============================================================
# Fixture: clean_test_data —— 自动清理测试数据（autouse）
# ============================================================

@pytest.fixture(scope="session", autouse=True)
def clean_test_data(db):
    """
    整个测试会话结束后自动清理测试产生的脏数据

    🔑 autouse=True 的含义：
        无需在用例中声明依赖，pytest 会自动激活此 fixture
        适用于"全局副作用管理"类 fixture（清理、初始化等）
        如果 autouse=False，则只有显式写了 def test_xxx(clean_test_data) 才会触发

    🔑 scope="session" + yield 的组合：
        yield 之前 → session 开始时执行（此处为空，即不做前置清理）
        yield 之后 → session 结束时执行（真正的清理逻辑）

        为什么不在 yield 之前清理？
            因为有些测试可能依赖上一轮残留的数据做调试
            放在最后清理更安全，且不影响本次测试的执行顺序

    清理策略：
        按外键依赖的逆序删除（先删子表，再删父表）
        避免外键约束导致的删除失败

        例如：tasks.project_id → projects.id
              必须先删 tasks，再删 projects

    ⚠️ 生产环境警告：
        此 fixture 会 DELETE 整表数据！
        确保只在测试环境（dev/test）使用，永远不要对 prod 数据库执行

    Args:
        db: 由上面的 db fixture 注入的数据库客户端
    """
    # ===== Setup 阶段（session 开始）=====
    # 当前无前置操作，直接 yield
    yield

    # ===== Teardown 阶段（session 结束）=====
    log.info("=" * 50)
    log.info("🧹 开始清理测试数据...")

    # 按外键依赖顺序排列：子表在前，父表在后
    # tasks       → 依赖 projects（project_id 外键）
    # projects    → 独立表或被 tasks 依赖
    # orders      → 可能依赖 users 等
    # file_uploads → 可能依赖 orders 等
    tables = ["tasks", "projects", "orders", "file_uploads"]

    for table in tables:
        try:
            # 执行 DELETE 清空整表
            # ⚠️ 注意：这里用的是字符串拼接，因为表名不能作为参数化绑定
            # 表名来自硬编码列表，不存在 SQL 注入风险
            db.execute(f"DELETE FROM {table}")
            log.info(f"✅ 已清理表: {table}")
        except Exception as e:
            # 某张表清理失败不应阻塞后续表的清理
            # 用 warning 级别记录，不抛异常
            log.warning(f"⚠️ 清理表 {table} 失败: {e}")

    log.info("🧹 测试数据清理完成")
    log.info("=" * 50)

'''
命令行: pytest --env=dev
            │
            ▼
    ┌───────────────┐
    │  pytest_addoption │  ← 钩子，注册 --env 参数
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │   env_name     │  ← session 级，读取 --env 值 → "dev"
    └───────┬───────┘
            │
            ▼
    ┌───────────────┐
    │     http       │  ← session 级，HttpClient(base_url=..., timeout=...)
    └───────────────┘
    
    ┌───────────────┐
    │      db        │  ← session 级，数据库客户端（独立，无依赖）
    └───────┬───────┘
            │
            ▼
    ┌───────────────────┐
    │  clean_test_data   │  ← session 级 + autouse，yield 后清理数据
    └───────────────────┘
    
    ┌───────────────┐
    │    context     │  ← session 级，yield 后 ctx.clear()
    └───────────────┘
'''

'''
pytest 启动
    │
    ├─ pytest_addoption()           ← 注册 --env 参数
    │
    ├─ env_name fixture 执行        ← 解析 --env → "dev"
    │
    ├─ http fixture 执行            ← 读取 dev.yaml，创建 HttpClient
    │
    ├─ db fixture 执行              ← 获取数据库客户端
    │
    ├─ context fixture 执行         ← yield ctx（setup 完成）
    │
    ├─ clean_test_data fixture 执行 ← yield（setup 为空，直接进入测试）
    │
    │   ╔══════════════════════════════════╗
    │   ║  所有测试用例依次执行             ║
    │   ║  test_login → test_order → ...  ║
    │   ╚══════════════════════════════════╝
    │
    ├─ clean_test_data teardown     ← DELETE FROM tasks/projects/orders/file_uploads
    │
    ├─ context teardown             ← ctx.clear()
    │
    └─ pytest 退出
'''