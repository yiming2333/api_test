"""
确保 Mock API 服务可用。

子命令:
  start     (默认) 已运行 → 直接退出 0；未运行且 env=dev → 后台启动 mock_flask.py 并等待就绪，写入 PID 文件
  stop              根据 PID 文件停止 Mock；若 PID 文件失效但端口仍有占用，按端口兜底清理
  status            打印 Mock 服务运行状态（HTTP 响应 / PID 文件 / 进程存活）
  reset-db          清空 orders/projects/tasks/file_uploads 四张业务表，保留 users 种子数据（dev 环境）

prod 环境 → 所有涉及 Mock 的操作都会跳过。
"""

import argparse
import os
import signal
import subprocess
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from common.yaml_handler import get_config  # noqa: E402

# PID 文件放在项目根目录，供后续 stop 子命令读取
PID_FILE = os.path.join(BASE_DIR, ".mock.pid")


# ============================================================
#  基础工具
# ============================================================

def is_mock_up(base_url, timeout=2):
    try:
        resp = requests.get(base_url.rstrip("/") + "/", timeout=timeout)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def wait_until_ready(base_url, retries=30, interval=1):
    for _ in range(retries):
        if is_mock_up(base_url):
            return True
        time.sleep(interval)
    return False


def _write_pid(pid):
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except OSError as exc:
        print(f"[ensure_mock] ⚠️ 写入 PID 文件失败: {exc}", file=sys.stderr)


def _read_pid():
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None


def _clear_pid():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except OSError:
        pass


def _process_exists(pid):
    """判断进程是否存在（Windows + 跨平台通用）。"""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        except subprocess.SubprocessError:
            return False
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True


def _kill_by_pid(pid):
    """尝试优雅终止，失败则强杀。返回 True 表示进程已不存在。"""
    if not _process_exists(pid):
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, timeout=10,
            )
        else:
            os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            if _process_exists(pid):
                os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    # 再判断一次是否真的没了
    for _ in range(10):
        if not _process_exists(pid):
            return True
        time.sleep(0.3)
    return not _process_exists(pid)


def start_mock():
    mock_script = os.path.join(BASE_DIR, "mock_flask.py")
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    return subprocess.Popen(
        [sys.executable, mock_script],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


# ============================================================
#  子命令实现
# ============================================================

def cmd_start(env_name):
    if env_name != "dev":
        print(f"[ensure_mock] env={env_name}，跳过 Mock 启动检查")
        return 0

    cfg = get_config(env_name)
    base_url = cfg["base_url"]

    if is_mock_up(base_url):
        print(f"[ensure_mock] Mock 已在运行: {base_url}")
        return 0

    print(f"[ensure_mock] Mock 未检测到，正在启动: {base_url}")
    proc = start_mock()
    _write_pid(proc.pid)

    if wait_until_ready(base_url):
        print(f"[ensure_mock] Mock 启动成功 (pid={proc.pid})")
        return 0

    # 启动超时，清理 PID 文件
    print("[ensure_mock] Mock 启动超时，请检查 MySQL 与 config/config.yaml", file=sys.stderr)
    _clear_pid()
    return 1


def cmd_stop(env_name):
    """停止 Mock 服务：按 PID 文件 → 按端口占用（兜底）两级清理。"""
    if env_name != "dev":
        print(f"[ensure_mock] env={env_name}，无需停止 Mock")
        return 0

    stopped = False
    pid = _read_pid()
    if pid is not None:
        print(f"[ensure_mock] 根据 PID 文件尝试停止 mock (pid={pid})...")
        if _kill_by_pid(pid):
            if _process_exists(pid):
                print(f"[ensure_mock] 已请求停止，pid={pid} 仍在退出中...")
                stopped = False
            else:
                print(f"[ensure_mock] 已停止进程 pid={pid}")
                stopped = True
        else:
            print(f"[ensure_mock] 进程 pid={pid} 不存在或已停止")
    _clear_pid()

    # 兜底：虽然 PID 文件里没有，但端口可能被占用
    cfg = get_config(env_name)
    base_url = cfg["base_url"]
    if is_mock_up(base_url):
        print("[ensure_mock] 检测到端口仍有服务响应，尝试按端口清理...")
        try:
            from urllib.parse import urlparse
            port = urlparse(base_url).port or 5000
            if sys.platform == "win32":
                result = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, text=True, timeout=10,
                )
                for line in result.stdout.splitlines():
                    if f":{port} " in line and "LISTENING" in line:
                        parts = line.strip().split()
                        listen_pid = int(parts[-1])
                        print(f"[ensure_mock] 发现端口 {port} 占用，pid={listen_pid}，尝试强杀...")
                        _kill_by_pid(listen_pid)
                        stopped = True
        except Exception as exc:
            print(f"[ensure_mock] 按端口清理失败: {exc}", file=sys.stderr)

    if not stopped and pid is None:
        print("[ensure_mock] 没有需要停止的 Mock 进程")
    return 0


def cmd_status(env_name):
    if env_name != "dev":
        print(f"[ensure_mock] env={env_name}，Mock 状态：不适用")
        return 0
    cfg = get_config(env_name)
    base_url = cfg["base_url"]
    pid = _read_pid()
    alive = _process_exists(pid) if pid else False
    up = is_mock_up(base_url)
    print(
        f"[ensure_mock] 状态: {'✅ 正常' if up else '❌ 未响应'}  "
        f"base_url={base_url}  PID文件={pid}  PID进程存活={'是' if alive else '否'}"
    )
    return 0 if up else 1


def cmd_reset_db(env_name):
    """清空所有业务表（orders/projects/tasks/file_uploads），保留 users 种子数据。

    在 Jenkins 跑 pytest 前调用，作为上一次中断残留的兜底清理。
    直连 MySQL，不依赖 Mock 服务是否启动。
    """
    if env_name != "dev":
        print(f"[ensure_mock] env={env_name}，跳过 DB 重置")
        return 0

    try:
        from common.db_pool import get_pool
    except Exception as exc:
        print(f"[ensure_mock] ❌ 无法导入 db_pool: {exc}", file=sys.stderr)
        return 1

    pool = get_pool(env=env_name, database="api_test", autocommit=True)

    # tasks 有外键指向 projects，清表时临时关闭外键检查，顺序就无所谓
    tables = ["tasks", "file_uploads", "orders", "projects"]
    totals = {}

    conn = None
    try:
        conn = pool.connection()
        with conn.cursor() as cur:
            # 先计数（日志展示清了多少）
            for table in tables:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                totals[table] = cur.fetchone()["c"]

            cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in tables:
                cur.execute(f"TRUNCATE TABLE {table}")
            cur.execute("SET FOREIGN_KEY_CHECKS = 1")

            # 再 count 一次确认清零
            for table in tables:
                cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
                after = cur.fetchone()["c"]
                if after != 0:
                    raise RuntimeError(f"{table} 表 TRUNCATE 后仍有 {after} 条记录")

        summary = ", ".join(f"{tbl}:{totals[tbl]}" for tbl in tables)
        print(f"[ensure_mock] ✅ DB 重置完成（清理前 -> {summary}）")
        return 0

    except Exception as exc:
        print(f"[ensure_mock] ❌ DB 重置失败: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn:
            conn.close()


# ============================================================
#  入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="确保 Mock API 服务可用")
    parser.add_argument(
        "action", nargs="?", default="start",
        choices=["start", "stop", "status", "reset-db"],
        help="start=确保启动(默认) / stop=停止 / status=检查状态 / reset-db=清空业务表",
    )
    parser.add_argument("--env", default="dev", help="运行环境 dev/prod")
    args = parser.parse_args()

    if args.action == "start":
        return cmd_start(args.env)
    if args.action == "stop":
        return cmd_stop(args.env)
    if args.action == "status":
        return cmd_status(args.env)
    if args.action == "reset-db":
        return cmd_reset_db(args.env)
    return 0


if __name__ == "__main__":
    sys.exit(main())
