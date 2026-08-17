# testcases/test_order.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json
from utils.context_resolver import resolve   # ← 新增

ORDER_QUERY_DATA = load_test_data("order.yaml", "test_order_query")


@allure.epic("订单中心")
@allure.feature("订单查询")
class TestOrderQuery:

    @pytest.mark.parametrize(
        "case_id, case_data", ORDER_QUERY_DATA,
        ids=[d[0] for d in ORDER_QUERY_DATA]
    )
    def test_order(self, http, context, request, case_id, case_data):
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        # ★ 如果声明了 depends_on，动态获取对应 fixture 的返回值
        #   确保前置 fixture 已执行（pytest 会自动处理依赖顺序）
        if case_data.get("depends_on"):
            request.getfixturevalue(case_data["depends_on"])

        req = case_data["request"]
        expect = case_data["expect"]

        # ★ 替换占位符
        resolved_req = resolve(req)

        with allure.step(f"发送请求: {resolved_req.get('url', '')}"):
            resp = getattr(http, resolved_req["method"])(
                resolved_req["url"],
                **{k: v for k, v in resolved_req.items()
                   if k in ("json", "params", "data", "headers")}
            )

        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"], \
                f"期望 {expect['status_code']}，实际 {resp.status_code}"

        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value, \
                        f"{path} 期望 {expected_value}，实际 {actual}"


@allure.epic("订单中心")
@allure.feature("订单管理")
class TestOrder:

    def test_query_order(self, http, context, created_order):
        """
        查询订单详情。
        created_order fixture 已经创建好订单并写入 context，
        这里直接取 order_id 用。
        """
        # 方式一：从 context 取
        order_id = context.get_or_fail("order_id")

        # 方式二：直接用 fixture 返回值（效果一样）
        # order_id = created_order

        with allure.step(f"查询订单 {order_id}"):
            resp = http.get(f"/api/orders/{order_id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

    def test_cancel_order(self, http, context, created_order):
        """取消订单"""
        order_id = context.get_or_fail("order_id")

        resp = http.put(f"/api/orders/{order_id}/cancel")
        assert resp.status_code == 200