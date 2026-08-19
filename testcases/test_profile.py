# testcases/test_profile.py

import allure


@allure.epic("用户中心")
@allure.feature("个人信息")
class TestProfile:

    def test_get_profile(self, logged_in_http):
        """获取个人信息（只需登录态）"""
        user_id = logged_in_http._user_id

        resp = logged_in_http.get(f"/api/users/{user_id}/profile")
        assert resp.status_code == 200
        assert resp.json()["data"]["username"] == "testuser"

    def test_get_profile_not_found(self, logged_in_http):
        """查询不存在的用户"""
        resp = logged_in_http.get("/api/users/99999/profile")
        assert resp.status_code == 404

    def test_update_avatar(self, logged_in_http, fresh_upload_token):
        """更新头像（用独立的上传凭证）"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": fresh_upload_token
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar"] == fresh_upload_token

    def test_update_avatar_invalid_key(self, logged_in_http):
        """无效的 file_key 返回 400"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": "fk-invalid-key-123"
        })
        assert resp.status_code == 400