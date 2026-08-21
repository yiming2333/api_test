import os

import pytest

from common.yaml_handler import read_yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_test_data(file_name, key):
    """加载测试数据并转为 (case_id, case_dict) 列表。"""
    path = os.path.join(BASE_DIR, "config", "testdata", file_name)
    data = read_yaml(path)[key]
    return [(item["case_id"], item) for item in data]


def load_parametrize_data(file_name, key):
    """加载数据并转为 pytest.param 列表，自动映射 YAML 中的 mark 字段。"""
    params = []
    for case_id, case_data in load_test_data(file_name, key):
        mark_name = case_data.get("mark")
        if mark_name:
            params.append(
                pytest.param(
                    case_id, case_data,
                    id=case_id,
                    marks=getattr(pytest.mark, mark_name),
                )
            )
        else:
            params.append(pytest.param(case_id, case_data, id=case_id))
    return params
