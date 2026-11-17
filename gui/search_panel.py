"""
搜索面板 —— 搜索栏 + 结果列表 + 操作按钮。
支持两种模式：搜索模式（搜狗结果）和收藏库模式（本地文章）。
"""

import os
import subprocess
import threading
import webbrowser

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

from core.searcher import Searcher
from core.fetcher import Fetcher
from gui.reader_window import ReaderWindow


def open_url(url):
    """可靠地在默认浏览器中打开 URL（Windows 优先用 os.startfile）。"""
    try:
        if os.name == "nt":
            os.startfile(url)
            return True
        else:
            webbrowser.open(url)
            return True
    except Exception:
        try:
            return webbrowser.open(url)
        except Exception:
            return False


class SearchPanel(ttk.Frame):
    """搜索 + 结果列表面板。"""

    MODE_SEARCH = "search"
    MODE_COLLECTION = "collection"

    def __init__(self, parent, db, on_status=None, on_refresh=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.db = db
        self.on_status = on_status or (lambda t: None)
        self.on_refresh = on_refresh or (lambda: None)
        self.searcher = Searcher()
        self.fetcher = Fetcher(self.searcher.http)

        self.mode = self.MODE_COLLECTION
        self.current_keyword = ""
        self.current_page = 1
        self.search_response = None
        self._search_results = []      # list[SearchResult]
        self._collection_items = []    # list[dict]
        self._item_map = {}            # tree iid -> data index

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
        self.keyword_var = ttk.StringVar()
        entry = ttk.Entry(search_frame, textvariable=self.keyword_var,
                          font=("微软雅黑", 11), width=40)
        entry.pack(side=LEFT, padx=4, fill=X, expand=True)
        entry.bind("<Return>", lambda e: self.do_search())

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

        # ---- 结果列表 ----
        list_frame = ttk.Frame(self)
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
        summary_label = ttk.Label(self, textvariable=self.summary_var,
                                  font=("微软雅黑", 9), bootstyle=SECONDARY,
                                  wraplength=700, justify=LEFT)
        summary_label.pack(fill=X, padx=12, pady=(0, 4))

        # ---- 操作按钮栏 ----
        btn_frame = ttk.Frame(self)
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
        # 不常驻，按需 pack

    # ==================================================================
    #  搜索模式
    # ==================================================================
    def do_search(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            self.on_status("请输入搜索关键词")
            return
        self.current_keyword = keyword
        self.current_page = 1
        self._search_page()

    def _search_page(self):
        self.mode = self.MODE_SEARCH
        self._set_buttons()
        self.on_status(f"正在搜索「{self.current_keyword}」第 {self.current_page} 页...")
        self._start_progress()

        def worker():
            resp = self.searcher.search(self.current_keyword, page=self.current_page)
            self.after(0, lambda: self._on_search_done(resp))

        threading.Thread(target=worker, daemon=True).start()

    def _on_search_done(self, resp):
        self._stop_progress()
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

        self.on_status(f"搜索完成: {len(resp.results)} 条结果" +
                       (f" (共{total}条)" if total else ""))

    def _populate_tree_search(self, results):
        self.tree.delete(*self.tree.get_children())
        self._item_map.clear()
        for i, r in enumerate(results):
            iid = self.tree.insert("", END, values=(
                r.title[:60], r.author, r.pub_date
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
            # 搜索模式: 在浏览器打开
            iid = self.tree.identify_row(event.y) or self.tree.focus()
            if iid and iid in self._item_map:
                idx = self._item_map[iid]
                r = self._search_results[idx]
                if r.link:
                    self.on_status(f"正在打开: {r.title[:30]}...")
                    ok = open_url(r.link)
                    self.on_status("已在浏览器打开" if ok else "打开失败")
                else:
                    self.on_status("该文章无链接")
            else:
                self.on_status("未识别到行")
        else:
            # 收藏库模式: 打开阅读窗口
            self._read_selected()

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
            menu.add_command(label="🏷 编辑标签", command=self._edit_tags_selected)
            menu.add_command(label="🔗 在浏览器打开原文", command=self._open_selected_in_browser)
            menu.add_separator()
            menu.add_command(label="📤 导出选中", command=self._export_selected)
            menu.add_command(label="🗑 删除选中", command=self._delete_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def _open_selected_in_browser(self):
        """在浏览器中打开选中文章的链接。"""
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选中一篇文章再点击打开")
            return
        if self.mode == self.MODE_SEARCH:
            for idx in indices:
                r = self._search_results[idx]
                if r.link:
                    self.on_status(f"正在打开: {r.title[:30]}...")
                    ok = open_url(r.link)
                    self.on_status("已在浏览器打开" if ok else "打开失败")
                    break  # 只打开第一个
            else:
                self.on_status("该文章无链接")
        else:
            for idx in indices:
                a = self._collection_items[idx]
                url = a.get("url", "")
                if url:
                    self.on_status(f"正在打开: {a.get('title','')[:30]}...")
                    ok = open_url(url)
                    self.on_status("已在浏览器打开" if ok else "打开失败")
                    self.on_status("已在浏览器打开")
                    break
            else:
                self.on_status("该文章无链接")

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
        CollectDialog(self.winfo_toplevel(), self.db, results, on_done=on_done)

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

    # ---- 编辑标签 ----
    def _edit_tags_selected(self):
        if self.mode != self.MODE_COLLECTION:
            return
        indices = self._get_selected_indices()
        if not indices:
            self.on_status("请先选择要编辑标签的文章")
            return
        from gui.dialogs import TagEditDialog
        for idx in indices:
            aid = self._collection_items[idx]["id"]
            TagEditDialog(self.winfo_toplevel(), self.db, aid,
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
        """根据模式显示/隐藏按钮。"""
        # 先全部隐藏
        self.collect_btn.pack_forget()
        self.open_btn.pack_forget()
        self.read_btn.pack_forget()
        self.export_btn.pack_forget()
        self.delete_btn.pack_forget()
        if self.mode == self.MODE_SEARCH:
            self.collect_btn.pack(side=LEFT, padx=4)
            self.open_btn.pack(side=LEFT, padx=4)
        else:
            self.open_btn.pack(side=LEFT, padx=4)
            self.read_btn.pack(side=LEFT, padx=4)
            self.export_btn.pack(side=LEFT, padx=4)
            self.delete_btn.pack(side=LEFT, padx=4)

    def _start_progress(self):
        self.progress.pack(side=LEFT, padx=8, before=self.count_label)
        self.progress.start(10)

    def _stop_progress(self):
        self.progress.stop()
        self.progress.pack_forget()
