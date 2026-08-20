# testcases/test_generic_isolated.py

import pytest
import allure
from utils.data_loader import load_test_data
from utils.jsonpath_util import extract_json
from common.logger import log



def _resolve_template(template: str, context: dict) -> str:
    """简易模板替换：${setup.order_id} → context['setup']['order_id']"""
    import re
    def _replace(m):
        keys = m.group(1).split(".")
        val = context
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                raise KeyError(
                    f"模板变量 ${{{m.group(1)}}} 解析失败: "
                    f"路径 '{k}' 在 context 中不存在。"
                    f"当前 context keys: {list(context.keys()) if context else '空（setup 可能未执行）'}"
                )
        return str(val)
    return re.sub(r'\$\{(.+?)\}', _replace, template)


def _execute_request(http, req_config, context):
    """执行单个请求配置"""
    url = _resolve_template(req_config["url"], context)
    method = req_config["method"]
    kwargs = {}
    if "json" in req_config:
        kwargs["json"] = req_config["json"]
    if "params" in req_config:
        kwargs["params"] = req_config["params"]

    resp = getattr(http, method)(url, **kwargs)
    return resp


ORDER_ISO_DATA = load_test_data("order.yaml", "test_order_isolated")


@allure.epic("订单中心")
@allure.feature("隔离数据驱动")
class TestOrderIsolated:

    @pytest.mark.parametrize("case_id, case_data", ORDER_ISO_DATA,
                             ids=[d[0] for d in ORDER_ISO_DATA])
    def test_order_flow(self, logged_in_http, db, case_id, case_data):
        """每条用例：setup → request → assert → teardown，完全自包含"""
        allure.dynamic.title(f"[{case_id}] {case_data['title']}")
        context = {}

        try:
            # Setup
            if "setup" in case_data:
                setup_resp = _execute_request(logged_in_http, case_data["setup"], context)
                assert setup_resp.status_code in (200, 201), \
                    f"Setup失败: {setup_resp.text}"
                context["setup"] = setup_resp.json().get("data", {})

            # Request
            req = case_data["request"]
            url = _resolve_template(req["url"], context)
            method = req["method"]
            kwargs = {k: v for k, v in req.items() if k in ("json", "params", "data", "headers")}
            resp = getattr(logged_in_http, method)(url, **kwargs)

            # Assert
            expect = case_data["expect"]
            assert resp.status_code == expect["status_code"]
            for path, expected_value in expect.get("json_path", []):
                actual = extract_json(resp.json(), path)
                if expected_value == "not_null":
                    assert actual is not None
                else:
                    assert actual == expected_value

            # DB 校验
            for check in expect.get("db_check", []):
                with allure.step(f"DB校验: {check['table']}.{check['field']} == {check['expected']}"):
                    # 解析 where 中的模板变量，如 ${setup.order_id}
                    where = _resolve_template(check["where"], context)
                    # 解析 params 中的模板变量
                    params = tuple(
                        _resolve_template(p, context) if isinstance(p, str) and p.startswith("$") else p
                        for p in check["params"]
                    )
                    db.assert_field_value(
                        check["table"], where, params,
                        field=check["field"], expected=check["expected"]
                    )

        finally:
            # Teardown（无论成功失败都清理）
            if "teardown" in case_data and context:
                try:
                    _execute_request(logged_in_http, case_data["teardown"], context)
                except Exception as e:
                    log.warning(
                        "[%s] Teardown 失败（已忽略）: %s", case_id, e,
                        exc_info=True  # 保留完整堆栈，方便排查
                    )