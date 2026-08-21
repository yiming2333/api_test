# testcases/test_login.py

import allure
import pytest

from utils.case_runner import run_simple_case
from utils.data_loader import load_parametrize_data

LOGIN_DATA = load_parametrize_data("login.yaml", "test_login")


@allure.epic("用户中心")
@allure.feature("登录模块")
class TestLogin:

    @pytest.mark.parametrize("case_id, case_data", LOGIN_DATA)
    def test_login(self, http, case_id, case_data):
        """登录接口是无状态的，天然并发安全"""
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")
        run_simple_case(http, case_data)
