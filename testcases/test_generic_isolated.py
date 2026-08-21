import allure
import pytest

from utils.case_runner import run_flow_case
from utils.data_loader import load_parametrize_data

ORDER_ISO_DATA = load_parametrize_data("order.yaml", "test_order_isolated")


@allure.epic("订单中心")
@allure.feature("隔离数据驱动")
class TestOrderIsolated:

    @pytest.mark.parametrize("case_id, case_data", ORDER_ISO_DATA)
    def test_order_flow(self, logged_in_http, db, case_id, case_data):
        """每条用例：setup → request → assert → teardown，完全自包含"""
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")
        run_flow_case(logged_in_http, case_data, db=db, case_id=case_id)


@allure.epic("订单中心")
@allure.feature("用户身份隔离")
class TestUserScoped:
    """
    以独立新用户身份执行操作，验证多用户隔离行为。
    authed_user_http = user_http(独立实例) + new_user(随机用户)，
    与 session 级 logged_in_http 完全隔离。
    """

    @allure.story("身份切换")
    @pytest.mark.smoke
    def test_user_http_identity_switched(self, authed_user_http, new_user):
        """新用户查询自己的资料，应返回 new_user 的 username。"""
        with allure.step("查询当前登录用户的 profile"):
            resp = authed_user_http.get(f"/api/users/{new_user['user_id']}/profile")
            assert resp.status_code == 200, f"查询 profile 失败: {resp.text}"

        with allure.step("断言返回 username 与新注册用户一致"):
            data = resp.json()["data"]
            assert data["username"] == new_user["username"], (
                f"profile 返回 username={data['username']!r}，"
                f"期望 {new_user['username']!r}"
            )

    @allure.story("订单归属")
    def test_user_http_create_order_owned_by_new_user(
        self, authed_user_http, new_user, db
    ):
        """新用户下单，DB 中 orders.user_id 应为新用户 user_id。"""
        with allure.step("以新用户身份创建订单"):
            resp = authed_user_http.post("/api/orders", json={
                "product_id": "SKU_USER_SCOPED_001",
                "quantity": 1,
            })
            assert resp.status_code == 201, f"创建订单失败: {resp.text}"
            order_id = resp.json()["data"]["order_id"]

        with allure.step("DB 校验: orders.user_id == 新用户 user_id"):
            row = db.query_one(
                "SELECT user_id, status FROM orders WHERE order_id = %s",
                (order_id,),
            )
            assert row is not None, f"订单 {order_id} 未落库"
            assert row["user_id"] == new_user["user_id"], (
                f"订单归属错误: user_id={row['user_id']}，"
                f"期望 {new_user['user_id']}"
            )

    @allure.story("上传凭证归属")
    def test_user_http_upload_token_owned_by_new_user(
        self, authed_user_http, new_user, db
    ):
        """新用户获取 upload-token，DB 中 file_uploads.user_id 应为新用户。"""
        with allure.step("以新用户身份获取 upload-token"):
            resp = authed_user_http.post("/api/files/upload-token", json={
                "file_name": "scoped_test.png",
                "file_type": "image/png",
            })
            assert resp.status_code == 200, f"获取 upload-token 失败: {resp.text}"
            file_key = resp.json()["data"]["file_key"]

        with allure.step("DB 校验: file_uploads.user_id == 新用户 user_id"):
            row = db.query_one(
                "SELECT user_id FROM file_uploads WHERE file_key = %s",
                (file_key,),
            )
            assert row is not None, f"file_key {file_key} 未落库"
            assert row["user_id"] == new_user["user_id"], (
                f"上传凭证归属错误: user_id={row['user_id']}，"
                f"期望 {new_user['user_id']}"
            )

    @allure.story("跨用户权限隔离")
    def test_user_http_cannot_see_others_order(
        self, authed_user_http, fresh_order
    ):
        """
        新用户访问 default 用户的订单，应返回 404。

        authed_user_http 自带新用户 token（由 new_user 提供），
        fresh_order 由 default 用户创建，两者身份天然不同。
        """
        with allure.step("新用户查询 default 用户的订单"):
            resp = authed_user_http.get(f"/api/orders/{fresh_order}")
            assert resp.status_code == 404, (
                f"新用户不应能看到他人订单，实际 status={resp.status_code}，"
                f"响应: {resp.text}"
            )