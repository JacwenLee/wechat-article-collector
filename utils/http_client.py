"""
HTTP 客户端封装 —— 带随机 UA 轮换、Cookie 管理、请求间隔控制。
降低被搜狗/微信拦截的概率。
"""

import random
import time
import threading
from datetime import datetime

import requests

# 常见桌面浏览器 User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

# 微信内嵌浏览器 UA（抓取全文时使用）
WECHAT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.49(0x18003131) NetType/WIFI Language/zh_CN"
)


class HttpClient:
    """带反爬策略的 requests 封装（线程安全）。"""

    def __init__(self, min_interval=2.0, max_interval=5.0, timeout=15):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.timeout = timeout
        self.session = requests.Session()
        self._lock = threading.Lock()
        self._last_request_time = 0.0

    # ------------------------------------------------------------------
    #  内部工具
    # ------------------------------------------------------------------
    def _wait_interval(self):
        """请求间隔随机延迟，降低触发验证码的概率。"""
        with self._lock:
            elapsed = time.time() - self._last_request_time
            needed = random.uniform(self.min_interval, self.max_interval)
            if elapsed < needed:
                time.sleep(needed - elapsed)
            self._last_request_time = time.time()

    def _make_headers(self, use_wechat_ua=False, extra=None):
        ua = WECHAT_UA if use_wechat_ua else random.choice(USER_AGENTS)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------
    def get(self, url, params=None, use_wechat_ua=False, extra_headers=None,
            allow_redirects=True):
        """发起 GET 请求，返回 Response 对象。"""
        self._wait_interval()
        headers = self._make_headers(use_wechat_ua, extra_headers)
        resp = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout,
            allow_redirects=allow_redirects,
        )
        return resp

    def get_text(self, url, params=None, use_wechat_ua=False, extra_headers=None,
                 encoding=None):
        """发起 GET 请求，返回解码后的文本。"""
        resp = self.get(url, params=params, use_wechat_ua=use_wechat_ua,
                        extra_headers=extra_headers)
        if encoding:
            resp.encoding = encoding
        else:
            resp.encoding = resp.apparent_encoding
        return resp.text, resp.url, resp.status_code

    def download_image(self, url):
        """下载图片，返回 bytes 或 None。"""
        try:
            self._wait_interval()
            headers = self._make_headers()
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                return resp.content
        except Exception:
            pass
        return None

    @property
    def cookies(self):
        return self.session.cookies

    def close(self):
        self.session.close()
