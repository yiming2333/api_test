# testcases/test_file_upload.py

import allure
import pytest


@allure.epic("文件管理")
@allure.feature("文件上传")
class TestFileUpload:

    @pytest.mark.smoke
    def test_get_upload_token(self, logged_in_http):
        """获取上传凭证，用例结束后 DELETE 清理"""
        file_key = None
        try:
            resp = logged_in_http.post("/api/files/upload-token", json={
                "file_name": "test_doc.pdf",
                "file_type": "application/pdf"
            })
            assert resp.status_code == 200
            file_key = resp.json()["data"]["file_key"]
            assert file_key is not None
        finally:
            if file_key:
                logged_in_http.delete(f"/api/files/{file_key}")

    def test_commit_file(self, logged_in_http, fresh_upload_token):
        """用凭证提交文件"""
        resp = logged_in_http.post("/api/files/commit", json={
            "file_key": fresh_upload_token
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "committed"

    def test_commit_invalid_key(self, logged_in_http):
        """无效凭证提交返回 400"""
        resp = logged_in_http.post("/api/files/commit", json={
            "file_key": "fk-nonexistent-key"
        })
        assert resp.status_code == 400

    @allure.story("跨用户权限隔离")
    def test_commit_cross_user_forbidden(self, authed_user_http, fresh_upload_token):
        """安全：新用户提交 default 用户的 file_key，应返回 400（归属校验）

        authed_user_http 自带新用户 token（由 new_user 提供），
        fresh_upload_token 由 default 用户身份创建，归属 default 用户。
        Mock 的 commit_file 通过 user_id 校验归属权，新用户提交时应返回 400。
        """
        resp = authed_user_http.post("/api/files/commit", json={
            "file_key": fresh_upload_token
        })
        assert resp.status_code == 400
        assert resp.json()["message"] == "无效的file_key"

    def test_upload_token_missing_filename(self, logged_in_http):
        """缺少 file_name 返回 400"""
        resp = logged_in_http.post("/api/files/upload-token", json={
            "file_type": "image/png"
        })
        assert resp.status_code == 400