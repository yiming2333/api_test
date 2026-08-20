import requests
import allure
import json
from urllib3.util.retry import Retry  # 重试策略配置
from requests.adapters import HTTPAdapter  # 请求适配器（挂载重试策略到 Session）
from common.logger import log  # 项目统一日志模块
from common.yaml_handler import get_config


class HttpClient:
    """
    封装的 HTTP 客户端

    设计目标：
    1. 统一管理 base_url，测试用例只写相对路径（如 /api/orders）
    2. 自动携带 Authorization Token（登录后注入）
    3. 网络抖动时自动重试（502/503/504 等临时性错误）
    4. 每次请求自动记录日志 + Allure 附件（方便排查和生成报告）
    5. 提供 get/post/put/delete 语法糖，调用简洁

    Usage:
        client = HttpClient(base_url="http://127.0.0.1:5000", token="xxx")
        resp = client.post("/api/login", json={"username": "admin", "password": "123"})
        assert resp.status_code == 200
    """

    def __init__(self, base_url, env="dev",timeout=10, token=None):
        """
        初始化 HTTP 客户端

        Args:
            base_url: API 根地址，例如 "http://127.0.0.1:5000"
                      后续请求只需传相对路径，会自动拼接
            timeout:  请求超时时间（秒），默认 10s
                      超过此时间未响应则抛出 Timeout 异常
            token:    JWT Token（可选），登录成功后传入
                      会自动添加到每个请求的 Authorization 头中
        """
        _cfg = get_config(env)
        self.base_url = base_url
        self.timeout = _cfg.get("timeout", timeout)

        # 使用 Session 而非裸 requests.get/post 的好处：
        # 1. 自动保持 Cookie（如果服务端用 Cookie 鉴权）
        # 2. 复用 TCP 连接（keep-alive），性能更好
        # 3. 统一设置 headers，不用每次请求都重复传
        self.session = requests.Session()

        # 如果传入了 token，设置到 Session 的默认请求头中
        # 之后所有通过该 Session 发出的请求都会自动带上这个头
        # 格式遵循 JWT 标准：Authorization: Bearer <token>
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        # ============================================================
        # 自动重试机制配置
        # ============================================================
        # 场景：Jenkins 跑测试时，Flask 可能偶尔返回 502/503（重启中）
        #        或者网络瞬断导致连接重置
        # 不加重试 → 测试直接失败（误报）
        # 加了重试 → 自动等一会儿再试，减少 flaky test

        retry = Retry(
            total=_cfg.get("retry", 2),  # 最多重试 2 次（加上原始请求，总共最多发 3 次）
            backoff_factor=0.5,  # 退避因子：第 1 次重试等 0.5s，第 2 次等 1.0s
            # 计算公式：{backoff_factor} * (2 ** (retry_count - 1))
            # 即：0.5s → 1.0s → 2.0s ...
            status_forcelist=[502, 503, 504]  # 只有这些状态码才触发重试
            # 502 Bad Gateway  → 网关/代理收到无效响应
            # 503 Service Unavailable → 服务暂时不可用
            # 504 Gateway Timeout → 网关超时
            # 注意：4xx 错误不会重试（那是客户端问题，重试也没用）
        )

        # 将重试策略挂载到 HTTPAdapter 上
        adapter = HTTPAdapter(max_retries=retry)

        # 分别对 http:// 和 https:// 协议的请求生效
        # mount 的意思是：所有以 "http://" 开头的 URL 都用这个 adapter 处理
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        """
        统一请求入口（核心方法）

        所有 HTTP 请求都经过这个方法，实现：
        1. URL 自动拼接（相对路径 + base_url）
        2. 请求前打印日志（方法、URL、参数）
        3. Allure 报告附加请求详情
        4. 发送请求
        5. 响应后打印日志（状态码、耗时、响应体）
        6. Allure 报告附加响应详情

        Args:
            method: HTTP 方法字符串，如 "GET", "POST", "PUT", "DELETE"
            url:    请求路径，可以是相对路径（/api/orders）或完整 URL
            **kwargs: 透传给 requests.Session.request 的参数，常用：
                      - json=dict   → 请求体（自动序列化为 JSON）
                      - params=dict → URL 查询参数
                      - headers=dict → 额外请求头
                      - data=str    → 表单数据

        Returns:
            requests.Response: 原始响应对象，调用方可自行 .json() / .status_code 等

        Raises:
            requests.exceptions.RequestException: 网络异常（连接超时、DNS 解析失败等）
        """

        # ---------- URL 拼接 ----------
        # 如果传入的已经是完整 URL（以 http 开头），则直接使用
        # 否则拼接 base_url + 相对路径
        # 例：base_url="http://127.0.0.1:5000", url="/api/orders"
        #     → full_url="http://127.0.0.1:5000/api/orders"
        full_url = url if url.startswith("http") else self.base_url + url

        # ---------- 请求前日志 ----------
        # 在终端/Jenkins Console 中可以看到每次请求的详细信息
        log.info(f"➡️  请求: {method.upper()} {full_url}")
        log.info(f"   参数: {kwargs}")
        # kwargs 示例输出：{'json': {'username': 'admin', 'password': '123'}}

        # ---------- Allure 记录请求详情 ----------
        # 在 Allure 报告中会显示为一个可展开的 JSON 附件
        # 方便测试失败时快速查看当时发了什么请求
        allure.attach(
            json.dumps(kwargs, ensure_ascii=False, indent=2, default=str),
            # ensure_ascii=False → 中文正常显示，不转义为 \uXXXX
            # indent=2           → 格式化缩进，便于阅读
            # default=str        → 遇到不可序列化的对象（如 datetime）转为字符串，避免报错
            name=f"请求-{method.upper()} {url}",  # 附件标题
            attachment_type=allure.attachment_type.JSON  # 附件类型（Allure 会高亮 JSON）
        )

        # ---------- 发送请求 ----------
        try:
            resp = self.session.request(
                method,  # HTTP 方法
                full_url,  # 完整 URL
                timeout=self.timeout,  # 超时时间（覆盖 Session 默认值）
                **kwargs  # 其余参数透传（json, params, headers 等）
            )
        except requests.exceptions.RequestException as e:
            # 捕获所有 requests 相关异常：
            # - ConnectionError: 无法连接到服务器
            # - Timeout: 请求超时
            # - TooManyRedirects: 重定向次数过多
            # - HTTPError: 其他 HTTP 错误
            log.error(f"❌ 请求异常: {e}")
            raise  # 重新抛出，让 pytest 标记该用例为 ERROR（不是 FAIL）

        # ---------- 响应日志 ----------
        # resp.elapsed 是 requests 自动计算的请求耗时（timedelta 对象）
        log.info(f"⬅️  状态码: {resp.status_code} | 耗时: {resp.elapsed.total_seconds():.3f}s")

        # 尝试按 JSON 格式打印响应体（更美观）
        # 如果不是 JSON（如 HTML 错误页），则打印原始文本（截取前 500 字符防止刷屏）
        try:
            log.info(f"   响应体: {resp.json()}")
        except Exception:
            log.info(f"   响应体(非JSON): {resp.text[:500]}")

        # ---------- Allure 记录响应 ----------
        # 根据 Content-Type 决定附件类型：
        # - JSON 响应 → 用 JSON 类型（Allure 会格式化显示）
        # - 其他响应 → 用 TEXT 类型
        content_type = resp.headers.get("Content-Type", "")
        allure.attach(
            resp.text,  # 响应原始文本
            name=f"响应-{resp.status_code}",
            attachment_type=(
                allure.attachment_type.JSON if "json" in content_type
                else allure.attachment_type.TEXT
            )
        )

        return resp

    # ============================================================
    # 语法糖方法（Syntactic Sugar）
    # ============================================================
    # 让调用更简洁直观：
    #   client.request("GET", "/api/orders")     →  client.get("/api/orders")
    #   client.request("POST", "/api/login", json={...})  →  client.post("/api/login", json={...})

    def get(self, url, **kwargs):
        """发送 GET 请求"""
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        """发送 POST 请求"""
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        """发送 PUT 请求"""
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        """发送 DELETE 请求"""
        return self.request("DELETE", url, **kwargs)

'''
测试用例调用
    │
    ▼
client.post("/api/login", json={"username":"admin"})
    │
    ▼
┌─────────────────────────────────────────────────┐
│  HttpClient.request("POST", "/api/login", ...)   │
│                                                   │
│  1. URL 拼接: base_url + "/api/login"             │
│     → "http://127.0.0.1:5000/api/login"           │
│                                                   │
│  2. 日志: ➡️ 请求: POST http://...                │
│                                                   │
│  3. Allure: 附加请求 JSON                          │
│                                                   │
│  4. Session.request() 发送                        │
│     ├── 自动带 Authorization: Bearer xxx          │
│     ├── 超时 10s                                   │
│     └── 502/503/504 自动重试 2 次                  │
│                                                   │
│  5. 日志: ⬅️ 状态码: 200 | 耗时: 0.023s           │
│                                                   │
│  6. Allure: 附加响应体                             │
│                                                   │
│  7. return resp                                   │
└─────────────────────────────────────────────────┘
    │
    ▼
assert resp.status_code == 200
assert resp.json()["data"]["token"] is not None
'''

'''
正常情况：
  请求 ──→ 200 OK ✅ （1 次请求）

遇到 503：
  请求 ──→ 503 ❌
  等待 0.5s
  重试1 ──→ 503 ❌
  等待 1.0s
  重试2 ──→ 200 OK ✅ （共 3 次请求）

遇到 503 且重试耗尽：
  请求 ──→ 503 ❌
  等待 0.5s
  重试1 ──→ 503 ❌
  等待 1.0s
  重试2 ──→ 503 ❌
  抛出 RetryError 🚨 （pytest 标记为 FAIL）

遇到 404（不在 status_forcelist 中）：
  请求 ──→ 404 ❌
  不重试，直接返回 resp（由测试用例自己 assert）
'''