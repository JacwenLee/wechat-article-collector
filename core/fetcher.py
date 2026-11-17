"""
文章全文抓取 —— 跟随搜狗临时链接 → 微信真实文章页 → 提取全文。
失败时降级为只存摘要+链接。
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from utils.http_client import HttpClient, WECHAT_UA

WEIXIN_BASE = "https://mp.weixin.qq.com"
# 搜狗 link 页面中可能用 JS 跳转: window.location = "mp.weixin.qq.com/s?..."
RE_JS_REDIRECT = re.compile(
    r'(?:window\.location|location\.href)\s*=\s*["\']([^"\']+)["\']'
)
RE_META_REFRESH = re.compile(
    r'url=(["\']?)(https?://[^"\'>\s]+)\1', re.IGNORECASE
)
# 搜狗 link 页面用 JS 拼接 URL: url += 'fragment'; url = 'first';
RE_JS_URL_ASSIGN = re.compile(r"""url\s*(?:\+=|=)\s*['"]([^'"]*)['"]""")
# window.location.replace(url) 或 location.href = url
RE_JS_LOCATION_CALL = re.compile(
    r'(?:window\.location\.replace|location\.replace|location\.href\s*=)\s*\(\s*url\s*\)'
)


@dataclass
class ArticleContent:
    """抓取到的文章全文。"""
    success: bool = False
    title: str = ""
    author: str = ""
    pub_date: str = ""
    content_html: str = ""     # 正文 HTML
    content_text: str = ""     # 正文纯文本
    real_url: str = ""         # 微信真实链接
    cover_img: str = ""
    error: str = ""


class Fetcher:
    """文章全文抓取器。"""

    def __init__(self, http_client=None):
        self.http = http_client or HttpClient()

    # ------------------------------------------------------------------
    def fetch_by_url(self, url) -> ArticleContent:
        """
        根据 URL 类型自动选择抓取方式。
        支持: 微信文章链接(mp.weixin.qq.com) / 搜狗链接(weixin.sogou.com)
        """
        if "mp.weixin.qq.com" in url:
            return self._fetch_wechat_direct(url)
        elif "weixin.sogou.com" in url:
            return self.fetch(url)
        else:
            return self._fetch_wechat_direct(url)

    # ------------------------------------------------------------------
    def fetch(self, sogou_link) -> ArticleContent:
        """
        从搜狗临时链接抓取文章全文。
        :param sogou_link: 搜狗 /link?url=... 链接
        :return: ArticleContent
        """
        result = ArticleContent()

        # Step 1: 访问搜狗临时链接，跟随跳转到微信文章页
        try:
            resp = self.http.get(
                sogou_link,
                extra_headers={"Referer": "https://weixin.sogou.com/"},
            )
        except Exception as e:
            result.error = f"请求搜狗链接失败: {e}"
            return result

        real_url = resp.url
        html = resp.text

        # 如果被重定向到微信文章页
        if "mp.weixin.qq.com" in real_url:
            return self._parse_wechat_article(html, real_url)

        # 尝试从 JS 拼接片段中提取跳转 URL (搜狗 link 页面常用)
        js_url = self._extract_js_concat_url(html)
        if js_url:
            return self._fetch_wechat_direct(js_url)

        # 尝试从 HTML 中提取 JS 跳转目标
        m = RE_JS_REDIRECT.search(html)
        if m:
            target = m.group(1)
            if not target.startswith("http"):
                target = urljoin(WEIXIN_BASE, target)
            return self._fetch_wechat_direct(target)

        # 尝试 meta refresh
        m = RE_META_REFRESH.search(html)
        if m:
            target = m.group(2)
            if "mp.weixin.qq.com" in target:
                return self._fetch_wechat_direct(target)

        # 搜狗有时直接在页面中给出微信链接
        m_wx = re.search(r'(https?://mp\.weixin\.qq\.com/s[^\s"\'<>]+)', html)
        if m_wx:
            return self._fetch_wechat_direct(m_wx.group(1))

        result.error = "无法获取微信文章真实链接（临时链接可能已过期）"
        result.real_url = real_url
        return result

    # ------------------------------------------------------------------
    def _extract_js_concat_url(self, html) -> str:
        """
        从搜狗 link 页面的 JS 代码中提取拼接构造的 URL。
        页面典型模式:
            var url = '';
            url += 'https://mp.';
            url += 'weixin.qq.c';
            url += 'om/s?src=11';
            ...
            window.location.replace(url)
        """
        # 必须存在 location.replace(url) 或类似调用才处理
        if not RE_JS_LOCATION_CALL.search(html):
            return ""
        # 提取所有 url += '...' / url = '...' 片段
        fragments = RE_JS_URL_ASSIGN.findall(html)
        if not fragments:
            return ""
        url = "".join(fragments)
        # JS 中可能有 url.replace("@", "")
        url = url.replace("@", "")
        # 验证是否为有效 URL
        if url.startswith("http"):
            return url
        return ""

    # ------------------------------------------------------------------
    def _fetch_wechat_direct(self, wx_url) -> ArticleContent:
        """直接抓取微信文章页。"""
        try:
            text, final_url, status = self.http.get_text(
                wx_url, use_wechat_ua=True,
            )
        except Exception as e:
            # 请求失败但仍保留真实链接，供浏览器打开
            return ArticleContent(error=f"请求微信文章页失败: {e}", real_url=wx_url)

        if status != 200:
            return ArticleContent(error=f"微信文章页 HTTP {status}", real_url=wx_url)

        # 检测验证码/环境异常页面
        if "wappoc_appmsgcaptcha" in final_url or "环境异常" in text:
            return ArticleContent(
                error="微信要求验证码，已保存链接，可点击「打开原文」在浏览器中阅读",
                real_url=wx_url,
            )

        result = self._parse_wechat_article(text, final_url)
        # 确保保留原始微信链接（而非跳转后的 URL）
        if not result.real_url or "captcha" in result.real_url:
            result.real_url = wx_url
        return result

    # ------------------------------------------------------------------
    def _parse_wechat_article(self, html, real_url) -> ArticleContent:
        """解析微信文章页 HTML，提取全文。"""
        result = ArticleContent(success=True, real_url=real_url)
        soup = BeautifulSoup(html, "lxml")

        # 标题
        title_el = soup.select_one("#activity-name") or soup.select_one("h1")
        if title_el:
            result.title = title_el.get_text(strip=True)

        # 公众号名
        author_el = (
            soup.select_one("#js_name")
            or soup.select_one(".profile_nickname")
            or soup.select_one("a.weui-wa-hotarea")
        )
        if author_el:
            result.author = author_el.get_text(strip=True)

        # 发布时间
        date_el = soup.select_one("#publish_time")
        if date_el:
            result.pub_date = date_el.get_text(strip=True)
        else:
            m = re.search(r'var\s+ct\s*=\s*["\'](\d{4}-\d{2}-\d{2})', html)
            if m:
                result.pub_date = m.group(1)

        # 正文 HTML
        content_el = (
            soup.select_one("#js_content")
            or soup.select_one("#page-content")
            or soup.select_one(".rich_media_content")
        )
        if content_el:
            # 清理 script/style 标签
            for tag in content_el.find_all(["script", "style"]):
                tag.decompose()
            result.content_html = str(content_el)
            result.content_text = content_el.get_text(separator="\n", strip=True)
        else:
            # 降级: 取 body 文本
            result.content_text = soup.get_text(separator="\n", strip=True)[:5000]

        # 封面图
        cover = soup.select_one('meta[property="og:image"]')
        if cover:
            result.cover_img = cover.get("content", "")

        if not result.content_text:
            result.success = False
            result.error = "未能提取正文内容"

        return result
