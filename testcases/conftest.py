# testcases/conftest.py

import pytest
import allure

from utils.accounts import get_account


@pytest.fixture(autouse=True)
def case_boundary(request):
    """每条用例的分隔线（纯日志，无状态）"""
    worker_id = request.config.workerinput.get("workerid", "master") \
        if hasattr(request.config, "workerinput") else "master"
    print(f"\n{'='*50}")
    print(f"▶ [{worker_id}] 开始用例: {request.node.name}")
    print(f"{'='*50}")
    yield
    print(f"◀ [{worker_id}] 结束用例: {request.node.name}")


# ============================================================
#  独立数据工厂 fixture（每条用例独立创建、独立清理）
# ============================================================

@pytest.fixture()
def fresh_order(logged_in_http):
    """
    每条用例独立的订单（function 级，默认就是 function）。
    创建 → yield → 清理，完全自包含。
    """
    with allure.step("前置：创建独立订单"):
        resp = logged_in_http.post("/api/orders", json={
            "product_id": "SKU_ISOLATED",
            "quantity": 1,
            "address": "隔离测试地址"
        })
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"
        order_id = resp.json()["data"]["order_id"]

    yield order_id

    # teardown：清理自己创建的订单
    with allure.step("清理：删除订单"):
        logged_in_http.delete(f"/api/orders/{order_id}")


@pytest.fixture()
def fresh_project(logged_in_http):
    """每条用例独立的项目"""
    with allure.step("前置：创建独立项目"):
        resp = logged_in_http.post("/api/projects", json={"name": "隔离测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"
        project_id = resp.json()["data"]["id"]

    yield project_id

    with allure.step("清理：删除项目"):
        logged_in_http.delete(f"/api/projects/{project_id}")


@pytest.fixture()
def fresh_task(logged_in_http, fresh_project):
    """
    每条用例独立的任务。
    依赖 fresh_project，但都是 function 级，每条用例独立一套。
    """
    with allure.step("前置：创建独立任务"):
        resp = logged_in_http.post(f"/api/projects/{fresh_project}/tasks", json={
            "title": "隔离测试任务",
            "priority": "high"
        })
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"
        task_id = resp.json()["data"]["id"]

    yield {"project_id": fresh_project, "task_id": task_id}

    # task 会随 project 删除而级联删除，无需额外清理


@pytest.fixture()
def fresh_upload_token(logged_in_http):
    """每条用例独立的上传凭证：自动创建 → yield → 自动 DELETE 清理。"""
    file_key = None
    with allure.step("前置：获取上传凭证"):
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_name": "isolated_test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"
        file_key = resp.json()["data"]["file_key"]

    yield file_key

    with allure.step("清理：删除上传记录"):
        if file_key:
            # 不 assert，避免之前用例失败时 teardown 再报错掩盖原问题
            logged_in_http.delete(f"/api/files/{file_key}")


@pytest.fixture
def another_user_file_key(http):
    """创建/获取 user_b 的 upload token，用例结束后 DELETE 清理。"""
    account = get_account("user_b")
    user_b_token = None
    file_key = None

    with allure.step(f"注册用户 {account['username']}（幂等）"):
        resp = http.post("/api/auth/register", json={
            "username": account["username"],
            "password": account["password"],
        })
        assert resp.status_code == 200, f"注册失败: {resp.text}"
        user_b_token = resp.json()["data"]["token"]
        auth_header = {"Authorization": f"Bearer {user_b_token}"}

    with allure.step(f"获取 {account['username']} 的 upload token"):
        resp2 = http.post(
            "/api/files/upload-token",
            json={"file_name": "b_test.png", "file_type": "png"},
            headers=auth_header,
        )
        assert resp2.status_code == 200, f"获取 upload-token 失败: {resp2.text}"
        file_key = resp2.json()["data"]["file_key"]

    yield file_key

    with allure.step(f"清理：删除 {account['username']} 的上传记录"):
        if file_key and user_b_token:
            http.delete(
                f"/api/files/{file_key}",
                headers={"Authorization": f"Bearer {user_b_token}"},
            )