import allure
import pytest


@allure.epic("用户中心")
@allure.feature("个人信息")
class TestProfile:

    def test_get_profile(self, http, context, login_token):
        """获取个人信息（只需要登录态）"""
        # login_token 确保已登录，http.session 已带 Authorization
        user_id = context.get_or_fail("user_id")

        resp = http.get(f"/api/users/{user_id}/profile")
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_update_avatar(self, http, context, login_token, upload_credential):
        """
        更新头像：
        1. upload_credential 先拿到 file_key
        2. 用 file_key 提交更新
        """
        file_key = context.get_or_fail("file_key")

        resp = http.put("/api/users/me/avatar", json={
            "file_key": file_key
        })
        assert resp.status_code == 200