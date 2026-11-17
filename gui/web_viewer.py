"""
应用内网页查看器 —— 使用 tkinterweb 在 tkinter 内渲染 HTML。
无需浏览器引擎，直接嵌入 tkinter 窗口。
"""

import threading
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from utils.helpers import center_on_parent, open_url


def open_html_in_app(html_content, title="文章阅读", parent=None):
    """在应用内渲染 HTML 内容（tkinterweb HtmlFrame）。"""
    win = ttk.Toplevel(parent) if parent else ttk.Toplevel()
    win.title(title[:50])
    win.geometry("800x650")
    win.minsize(500, 400)

    # 工具栏
    toolbar = ttk.Frame(win, bootstyle=SECONDARY)
    toolbar.pack(fill=X, padx=5, pady=5)
    ttk.Label(toolbar, text=title[:40], font=("微软雅黑", 11, "bold"),
              bootstyle=INVERSE).pack(side=LEFT, padx=10)

    # HTML 渲染区
    try:
        from tkinterweb import HtmlFrame
        html_frame = HtmlFrame(win, messages_enabled=False)
        html_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        html_frame.load_html(html_content)
    except Exception as e:
        # tkinterweb 不可用时降级为 Text
        text = ttk.ScrolledText(win, font=("微软雅黑", 11), wrap=WORD)
        text.pack(fill=BOTH, expand=True, padx=5, pady=5)
        text.insert("1.0", f"HTML 渲染器不可用: {e}\n\n原始内容:\n{html_content[:2000]}")

    if parent:
        center_on_parent(win, parent)
    win.focus_set()
    return True


def open_in_app(url, title="文章阅读", parent=None, html_content=None):
    """
    在应用内打开文章。
    有 HTML 内容时用 tkinterweb 渲染；无内容时直接浏览器打开。
    """
    if html_content:
        return open_html_in_app(html_content, title, parent)

    # 无 HTML 内容，直接浏览器打开（不弹框）
    return open_url(url)
