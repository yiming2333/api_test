# 确认你的根目录 conftest.py 包含以下内容（已有则不动）
import pytest
from common.http_client import HttpClient
from common.yaml_handler import get_config
from common.context import ctx


def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")


@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def http(env_name):
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client


@pytest.fixture(scope="session")
def context():
    yield ctx
    ctx.clear()
