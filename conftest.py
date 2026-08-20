# conftest.py（根目录）

import pytest
from common.http_client import HttpClient
from common.yaml_handler import get_config


def pytest_addoption(parser):
    parser.addoption("--env", default="dev", help="运行环境: dev/prod")


@pytest.fixture(scope="session")
def env_name(request):
    return request.config.getoption("--env")


@pytest.fixture(scope="session")
def http(env_name):
    """
    全局 HTTP 客户端。
    注意：xdist 下每个 worker 会各自创建一个，互不干扰。
    """
    cfg = get_config(env_name)
    client = HttpClient(base_url=cfg["base_url"], timeout=cfg.get("timeout", 10))
    return client


@pytest.fixture(scope="session")
def logged_in_http(http):
    """
    已登录的 HTTP 客户端（session 级，每个 worker 登录一次）。
    登录是幂等操作，多个 worker 各登录一次完全没问题。
    """
    resp = http.post("/api/auth/login", json={
        "username": "testuser",
        "password": "Test@123"
    })
    assert resp.status_code == 200, f"登录失败: {resp.text}"
    data = resp.json()["data"]
    token = data["token"]
    user_id = data["user_id"]

    # 把 token 注入 session headers
    http.session.headers["Authorization"] = f"Bearer {token}"

    # 通过 fixture 的 request 对象存储，方便后续取 user_id
    http._user_id = user_id
    http._token = token
    http._username = "testuser"

    return http


@pytest.fixture(scope="session")
def db(env_name):
    """全局数据库客户端（跟随 --env 参数选择环境）"""
    from utils.db import DBClient
    return DBClient(env=env_name)