import pytest
import allure
from common.context import ctx


# ============================================================
#  每条用例的分隔线（autouse，放最前面）
# ============================================================
@pytest.fixture(autouse=True)
def case_boundary(request, context):
    print(f"\n{'='*50}")
    print(f"▶ 开始用例: {request.node.name}")
    print(f"  Context keys: {context.keys()}")
    print(f"{'='*50}")
    yield
    print(f"◀ 结束用例: {request.node.name}")


# ============================================================
#  登录 fixture（session 级，整个会话只登录 1 次）
# ============================================================
@pytest.fixture(scope="session")
def login_token(http, context):
    with allure.step("前置操作：用户登录"):
        resp = http.post("/api/auth/login", json={
            "username": "testuser",
            "password": "Test@123"
        })
        assert resp.status_code == 200, f"登录失败: {resp.text}"

        data = resp.json()["data"]
        token = data["token"]
        user_id = data["user_id"]       # ← Flask 现在正确返回了

        context.set("token", token)
        context.set("user_id", user_id)
        http.session.headers["Authorization"] = f"Bearer {token}"

        return token


# ============================================================
#  创建订单 fixture（class 级，依赖 login_token）
# ============================================================
@pytest.fixture(scope="class")
def created_order(http, context, login_token):
    with allure.step("前置操作：创建测试订单"):
        resp = http.post("/api/orders", json={
            "product_id": "SKU_001",
            "quantity": 1,
            "address": "测试地址"
        })
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"

        order_id = resp.json()["data"]["order_id"]
        context.set("order_id", order_id)

        yield order_id

        # teardown
        with allure.step("清理：取消测试订单"):
            http.delete(f"/api/orders/{order_id}")


# ============================================================
#  上传凭证 fixture（class 级）
# ============================================================
@pytest.fixture(scope="class")
def upload_credential(http, context, login_token):
    with allure.step("前置操作：获取上传凭证"):
        resp = http.post("/api/files/upload-token", json={
            "file_name": "test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"

        file_key = resp.json()["data"]["file_key"]
        context.set("file_key", file_key)
        return file_key


# ============================================================
#  项目 fixture（class 级）
# ============================================================
@pytest.fixture(scope="class")
def project(http, context, login_token):
    with allure.step("前置操作：创建测试项目"):
        resp = http.post("/api/projects", json={"name": "自动化测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"

        project_id = resp.json()["data"]["id"]
        context.set("project_id", project_id)

        yield project_id

        with allure.step("清理：删除测试项目"):
            http.delete(f"/api/projects/{project_id}")


# ============================================================
#  任务 fixture（class 级，依赖 project）
# ============================================================
@pytest.fixture(scope="class")
def task(http, context, project):
    with allure.step("前置操作：创建测试任务"):
        project_id = context.get_or_fail("project_id")
        resp = http.post(f"/api/projects/{project_id}/tasks", json={
            "title": "测试任务",
            "priority": "high"
        })
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"

        task_id = resp.json()["data"]["id"]
        context.set("task_id", task_id)

        yield task_id