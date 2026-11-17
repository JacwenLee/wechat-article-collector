"""
搜狗微信搜索核心 —— 构造请求、解析结果页。
搜索 URL: https://weixin.sogou.com/weixin?type=2&query={关键词}&page={页码}
"""

import re
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from utils.http_client import HttpClient

SOGOU_BASE = "https://weixin.sogou.com"
SOGOU_SEARCH_URL = f"{SOGOU_BASE}/weixin"

# timeConvert('1794820020') 中的时间戳
RE_TIMESTAMP = re.compile(r"timeConvert\('(\d+)'\)")
# 验证码页面特征
RE_CAPTCHA = re.compile(r"antispider|user/images|验证码|captcha", re.IGNORECASE)


@dataclass
class SearchResult:
    """单条搜索结果。"""
    title: str = ""
    summary: str = ""
    author: str = ""          # 公众号名称
    pub_date: str = ""        # 发布时间 (YYYY-MM-DD)
    link: str = ""            # 搜狗临时链接 (绝对)
    cover_img: str = ""       # 封面图 URL (绝对)
    account_id: str = ""


@dataclass
class SearchResponse:
    """一次搜索的完整响应。"""
    results: list = field(default_factory=list)   # list[SearchResult]
    total: int = 0             # 总结果数
    page: int = 1              # 当前页
    has_next: bool = False     # 是否有下一页
    is_captcha: bool = False   # 是否被验证码拦截
    error: str = ""            # 错误信息


class Searcher:
    """搜狗微信文章搜索器。"""

    def __init__(self, http_client=None):
        self.http = http_client or HttpClient()

    # ------------------------------------------------------------------
    def search(self, keyword, page=1) -> SearchResponse:
        """
        搜索公众号文章。
        :param keyword: 搜索关键词
        :param page: 页码 (从 1 开始)
        :return: SearchResponse
        """
        params = {
            "type": "2",        # 2=搜文章, 1=搜公众号
            "query": keyword,
            "page": str(page),
            "ie": "utf8",
        }
        try:
            text, final_url, status = self.http.get_text(
                SOGOU_SEARCH_URL, params=params,
                extra_headers={"Referer": SOGOU_BASE},
            )
        except Exception as e:
            return SearchResponse(error=f"请求失败: {e}", page=page)

        if status != 200:
            return SearchResponse(error=f"HTTP {status}", page=page)

        # 检测验证码
        if RE_CAPTCHA.search(text):
            return SearchResponse(
                is_captcha=True,
                error="搜狗要求验证码，请稍后重试或在浏览器中手动访问",
                page=page,
            )

        return self._parse(text, page)

    # ------------------------------------------------------------------
    def _parse(self, html, page) -> SearchResponse:
        """解析搜索结果 HTML。"""
        soup = BeautifulSoup(html, "lxml")
        resp = SearchResponse(page=page)

        # 总结果数
        total_text = ""
        for el in soup.select("div.news-box2, .p-fy, .results-num"):
            total_text = el.get_text(strip=True)
            break
        # 备选: "找到约5,989条结果"
        m = re.search(r"找到约\s*([\d,]+)\s*条", html)
        if m:
            resp.total = int(m.group(1).replace(",", ""))
        else:
            m2 = re.search(r"约\s*([\d,]+)\s*条", html)
            if m2:
                resp.total = int(m2.group(1).replace(",", ""))

        # 结果列表
        lis = soup.select("ul.news-list > li")
        for li in lis:
            result = self._parse_item(li)
            if result.title:
                resp.results.append(result)

        # 翻页: 检查是否有 "下一页" 链接
        next_link = soup.find("a", string=re.compile(r"下一页"))
        if next_link and next_link.get("href"):
            resp.has_next = True
        # 备选: 检查 page 参数
        if not resp.has_next:
            page_links = soup.select("a[href*='page=']")
            max_page = page
            for a in page_links:
                m = re.search(r"page=(\d+)", a.get("href", ""))
                if m:
                    max_page = max(max_page, int(m.group(1)))
            resp.has_next = max_page > page

        return resp

    # ------------------------------------------------------------------
    def _parse_item(self, li) -> SearchResult:
        """解析单条结果。"""
        result = SearchResult()

        # 标题 + 链接
        title_a = li.select_one("h3 a") or li.select_one("h4 a")
        if title_a:
            result.title = title_a.get_text(strip=True)
            href = title_a.get("href", "")
            if href:
                result.link = urljoin(SOGOU_BASE, href)

        # 摘要
        p = li.select_one("p.txt-info")
        if p:
            result.summary = p.get_text(strip=True)

        # 封面图
        img = li.select_one("img")
        if img:
            src = img.get("src") or img.get("data-src") or ""
            if src.startswith("//"):
                src = "https:" + src
            result.cover_img = src

        # 公众号名 + 发布时间
        sp = li.select_one("div.s-p")
        if sp:
            # 公众号名
            author_span = sp.select_one("span.all-time-y2") or sp.select_one("a")
            if author_span:
                result.author = author_span.get_text(strip=True)
            # 发布时间 (从 script timeConvert 提取时间戳)
            sp_html = str(sp)
            m = RE_TIMESTAMP.search(sp_html)
            if m:
                ts = int(m.group(1))
                result.pub_date = time.strftime(
                    "%Y-%m-%d", time.localtime(ts)
                )

        # 公众号 ID (从链接中尝试提取)
        account_a = sp.select_one("a") if sp else None
        if account_a:
            href = account_a.get("href", "")
            m = re.search(r"openid=([^&]+)", href)
            if m:
                result.account_id = m.group(1)

        return result

    # ------------------------------------------------------------------
    def search_all(self, keyword, max_pages=3, on_page=None):
        """
        多页搜索，收集所有结果。
        :param on_page: 回调 fn(page, results) 用于进度通知
        :return: list[SearchResult]
        """
        all_results = []
        for page in range(1, max_pages + 1):
            resp = self.search(keyword, page=page)
            if resp.is_captcha:
                break
            if resp.error:
                break
            all_results.extend(resp.results)
            if on_page:
                on_page(page, resp.results)
            if not resp.has_next:
                break
        return all_results
