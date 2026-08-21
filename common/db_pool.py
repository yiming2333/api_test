"""共享 MySQL 连接池，供 mock_flask 与测试 DB 客户端使用。"""

import pymysql
from dbutils.pooled_db import PooledDB

from common.yaml_handler import get_config

_pools = {}


def get_pool(env="dev", database="api_test", autocommit=True):
    """按 (env, database, autocommit) 缓存连接池。"""
    key = (env, database, autocommit)
    if key not in _pools:
        cfg = get_config(env)
        _pools[key] = PooledDB(
            creator=pymysql,
            maxconnections=20,
            mincached=2,
            maxcached=5,
            blocking=True,
            host=cfg.get("db_host", "localhost"),
            port=cfg.get("db_port", 3306),
            user=cfg.get("db_user", "root"),
            password=cfg.get("db_password", ""),
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=autocommit,
        )
    return _pools[key]
