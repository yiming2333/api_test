# testcases/conftest.py

import pytest
import allure


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
    """每条用例独立的上传凭证"""
    with allure.step("前置：获取上传凭证"):
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_name": "isolated_test.png",
            "file_type": "image/png"
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"
        file_key = resp.json()["data"]["file_key"]

    yield file_key