import uuid

import pytest
import allure

from common.logger import log
from utils.accounts import get_account


@pytest.fixture(autouse=True)
def case_boundary(request):
    """每条用例的分隔线（纯日志，无状态）"""
    worker_id = (
        request.config.workerinput.get("workerid", "master")
        if hasattr(request.config, "workerinput")
        else "master"
    )
    print(f"\n{'=' * 50}")
    print(f"▶ [{worker_id}] 开始用例: {request.node.name}")
    print(f"{'=' * 50}")
    yield
    print(f"◀ [{worker_id}] 结束用例: {request.node.name}")


# ============================================================
#  独立 HttpClient + 新用户身份（用例级，完全隔离）
# ============================================================

@pytest.fixture
def user_http(env_name):
    """
    用例级独立 HttpClient 实例。
    与 session 级 http / logged_in_http 完全隔离。
    用例结束后自动关闭 session。
    """
    from common.http_client import HttpClient
    from common.yaml_handler import get_config

    cfg = get_config(env_name)
    client = HttpClient(
        base_url=cfg["base_url"],
        env=env_name,
        timeout=cfg.get("timeout", 10),
    )
    yield client
    client.session.close()


@pytest.fixture
def new_user(user_http, db):
    """
    用例级 fixture：注册一个全新用户，返回用户信息字典。

    返回结构:
        {
            "token": str,
            "user_id": int,
            "username": str,
            "auth_header": {"Authorization": "Bearer xxx"},
        }

    ★ 不修改 user_http 的任何状态，调用方自行决定如何使用 token。
    ★ 用例结束后从 DB 清理该用户及所有关联数据。
    """
    account = get_account("user_b")
    unique_username = f"{account['username']}_{uuid.uuid4().hex[:8]}"
    user_id = None

    with allure.step(f"注册用户 {unique_username}"):
        resp = user_http.post("/api/auth/register", json={
            "username": unique_username,
            "password": account["password"],
        })
        assert resp.status_code == 200, f"注册失败: {resp.text}"
        data = resp.json()["data"]
        user_id = data["user_id"]

    user_info = {
        "token": data["token"],
        "user_id": user_id,
        "username": unique_username,
        "auth_header": {"Authorization": f"Bearer {data['token']}"},
    }

    yield user_info

    with allure.step(f"清理：删除用户 {unique_username} (user_id={user_id})"):
        if user_id:
            try:
                # 按外键依赖从叶子到根逐个删除
                tables = [
                    ("tasks", "project_id IN (SELECT id FROM projects WHERE user_id = %s)"),
                    ("orders", "user_id = %s"),
                    ("projects", "user_id = %s"),
                    ("file_uploads", "user_id = %s"),
                ]
                for table, where in tables:
                    db.execute(f"DELETE FROM {table} WHERE {where}", (user_id,))
                db.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            except Exception as e:
                log.error(f"❌ 清理用户 {unique_username} 失败: {e}")
                raise


@pytest.fixture
def authed_user_http(user_http, new_user):
    """
    已认证的用户级 HttpClient：基于 user_http + new_user 组合而成。
    用例拿到时已带好 Authorization header，可直接发请求。

    ★ 只在 user_http 这个独立实例上设置 header，不影响 session 级 http。
    ★ 用例结束后 user_http 被销毁，header 随之消失，零残留。
    """
    user_http.session.headers["Authorization"] = new_user["auth_header"]["Authorization"]
    user_http._user_id = new_user["user_id"]
    user_http._token = new_user["token"]
    user_http._username = new_user["username"]
    return user_http


# ============================================================
#  独立数据工厂 fixture（function 级，自包含）
# ============================================================

@pytest.fixture
def fresh_order(logged_in_http):
    """每条用例独立的订单（default 用户身份）"""
    with allure.step("前置：创建独立订单"):
        resp = logged_in_http.post("/api/orders", json={
            "product_id": "SKU_ISOLATED",
            "quantity": 1,
            "address": "隔离测试地址",
        })
        assert resp.status_code == 201, f"创建订单失败: {resp.text}"
        order_id = resp.json()["data"]["order_id"]

    yield order_id

    with allure.step("清理：删除订单"):
        logged_in_http.delete(f"/api/orders/{order_id}")


@pytest.fixture
def fresh_project(logged_in_http):
    """每条用例独立的项目"""
    with allure.step("前置：创建独立项目"):
        resp = logged_in_http.post("/api/projects", json={"name": "隔离测试项目"})
        assert resp.status_code == 201, f"创建项目失败: {resp.text}"
        project_id = resp.json()["data"]["id"]

    yield project_id

    with allure.step("清理：删除项目"):
        logged_in_http.delete(f"/api/projects/{project_id}")


@pytest.fixture
def fresh_task(logged_in_http, fresh_project):
    """每条用例独立的任务（依赖 fresh_project）"""
    with allure.step("前置：创建独立任务"):
        resp = logged_in_http.post(
            f"/api/projects/{fresh_project}/tasks",
            json={"title": "隔离测试任务", "priority": "high"},
        )
        assert resp.status_code == 201, f"创建任务失败: {resp.text}"
        task_id = resp.json()["data"]["id"]

    yield {"project_id": fresh_project, "task_id": task_id}
    # task 随 project 级联删除，无需额外清理


@pytest.fixture
def fresh_upload_token(logged_in_http):
    """每条用例独立的上传凭证"""
    file_key = None
    with allure.step("前置：获取上传凭证"):
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_name": "isolated_test.png",
            "file_type": "image/png",
        })
        assert resp.status_code == 200, f"获取上传凭证失败: {resp.text}"
        file_key = resp.json()["data"]["file_key"]

    yield file_key

    with allure.step("清理：删除上传记录"):
        if file_key:
            logged_in_http.delete(f"/api/files/{file_key}")


@pytest.fixture
def another_user_file_key(authed_user_http, db):
    """
    以独立新用户身份获取 upload token，用例结束后清理。
    ★ 复用 authed_user_http（已带新用户 token），无需额外注册或创建 client。
    ★ 每次随机生成用户名（由 new_user 保证），xdist 安全。
    """
    file_key = None

    with allure.step("获取新用户的 upload token"):
        resp = authed_user_http.post(
            "/api/files/upload-token",
            json={"file_name": "b_test.png", "file_type": "png"},
        )
        assert resp.status_code == 200, f"获取 upload-token 失败: {resp.text}"
        file_key = resp.json()["data"]["file_key"]

    yield file_key

    with allure.step("清理：删除上传记录"):
        if file_key:
            authed_user_http.delete(f"/api/files/{file_key}")
