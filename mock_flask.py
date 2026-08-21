"""
mock_flask.py - 并发安全版
支持 pytest-xdist 多 worker 同时请求
"""
from flask import Flask, request, jsonify
import uuid
import time
import threading
import pymysql
from common.db_pool import get_pool
from common.logger import log

app = Flask(__name__)

# Mock 服务固定使用 dev 环境数据库
DB_POOL = get_pool(env="dev", autocommit=False)


def get_db():
    """从连接池获取连接"""
    return DB_POOL.connection()


# ============================================================
#  Token 存储（内存 + 线程锁）
# ============================================================
_tokens = {}
_token_lock = threading.Lock()


def _store_token(token, user_id):
    with _token_lock:
        _tokens[token] = user_id


def _get_token_user(token):
    with _token_lock:
        return _tokens.get(token)


# ============================================================
#  认证校验
# ============================================================
def _verify_token(req):
    auth_header = req.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    return _get_token_user(token)


def _require_auth(req):
    user_id = _verify_token(req)
    if user_id is None:
        return None, (jsonify({"code": 401, "message": "未登录或token已过期", "data": None}), 401)
    return user_id, None

# ============================================================
#  用户注册（无需认证，幂等）
# ============================================================
@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json(silent=True)
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"code": 400, "message": "缺少 username 或 password", "data": None}), 400

    username = data['username']
    password = data['password']

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # 幂等：先查是否已存在
            cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            existing = cur.fetchone()

            if existing:
                user_id = existing["user_id"]
            else:
                # 取当前最大 user_id + 1
                cur.execute("SELECT COALESCE(MAX(user_id), 10000) AS max_uid FROM users")
                new_uid = cur.fetchone()["max_uid"] + 1

                try:
                    cur.execute(
                        "INSERT INTO users (user_id, username, password) VALUES (%s, %s, %s)",
                        (new_uid, username, password)
                    )
                    conn.commit()
                    user_id = new_uid
                except pymysql.err.IntegrityError:
                    # 并发竞争：另一个 worker 同时插入了同名用户或相同 user_id
                    conn.rollback()
                    cur.execute("SELECT user_id FROM users WHERE username = %s", (username,))
                    row = cur.fetchone()
                    if not row:
                        return jsonify({"code": 500, "message": "注册异常", "data": None}), 500
                    user_id = row["user_id"]
    finally:
        conn.close()

    token = f"mock-jwt-{uuid.uuid4().hex[:16]}"
    _store_token(token, user_id)

    return jsonify({
        "code": 0, "message": "success",
        "data": {"user_id": user_id, "username": username, "token": token}
    }), 200

# ============================================================
#  故障注入（并发安全：按用户名隔离 + 线程锁）
# ============================================================
# 每个用户名独立维护一份故障配额，多 worker 并发请求互不干扰。
FAULT_COUNT = 2
_fault_lock = threading.Lock()
_fault_counters = {}   # username -> 剩余可注入次数


def _consume_fault(username):
    """线程安全地消耗一次故障配额。

    返回 (injected, remaining):
      injected  - True 表示本次注入故障（应返回 500）
      remaining - 消耗后剩余可注入次数（仅供日志展示）
    """
    with _fault_lock:
        remaining = _fault_counters.get(username, FAULT_COUNT)
        if remaining > 0:
            _fault_counters[username] = remaining - 1
            return True, remaining - 1
        return False, 0


# ============================================================
#  认证模块
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True)
    if not data or 'username' not in data:
        return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400

    username = data.get('username')
    password = data.get('password')

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, password FROM users WHERE username = %s",
                (username,)
            )
            user = cur.fetchone()
    finally:
        conn.close()

    if user and user["password"] == password:
        token = f"mock-jwt-{uuid.uuid4().hex[:16]}"
        _store_token(token, user["user_id"])
        return jsonify({
            "code": 0, "message": "success",
            "data": {"token": token, "user_id": user["user_id"], "username": username}
        }), 200

    # 密码错误：先尝试故障注入（按用户名隔离，并发安全）
    injected, remaining = _consume_fault(username)
    if injected:
        log.warning(f"⚡ [FAULT] 用户 {username} 触发故障注入，剩余 {remaining} 次")
        return jsonify({"code": 500, "message": "临时故障", "data": None}), 500

    log.info(f"🔑 登录失败（用户名或密码错误）: username={username}")
    return jsonify({"code": 401, "message": "用户名或密码错误", "data": None}), 401


# ============================================================
#  用户模块
# ============================================================
@app.route('/api/users/<int:user_id>/profile', methods=['GET'])
def get_profile(user_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, username, avatar FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
    finally:
        conn.close()

    if not user:
        return jsonify({"code": 404, "message": "用户不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": user}), 200


@app.route('/api/users/me/avatar', methods=['PUT'])
def update_avatar():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT file_key FROM file_uploads WHERE file_key = %s AND user_id = %s",
                        (file_key, uid))
            if not cur.fetchone():
                return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400
            cur.execute("UPDATE users SET avatar = %s WHERE user_id = %s", (file_key, uid))
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"avatar": file_key}}), 200


# ============================================================
#  文件上传模块
# ============================================================
@app.route('/api/files/upload-token', methods=['POST'])
def get_upload_token():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_name" not in data:
        return jsonify({"code": 400, "message": "缺少file_name", "data": None}), 400

    file_key = f"fk-{uuid.uuid4().hex[:12]}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO file_uploads (file_key, file_name, file_type, user_id, committed)
                   VALUES (%s, %s, %s, %s, 0)""",
                (file_key, data["file_name"], data.get("file_type", ""), uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"file_key": file_key}}), 200


@app.route('/api/files/commit', methods=['POST'])
def commit_file():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "file_key" not in data:
        return jsonify({"code": 400, "message": "缺少file_key", "data": None}), 400

    file_key = data["file_key"]
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE file_uploads SET committed = 1 WHERE file_key = %s AND user_id = %s",
                (file_key, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 400, "message": "无效的file_key", "data": None}), 400

    return jsonify({"code": 0, "message": "success",
                    "data": {"file_key": file_key, "status": "committed"}}), 200


@app.route('/api/files/<file_key>', methods=['DELETE'])
def delete_file(file_key):
    """删除上传记录（归属权校验：只能删自己的）。用于集成测试 teardown 清理。"""
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM file_uploads WHERE file_key = %s AND user_id = %s",
                (file_key, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "文件不存在或不属于当前用户", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  订单模块
# ============================================================
@app.route('/api/orders', methods=['POST'])
def create_order():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "product_id" not in data:
        return jsonify({"code": 400, "message": "缺少product_id", "data": None}), 400

    order_id = f"ORD{int(time.time())}{uuid.uuid4().hex[:4].upper()}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO orders (order_id, user_id, product_id, quantity, address, status)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (order_id, uid, data["product_id"],
                 data.get("quantity", 1), data.get("address", ""), "pending")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"order_id": order_id}}), 201


@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            order = cur.fetchone()
    finally:
        conn.close()

    if not order:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": order}), 200


@app.route('/api/orders/<order_id>/cancel', methods=['PUT'])
def cancel_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = 'cancelled' WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success",
                    "data": {"order_id": order_id, "status": "cancelled"}}), 200


@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM orders WHERE order_id = %s AND user_id = %s",
                (order_id, uid)
            )
            affected = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if affected == 0:
        return jsonify({"code": 404, "message": "订单不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  项目模块
# ============================================================
@app.route('/api/projects', methods=['POST'])
def create_project():
    uid, err = _require_auth(request)
    if err:
        return err

    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"code": 400, "message": "缺少name", "data": None}), 400

    project_id = f"PRJ{uuid.uuid4().hex[:8].upper()}"
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO projects (id, name, user_id) VALUES (%s, %s, %s)",
                (project_id, data["name"], uid)
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": project_id}}), 201


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # ✅ 先级联删除该项目下的所有任务
            cur.execute(
                "DELETE FROM tasks WHERE project_id = %s",
                (project_id,)
            )
            # 再删除项目本身
            cur.execute(
                "DELETE FROM projects WHERE id = %s AND user_id = %s",
                (project_id, uid),
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": None}), 200


# ============================================================
#  任务模块
# ============================================================
@app.route('/api/projects/<project_id>/tasks', methods=['POST'])
def create_task(project_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
            if not cur.fetchone():
                return jsonify({"code": 404, "message": "项目不存在", "data": None}), 404

        data = request.get_json(silent=True)
        if not data or "title" not in data:
            return jsonify({"code": 400, "message": "缺少title", "data": None}), 400

        task_id = f"TSK{uuid.uuid4().hex[:8].upper()}"
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (id, project_id, title, priority, status)
                   VALUES (%s, %s, %s, %s, %s)""",
                (task_id, project_id, data["title"], data.get("priority", "medium"), "open")
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": {"id": task_id}}), 201


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['GET'])
def get_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
    finally:
        conn.close()

    if not task:
        return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

    return jsonify({"code": 0, "message": "success", "data": task}), 200


@app.route('/api/projects/<project_id>/tasks/<task_id>', methods=['PUT'])
def update_task(project_id, task_id):
    uid, err = _require_auth(request)
    if err:
        return err

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tasks WHERE id = %s AND project_id = %s",
                (task_id, project_id)
            )
            task = cur.fetchone()
            if not task:
                return jsonify({"code": 404, "message": "任务不存在", "data": None}), 404

            data = request.get_json(silent=True)
            if data:
                updates = []
                values = []
                for key in ("title", "priority", "status"):
                    if key in data:
                        updates.append(f"{key} = %s")
                        values.append(data[key])
                if updates:
                    values.extend([task_id, project_id])
                    cur.execute(
                        f"UPDATE tasks SET {', '.join(updates)} WHERE id = %s AND project_id = %s",
                        values
                    )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
            updated = cur.fetchone()
    finally:
        conn.close()

    return jsonify({"code": 0, "message": "success", "data": updated}), 200


# ============================================================
#  健康检查（供 Jenkins/ensure_mock 探测服务是否就绪）
# ============================================================
@app.route('/api/ping', methods=['GET'])
def api_ping():
    """轻量健康检查：返回服务状态+DB连通性（不做重操作，避免影响探测性能）。"""
    db_ok = True
    try:
        conn = DB_POOL.connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
    except Exception as exc:
        log.error(f"/api/ping DB 健康检查失败: {exc}")
        db_ok = False
    status = "ok" if db_ok else "db_error"
    return jsonify({
        "code": 0,
        "status": status,
        "service": "mock_api",
        "port": 5000
    }), 200


# ============================================================
#  首页
# ============================================================
@app.route('/', methods=['GET'])
def home():
    return '<h1>Mock API Server (Concurrent Safe)</h1>'


if __name__ == '__main__':
    # ★ 关键：关闭 debug，开启多线程
    log.info("🚀 Mock API Server 启动中: host=0.0.0.0 port=5000 threaded=True")
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,          # 生产模式，不开 reloader
        threaded=True         # 每个请求一个线程，支持并发
    )