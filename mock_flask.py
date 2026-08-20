"""
mock_flask.py - 并发安全版
支持 pytest-xdist 多 worker 同时请求
"""
from flask import Flask, request, jsonify
import uuid
import time
import threading
import pymysql
from dbutils.pooled_db import PooledDB
from common.yaml_handler import get_config

app = Flask(__name__)

# ============================================================
#  数据库连接池（从 config.yaml 读取配置）
# ============================================================
_cfg = get_config("dev")  # Mock 服务固定用 dev 环境

DB_POOL = PooledDB(
    creator=pymysql,
    maxconnections=20,      # 最大连接数（根据 worker 数调整）
    mincached=2,            # 初始空闲连接
    maxcached=5,            # 最大空闲连接
    blocking=True,          # 连接用完时等待而非报错
    host=_cfg.get("db_host", "localhost"),
    port=_cfg.get("db_port", 3306),
    user=_cfg.get("db_user", "root"),
    password=_cfg.get("db_password", ""),
    database="api_test",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False
)


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


FAULT_COUNT= 2
_login_fault_remaining = FAULT_COUNT       # 每次触发消耗的总次数
_login_fault_counter = FAULT_COUNT         # 当前剩余次数（运行时递减）
# ============================================================
#  认证模块
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    global _login_fault_counter
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
    else:
        if _login_fault_counter > 0:
            _login_fault_counter -= 1
            print(f"⚡ [FAULT] 剩余{_login_fault_counter}次")
            return jsonify({"code": 500, "message": "临时故障", "data": None}), 500

        else:
            # ★ 归零后立刻重置，然后本次请求走正常错误返回
            _login_fault_counter = _login_fault_remaining
            # 不 return，继续往下走正常的 400/401 逻辑

        if not data or 'username' not in data:
            return jsonify({"code": 400, "message": "缺少用户名参数", "data": None}), 400
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
            cur.execute("DELETE FROM tasks WHERE project_id = %s", (project_id,))
            cur.execute("DELETE FROM projects WHERE id = %s AND user_id = %s", (project_id, uid))
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
#  首页
# ============================================================
@app.route('/', methods=['GET'])
def home():
    return '<h1>Mock API Server (Concurrent Safe)</h1>'


if __name__ == '__main__':
    # ★ 关键：关闭 debug，开启多线程
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,          # 生产模式，不开 reloader
        threaded=True         # 每个请求一个线程，支持并发
    )