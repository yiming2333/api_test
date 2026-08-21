import json

import allure
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from common.logger import log
from common.sanitize import sanitize_for_report
from common.yaml_handler import get_config


class HttpClient:
    """封装的 HTTP 客户端：base_url、重试、日志、Allure 附件。"""

    def __init__(self, base_url, env="dev", timeout=10, token=None):
        _cfg = get_config(env)
        self.base_url = base_url
        self.timeout = _cfg.get("timeout", timeout)

        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        retry = Retry(
            total=_cfg.get("retry", 2),
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        full_url = url if url.startswith("http") else self.base_url + url

        log.info(f"➡️  请求: {method.upper()} {full_url}")
        log.info(f"   参数: {sanitize_for_report(kwargs)}")

        allure.attach(
            json.dumps(sanitize_for_report(kwargs), ensure_ascii=False, indent=2, default=str),
            name=f"请求-{method.upper()} {url}",
            attachment_type=allure.attachment_type.JSON,
        )

        try:
            resp = self.session.request(method, full_url, timeout=self.timeout, **kwargs)
        except requests.exceptions.RequestException as exc:
            log.error(f"❌ 请求异常: {exc}")
            raise

        log.info(f"⬅️  状态码: {resp.status_code} | 耗时: {resp.elapsed.total_seconds():.3f}s")
        try:
            log.info(f"   响应体: {sanitize_for_report(resp.json())}")
        except Exception:
            log.info(f"   响应体(非JSON): {resp.text[:500]}")

        content_type = resp.headers.get("Content-Type", "")
        allure.attach(
            resp.text,
            name=f"响应-{resp.status_code}",
            attachment_type=(
                allure.attachment_type.JSON if "json" in content_type
                else allure.attachment_type.TEXT
            ),
        )

        return resp

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)
