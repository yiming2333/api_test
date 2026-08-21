# testcases/test_register.py
#
# 注册接口用例。Mock 端点：POST /api/auth/register
# 行为契约：
#   - 缺 username 或 password → 400
#   - 已存在的用户名 → 返回相同 user_id（幂等）
#   - 注册成功 → 返回 {user_id, username, token}
# ★ 用例自包含：自己造随机用户、自己清理 DB 记录，不依赖 new_user fixture
#   （new_user 是已注册完成的状态，不能用于测试 register 本身）。

import uuid

import allure
import pytest

from utils.accounts import get_account


@allure.epic("用户中心")
@allure.feature("注册模块")
class TestRegister:

    @pytest.mark.smoke
    def test_register_success(self, user_http, db):
        """正向：注册全新用户，返回 user_id 和 token，并落库"""
        account = get_account("user_b")
        username = f"reg_ok_{uuid.uuid4().hex[:8]}"
        user_id = None

        try:
            with allure.step("注册新用户"):
                resp = user_http.post("/api/auth/register", json={
                    "username": username,
                    "password": account["password"],
                })
                assert resp.status_code == 200, f"注册失败: {resp.text}"
                data = resp.json()["data"]

            with allure.step("断言响应字段"):
                assert data["username"] == username
                assert data["user_id"] is not None
                assert data["token"]

            with allure.step("DB 校验：用户已落库"):
                row = db.query_one(
                    "SELECT username FROM users WHERE user_id = %s",
                    (data["user_id"],),
                )
                assert row is not None, "注册后 users 表未找到记录"
                assert row["username"] == username

            user_id = data["user_id"]
        finally:
            if user_id:
                db.execute(
                    "DELETE FROM users WHERE user_id = %s", (user_id,)
                )

    def test_register_idempotent(self, user_http, db):
        """重复注册同一用户名，应返回相同 user_id（幂等）"""
        account = get_account("user_b")
        username = f"reg_idem_{uuid.uuid4().hex[:8]}"
        user_id = None

        try:
            with allure.step("第一次注册"):
                resp1 = user_http.post("/api/auth/register", json={
                    "username": username,
                    "password": account["password"],
                })
                assert resp1.status_code == 200
                uid1 = resp1.json()["data"]["user_id"]

            with allure.step("第二次注册（密码不同）"):
                resp2 = user_http.post("/api/auth/register", json={
                    "username": username,
                    "password": "another_pwd_456",
                })
                assert resp2.status_code == 200
                uid2 = resp2.json()["data"]["user_id"]

            with allure.step("断言两次返回相同 user_id"):
                assert uid1 == uid2, "重复注册应返回相同 user_id（幂等）"

            user_id = uid1
        finally:
            if user_id:
                db.execute(
                    "DELETE FROM users WHERE user_id = %s", (user_id,)
                )

    def test_register_missing_username(self, user_http):
        """缺少 username 返回 400"""
        resp = user_http.post("/api/auth/register", json={
            "password": "any_pwd",
        })
        assert resp.status_code == 400
        assert resp.json()["message"] == "缺少 username 或 password"

    def test_register_missing_password(self, user_http):
        """缺少 password 返回 400"""
        resp = user_http.post("/api/auth/register", json={
            "username": f"reg_no_pwd_{uuid.uuid4().hex[:8]}",
        })
        assert resp.status_code == 400
        assert resp.json()["message"] == "缺少 username 或 password"

    def test_register_empty_body(self, user_http):
        """空 body 返回 400"""
        resp = user_http.post("/api/auth/register", json=None)
        assert resp.status_code == 400
        assert resp.json()["message"] == "缺少 username 或 password"
