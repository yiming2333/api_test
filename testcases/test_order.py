# testcases/test_order.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json
from utils.context_resolver import resolve

ORDER_QUERY_DATA = load_test_data("order.yaml", "test_order_query")


@allure.epic("订单中心")
@allure.feature("订单查询")
class TestOrderQuery:

    @pytest.mark.parametrize(
        "case_id, case_data", ORDER_QUERY_DATA,
        ids=[d[0] for d in ORDER_QUERY_DATA]
    )
    def test_order(self, http, context, request, db, case_id, case_data):
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        if case_data.get("depends_on"):
            request.getfixturevalue(case_data["depends_on"])

        req = case_data["request"]
        expect = case_data["expect"]
        resolved_req = resolve(req)

        with allure.step(f"发送请求: {resolved_req.get('url', '')}"):
            resp = getattr(http, resolved_req["method"])(
                resolved_req["url"],
                **{k: v for k, v in resolved_req.items()
                   if k in ("json", "params", "data", "headers")}
            )

        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"]

        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value

        # DB 校验
        for check in expect.get("db_check", []):
            resolved_check = resolve(check)
            with allure.step(f"DB校验: {resolved_check['table']}.{resolved_check['field']} == {resolved_check['expected']}"):
                db.assert_field_value(
                    table=resolved_check["table"],
                    where=resolved_check["where"],
                    params=tuple(resolved_check["params"]),
                    field=resolved_check["field"],
                    expected=resolved_check["expected"]
                )


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_create_and_verify_in_db(self, http, context, login_token, db):
        """创建订单后，验证数据库记录正确落库"""
        with allure.step("创建订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_DB_TEST",
                "quantity": 3,
                "address": "数据库校验测试地址"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("DB校验：订单记录存在"):
            db.assert_record_exists(
                "orders", "order_id = %s", (order_id,),
                msg=f"订单 {order_id} "
            )

        with allure.step("DB校验：product_id 正确"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="product_id", expected="SKU_DB_TEST"
            )

        with allure.step("DB校验：quantity 正确"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="quantity", expected=3
            )

        with allure.step("DB校验：初始状态为 pending"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="status", expected="pending"
            )

        # 清理
        http.delete(f"/api/orders/{order_id}")

    def test_cancel_order_updates_db(self, http, context, login_token, db):
        """取消订单后，验证数据库状态变更（独立创建订单，不与其他用例共享）"""
        with allure.step("创建待取消的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_CANCEL_TEST",
                "quantity": 1,
                "address": "取消测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step("取消订单"):
            resp = http.put(f"/api/orders/{order_id}/cancel")
            assert resp.status_code == 200

        with allure.step("DB校验：状态变为 cancelled"):
            db.assert_field_value(
                "orders", "order_id = %s", (order_id,),
                field="status", expected="cancelled"
            )

    def test_query_order_pending(self, http, context, login_token, db):
        """查询刚创建的订单，状态应为 pending（独立订单，不受其他用例影响）"""
        with allure.step("创建待查询的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_QUERY_TEST",
                "quantity": 1,
                "address": "查询测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        with allure.step(f"查询订单 {order_id}"):
            resp = http.get(f"/api/orders/{order_id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

        # 清理
        http.delete(f"/api/orders/{order_id}")

    def test_cancel_order_api(self, http, context, login_token):
        """取消订单接口返回 200（独立订单）"""
        with allure.step("创建待取消的订单"):
            resp = http.post("/api/orders", json={
                "product_id": "SKU_API_TEST",
                "quantity": 1,
                "address": "API测试"
            })
            assert resp.status_code == 201
            order_id = resp.json()["data"]["order_id"]

        resp = http.put(f"/api/orders/{order_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "cancelled"