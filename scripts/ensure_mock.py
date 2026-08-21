"""
确保 Mock API 服务可用。

- 已运行 → 直接退出 0，不重复启动
- 未运行且 env=dev → 后台启动 mock_flask.py 并等待就绪
- prod 环境 → 跳过（不启动 Mock）
"""

import argparse
import os
import subprocess
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from common.yaml_handler import get_config  # noqa: E402


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


def main():
    parser = argparse.ArgumentParser(description="确保 Mock API 服务可用")
    parser.add_argument("--env", default="dev", help="运行环境 dev/prod")
    args = parser.parse_args()

    if args.env != "dev":
        print(f"[ensure_mock] env={args.env}，跳过 Mock 启动检查")
        return 0

    cfg = get_config(args.env)
    base_url = cfg["base_url"]

    if is_mock_up(base_url):
        print(f"[ensure_mock] Mock 已在运行: {base_url}")
        return 0

    print(f"[ensure_mock] Mock 未检测到，正在启动: {base_url}")
    proc = start_mock()

    if wait_until_ready(base_url):
        print(f"[ensure_mock] Mock 启动成功 (pid={proc.pid})")
        return 0

    print("[ensure_mock] Mock 启动超时，请检查 MySQL 与 config/config.yaml", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
