"""YAML 数据驱动用例执行引擎：模板解析、请求发送、断言、setup/teardown。"""

import re

import allure

from common.logger import log
from utils.accounts import get_accounts_context
from utils.jsonpath_util import extract_json


def build_context(extra=None):
    context = {"accounts": get_accounts_context()}
    if extra:
        context.update(extra)
    return context


def resolve_template(template: str, context: dict) -> str:
    """${setup.order_id} / ${accounts.default.username} → 实际值。"""
    def _replace(match):
        keys = match.group(1).split(".")
        value = context
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                raise KeyError(
                    f"模板变量 ${{{match.group(1)}}} 解析失败: "
                    f"路径 '{key}' 不存在。"
                    f"当前 context keys: {list(context.keys()) if context else '空'}"
                )
        return str(value)

    return re.sub(r"\$\{(.+?)\}", _replace, template)


def resolve_value(value, context: dict):
    """递归解析 str / list / dict 中的模板变量。"""
    if isinstance(value, str) and "${" in value:
        return resolve_template(value, context)
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    return value


def execute_request(http, req_config, context):
    url = resolve_template(req_config["url"], context)
    method = req_config["method"]
    kwargs = {}
    for key in ("json", "params", "data", "headers"):
        if key in req_config:
            kwargs[key] = resolve_value(req_config[key], context)
    return getattr(http, method)(url, **kwargs)


def assert_response(resp, expect, db=None, context=None):
    context = context or {}
    assert resp.status_code == expect["status_code"], (
        f"期望状态码 {expect['status_code']}，实际 {resp.status_code}，响应: {resp.text}"
    )

    for path, expected_value in expect.get("json_path", []):
        actual = extract_json(resp.json(), path)
        if expected_value == "not_null":
            assert actual is not None, f"{path} 为空"
        else:
            assert actual == expected_value, (
                f"{path} 期望 {expected_value!r}，实际 {actual!r}"
            )

    for check in expect.get("db_check", []):
        with allure.step(
            f"DB校验: {check['table']}.{check['field']} == {check['expected']}"
        ):
            # 递归解析模板变量，支持嵌套 list / dict / str 中的 ${...}
            where = resolve_value(check["where"], context)
            params = tuple(
                resolve_value(item, context) for item in check["params"]
            )
            db.assert_field_value(
                check["table"], where, params,
                field=check["field"], expected=check["expected"],
            )


def run_simple_case(http, case_data, db=None):
    """无 setup/teardown 的单请求用例（如登录）。"""
    context = build_context()
    req = case_data["request"]
    expect = case_data["expect"]

    with allure.step(f"发送 {req['method'].upper()} 请求: {req['url']}"):
        resp = execute_request(http, req, context)

    with allure.step(f"断言状态码 == {expect['status_code']}"):
        assert_response(resp, expect, db=db, context=context)

    return resp


def run_flow_case(http, case_data, db=None, case_id=None):
    """setup → request → assert → teardown 完整流程。"""
    context = build_context()

    try:
        if "setup" in case_data:
            setup_resp = execute_request(http, case_data["setup"], context)
            assert setup_resp.status_code in (200, 201), (
                f"Setup 失败: {setup_resp.text}"
            )
            context["setup"] = setup_resp.json().get("data", {})

        resp = execute_request(http, case_data["request"], context)
        assert_response(resp, case_data["expect"], db=db, context=context)
        return resp

    finally:
        if "teardown" in case_data and context:
            try:
                execute_request(http, case_data["teardown"], context)
            except Exception as exc:
                log.warning(
                    "[%s] Teardown 失败（已忽略）: %s",
                    case_id or "unknown",
                    exc,
                    exc_info=True,
                )
