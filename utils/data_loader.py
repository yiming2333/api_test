import os
from common.yaml_handler import read_yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_test_data(file_name, key):
    """加载测试数据并转为 pytest 参数化格式"""
    path = os.path.join(BASE_DIR, "config", "testdata", file_name)
    data = read_yaml(path)[key]
    # 转成 (case_id, case_dict) 元组，方便参数化时显示用例ID
    return [(item["case_id"], item) for item in data]