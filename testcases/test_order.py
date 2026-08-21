# testcases/test_order.py

import pytest
import allure


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    @pytest.mark.smoke
    def test_create_order(self, logged_in_http, db):
        """创建订单 + DB校验（自包含）"""
        order_id=None
        try:
            with allure.step("创建订单"):
                resp = logged_in_http.post("/api/orders", json={
                    "product_id": "SKU_CREATE_001",
                    "quantity": 2,
                    "address": "创建测试"
                })
                assert resp.status_code == 201
                order_id = resp.json()["data"]["order_id"]

            with allure.step("DB校验：记录存在且字段正确"):
                db.assert_field_value("orders", "order_id = %s", (order_id,),
                                      field="product_id", expected="SKU_CREATE_001")
                db.assert_field_value("orders", "order_id = %s", (order_id,),
                                      field="quantity", expected=2)
                db.assert_field_value("orders", "order_id = %s", (order_id,),
                                      field="status", expected="pending")
        finally:
            if order_id:
                logged_in_http.delete(f"/api/orders/{order_id}")

    @pytest.mark.smoke
    def test_query_order(self, fresh_order, logged_in_http):
        """查询订单（用 fixture 创建的独立订单）"""
        with allure.step(f"查询订单 {fresh_order}"):
            resp = logged_in_http.get(f"/api/orders/{fresh_order}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"
        assert resp.json()["data"]["product_id"] == "SKU_ISOLATED"

    def test_cancel_order(self, fresh_order, logged_in_http, db):
        """取消订单 + DB校验（独立订单，不影响别人）"""
        with allure.step(f"取消订单 {fresh_order}"):
            resp = logged_in_http.put(f"/api/orders/{fresh_order}/cancel")
            assert resp.status_code == 200
            assert resp.json()["data"]["status"] == "cancelled"

        with allure.step("DB校验：状态变为 cancelled"):
            db.assert_field_value("orders", "order_id = %s", (fresh_order,),
                                  field="status", expected="cancelled")

    def test_query_cancelled_order(self, fresh_order, logged_in_http):
        """取消后再查询，状态应为 cancelled"""
        # 先取消
        logged_in_http.put(f"/api/orders/{fresh_order}/cancel")

        # 再查询
        resp = logged_in_http.get(f"/api/orders/{fresh_order}")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"

    def test_query_nonexistent_order(self, logged_in_http):
        """查询不存在的订单返回 404（无前置依赖）"""
        resp = logged_in_http.get("/api/orders/ORD_NOT_EXIST_999")
        assert resp.status_code == 404

    def test_create_order_missing_product_id(self, logged_in_http):
        """缺少 product_id 返回 400（无前置依赖）"""
        resp = logged_in_http.post("/api/orders", json={
            "quantity": 1
        })
        assert resp.status_code == 400