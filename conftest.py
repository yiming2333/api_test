import pytest
import allure
from common.http_client import HttpClient
from common.yaml_handler import get_config

# 命令行传入环境：pytest --env=prod
def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")

@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")

@pytest.fixture(scope="session")
def http(env_name):
    """全局 HTTP 客户端，整个会话共用"""
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client