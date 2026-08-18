# 确认你的根目录 conftest.py 包含以下内容（已有则不动）
import pytest
from common.http_client import HttpClient
from common.yaml_handler import get_config
from common.context import ctx
from utils.db import db as db_client
from common.logger import get_logger
logger = get_logger(__name__)


@pytest.fixture(scope="session")
def db():
    """全局数据库客户端，session 级别复用"""
    yield db_client


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


@pytest.fixture(scope="session", autouse=True)
def clean_test_data(db):
    """整个测试会话结束后清理测试数据"""
    yield
    # 按外键依赖顺序删除
    tables = ["tasks", "projects", "orders", "file_uploads"]
    for table in tables:
        try:
            db.execute(f"DELETE FROM {table}")
            logger.info(f"🧹 已清理表: {table}")
        except Exception as e:
            logger.warning(f"清理表 {table} 失败: {e}")
