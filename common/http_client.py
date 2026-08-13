import requests
import allure
import json
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from common.logger import log

class HttpClient:
    def __init__(self, base_url, timeout=10, token=None):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

        # 自动重试机制：网络抖动时自动重试
        retry = Retry(total=2, backoff_factor=0.5,
                      status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        """统一请求入口：拼接URL + 日志 + Allure附件"""
        full_url = url if url.startswith("http") else self.base_url + url

        # 请求前日志
        log.info(f"➡️  请求: {method.upper()} {full_url}")
        log.info(f"   参数: {kwargs}")

        # Allure 记录请求详情
        allure.attach(
            json.dumps(kwargs, ensure_ascii=False, indent=2, default=str),
            name=f"请求-{method.upper()} {url}",
            attachment_type=allure.attachment_type.JSON
        )

        try:
            resp = self.session.request(
                method, full_url, timeout=self.timeout, **kwargs
            )
        except requests.exceptions.RequestException as e:
            log.error(f"❌ 请求异常: {e}")
            raise

        # 响应日志
        log.info(f"⬅️  状态码: {resp.status_code} | 耗时: {resp.elapsed.total_seconds()}s")
        try:
            log.info(f"   响应体: {resp.json()}")
        except Exception:
            log.info(f"   响应体(非JSON): {resp.text[:500]}")

        # Allure 记录响应
        allure.attach(
            resp.text,
            name=f"响应-{resp.status_code}",
            attachment_type=allure.attachment_type.JSON
            if "json" in resp.headers.get("Content-Type","")
            else allure.attachment_type.TEXT
        )
        return resp

    # 语法糖
    def get(self, url, **kwargs):    return self.request("GET", url, **kwargs)
    def post(self, url, **kwargs):   return self.request("POST", url, **kwargs)
    def put(self, url, **kwargs):    return self.request("PUT", url, **kwargs)
    def delete(self, url, **kwargs): return self.request("DELETE", url, **kwargs)