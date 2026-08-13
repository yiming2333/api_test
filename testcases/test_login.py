import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json

# 加载 YAML 数据
LOGIN_DATA = load_test_data("login.yaml", "test_login")

@allure.epic("用户中心")
@allure.feature("登录模块")
class TestLogin:

    @pytest.mark.parametrize("case_id, case_data", LOGIN_DATA,
                             ids=[d[0] for d in LOGIN_DATA])
    def test_login(self, http, case_id, case_data):
        # 动态打标记
        if case_data.get("mark") == "smoke":
            pytest.mark.smoke

        allure.dynamic.story(case_data["title"])
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")

        req = case_data["request"]
        expect = case_data["expect"]

        # 发起请求
        with allure.step(f"发送 {req['method'].upper()} 请求: {req['url']}"):
            resp = getattr(http, req["method"])(
                req["url"], **{k: v for k, v in req.items()
                               if k in ("json", "params", "data", "headers")}
            )

        # 断言状态码
        with allure.step(f"断言状态码 == {expect['status_code']}"):
            assert resp.status_code == expect["status_code"], \
                f"期望 {expect['status_code']}，实际 {resp.status_code}"

        # 断言 JSON 字段
        for path, expected_value in expect.get("json_path", []):
            with allure.step(f"断言 {path} == {expected_value}"):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None, f"{path} 为空"
                else:
                    assert actual == expected_value, \
                        f"{path} 期望 {expected_value}，实际 {actual}"