"""
主窗口 —— 左侧标签树 + 右侧搜索面板 + 底部状态栏。
"""

import os

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox

from core.database import Database
from gui.search_panel import SearchPanel


class MainWindow:
    """微信文章收藏器主窗口。"""

    def __init__(self, db_path="articles.db"):
        self.db = Database(db_path)
        self.db_path = db_path

        self.root = ttk.Window(title="微信文章收藏器", themename="litera",
                               size=(1100, 700), minsize=(800, 500))
        self.root.place_window_center()

        self._build_menu()
        self._build_layout()
        self._refresh_sidebar()
        self._update_status("就绪")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================================================================
    #  菜单栏
    # ==================================================================
    def _build_menu(self):
        menubar = ttk.Menu(self.root)

        file_menu = ttk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="导出全部 (Markdown)", command=self._export_all_md)
        file_menu.add_command(label="导出全部 (HTML)", command=self._export_all_html)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self._on_close)
        menubar.add_cascade(label="文件", menu=file_menu)

        tag_menu = ttk.Menu(menubar, tearoff=False)
        tag_menu.add_command(label="新建标签", command=self._new_tag)
        tag_menu.add_command(label="管理标签", command=self._manage_tags)
        menubar.add_cascade(label="标签", menu=tag_menu)

        help_menu = ttk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.configure(menu=menubar)

    # ==================================================================
    #  布局
    # ==================================================================
    def _build_layout(self):
        # ---- 底部状态栏 (先创建，搜索面板初始化时会调用) ----
        status_frame = ttk.Frame(self.root, bootstyle=SECONDARY)
        status_frame.pack(fill=X, side=BOTTOM)
        self.status_var = ttk.StringVar(value="就绪")
        ttk.Label(status_frame, textvariable=self.status_var,
                  bootstyle=INVERSE, anchor=W).pack(fill=X, padx=8, ipady=4)

        # 主容器
        main_paned = ttk.Panedwindow(self.root, orient=HORIZONTAL)
        main_paned.pack(fill=BOTH, expand=True, padx=4, pady=4)

        # ---- 左侧边栏 ----
        sidebar = ttk.Frame(main_paned, bootstyle=LIGHT, width=200)
        sidebar.pack_propagate(False)
        main_paned.add(sidebar, weight=0)

        ttk.Label(sidebar, text="📚 我的收藏", font=("微软雅黑", 12, "bold"),
                  bootstyle=INVERSE, anchor=CENTER).pack(fill=X, ipady=8)

        # 导航 Treeview
        nav_frame = ttk.Frame(sidebar)
        nav_frame.pack(fill=BOTH, expand=True, padx=4, pady=4)

        self.nav_tree = ttk.Treeview(nav_frame, show="tree", bootstyle=LIGHT,
                                     selectmode=BROWSE)
        nav_scroll = ttk.Scrollbar(nav_frame, orient=VERTICAL,
                                   command=self.nav_tree.yview)
        self.nav_tree.configure(yscrollcommand=nav_scroll.set)
        self.nav_tree.pack(side=LEFT, fill=BOTH, expand=True)
        nav_scroll.pack(side=RIGHT, fill=Y)
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_nav_select)

        # 新标签按钮
        ttk.Button(sidebar, text="+ 新建标签", bootstyle=(SECONDARY, OUTLINE),
                   command=self._new_tag).pack(fill=X, padx=8, pady=(0, 8))

        # ---- 右侧搜索面板 ----
        self.search_panel = SearchPanel(
            main_paned, self.db,
            on_status=self._update_status,
            on_refresh=self._refresh_sidebar,
        )
        main_paned.add(self.search_panel, weight=1)

    # ==================================================================
    #  侧边栏导航
    # ==================================================================
    def _refresh_sidebar(self):
        self.nav_tree.delete(*self.nav_tree.get_children())

        # 固定分类
        all_id = self.nav_tree.insert("", END, text="📋 全部", open=True,
                                      tags=("all",))
        self.nav_tree.insert(all_id, END, text="🔔 未读", tags=("unread",))
        self.nav_tree.insert(all_id, END, text="✅ 已读", tags=("read",))

        # 标签分类
        tags = self.db.list_tags()
        if tags:
            tag_root = self.nav_tree.insert("", END, text="🏷 标签", open=True,
                                            tags=("tag_root",))
            for t in tags:
                self.nav_tree.insert(tag_root, END,
                                     text=f"{t['name']} ({t['cnt']})",
                                     tags=("tag", str(t["id"])))

        self.nav_tree.selection_set(all_id)

    def _on_nav_select(self, event):
        sel = self.nav_tree.selection()
        if not sel:
            return
        item = sel[0]
        tags = self.nav_tree.item(item, "tags")
        if not tags:
            return

        tag_type = tags[0]
        if tag_type == "all":
            self.search_panel.show_collection()
        elif tag_type == "unread":
            self.search_panel.show_collection(read_filter=False)
        elif tag_type == "read":
            self.search_panel.show_collection(read_filter=True)
        elif tag_type == "tag":
            tag_id = int(tags[1])
            self.search_panel.show_collection(tag_id=tag_id)

    # ==================================================================
    #  标签管理
    # ==================================================================
    def _new_tag(self):
        from gui.dialogs import NewTagDialog

        def on_done(created):
            self._refresh_sidebar()
            self._update_status(f"已创建标签: {', '.join(created)}")

        NewTagDialog(self.root, self.db, on_done=on_done)

    def _manage_tags(self):
        tags = self.db.list_tags()

        win = ttk.Toplevel(self.root)
        win.title("管理标签")
        win.geometry("420x480")
        win.transient(self.root)

        ttk.Label(win, text="🏷 标签管理",
                  font=("微软雅黑", 14, "bold")).pack(pady=(15, 5))

        list_frame = ttk.Frame(win)
        list_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        listbox = ttk.Treeview(list_frame, columns=("count",), show="tree headings",
                               bootstyle=LIGHT)
        listbox.heading("#0", text="标签名")
        listbox.heading("count", text="文章数")
        listbox.column("#0", width=200)
        listbox.column("count", width=80, anchor=CENTER)
        sb = ttk.Scrollbar(list_frame, orient=VERTICAL, command=listbox.yview)
        listbox.configure(yscrollcommand=sb.set)
        listbox.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        def refresh_list():
            listbox.delete(*listbox.get_children())
            for t in self.db.list_tags():
                listbox.insert("", END, text=t["name"],
                               values=(t["cnt"],), tags=(str(t["id"]),))

        refresh_list()

        def rename_tag():
            sel = listbox.selection()
            if not sel:
                return
            tid = int(listbox.item(sel[0], "tags")[0])
            old_name = listbox.item(sel[0], "text")
            from ttkbootstrap.dialogs import QueryDialog
            new_name = QueryDialog.get_string(
                "重命名标签", f"将标签「{old_name}」重命名为:", parent=win,
            )
            if new_name and new_name.strip():
                new_name = new_name.strip()
                try:
                    self.db._conn.execute(
                        "UPDATE tags SET name=? WHERE id=?", (new_name, tid)
                    )
                    self.db._conn.commit()
                    refresh_list()
                    self._refresh_sidebar()
                except Exception:
                    Messagebox.show_error("错误", "标签名已存在或无效", parent=win)

        def delete_tag():
            sel = listbox.selection()
            if not sel:
                return
            tid = int(listbox.item(sel[0], "tags")[0])
            tname = listbox.item(sel[0], "text")
            if Messagebox.yesno("确认", f"删除标签「{tname}」？\n文章不会被删除，仅移除标签关联。", parent=win):
                self.db.delete_tag(tid)
                refresh_list()
                self._refresh_sidebar()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="重命名", bootstyle=(INFO, OUTLINE),
                   command=rename_tag).pack(side=LEFT, padx=4)
        ttk.Button(btn_frame, text="删除", bootstyle=(DANGER, OUTLINE),
                   command=delete_tag).pack(side=LEFT, padx=4)
        ttk.Button(btn_frame, text="关闭", bootstyle=SECONDARY,
                   command=win.destroy).pack(side=RIGHT, padx=4)

        # 居中到主窗口
        win.update_idletasks()
        try:
            px = self.root.winfo_rootx()
            py = self.root.winfo_rooty()
            pw = self.root.winfo_width()
            ph = self.root.winfo_height()
            w = win.winfo_width()
            h = win.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

        win.grab_set()

    # ==================================================================
    #  导出
    # ==================================================================
    def _export_all_md(self):
        from utils.exporter import Exporter
        from tkinter import filedialog
        articles = self.db.list_articles(limit=10000)
        if not articles:
            Messagebox.show_info("导出", "收藏库为空，无可导出内容。", parent=self.root)
            return
        full = [self.db.get_article(a["id"]) for a in articles]
        filepath = filedialog.asksaveasfilename(
            parent=self.root, title="导出全部为 Markdown",
            defaultextension=".md", filetypes=[("Markdown", "*.md")],
            initialfile="微信文章收藏.md",
        )
        if filepath:
            Exporter.to_markdown(full, filepath)
            self._update_status(f"已导出 {len(full)} 篇到 {filepath}")

    def _export_all_html(self):
        from utils.exporter import Exporter
        from tkinter import filedialog
        articles = self.db.list_articles(limit=10000)
        if not articles:
            Messagebox.show_info("导出", "收藏库为空，无可导出内容。", parent=self.root)
            return
        full = [self.db.get_article(a["id"]) for a in articles]
        filepath = filedialog.asksaveasfilename(
            parent=self.root, title="导出全部为 HTML",
            defaultextension=".html", filetypes=[("HTML", "*.html")],
            initialfile="微信文章收藏.html",
        )
        if filepath:
            Exporter.to_html(full, filepath)
            self._update_status(f"已导出 {len(full)} 篇到 {filepath}")

    # ==================================================================
    #  关于
    # ==================================================================
    def _show_about(self):
        Messagebox.show_info(
            "关于",
            "微信文章收藏器 v1.0\n\n"
            "通过搜狗微信搜索 (weixin.sogou.com) 搜索公众号文章，\n"
            "支持一键收藏全文、标签管理、本地搜索、导出 Markdown/HTML。\n\n"
            "数据存储: SQLite (articles.db)\n"
            "GUI: Tkinter + ttkbootstrap",
            parent=self.root,
        )

    # ==================================================================
    #  状态栏 & 生命周期
    # ==================================================================
    def _update_status(self, text):
        stats = self.db.stats()
        self.status_var.set(f"{text}  |  收藏库: {stats['total']}篇 "
                            f"(未读{stats['unread']}/已读{stats['read']}) "
                            f"|  标签: {stats['tags']}个")

    def _on_close(self):
        self.db.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
