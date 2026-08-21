import allure
import pytest


@allure.epic("用户中心")
@allure.feature("个人信息")
class TestProfile:

    # ==================== 查询 ====================

    @allure.story("获取个人信息")
    @pytest.mark.smoke
    def test_get_profile(self, logged_in_http):
        """正向：获取当前用户信息，验证返回字段完整性"""
        resp = logged_in_http.get(f"/api/users/{logged_in_http._user_id}/profile")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == logged_in_http._user_id
        assert data["username"] == logged_in_http._username
        assert "avatar" in data

    @allure.story("获取个人信息")
    def test_get_profile_not_found(self, logged_in_http):
        """异常：查询不存在的用户 → 404"""
        resp = logged_in_http.get("/api/users/99999/profile")
        assert resp.status_code == 404

    @allure.story("获取个人信息")
    def test_get_profile_unauthorized(self, http, logged_in_http):
        """安全：无效 token → 401"""
        resp = http.get(
            f"/api/users/{logged_in_http._user_id}/profile",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert resp.status_code == 401

    # ==================== 更新头像 ====================

    @allure.story("更新头像")
    def test_update_avatar(self, logged_in_http, fresh_upload_token, db):
        """正向：使用自己的有效 file_key 更新头像

        ★ 该用例会修改 default 用户的 avatar 字段，必须用 try-finally 恢复，
          避免污染后续依赖 default 用户 avatar 初始状态的用例。
        """
        uid = logged_in_http._user_id
        old_avatar = db.query_one(
            "SELECT avatar FROM users WHERE user_id = %s", (uid,)
        )["avatar"]
        try:
            resp = logged_in_http.put("/api/users/me/avatar", json={
                "file_key": fresh_upload_token
            })
            assert resp.status_code == 200
            assert resp.json()["data"]["avatar"] == fresh_upload_token
        finally:
            # 恢复 default 用户 avatar，避免污染其他用例
            db.execute(
                "UPDATE users SET avatar = %s WHERE user_id = %s",
                (old_avatar, uid)
            )

    @allure.story("更新头像")
    def test_update_avatar_invalid_key(self, logged_in_http):
        """异常：不存在的 file_key → 400"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": "fk-nonexistent-xyz"
        })
        assert resp.status_code == 400
        assert resp.json()["message"] == "无效的file_key"

    @allure.story("更新头像")
    def test_update_avatar_missing_key(self, logged_in_http):
        """异常：缺少 file_key → 400"""
        resp = logged_in_http.put("/api/users/me/avatar", json={})
        assert resp.status_code == 400
        assert resp.json()["message"] == "缺少file_key"

    @allure.story("更新头像")
    def test_update_avatar_cross_user_forbidden(self, logged_in_http, another_user_file_key):
        """安全：使用他人的 file_key → 400（归属权校验）"""
        resp = logged_in_http.put("/api/users/me/avatar", json={
            "file_key": another_user_file_key
        })
        assert resp.status_code == 400
        assert resp.json()["message"] == "无效的file_key"