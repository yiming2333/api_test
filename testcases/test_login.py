# testcases/test_login.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json

LOGIN_RAW = load_test_data("login.yaml", "test_login")

# 根据 YAML 中的 mark 字段动态打标，支持 pytest -m smoke / regression
LOGIN_DATA = []
for case_id, case_data in LOGIN_RAW:
    mark_name = case_data.get("mark")
    if mark_name:
        LOGIN_DATA.append(
            pytest.param(case_id, case_data, id=case_id,
                         marks=getattr(pytest.mark, mark_name))
        )
    else:
        LOGIN_DATA.append(pytest.param(case_id, case_data, id=case_id))


@allure.epic("用户中心")
@allure.feature("登录模块")
class TestLogin:

    @pytest.mark.parametrize("case_id, case_data", LOGIN_DATA)
    def test_login(self, http, case_id, case_data):
        """登录接口是无状态的，天然并发安全"""
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        req = case_data["request"]
        expect = case_data["expect"]

        with allure.step(f"发送 {req['method'].upper()} 请求: {req['url']}"):
            resp = getattr(http, req["method"])(
                req["url"], **{k: v for k, v in req.items()
                               if k in ("json", "params", "data", "headers")}
            )

        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"], \
                f"期望 {expect['status_code']}，实际 {resp.status_code}"

        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None, f"{path} 为空"
                else:
                    assert actual == expected_value, \
                        f"{path} 期望 {expected_value}，实际 {actual}"