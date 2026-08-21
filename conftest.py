# conftest.py（根目录）

import pytest

from common.http_client import HttpClient
from common.yaml_handler import get_config
from utils.accounts import get_account


def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")


@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def http(env_name):
    """全局 HTTP 客户端。xdist 下每个 worker 各自创建。"""
    cfg = get_config(env_name)
    return HttpClient(
        base_url=cfg["base_url"],
        env=env_name,
        timeout=cfg.get("timeout", 10),
    )


@pytest.fixture(scope="session")
def logged_in_http(http):
    """已登录的 HTTP 客户端（session 级，每个 worker 登录一次）。"""
    account = get_account("default")
    resp = http.post("/api/auth/login", json={
        "username": account["username"],
        "password": account["password"],
    })
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()["data"]

    http.session.headers["Authorization"] = f"Bearer {data['token']}"
    http._user_id = data["user_id"]
    http._token = data["token"]
    http._username = account["username"]

    return http


@pytest.fixture(scope="session")
def db(env_name):
    """全局数据库客户端（跟随 --env 参数选择环境）。"""
    from utils.db import DBClient
    return DBClient(env=env_name)
