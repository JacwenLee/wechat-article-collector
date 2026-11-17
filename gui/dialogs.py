"""
自定义对话框 —— 收藏对话框、标签编辑对话框、新建标签对话框。
"""

import threading

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox


def center_on_parent(win, parent):
    """将 Toplevel 窗口居中到父窗口。"""
    win.update_idletasks()
    try:
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        w = win.winfo_width()
        h = win.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        pass


class CollectDialog:
    """
    收藏对话框 —— 选择标签 + 显示进度 + 逐篇状态。
    """

    def __init__(self, parent, db, results, fetcher=None, on_done=None):
        """
        :param parent: 父窗口
        :param db: Database 实例
        :param results: list[SearchResult] 待收藏文章
        :param fetcher: 共享的 Fetcher 实例（复用 HTTP 会话和限速）
        :param on_done: 完成回调 fn(success, fail, dup)
        """
        self.db = db
        self.results = results
        self.fetcher = fetcher
        self.on_done = on_done
        self.selected_tags = []

        self.win = ttk.Toplevel(parent)
        self.win.title("收藏文章")
        self.win.geometry("520x560")
        self.win.minsize(420, 400)
        self.win.transient(parent)

        self._build_ui()
        center_on_parent(self.win, parent)
        self.win.grab_set()
        self.win.wait_window()

    # ------------------------------------------------------------------
    def _build_ui(self):
        # 标题
        ttk.Label(self.win, text=f"📥 收藏 {len(self.results)} 篇文章",
                  font=("微软雅黑", 14, "bold")).pack(pady=(15, 5))

        # ---- 标签选择区 ----
        tag_frame = ttk.Labelframe(self.win, text="选择标签（可选）", padding=10)
        tag_frame.pack(fill=X, padx=15, pady=5)

        # 现有标签
        existing_tags = self.db.list_tags()
        self.tag_vars = {}
        self.tag_inner = ttk.Frame(tag_frame)
        self.tag_inner.pack(fill=X)
        if existing_tags:
            for i, t in enumerate(existing_tags):
                var = ttk.BooleanVar(value=False)
                self.tag_vars[t["name"]] = var
                cb = ttk.Checkbutton(self.tag_inner, text=f"{t['name']} ({t['cnt']})",
                                     variable=var, bootstyle=PRIMARY)
                cb.grid(row=i // 4, column=i % 4, sticky=W, padx=3, pady=2)
        else:
            ttk.Label(self.tag_inner,
                      text="暂无标签，可在下方新建", bootstyle=SECONDARY).pack(anchor=W)

        # 新标签输入
        new_tag_frame = ttk.Frame(tag_frame)
        new_tag_frame.pack(fill=X, pady=(8, 0))
        ttk.Label(new_tag_frame, text="新建标签:").pack(side=LEFT)
        self.new_tag_var = ttk.StringVar()
        ttk.Entry(new_tag_var_frame := ttk.Frame(new_tag_frame),
                  textvariable=self.new_tag_var, width=20).pack(side=LEFT, padx=5)
        ttk.Button(new_tag_frame, text="添加", bootstyle=(SECONDARY, OUTLINE),
                   command=self._add_new_tag, width=6).pack(side=LEFT)
        self.new_tag_entry = new_tag_var_frame.winfo_children()[0]

        # 已选新标签展示
        self.new_tags_display = ttk.StringVar(value="")
        ttk.Label(tag_frame, textvariable=self.new_tags_display,
                  bootstyle=SUCCESS).pack(anchor=W, pady=(5, 0))

        # ---- 文章列表 + 进度 ----
        list_frame = ttk.Labelframe(self.win, text="收藏进度", padding=10)
        # 先 pack 底部固定区域，再 pack 中间可变区域

        # 进度条（底部）
        self.progress_bar = ttk.Progressbar(self.win, mode=DETERMINATE,
                                            maximum=len(self.results),
                                            bootstyle=SUCCESS)
        self.progress_bar.pack(side=BOTTOM, fill=X, padx=15, pady=(0, 5))

        # ---- 按钮（底部）----
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(side=BOTTOM, fill=X, padx=15, pady=(0, 10))
        self.collect_btn = ttk.Button(btn_frame, text="✅ 确认收藏",
                                      bootstyle=SUCCESS, command=self._start_collect)
        self.collect_btn.pack(side=LEFT, padx=5)
        self.close_btn = ttk.Button(btn_frame, text="关闭",
                                    bootstyle=SECONDARY, command=self._close)
        self.close_btn.pack(side=LEFT, padx=5)
        self.result_label = ttk.Label(btn_frame, text="", bootstyle=SECONDARY)
        self.result_label.pack(side=RIGHT, padx=10)

        # 列表（中间，填充剩余空间）
        list_frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        self.progress_tree = ttk.Treeview(list_frame,
                                          columns=("status",),
                                          show="tree headings",
                                          bootstyle=LIGHT)
        self.progress_tree.heading("#0", text="标题")
        self.progress_tree.heading("status", text="状态")
        self.progress_tree.column("#0", width=350)
        self.progress_tree.column("status", width=80, anchor=CENTER)
        sb = ttk.Scrollbar(list_frame, orient=VERTICAL,
                           command=self.progress_tree.yview)
        self.progress_tree.configure(yscrollcommand=sb.set)
        self.progress_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        for i, r in enumerate(self.results):
            self.progress_tree.insert("", END, iid=str(i),
                                      text=r.title[:50],
                                      values=("等待中",))

        # 状态标签
        self.progress_tree.tag_configure("ok", foreground="green")
        self.progress_tree.tag_configure("fail", foreground="red")
        self.progress_tree.tag_configure("dup", foreground="#e65100")

    # ------------------------------------------------------------------
    def _add_new_tag(self):
        name = self.new_tag_var.get().strip()
        if not name:
            return
        if name not in self.tag_vars:
            var = ttk.BooleanVar(value=True)
            self.tag_vars[name] = var
        else:
            self.tag_vars[name].set(True)
        self.new_tag_var.set("")
        self._rebuild_tag_checkboxes()
        self._update_new_tags_display()

    def _rebuild_tag_checkboxes(self):
        """重建标签勾选区，显示所有标签（含新增）。"""
        for child in self.tag_inner.winfo_children():
            child.destroy()
        all_names = list(self.tag_vars.keys())
        for i, name in enumerate(all_names):
            cb = ttk.Checkbutton(self.tag_inner, text=name,
                                 variable=self.tag_vars[name],
                                 bootstyle=PRIMARY)
            cb.grid(row=i // 4, column=i % 4, sticky=W, padx=3, pady=2)

    def _update_new_tags_display(self):
        tags = [n for n, v in self.tag_vars.items() if v.get()]
        if tags:
            self.new_tags_display.set("已选: " + ", ".join(tags))
        else:
            self.new_tags_display.set("")

    # ------------------------------------------------------------------
    def _start_collect(self):
        self.selected_tags = [n for n, v in self.tag_vars.items() if v.get()]
        self.collect_btn.config(state=DISABLED)

        def worker():
            success, fail, dup = 0, 0, 0
            for i, r in enumerate(self.results):
                # 更新状态
                self.win.after(0, lambda idx=i: self.progress_tree.item(
                    str(idx), values=("抓取中...",)))
                content_text = ""
                content_html = ""
                real_url = r.link
                try:
                    art = self.fetcher.fetch(r.link) if self.fetcher else None
                    if art and art.real_url:
                        real_url = art.real_url
                    if art and art.success:
                        content_text = art.content_text
                        content_html = art.content_html
                except Exception:
                    pass

                try:
                    # 检查是否已存在
                    existing = self.db._conn.execute(
                        "SELECT id FROM articles WHERE url=?", (real_url,)
                    ).fetchone()
                    aid = self.db.add_article(
                        title=r.title, author=r.author, summary=r.summary,
                        content=content_html, content_text=content_text,
                        url=real_url, cover_img=r.cover_img,
                        pub_date=r.pub_date,
                    )
                    # 分配标签
                    if self.selected_tags:
                        self.db.set_article_tags(aid, self.selected_tags)

                    if existing:
                        dup += 1
                        status = "已更新"
                        tag = "dup"
                    else:
                        success += 1
                        status = "✓ 成功"
                        tag = "ok"
                except Exception:
                    fail += 1
                    status = "✗ 失败"
                    tag = "fail"

                self.win.after(0, lambda idx=i, s=status, t=tag: (
                    self.progress_tree.item(str(idx), values=(s,), tags=(t,)),
                    self.progress_bar.step(1),
                ))

            # 完成
            self.win.after(0, lambda: self._on_done(success, fail, dup))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    def _on_done(self, success, fail, dup):
        self.collect_btn.config(state=NORMAL)
        parts = []
        if success:
            parts.append(f"新增 {success}")
        if dup:
            parts.append(f"更新 {dup}")
        if fail:
            parts.append(f"失败 {fail}")
        msg = "、".join(parts) if parts else "无操作"
        self.result_label.config(text=f"完成: {msg}")
        self.on_done and self.on_done(success, fail, dup)

    def _close(self):
        self.win.grab_release()
        self.win.destroy()


class TagEditDialog:
    """
    标签编辑对话框 —— 为已收藏文章添加/移除标签。
    """

    def __init__(self, parent, db, article_id, on_done=None):
        self.db = db
        self.article_id = article_id
        self.on_done = on_done

        article = db.get_article(article_id)
        title = article.get("title", "") if article else ""
        current_tags = set(article.get("tags", [])) if article else set()
        self.tag_vars = {}

        self.win = ttk.Toplevel(parent)
        self.win.title("编辑标签")
        self.win.geometry("400x450")
        self.win.transient(parent)

        ttk.Label(self.win, text="🏷 编辑标签",
                  font=("微软雅黑", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self.win, text=title[:40], bootstyle=SECONDARY,
                  font=("微软雅黑", 9)).pack(pady=(0, 10))

        frame = ttk.Labelframe(self.win, text="标签", padding=15)
        frame.pack(fill=BOTH, expand=True, padx=15, pady=5)

        # 标签勾选区（可重建）
        self.tag_area = ttk.Frame(frame)
        self.tag_area.pack(fill=BOTH, expand=True)

        # 新标签输入区（固定不重建）
        new_frame = ttk.Frame(frame)
        new_frame.pack(fill=X, side=BOTTOM, pady=(10, 0))
        ttk.Label(new_frame, text="新建:").pack(side=LEFT)
        self.new_tag_var = ttk.StringVar()
        entry = ttk.Entry(new_frame, textvariable=self.new_tag_var, width=15)
        entry.pack(side=LEFT, padx=5)
        entry.bind("<Return>", lambda e: self._add_tag())
        ttk.Button(new_frame, text="+ 添加", bootstyle=(SUCCESS, OUTLINE),
                   command=self._add_tag).pack(side=LEFT)

        # 初始化标签列表
        self._current_tags = current_tags
        self._rebuild_tag_area()

        # 按钮
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="✅ 保存", bootstyle=SUCCESS,
                   command=self._save).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", bootstyle=SECONDARY,
                   command=self.win.destroy).pack(side=LEFT, padx=5)

        center_on_parent(self.win, parent)
        self.win.grab_set()
        self.win.wait_window()

    def _rebuild_tag_area(self):
        """重建标签勾选区。"""
        for child in self.tag_area.winfo_children():
            child.destroy()
        all_tags = self.db.list_tags()
        if not all_tags and not self.tag_vars:
            ttk.Label(self.tag_area, text="暂无标签，请在下方新建",
                      bootstyle=SECONDARY).pack(anchor=W)
            return
        inner = ttk.Frame(self.tag_area)
        inner.pack(fill=X)
        # 合并已有标签和新添加的标签
        all_names = [t["name"] for t in all_tags]
        for name in list(self.tag_vars.keys()):
            if name not in all_names:
                all_names.append(name)
        cnt_map = {t["name"]: t["cnt"] for t in all_tags}
        for i, name in enumerate(sorted(all_names)):
            if name not in self.tag_vars:
                self.tag_vars[name] = ttk.BooleanVar(
                    value=name in self._current_tags
                )
            cb = ttk.Checkbutton(inner, text=f"{name} ({cnt_map.get(name, 0)})",
                                 variable=self.tag_vars[name], bootstyle=PRIMARY)
            cb.grid(row=i // 3, column=i % 3, sticky=W, padx=5, pady=3)

    def _add_tag(self):
        name = self.new_tag_var.get().strip()
        if not name:
            return
        if name not in self.tag_vars:
            self.tag_vars[name] = ttk.BooleanVar(value=True)
        else:
            self.tag_vars[name].set(True)
        self.new_tag_var.set("")
        self._rebuild_tag_area()

    def _save(self):
        tags = [n for n, v in self.tag_vars.items() if v.get()]
        self.db.set_article_tags(self.article_id, tags)
        if self.on_done:
            self.on_done()
        self.win.grab_release()
        self.win.destroy()


class NewTagDialog:
    """
    新建标签对话框 —— 支持批量创建、显示已有标签。
    """

    def __init__(self, parent, db, on_done=None):
        self.db = db
        self.on_done = on_done
        self.created = []

        self.win = ttk.Toplevel(parent)
        self.win.title("新建标签")
        self.win.geometry("380x420")
        self.win.transient(parent)

        ttk.Label(self.win, text="🏷 新建标签",
                  font=("微软雅黑", 14, "bold")).pack(pady=(15, 5))

        # 已有标签展示
        existing = db.list_tags()
        if existing:
            ex_frame = ttk.Labelframe(self.win, text="已有标签", padding=10)
            ex_frame.pack(fill=X, padx=15, pady=5)
            names = "  ".join(f"#{t['name']}" for t in existing)
            ttk.Label(ex_frame, text=names, bootstyle=SECONDARY,
                      wraplength=330, justify=LEFT).pack(anchor=W)

        # 输入区
        input_frame = ttk.Labelframe(self.win, text="输入标签名称", padding=10)
        input_frame.pack(fill=X, padx=15, pady=5)
        self.entry_var = ttk.StringVar()
        entry = ttk.Entry(input_frame, textvariable=self.entry_var,
                          font=("微软雅黑", 11))
        entry.pack(fill=X, side=LEFT, expand=True, padx=(0, 5))
        entry.bind("<Return>", lambda e: self._add())
        ttk.Button(input_frame, text="添加", bootstyle=(PRIMARY, OUTLINE),
                   command=self._add).pack(side=LEFT)

        # 已创建列表
        self.created_var = ttk.StringVar(value="提示: 输入标签名后按回车或点「添加」，可连续创建多个")
        ttk.Label(self.win, textvariable=self.created_var,
                  bootstyle=SUCCESS, wraplength=330,
                  justify=LEFT).pack(fill=X, padx=15, pady=5)

        # 按钮
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill=X, padx=15, pady=15)
        ttk.Button(btn_frame, text="✅ 创建并关闭", bootstyle=SUCCESS,
                   command=self._finish).pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", bootstyle=SECONDARY,
                   command=self.win.destroy).pack(side=LEFT, padx=5)

        entry.focus_set()
        center_on_parent(self.win, parent)
        self.win.grab_set()
        self.win.wait_window()

    def _add(self):
        name = self.entry_var.get().strip()
        if not name:
            return
        try:
            self.db.add_tag(name)
            self.created.append(name)
            self.entry_var.set("")
            self.created_var.set("已创建: " + ", ".join(self.created))
        except Exception:
            Messagebox.show_warning("提示", f"标签「{name}」已存在", parent=self.win)

    def _finish(self):
        # 自动提交输入框中未添加的内容
        name = self.entry_var.get().strip()
        if name:
            self._add()
        if self.created:
            if self.on_done:
                self.on_done(self.created)
        self.win.destroy()


class UrlCollectDialog:
    """
    输入链接收藏对话框 —— 粘贴微信文章链接，直接收藏。
    """

    def __init__(self, parent, db, fetcher=None, on_done=None):
        self.db = db
        self.fetcher = fetcher
        self.on_done = on_done
        self.selected_tags = []

        self.win = ttk.Toplevel(parent)
        self.win.title("输入链接收藏")
        self.win.geometry("500x520")
        self.win.transient(parent)

        ttk.Label(self.win, text="📋 输入链接收藏",
                  font=("微软雅黑", 14, "bold")).pack(pady=(15, 5))
        ttk.Label(self.win, text="粘贴微信文章链接或搜狗链接，自动抓取并收藏",
                  bootstyle=SECONDARY).pack(pady=(0, 10))

        # URL 输入区
        url_frame = ttk.Labelframe(self.win, text="文章链接", padding=10)
        url_frame.pack(fill=X, padx=15, pady=5)
        self.url_var = ttk.StringVar()
        url_entry = ttk.Entry(url_frame, textvariable=self.url_var,
                              font=("微软雅黑", 10), width=55)
        url_entry.pack(fill=X, side=LEFT, expand=True, padx=(0, 5))
        url_entry.bind("<Return>", lambda e: self._start())

        ttk.Button(url_frame, text="粘贴", bootstyle=(SECONDARY, OUTLINE),
                   command=self._paste_url).pack(side=LEFT)

        # 标题输入区（手动填写，抓取成功则自动覆盖）
        title_frame = ttk.Labelframe(self.win, text="文章标题（可选，抓取失败时手动填写）", padding=10)
        title_frame.pack(fill=X, padx=15, pady=5)
        self.title_var = ttk.StringVar()
        ttk.Entry(title_frame, textvariable=self.title_var,
                  font=("微软雅黑", 10), width=55).pack(fill=X)

        # 标签选择区
        tag_frame = ttk.Labelframe(self.win, text="选择标签（可选）", padding=10)
        tag_frame.pack(fill=X, padx=15, pady=5)

        existing_tags = self.db.list_tags()
        self.tag_vars = {}
        self.tag_inner = ttk.Frame(tag_frame)
        self.tag_inner.pack(fill=X)
        if existing_tags:
            for i, t in enumerate(existing_tags):
                var = ttk.BooleanVar(value=False)
                self.tag_vars[t["name"]] = var
                cb = ttk.Checkbutton(self.tag_inner, text=f"{t['name']} ({t['cnt']})",
                                     variable=var, bootstyle=PRIMARY)
                cb.grid(row=i // 4, column=i % 4, sticky=W, padx=3, pady=2)
        else:
            ttk.Label(self.tag_inner, text="暂无标签",
                      bootstyle=SECONDARY).pack(anchor=W)

        # 新标签输入
        new_tag_frame = ttk.Frame(tag_frame)
        new_tag_frame.pack(fill=X, pady=(8, 0))
        ttk.Label(new_tag_frame, text="新建标签:").pack(side=LEFT)
        self.new_tag_var = ttk.StringVar()
        ttk.Entry(new_tag_frame, textvariable=self.new_tag_var, width=18).pack(side=LEFT, padx=5)
        ttk.Button(new_tag_frame, text="添加", bootstyle=(SECONDARY, OUTLINE),
                   command=self._add_new_tag).pack(side=LEFT)

        # 状态区
        self.status_var = ttk.StringVar(value="")
        self.status_label = ttk.Label(self.win, textvariable=self.status_var,
                                      bootstyle=SECONDARY, wraplength=440)
        self.status_label.pack(fill=X, padx=15, pady=5)

        self.progress_bar = ttk.Progressbar(self.win, mode=INDETERMINATE,
                                            length=300, bootstyle=SUCCESS)

        # 按钮
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(side=BOTTOM, fill=X, padx=15, pady=15)
        self.collect_btn = ttk.Button(btn_frame, text="✅ 收藏",
                                      bootstyle=SUCCESS, command=self._start)
        self.collect_btn.pack(side=LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", bootstyle=SECONDARY,
                   command=self._close).pack(side=LEFT, padx=5)

        center_on_parent(self.win, parent)
        url_entry.focus_set()
        self.win.grab_set()
        self.win.wait_window()

    # ------------------------------------------------------------------
    def _paste_url(self):
        try:
            clipped = self.win.clipboard_get()
            self.url_var.set(clipped.strip())
        except Exception:
            self.status_var.set("剪贴板为空")

    def _add_new_tag(self):
        name = self.new_tag_var.get().strip()
        if not name:
            return
        if name not in self.tag_vars:
            self.tag_vars[name] = ttk.BooleanVar(value=True)
        else:
            self.tag_vars[name].set(True)
        self.new_tag_var.set("")
        for child in self.tag_inner.winfo_children():
            child.destroy()
        for i, (n, v) in enumerate(self.tag_vars.items()):
            cb = ttk.Checkbutton(self.tag_inner, text=n, variable=v, bootstyle=PRIMARY)
            cb.grid(row=i // 4, column=i % 4, sticky=W, padx=3, pady=2)

    # ------------------------------------------------------------------
    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            self.status_var.set("请输入文章链接")
            return
        if not url.startswith("http"):
            self.status_var.set("链接格式不正确，需以 http 开头")
            return

        self.selected_tags = [n for n, v in self.tag_vars.items() if v.get()]
        self.collect_btn.config(state=DISABLED)
        self.status_var.set("正在抓取文章...")
        self.progress_bar.pack(pady=5)
        self.progress_bar.start()

        def worker():
            try:
                from core.fetcher import Fetcher
                fetcher = self.fetcher or Fetcher()
                art = fetcher.fetch_by_url(url)

                if not art.success and not art.real_url:
                    self.win.after(0, lambda: self._on_fail(
                        art.error or "抓取失败，请检查链接是否正确"))
                    return

                # 用抓取到的信息收藏，标题优先用抓取的，其次用手动输入的
                manual_title = self.title_var.get().strip()
                title = art.title or manual_title or "未知标题"
                author = art.author or ""
                summary = ""
                content_html = art.content_html or ""
                content_text = art.content_text or ""
                real_url = art.real_url or url
                pub_date = art.pub_date or ""
                cover = art.cover_img or ""

                aid = self.db.add_article(
                    title=title, author=author, summary=summary,
                    content=content_html, content_text=content_text,
                    url=real_url, cover_img=cover, pub_date=pub_date,
                )
                if self.selected_tags:
                    self.db.set_article_tags(aid, self.selected_tags)

                has_text = bool(content_text)
                self.win.after(0, lambda: self._on_success(title, has_text))
            except Exception as e:
                self.win.after(0, lambda: self._on_fail(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_success(self, title, has_text):
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.collect_btn.config(state=NORMAL)
        msg = f"✅ 收藏成功: {title[:30]}"
        if not has_text:
            msg += "\n⚠ 未获取到全文（微信反爬限制），已保存链接，可点击「打开原文」在浏览器阅读"
        self.status_var.set(msg)
        if self.on_done:
            self.on_done()

    def _on_fail(self, error):
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.collect_btn.config(state=NORMAL)
        self.status_var.set(f"❌ 收藏失败: {error}")

    def _close(self):
        self.win.grab_release()
        self.win.destroy()
