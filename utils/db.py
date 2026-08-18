"""
数据库操作工具类
用于接口测试后的数据校验
"""
import pymysql
from contextlib import contextmanager
from common.logger import log


# ============================================================
#  数据库配置（后续可改为从 config.yaml 读取）
# ============================================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'Root@123456',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,  # ← 关键：返回字典而非元组
}


class DBClient:
    """轻量级数据库客户端，支持上下文管理器自动关闭连接"""

    def __init__(self, database=None, **overrides):
        self.config = {**DB_CONFIG, **overrides}
        if database:
            self.config['database'] = database

    @contextmanager
    def connect(self):
        """上下文管理器：自动提交/回滚/关闭"""
        conn = None
        try:
            conn = pymysql.connect(**self.config)
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            log.error(f"❌ 数据库异常: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def query(self, sql, params=None, database=None):
        """
        查询多条记录，返回 list[dict]

        示例:
            db.query("SELECT * FROM orders WHERE user_id = %s", (10086,))
        """
        cfg = {**self.config}
        if database:
            cfg['database'] = database

        with pymysql.connect(**cfg) as conn:
            with conn.cursor() as cursor:
                log.info(f"🔍 SQL: {sql} | 参数: {params}")
                cursor.execute(sql, params)
                results = cursor.fetchall()
                log.info(f"   返回 {len(results)} 条记录")
                return results

    def query_one(self, sql, params=None, database=None):
        """查询单条记录，返回 dict 或 None"""
        results = self.query(sql, params, database)
        return results[0] if results else None

    def execute(self, sql, params=None, database=None):
        """执行写操作（INSERT/UPDATE/DELETE），返回影响行数"""
        cfg = {**self.config}
        if database:
            cfg['database'] = database

        with self.connect() as conn:
            with conn.cursor() as cursor:
                log.info(f"✏️  SQL: {sql} | 参数: {params}")
                affected = cursor.execute(sql, params)
                log.info(f"   影响 {affected} 行")
                return affected

    def count(self, table, where=None, params=None, database=None):
        """
        快捷计数

        示例:
            db.count("orders", "user_id = %s AND status = %s", (10086, "pending"))
        """
        sql = f"SELECT COUNT(*) AS cnt FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self.query_one(sql, params, database)
        return row["cnt"] if row else 0

    def exists(self, table, where, params=None, database=None):
        """判断记录是否存在"""
        return self.count(table, where, params, database) > 0

    def assert_record_exists(self, table, where, params=None, database=None, msg=""):
        """断言记录存在，不存在直接抛 AssertionError"""
        if not self.exists(table, where, params, database):
            raise AssertionError(
                f"{msg}数据库中未找到记录: {table} WHERE {where} | 参数: {params}"
            )

    def assert_field_value(self, table, where, params, field, expected, database=None):
        """
        断言某条记录的某个字段值等于预期值

        示例:
            db.assert_field_value(
                "orders", "order_id = %s", ("ORD001",),
                field="status", expected="pending"
            )
        """
        row = self.query_one(
            f"SELECT {field} FROM {table} WHERE {where}", params, database
        )
        assert row is not None, \
            f"数据库中未找到记录: {table} WHERE {where} | 参数: {params}"

        actual = row[field]
        assert actual == expected, \
            f"字段 {field} 期望 '{expected}'，实际 '{actual}'"


# ============================================================
#  全局单例（按需指定 database）
# ============================================================
db = DBClient(database="api_test")