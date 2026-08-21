import os
from functools import lru_cache

from common.yaml_handler import read_yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache
def load_accounts():
    path = os.path.join(BASE_DIR, "config", "test_accounts.yaml")
    return read_yaml(path)["accounts"]


def get_account(name="default"):
    return load_accounts()[name]


def get_accounts_context():
    """供 case_runner 模板变量 ${accounts.default.username} 使用。"""
    return load_accounts()
