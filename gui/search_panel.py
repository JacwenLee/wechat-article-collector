"""
搜索面板 —— 搜索栏 + 结果列表 + 操作按钮。
支持两种模式：搜索模式（搜狗结果）和收藏库模式（本地文章）。
"""

import threading

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

from core.searcher import Searcher
from core.fetcher import Fetcher
from gui.reader_window import ReaderWindow
from utils.helpers import open_url
from utils.config import Config
from gui.web_viewer import open_in_app, open_html_in_app


class SearchPanel(ttk.Frame):
    """搜索 + 结果列表面板。"""

    MODE_SEARCH = "search"
    MODE_COLLECTION = "collection"

    def __init__(self, parent, db, on_status=None, on_refresh=None,
                 config=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.on_status = on_status or (lambda t: None)
        self.on_refresh = on_refresh or (lambda: None)
        self.config = config or Config()
        self.searcher = Searcher()
        self.fetcher = Fetcher(self.searcher.http)
        self._searching = False

        self.mode = self.MODE_COLLECTION
        self.search_scope = "online"
        self.current_keyword = ""
        self.current_page = 1
        self.search_response = None
        self._search_results = []
        self._collection_items = []
        self._item_map = {}

        self._build_ui()
        self.show_collection()

    # ==================================================================
    #  UI 构建
    # ==================================================================
    def _build_ui(self):
        # ---- 搜索栏 ----
        search_frame = ttk.Frame(self, bootstyle=SECONDARY)
        search_frame.pack(fill=X, padx=8, pady=(8, 4))

        ttk.Label(search_frame, text="🔍", font=("", 14)).pack(side=LEFT, padx=(8, 4))

        # 本地/在线切换
        self.scope_var = ttk.StringVar(value="online")
        scope_box = ttk.Combobox(search_frame, textvariable=self.scope_var,
                                 values=["online 在线搜索", "local 本地搜索"],
                                 state="readonly", width=12, bootstyle=SECONDARY)
        scope_box.pack(side=LEFT, padx=2)
        scope_box.bind("<<ComboboxSelected>>", self._on_scope_change)

        # 搜索历史 Combobox
        self.keyword_var = ttk.StringVar()
        hist = self.config.get_search_history()
        self.keyword_combo = ttk.Combobox(search_frame, textvariable=self.keyword_var,
                                          font=("微软雅黑", 11), width=35,
                                          values=hist)
        self.keyword_combo.pack(side=LEFT, padx=4, fill=X, expand=True)
        self.keyword_combo.bind("<Return>", lambda e: self.do_search())

        self.search_btn = ttk.Button(search_frame, text="搜索", bootstyle=PRIMARY,
                                     command=self.do_search, width=8)
        self.search_btn.pack(side=LEFT, padx=4)

        self.prev_btn = ttk.Button(search_frame, text="上一页", bootstyle=(SECONDARY, OUTLINE),
                                   command=self._prev_page, width=8, state=DISABLED)
        self.prev_btn.pack(side=LEFT, padx=2)
        self.next_btn = ttk.Button(search_frame, text="下一页", bootstyle=(SECONDARY, OUTLINE),
                                   command=self._next_page, width=8, state=DISABLED)
        self.next_btn.pack(side=LEFT, padx=2)

        self.page_label = ttk.Label(search_frame, text="", bootstyle=SECONDARY)
        self.page_label.pack(side=LEFT, padx=8)

        # ---- 垂直分割：上方列表+按钮，下方嵌入式浏览器 ----
        vpaned = ttk.Panedwindow(self, orient=VERTICAL)
        vpaned.pack(fill=BOTH, expand=True, padx=4, pady=4)

        # ===== 上方区域 =====
        top_pane = ttk.Frame(vpaned)
        vpaned.add(top_pane, weight=2)

        # ---- 结果列表 ----
        list_frame = ttk.Frame(top_pane)
        list_frame.pack(fill=BOTH, expand=True, padx=8, pady=4)

        # Treeview
        columns = ("title", "author", "date")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                 bootstyle=LIGHT, selectmode=EXTENDED)
        self.tree.heading("title", text="标题", anchor=W)
        self.tree.heading("author", text="公众号", anchor=W)
        self.tree.heading("date", text="日期", anchor=CENTER)
        self.tree.column("title", width=450, minwidth=200)
        self.tree.column("author", width=150, minwidth=80)
        self.tree.column("date", width=90, minwidth=60, anchor=CENTER)

        # 行标签交替色
        self.tree.tag_configure("even", background="#f8f9fa")
        self.tree.tag_configure("odd", background="#ffffff")

        scrollbar = ttk.Scrollbar(list_frame, orient=VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Button-3>", self._on_right_click)  # 右键菜单

        # ---- 摘要预览 ----
        self.summary_var = ttk.StringVar(value="")
        summary_label = ttk.Label(top_pane, textvariable=self.summary_var,
                                  font=("微软雅黑", 9), bootstyle=SECONDARY,
                                  wraplength=700, justify=LEFT)
        summary_label.pack(fill=X, padx=12, pady=(0, 4))

        # ---- 操作按钮栏 ----
        btn_frame = ttk.Frame(top_pane)
        btn_frame.pack(fill=X, padx=8, pady=(0, 4))

        self.select_all_var = ttk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text="全选", variable=self.select_all_var,
                        command=self._toggle_select_all,
                        bootstyle=PRIMARY).pack(side=LEFT, padx=4)

        self.collect_btn = ttk.Button(btn_frame, text="📥 收藏选中",
                                      bootstyle=SUCCESS, command=self._collect_selected)
        self.collect_btn.pack(side=LEFT, padx=4)

        self.open_btn = ttk.Button(btn_frame, text="🔗 打开",
                                   bootstyle=INFO, command=self._open_selected_in_browser)
        self.open_btn.pack(side=LEFT, padx=4)

        self.read_btn = ttk.Button(btn_frame, text="📖 阅读",
                                   bootstyle=INFO, command=self._read_selected)
        self.read_btn.pack(side=LEFT, padx=4)

        self.export_btn = ttk.Button(btn_frame, text="📤 导出",
                                     bootstyle=(WARNING, OUTLINE), command=self._export_selected)
        self.export_btn.pack(side=LEFT, padx=4)

        self.delete_btn = ttk.Button(btn_frame, text="🗑 删除",
                                     bootstyle=(DANGER, OUTLINE), command=self._delete_selected)
        self.delete_btn.pack(side=LEFT, padx=4)

        self.count_label = ttk.Label(btn_frame, text="", bootstyle=SECONDARY)
        self.count_label.pack(side=RIGHT, padx=8)

        # 进度条
        self.progress = ttk.Progressbar(btn_frame, mode=INDETERMINATE,
                                        length=120, bootstyle=SUCCESS)

        # ===== 下方区域：嵌入式浏览器 =====
        bottom_pane = ttk.Frame(vpaned)
        vpaned.add(bottom_pane, weight=3)

        # 浏览器工具栏
        browser_bar = ttk.Frame(bottom_pane, bootstyle=SECONDARY)
        browser_bar.pack(fill=X, padx=2, pady=2)
        self.browser_title_var = ttk.StringVar(value="文章预览")
        ttk.Label(browser_bar, textvariable=self.browser_title_var,
                  font=("微软雅黑", 10, "bold"), bootstyle=INVERSE).pack(side=LEFT, padx=8)
        ttk.Button(browser_bar, text="刷新", bootstyle=(SECONDARY, OUTLINE),
                   command=self._refresh_browser, width=6).pack(side=RIGHT, padx=4)
        ttk.Button(browser_bar, text="外部打开", bootstyle=(SECONDARY, OUTLINE),
                   command=self._open_browser_external, width=8).pack(side=RIGHT, padx=4)

        # tkinterweb HtmlFrame
        try:
            from tkinterweb import HtmlFrame
            self.browser_frame = HtmlFrame(bottom_pane, messages_enabled=False)
            self.browser_frame.pack(fill=BOTH, expand=True, padx=2, pady=2)
            self._browser_ok = True
        except Exception:
            self.browser_frame = ttk.ScrolledText(bottom_pane, font=("微软雅黑", 11), wrap=WORD)
            self.browser_frame.pack(fill=BOTH, expand=True, padx=2, pady=2)
            self._browser_ok = False

        self._current_browser_url = ""

    # ==================================================================
    #  嵌入式浏览器
    # ==================================================================
    def _load_in_browser(self, url, title="文章阅读"):
        """在下方嵌入式浏览器中加载 URL。"""
        self._current_browser_url = url
        self.browser_title_var.set(title[:50])
        self.on_status(f"正在加载: {title[:30]}...")
        if self._browser_ok:
            try:
                self.browser_frame.load_url(url)
            except Exception:
                self.browser_frame.load_html(f"<html><body><h2>加载失败</h2><p>URL: {url}</p></body></html>")
        else:
            self.browser_frame.delete("1.0", END)
            self.browser_frame.insert("1.0", f"加载: {url}\n\n（tkinterweb 不可用，请点击「外部打开」在浏览器中查看）")
        self.on_status(f"已加载: {title[:30]}")

    def _load_in_browser_resolved(self, sogou_link, title="文章阅读"):
        """解析搜狗链接获取真实 URL，然后在浏览器中加载。"""
        self.browser_title_var.set(title[:50])
        self.on_status(f"正在解析链接: {title[:30]}...")

        def worker():
            try:
                art = self.fetcher.fetch(sogou_link)
                real_url = art.real_url or sogou_link
                self.after(0, lambda: self._load_in_browser(real_url, title))
            except Exception:
                self.after(0, lambda: self._load_in_browser(sogou_link, title))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_browser(self):
        """刷新当前页面。"""
        if self._current_browser_url:
            self._load_in_browser(self._current_browser_url, self.browser_title_var.get())

    def _open_browser_external(self):
        """在外部浏览器中打开当前页面。"""
        if self._current_browser_url:
            open_url(self._current_browser_url)

    # ==================================================================
    #  搜索模式
    # ==================================================================
    def _on_scope_change(self, event=None):
        val = self.scope_var.get()
        self.search_scope = "local" if "local" in val else "online"
        if self.search_scope == "local":
            self.prev_btn.config(state=DISABLED)
            self.next_btn.config(state=DISABLED)
            self.page_label.config(text="")

    def do_search(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            self.on_status("请输入搜索关键词")
            return
        if self._searching:
            return  # 防抖
        self.current_keyword = keyword

        # 本地搜索
        if self.search_scope == "local":
            self.config.add_search_history(keyword)
            self.keyword_combo['values'] = self.config.get_search_history()
            results = self.db.fulltext_search(keyword)
            self.mode = self.MODE_COLLECTION
            self._collection_items = results
            self._set_buttons()
            self._populate_tree_collection(results)
            self.on_status(f"本地搜索「{keyword}」: {len(results)} 条")
            return

        # 在线搜索
        self.config.add_search_history(keyword)
        self.keyword_combo['values'] = self.config.get_search_history()
        self.current_page = 1
        self._search_page()

    def _search_page(self):
        self.mode = self.MODE_SEARCH
        self._searching = True
        self.search_btn.config(state=DISABLED)
        self._set_buttons()
        self.on_status(f"正在搜索「{self.current_keyword}」第 {self.current_page} 页...")
        self._start_progress()

        def worker():
            try:
                resp = self.searcher.search(self.current_keyword, page=self.current_page)
            except Exception as e:
                resp = type(resp, (), {"error": str(e), "is_captcha": False,
                                       "results": [], "total": 0,
                                       "page": self.current_page, "has_next": False})()
            self.after(0, lambda: self._on_search_done(resp))

        threading.Thread(target=worker, daemon=True).start()

    def _on_search_done(self, resp):
        self._stop_progress()
        self._searching = False
        self.search_btn.config(state=NORMAL)
        if resp.is_captcha:
            Messagebox.show_warning(
                "搜狗要求验证码",
                "搜索过于频繁，搜狗要求验证码。\n请稍等几分钟再试，或在浏览器中手动访问 weixin.sogou.com",
                parent=self,
            )
            self.on_status("搜索被验证码拦截")
            return
        if resp.error:
            self.on_status(f"搜索失败: {resp.error}")
            return

        self.search_response = resp
        self._search_results = resp.results
        self._populate_tree_search(resp.results)

        total = resp.total
        self.page_label.config(text=f"第{resp.page}页" + (f" / 共{total}条" if total else ""))
        self.prev_btn.config(state=NORMAL if resp.page > 1 else DISABLED)
        self.next_btn.config(state=NORMAL if resp.has_next else DISABLED)

        if not resp.results:
            self.on_status("未找到相关文章，试试其他关键词")
        else:
            self.on_status(f"搜索完成: {len(resp.results)} 条结果" +
                           (f" (共{total}条)" if total else ""))

    def _populate_tree_search(self, results):
        self.tree.delete(*self.tree.get_children())
        self._item_map.clear()
        # 获取已收藏的 URL 集合，用于标记
        collected_urls = set()
        try:
            for r in results:
                if r.link:
                    aid = self.db.get_article_by_url(r.link)
                    if aid:
                        collected_urls.add(r.link)
        except Exception:
            pass
        for i, r in enumerate(results):
            mark = "✅ " if r.link in collected_urls else ""
            iid = self.tree.insert("", END, values=(
                mark + r.title[:58], r.author, r.pub_date
            ), tags=("even" if i % 2 == 0 else "odd",))
            self._item_map[iid] = i
        self.count_label.config(text=f"共 {len(results)} 条")

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._search_page()

    def _next_page(self):
        if self.search_response and self.search_response.has_next:
            self.current_page += 1
            self._search_page()

    # ==================================================================
    #  收藏库模式
    # ==================================================================
    def show_collection(self, tag_id=None, read_filter=None, search=""):
        self.mode = self.MODE_COLLECTION
        self._set_buttons()
        self.page_label.config(text="")

        articles = self.db.list_articles(
            tag_id=tag_id, search=search, read_filter=read_filter,
            sort_by="collected_at", sort_desc=True,
        )
        self._collection_items = articles
        self._populate_tree_collection(articles)

        label = "全部" if tag_id is None and read_filter is None and not search else "筛选"
        self.on_status(f"收藏库 [{label}]: {len(articles)} 篇")

    def _populate_tree_collection(self, articles):
        self.tree.delete(*self.tree.get_children())
        self._item_map.clear()
        for i, a in enumerate(articles):
            read_mark = "" if a.get("is_read") else "●"
            iid = self.tree.insert("", END, values=(
                read_mark + a.get("title", "")[:60],
                a.get("author", ""),
                a.get("pub_date", "") or a.get("collected_at", "")[:10],
            ), tags=("even" if i % 2 == 0 else "odd",))
            self._item_map[iid] = i
        self.count_label.config(text=f"共 {len(articles)} 篇")

    # ==================================================================
    #  事件处理
    # ==================================================================
    def _on_double_click(self, event):
        """双击事件处理。"""
        if self.mode == self.MODE_SEARCH:
            # 搜索模式: 解析链接后在下方浏览器加载
            iid = self.tree.identify_row(event.y) or self.tree.focus()
            if iid and iid in self._item_map:
                idx = self._item_map[iid]
                r = self._search_results[idx]
                if r.link:
                    self._load_in_browser_resolved(r.link, r.title[:30])
                else:
                    self.on_status("该文章无链接")
            else:
                self.on_status("未识别到行")
        else:
            # 收藏库模式: 在下方浏览器加载
            indices = self._get_selected_indices()
            if indices:
                idx = indices[0]
                a = self._collection_items[idx]
                url = a.get("url", "")
                if url:
                    self._load_in_browser(url, a.get("title", "文章阅读")[:30])
                else:
                    self.on_status("该文章无链接")

    def _on_select(self, event):
        iid = self.tree.focus()
        if not iid or iid not in self._item_map:
            self.summary_var.set("")
            return
        idx = self._item_map[iid]
        if self.mode == self.MODE_SEARCH:
            r = self._search_results[idx]
            self.summary_var.set(r.summary[:200] if r.summary else "")
        else:
            a = self._collection_items[idx]
            summary = a.get("summary", "") or (a.get("content_text", "")[:200] if a.get("content_text") else "")
            self.summary_var.set(summary[:200])

    def _on_right_click(self, event):
        """右键上下文菜单。"""
        iid = self.tree.identify_row(event.y)
        if not iid or iid not in self._item_map:
            return
        # 选中右键的行
        self.tree.selection_set(iid)
        self.tree.focus(iid)

        menu = ttk.Menu(self, tearoff=False)
        if self.mode == self.MODE_SEARCH:
            menu.add_command(label="📥 收藏选中", command=self._collect_selected)
            menu.add_command(label="🔗 在浏览器打开", command=self._open_selected_in_browser)
        else:
            menu.add_command(label="📖 阅读", command=self._read_selected)
            menu.add_command(label="✏ 编辑标题", command=self._edit_title_selected)
            menu.add_command(label="🏷 编辑标签", command=self._edit_tags_selected)
            menu.add_command(label="🔗 在浏览器打开原文", command=self._open_selected_in_browser)
            menu.add_separator()
            menu.add_command(label="📤 导出选中", command=self._export_selected)
            menu.add_command(label="🗑 删除选中", command=self._delete_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def _open_selected_in_browser(self):
        """在下方浏览器面板中打开选中文章。"""
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选中一篇文章再点击打开")
            return
        if self.mode == self.MODE_SEARCH:
            for idx in indices:
                r = self._search_results[idx]
                if r.link:
                    self._load_in_browser_resolved(r.link, r.title[:30])
                    break
            else:
                self.on_status("该文章无链接")
        else:
            for idx in indices:
                a = self._collection_items[idx]
                url = a.get("url", "")
                if url:
                    self._load_in_browser(url, a.get("title", "文章阅读")[:30])
                    break
            else:
                self.on_status("该文章无链接")

    def _open_in_app_resolved(self, sogou_link, title):
        """解析搜狗链接获取微信真实链接和内容，然后应用内打开。"""
        self.on_status(f"正在解析链接: {title}...")

        def worker():
            try:
                art = self.fetcher.fetch(sogou_link)
                if art.success and art.content_html:
                    # 有全文 HTML，本地渲染
                    full_html = "<html><head><meta charset='utf-8'></head><body style='max-width:677px;margin:0 auto;padding:20px;font-family:sans-serif'>" + art.content_html + "</body></html>"
                    self.after(0, lambda: self._do_open_html(full_html, title))
                else:
                    # 无全文，用真实链接打开
                    real_url = art.real_url or sogou_link
                    self.after(0, lambda: self._do_open_in_app(real_url, title))
            except Exception:
                self.after(0, lambda: self._do_open_in_app(sogou_link, title))

        threading.Thread(target=worker, daemon=True).start()

    def _do_open_in_app(self, url, title):
        """在应用内打开 URL。"""
        ok = open_in_app(url, title, parent=self.winfo_toplevel())
        self.on_status("已在应用内打开" if ok else "打开失败")

    def _do_open_html(self, html, title):
        """在应用内渲染 HTML。"""
        ok = open_in_app("", title, parent=self.winfo_toplevel(), html_content=html)
        self.on_status("已在应用内打开" if ok else "打开失败")

    def _toggle_select_all(self):
        items = self.tree.get_children()
        if self.select_all_var.get():
            self.tree.selection_set(items)
        else:
            self.tree.selection_remove(items)

    def _get_selected_indices(self):
        """获取选中项索引，选中为空时回退到 focus 行。"""
        indices = [self._item_map[iid] for iid in self.tree.selection()
                   if iid in self._item_map]
        if not indices:
            # 回退: 使用 focus（最后点击的行）
            focus = self.tree.focus()
            if focus and focus in self._item_map:
                indices = [self._item_map[focus]]
        return indices

    # ---- 收藏 ----
    def _collect_selected(self):
        if self.mode != self.MODE_SEARCH:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要收藏的文章")
            return

        results = [self._search_results[i] for i in indices]

        def on_done(success, fail, dup):
            parts = []
            if success:
                parts.append(f"新增 {success} 篇")
            if dup:
                parts.append(f"更新 {dup} 篇")
            if fail:
                parts.append(f"失败 {fail} 篇")
            msg = "、".join(parts) if parts else "无操作"
            self.on_status(f"收藏完成: {msg}")
            # 刷新侧边栏和收藏库
            self.on_refresh()
            # 自动切换到收藏库视图
            self.show_collection()

        from gui.dialogs import CollectDialog
        CollectDialog(self.winfo_toplevel(), self.db, results,
                      fetcher=self.fetcher, on_done=on_done)

    # ---- 阅读 ----
    def _read_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要阅读的文章")
            return
        idx = indices[0]
        article = self.db.get_article(self._collection_items[idx]["id"])
        if article:
            ReaderWindow(self.winfo_toplevel(), article, self.db, self.on_status)

    # ---- 编辑标题 ----
    def _edit_title_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要编辑的文章")
            return
        idx = indices[0]
        aid = self._collection_items[idx]["id"]
        article = self.db.get_article(aid)
        old_title = article.get("title", "") if article else ""

        # 自定义标题编辑对话框
        win = ttk.Toplevel(self.winfo_toplevel())
        win.title("编辑标题")
        win.geometry("450x150")
        win.transient(self.winfo_toplevel())
        ttk.Label(win, text="✏ 编辑标题", font=("微软雅黑", 12, "bold")).pack(pady=10)
        title_var = ttk.StringVar(value=old_title)
        entry = ttk.Entry(win, textvariable=title_var, font=("微软雅黑", 11), width=50)
        entry.pack(padx=15, pady=5)
        entry.focus_set()
        entry.select_range(0, END)

        def save_title():
            new_title = title_var.get().strip()
            if new_title:
                self.db.update_article(aid, title=new_title)
                self.on_status("标题已更新")
                self.show_collection()
            win.destroy()

        entry.bind("<Return>", lambda e: save_title())
        ttk.Button(win, text="保存", bootstyle=SUCCESS, command=save_title).pack(pady=5)
        from utils.helpers import center_on_parent
        center_on_parent(win, self.winfo_toplevel())
        win.grab_set()

    # ---- 编辑标签（批量） ----
    def _edit_tags_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要编辑标签的文章")
            return
        from gui.dialogs import TagEditDialog
        # 批量模式：传入所有选中文章的 ID
        article_ids = [self._collection_items[idx]["id"] for idx in indices]
        TagEditDialog(self.winfo_toplevel(), self.db, article_ids,
                      on_done=lambda: (self.on_refresh(), self.show_collection()))

    # ---- 导出 ----
    def _export_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要导出的文章")
            return

        from utils.exporter import Exporter
        from tkinter import filedialog

        articles = []
        for idx in indices:
            a = self.db.get_article(self._collection_items[idx]["id"])
            if a:
                articles.append(a)

        filepath = filedialog.asksaveasfilename(
            parent=self,
            title="导出文章",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("HTML", "*.html"), ("全部文件", "*.*")],
        )
        if not filepath:
            return

        try:
            if filepath.endswith(".html"):
                Exporter.to_html(articles, filepath)
            else:
                Exporter.to_markdown(articles, filepath)
            self.on_status(f"已导出 {len(articles)} 篇到 {filepath}")
            Messagebox.show_info("导出成功", f"已导出 {len(articles)} 篇文章", parent=self)
        except Exception as e:
            Messagebox.show_error("导出失败", str(e), parent=self)

    # ---- 删除 ----
    def _delete_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要删除的文章")
            return

        confirm = Messagebox.yesno(
            "确认删除",
            f"确定要删除选中的 {len(indices)} 篇文章吗？此操作不可撤销。",
            parent=self,
        )
        if not confirm:
            return

        for idx in indices:
            self.db.delete_article(self._collection_items[idx]["id"])
        self.on_status(f"已删除 {len(indices)} 篇文章")
        self.on_refresh()
        self.show_collection()

    # ==================================================================
    #  辅助
    # ==================================================================
    def _set_buttons(self):
        """所有按钮始终启用，靠方法内模式检查防止误操作。"""
        pass

    def _start_progress(self):
        self.progress.pack(side=LEFT, padx=8, before=self.count_label)
        self.progress.start(10)

    def _stop_progress(self):
        self.progress.stop()
        self.progress.pack_forget()
