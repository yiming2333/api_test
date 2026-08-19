"""
testcases/conftest.py —— 业务级 Fixture 定义

本文件职责：
    1. 用例执行前后的分隔线日志（方便终端阅读）
    2. 登录获取 Token（session 级，全程只登录一次）
    3. 各类业务资源的创建与清理（订单、文件凭证、项目、任务）

Fixture 作用域设计原则：
    session → 整个测试会话只执行一次（如登录）
    class   → 每个测试类执行一次（如创建订单/项目，同类多个用例共享）
    function→ 每个测试函数执行一次（默认，适用于需要隔离的场景）

依赖链总览：
    http (根conftest)
      └─ login_token (session)
           ├─ created_order (class)
           ├─ upload_credential (class)
           ├─ project (class)
           │    └─ task (class)
           └─ case_boundary (autouse, function级)
"""

import pytest
import allure
from common.context import ctx


# ============================================================
#  Fixture: case_boundary —— 每条用例的分隔线
# ============================================================

@pytest.fixture(autouse=True)
def case_boundary(request, context):
    """
    自动在每个测试用例执行前后打印分隔线

    🔑 autouse=True:
        无需在用例中声明依赖，pytest 对每个测试函数自动激活
        作用域默认为 function（每个用例执行一次）

    🔑 request.node.name:
        pytest 内置对象，获取当前测试用例的名称
        例如："test_create_order_success"

    🔑 yield 的两阶段:
        yield 之前 → 用例执行前打印开始信息
        yield 之后 → 用例执行后打印结束信息

    Args:
        request: pytest 内置 fixture，提供当前测试节点信息
        context: 全局上下文 fixture（来自根 conftest）
    """
    # ===== Setup: 用例开始前 =====
    print(f"\n{'=' * 50}")
    print(f"▶ 开始用例: {request.node.name}")
    print(f"  Context keys: {context.keys()}")
    # 打印当前上下文中已有的 key，方便排查数据依赖问题
    # 例如看到 ['token', 'user_id'] 就知道登录已完成
    print(f"{'=' * 50}")

    yield  # ← 测试用例在此处执行

    # ===== Teardown: 用例结束后 =====
    print(f"◀ 结束用例: {request.node.name}")


# ============================================================
#  Fixture: login_token —— 用户登录（session 级）
# ============================================================

@pytest.fixture(scope="session")
def login_token(http, context):
    """
    登录并获取 Token，整个测试会话只执行一次

    scope="session" 的意义：
        登录是耗时操作（网络请求 + 服务端校验），没必要每个用例都登录
        整个 pytest 运行期间只调用一次，所有用例共享同一个 token

    副作用：
        1. 将 token 和 user_id 写入全局 context（供其他 fixture/用例读取）
        2. 将 Authorization 头设置到 http.session 上
           → 后续所有通过 http 发出的请求都自动携带 Token

    ⚠️ 注意：这里直接修改了 http.session.headers
        这意味着 session 级的 http 客户端从此变为"已认证"状态
        如果某些用例需要未认证状态，应单独创建不带 token 的客户端

    Args:
        http:    全局 HTTP 客户端（来自根 conftest）
        context: 全局上下文

    Returns:
        str: JWT Token 字符串

    Raises:
        AssertionError: 登录失败时立即中断，后续依赖 token 的用例会跳过
    """
    # allure.step 会在 Allure 报告中生成一个可折叠的步骤节点
    # 方便在报告中直观看到"前置操作"和"测试步骤"的分界
    with allure.step("前置操作：用户登录"):
        # 发送登录请求
        resp = http.post("/api/auth/login", json={
            "username": "testuser",
            "password": "Test@123"
        })

        # 断言登录成功，失败时附带响应体便于排查
        assert resp.status_code == 200, f"登录失败: {resp.text}"

        # 解析响应数据
        data = resp.json()["data"]
        token = data["token"]
        user_id = data["user_id"]
        # 注释说明：Flask 后端已修复返回 user_id 字段
        # （保留此注释是因为曾经有过 bug，防止回归）

        # 写入全局上下文，供其他 fixture 和用例使用
        context.set("token", token)
        context.set("user_id", user_id)

        # 将 Token 注入到 HTTP Session 的默认请求头中
        # 之后所有 http.get/post/put/delete 都会自动带上这个头
        http.session.headers["Authorization"] = f"Bearer {token}"

        return token


# ============================================================
#  Fixture: created_order —— 创建测试订单（class 级）
# ============================================================

@pytest.fixture(scope="class")
def created_order(http, context, login_token):
    """
    创建测试订单，并在测试类结束后自动删除

    scope="class" 的含义：
        同一个测试类中的所有用例共享同一个订单
        例如 TestOrder 类中有 test_query / test_update / test_cancel
        它们共用一个 order_id，避免重复创建

        不同测试类会各自创建独立的订单（隔离性）

    依赖 login_token:
        确保在创建订单之前已完成登录（http.session 已有 Authorization 头）
        pytest 会自动按依赖顺序执行：login_token → created_order

    yield + teardown:
        yield 之前 → 创建订单（setup）
        yield order_id → 将 order_id 注入到用例中
        yield 之后 → 删除订单（teardown），保证不留脏数据

    Args:
        http:       已认证的 HTTP 客户端
        context:    全局上下文
        login_token: 登录 token（仅用于触发依赖，不直接使用返回值）

    Yields:
        str/int: 订单 ID
    """
    with allure.step("前置操作：创建测试订单"):
        resp = http.post("/api/orders", json={
            "product_id": "SKU_001",
            "quantity": 1,
            "address": "测试地址"
        })
        # 201 Created 表示资源创建成功（RESTful 规范）
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"

        order_id = resp.json()["data"]["order_id"]

        # 写入上下文，供不直接依赖此 fixture 的用例也能获取
        context.set("order_id", order_id)

        yield order_id  # ← 测试用例在这里执行，接收到 order_id

    # ===== Teardown: 测试类结束后清理 =====
    # Flask 后端已支持 DELETE /api/orders/<id>
    with allure.step("清理：删除测试订单"):
        http.delete(f"/api/orders/{order_id}")
        # 注意：此处没有 assert，因为清理失败不应阻塞后续测试
        # 如果担心清理失败，可以加 log.warning


# ============================================================
#  Fixture: upload_credential —— 获取文件上传凭证（class 级）
# ============================================================

@pytest.fixture(scope="class")
def upload_credential(http, context, login_token):
    """
    获取文件上传凭证（预签名 URL / file_key）

    适用场景：
        对象存储（OSS/S3）上传流程通常是：
        1. 先调后端接口获取上传凭证（file_key + 预签名URL）
        2. 再用凭证直传文件到 OSS
        3. 最后通知后端确认上传完成

        本 fixture 只负责第 1 步，后续步骤在具体用例中完成

    注意：此 fixture 只有 setup 没有 teardown
        因为 file_key 是一次性凭证，无需清理
        如果用 return 而非 yield，就不需要写 teardown 代码

    Args:
        http:       已认证的 HTTP 客户端
        context:    全局上下文
        login_token: 触发登录依赖

    Returns:
        str: file_key，用于后续文件上传
    """
    with allure.step("前置操作：获取上传凭证"):
        resp = http.post("/api/files/upload-token", json={
            "file_name": "test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"

        file_key = resp.json()["data"]["file_key"]

        # 写入上下文
        context.set("file_key", file_key)

        # 用 return 而非 yield，因为不需要 teardown
        return file_key


# ============================================================
#  Fixture: project —— 创建测试项目（class 级，带清理）
# ============================================================

@pytest.fixture(scope="class")
def project(http, context, login_token):
    """
    创建测试项目，测试类结束后自动删除

    与 created_order 类似的模式：yield + teardown
    但这里是项目资源，被 task fixture 依赖

    Args:
        http:       已认证的 HTTP 客户端
        context:    全局上下文
        login_token: 触发登录依赖

    Yields:
        str/int: 项目 ID
    """
    with allure.step("前置操作：创建测试项目"):
        resp = http.post("/api/projects", json={"name": "自动化测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"

        project_id = resp.json()["data"]["id"]
        context.set("project_id", project_id)

        yield project_id  # ← 用例或下游 fixture（task）在此接收 project_id

        # ===== Teardown =====
        with allure.step("清理：删除测试项目"):
            http.delete(f"/api/projects/{project_id}")


# ============================================================
#  Fixture: task —— 创建测试任务（class 级，依赖 project）
# ============================================================

@pytest.fixture(scope="class")
def task(http, context, project):
    """
    创建测试任务，依赖于已创建的项目

    依赖链：task ← project ← login_token ← http
    pytest 自动按此顺序执行，确保项目先于任务创建

    ⚠️ 注意：此 fixture 只有 setup 没有 teardown
        因为任务属于项目的子资源，删除项目时会级联删除任务
        如果后端不支持级联删除，应在此处添加 yield + delete teardown

    Args:
        http:    已认证的 HTTP 客户端
        context: 全局上下文
        project: 项目 ID（由 project fixture 注入）
                 同时触发了 project 的创建

    Returns:
        str/int: 任务 ID
    """
    with allure.step("前置操作：创建测试任务"):
        # 从上下文获取 project_id（双重保险）
        # 也可以直接用参数 project，这里演示 context 的使用方式
        project_id = context.get_or_fail("project_id")
        # get_or_fail 如果取不到会立即报错，比 get() 更安全
        # 能快速暴露"project fixture 没执行"的问题

        resp = http.post(f"/api/projects/{project_id}/tasks", json={
            "title": "测试任务",
            "priority": "high"
        })
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"

        task_id = resp.json()["data"]["id"]
        context.set("task_id", task_id)

        # 用 return，因为任务随项目级联删除，无需单独 teardown
        return task_id

    '''
    scope=session                          scope=class                    scope=function
┌─────────────────────┐
│       http          │ ← 根 conftest
│  (HttpClient实例)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    login_token      │ ← 整个会话只登录 1 次
│  (JWT Token字符串)   │
│  副作用:             │
│  · ctx.set(token)   │
│  · http.headers     │
└──────────┬──────────┘
           │
     ┌─────┼──────────┬──────────────┐
     ▼     ▼          ▼              ▼
┌─────────┐ ┌──────────────┐ ┌──────────┐ ┌──────────────┐
│created_ │ │upload_       │ │ project  │ │case_boundary │ ← autouse
│ order   │ │credential    │ │          │ │(分隔线日志)   │ 每个用例
│(class)  │ │(class)       │ │(class)   │ │(function)    │ 都执行
│yield+   │ │return        │ │yield+    │ │yield         │
│teardown │ │(无teardown)  │ │teardown  │ │              │
└─────────┘ └──────────────┘ └────┬─────┘ └──────────────┘
                                   │
                                   ▼
                            ┌──────────┐
                            │   task   │
                            │(class)   │
                            │return    │
                            │(级联删除) │
                            └──────────┘
    '''