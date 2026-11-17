"""
阅读窗口 —— 弹出窗口阅读已收藏文章全文。
支持纯文本阅读 + 打开原文链接 + 标记已读。
"""

import os
import subprocess
import threading
import webbrowser

import ttkbootstrap as ttk
from ttkbootstrap.constants import *


def open_url(url):
    """可靠地在默认浏览器中打开 URL。"""
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


class ReaderWindow:
    """文章阅读弹窗。"""

    def __init__(self, parent, article, db, on_status=None):
        """
        :param parent: 父窗口
        :param article: dict 文章记录
        :param db: Database 实例
        :param on_status: 状态栏回调 fn(text)
        """
        self.article = article
        self.db = db
        self.on_status = on_status or (lambda t: None)

        self.win = ttk.Toplevel(parent)
        self.win.title(article.get("title", "阅读")[:50])
        self.win.geometry("900x700")
        self.win.minsize(600, 400)

        self._build_ui()
        self._show_article()

        # 标记已读
        if not article.get("is_read"):
            self.db.update_article(article["id"], is_read=1)

        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_on_parent(parent)
        self.win.grab_set()

    def _center_on_parent(self, parent):
        """将窗口居中到父窗口。"""
        self.win.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.win.winfo_width()
            h = self.win.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            self.win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self.win, bootstyle=SECONDARY)
        toolbar.pack(fill=X, padx=10, pady=(10, 5))

        ttk.Button(toolbar, text="🔗 打开原文", bootstyle=INFO,
                   command=self._open_original).pack(side=LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="复制全文", bootstyle=(PRIMARY, OUTLINE),
                   command=self._copy_content).pack(side=LEFT, padx=5)

        self.note_var = ttk.StringVar(value=self.article.get("note", ""))
        ttk.Label(toolbar, text="备注:").pack(side=LEFT, padx=(10, 5))
        note_entry = ttk.Entry(toolbar, textvariable=self.note_var, width=30)
        note_entry.pack(side=LEFT, padx=5)
        ttk.Button(toolbar, text="保存备注", bootstyle=(SUCCESS, OUTLINE),
                   command=self._save_note).pack(side=LEFT, padx=5)

        # 标题
        title_frame = ttk.Frame(self.win)
        title_frame.pack(fill=X, padx=15, pady=(5, 2))
        ttk.Label(title_frame, text=self.article.get("title", "无标题"),
                  font=("微软雅黑", 16, "bold"), wraplength=850).pack(anchor=W)

        # 元信息
        meta_frame = ttk.Frame(self.win)
        meta_frame.pack(fill=X, padx=15, pady=(2, 8))
        meta_parts = []
        if self.article.get("author"):
            meta_parts.append(f"公众号: {self.article['author']}")
        if self.article.get("pub_date"):
            meta_parts.append(f"发布: {self.article['pub_date']}")
        if self.article.get("collected_at"):
            meta_parts.append(f"收藏: {self.article['collected_at']}")
        tags = self.article.get("tags", [])
        if tags:
            meta_parts.append(f"标签: {', '.join(tags)}")
        if meta_parts:
            ttk.Label(meta_frame, text="  |  ".join(meta_parts),
                      font=("微软雅黑", 9), bootstyle=SECONDARY).pack(anchor=W)

        # 分隔线
        ttk.Separator(self.win).pack(fill=X, padx=15, pady=5)

        # 正文区域
        self.text = ttk.ScrolledText(
            self.win, font=("微软雅黑", 11), wrap=WORD,
            bootstyle=LIGHT, padx=15, pady=10,
        )
        self.text.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))
        self.text.configure(state=DISABLED)

    # ------------------------------------------------------------------
    def _show_article(self):
        """显示文章内容。"""
        self.text.configure(state=NORMAL)
        self.text.delete("1.0", END)

        content = self.article.get("content_text", "")
        has_fulltext = bool(content)

        if has_fulltext:
            self.text.insert("1.0", content)
        else:
            # 无全文时显示摘要 + 提示
            summary = self.article.get("summary", "")
            url = self.article.get("url", "")
            self.text.insert(END, "【摘要】\n\n", "header")
            if summary:
                self.text.insert(END, summary + "\n\n", "body")
            self.text.insert(END, "─" * 40 + "\n\n", "sep")
            self.text.insert(END, "⚠ 未获取到文章全文（微信反爬限制）。\n", "warn")
            if url:
                self.text.insert(END, "请点击上方「打开原文」按钮，在浏览器中阅读完整文章。\n", "tip")
            self.text.tag_configure("header", font=("微软雅黑", 13, "bold"),
                                    foreground="#1a73e8")
            self.text.tag_configure("body", font=("微软雅黑", 11))
            self.text.tag_configure("sep", foreground="#ccc")
            self.text.tag_configure("warn", font=("微软雅黑", 11, "bold"),
                                    foreground="#e65100")
            self.text.tag_configure("tip", font=("微软雅黑", 11),
                                    foreground="#1a73e8")
        self.text.configure(state=DISABLED)

    # ------------------------------------------------------------------
    def _open_original(self):
        url = self.article.get("url", "")
        if url:
            ok = open_url(url)
            self.on_status("已打开原文链接" if ok else "打开失败")
        else:
            self.on_status("无原文链接")

    def _copy_content(self):
        content = self.article.get("content_text", "") or self.article.get("summary", "")
        if content:
            self.win.clipboard_clear()
            self.win.clipboard_append(content)
            self.on_status("全文已复制到剪贴板")

    def _save_note(self):
        note = self.note_var.get().strip()
        self.db.update_article(self.article["id"], note=note)
        self.on_status("备注已保存")

    def _on_close(self):
        self.win.grab_release()
        self.win.destroy()
