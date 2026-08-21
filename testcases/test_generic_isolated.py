# testcases/test_generic_isolated.py

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
