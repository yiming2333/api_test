"""
数据库操作工具类
用于接口测试后的数据校验
使用 PooledDB 连接池，与 mock_flask.py 保持一致
"""
import pymysql
from contextlib import contextmanager
from dbutils.pooled_db import PooledDB
from common.logger import log


# ============================================================
#  数据库连接池配置
# ============================================================
# 从 config.yaml 读取，避免硬编码
from common.yaml_handler import get_config

def _build_pool(database="api_test"):
    """根据 config.yaml 构建连接池"""
    cfg = get_config()  # 默认 dev 环境
    return PooledDB(
        creator=pymysql,
        maxconnections=20,       # 最大连接数
        mincached=2,             # 初始空闲连接
        maxcached=5,             # 最大空闲连接
        blocking=True,           # 连接用完时等待而非报错
        host=cfg.get("db_host", "localhost"),
        port=cfg.get("db_port", 3306),
        user=cfg.get("db_user", "root"),
        password=cfg.get("db_password", ""),
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


# ============================================================
#  连接池单例（模块级，进程内共享）
# ============================================================
_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


class DBClient:
    """轻量级数据库客户端，基于 PooledDB 连接池"""

    def __init__(self, database=None):
        self.database = database

    def _get_connection(self):
        """从连接池获取连接"""
        pool = _get_pool()
        return pool.connection()

    @contextmanager
    def connect(self):
        """上下文管理器：自动归还连接到池"""
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except Exception as e:
            log.error(f"❌ 数据库异常: {e}")
            raise
        finally:
            if conn:
                conn.close()  # PooledDB 的 close() 是归还到池，不是真正关闭

    def query(self, sql, params=None):
        """
        查询多条记录，返回 list[dict]

        示例:
            db.query("SELECT * FROM orders WHERE user_id = %s", (10086,))
        """
        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"🔍 SQL: {sql} | 参数: {params}")
                cursor.execute(sql, params)
                results = cursor.fetchall()
                log.info(f"   返回 {len(results)} 条记录")
                return results

    def query_one(self, sql, params=None):
        """查询单条记录，返回 dict 或 None"""
        results = self.query(sql, params)
        return results[0] if results else None

    def execute(self, sql, params=None):
        """执行写操作（INSERT/UPDATE/DELETE），返回影响行数"""
        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"✏️  SQL: {sql} | 参数: {params}")
                affected = cursor.execute(sql, params)
                conn.commit()
                log.info(f"   影响 {affected} 行")
                return affected

    def count(self, table, where=None, params=None):
        """
        快捷计数

        示例:
            db.count("orders", "user_id = %s AND status = %s", (10086, "pending"))
        """
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.query_one(sql, params)
        return row["cnt"] if row else 0

    def exists(self, table, where, params=None):
        """判断记录是否存在"""
        return self.count(table, where, params) > 0

    def assert_record_exists(self, table, where, params=None, msg=""):
        """断言记录存在，不存在直接抛 AssertionError"""
        if not self.exists(table, where, params):
            raise AssertionError(
                f"{msg}数据库中未找到记录: {table} WHERE {where} | 参数: {params}"
            )

    def assert_field_value(self, table, where, params, field, expected):
        """
        断言某条记录的某个字段值等于预期值

        示例:
            db.assert_field_value(
                "orders", "order_id = %s", ("ORD001",),
                field="status", expected="pending"
            )
        """
        row = self.query_one(
            f"SELECT {field} FROM {table} WHERE {where}", params
        )
        assert row is not None, \
            f"数据库中未找到记录: {table} WHERE {where} | 参数: {params}"

        actual = row[field]
        assert actual == expected, \
            f"字段 {field} 期望 '{expected}'，实际 '{actual}'"


# ============================================================
#  全局单例
# ============================================================
db = DBClient()
