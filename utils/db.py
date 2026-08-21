"""数据库操作工具类，用于接口测试后的数据校验。"""

import re
from contextlib import contextmanager

from common.db_pool import get_pool
from common.logger import log


# 字段名/表名白名单字符（防止 SQL 注入）
# 仅允许字母数字 + 下划线，必须以字母或下划线开头
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name, kind):
    """校验表名/字段名是否为合法标识符（防 SQL 注入）。"""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"非法 {kind} 标识符: {name!r}（仅允许字母数字下划线）")
    return name


class DBClient:
    """轻量级数据库客户端，基于 PooledDB 连接池。"""

    def __init__(self, database="api_test", env="dev"):
        self.database = database
        self.env = env

    def _get_connection(self):
        return get_pool(env=self.env, database=self.database, autocommit=True).connection()

    @contextmanager
    def connect(self):
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except Exception as exc:
            log.error(f"❌ 数据库异常: {exc}")
            raise
        finally:
            if conn:
                conn.close()

    def query(self, sql, params=None):
        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"🔍 SQL: {sql} | 参数: {params}")
                try:
                    cursor.execute(sql, params)
                    results = cursor.fetchall()
                except Exception as exc:
                    log.error(f"❌ 查询失败: {exc}")
                    raise
                log.info(f"   返回 {len(results)} 条记录")
                return results

    def query_one(self, sql, params=None):
        results = self.query(sql, params)
        return results[0] if results else None

    def execute(self, sql, params=None):
        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"✏️  SQL: {sql} | 参数: {params}")
                try:
                    affected = cursor.execute(sql, params)
                    conn.commit()
                except Exception as exc:
                    log.error(f"❌ 执行失败: {exc}")
                    raise
                log.info(f"   影响 {affected} 行")
                return affected

    def count(self, table, where=None, params=None):
        _validate_identifier(table, "表名")
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.query_one(sql, params)
        return row["cnt"] if row else 0

    def exists(self, table, where, params=None):
        return self.count(table, where, params) > 0

    def assert_record_exists(self, table, where, params=None, msg=""):
        if not self.exists(table, where, params):
            raise AssertionError(
                f"{msg}数据库中未找到记录: {table} WHERE {where} | 参数: {params}"
            )

    def assert_field_value(self, table, where, params, field, expected):
        _validate_identifier(table, "表名")
        _validate_identifier(field, "字段名")
        row = self.query_one(
            f"SELECT {field} FROM {table} WHERE {where}", params
        )
        assert row is not None, (
            f"数据库中未找到记录: {table} WHERE {where} | 参数: {params}"
        )
        actual = row[field]
        assert actual == expected, (
            f"字段 {field} 期望 '{expected}'，实际 '{actual}'"
        )
