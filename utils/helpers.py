"""
公共工具函数 —— 浏览器打开、窗口居中、HTML 清洗。
"""

import os
import re
import webbrowser


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


def sanitize_html(html):
    """清洗 HTML，移除 script/iframe/on* 属性，防止 XSS。"""
    if not html:
        return html
    # 移除 script 和 iframe 标签
    html = re.sub(r'<script[^>]*>.*?</script>', '', html,
                  flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html,
                  flags=re.IGNORECASE | re.DOTALL)
    # 移除 on* 事件属性
    html = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', html,
                  flags=re.IGNORECASE)
    return html
