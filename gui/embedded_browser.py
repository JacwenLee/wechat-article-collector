"""
嵌入式浏览器 —— 使用 pythonnet + WinForms WebBrowser 控件嵌入 tkinter。
支持完整交互（滚动、点击、JavaScript），不弹出独立窗口。
"""

import ctypes


def create_embedded_browser(parent_frame, url="about:blank"):
    """
    在 tkinter Frame 中嵌入 WinForms WebBrowser 控件。
    返回 (browser, form) 或 None（失败时）。
    """
    try:
        # 初始化 COM 为 STA 模式（WebBrowser 控件需要）
        ctypes.windll.ole32.OleInitialize(None)

        import clr
        clr.AddReference("System.Windows.Forms")
        clr.AddReference("System.Drawing")
        import System.Windows.Forms as WinForms
        import System.Drawing as Drawing
        import System.Threading as Threading

        # 确保当前线程在 STA 模式
        thread = Threading.Thread.CurrentThread
        if not thread.GetApartmentState() == Threading.ApartmentState.STA:
            thread.SetApartmentState(Threading.ApartmentState.STA)

        # 创建无边框 WinForms Form 作为容器
        form = WinForms.Form()
        form.FormBorderStyle = getattr(WinForms.FormBorderStyle, "None")
        form.TopLevel = False
        form.ShowInTaskbar = False

        # 创建 WebBrowser 控件
        browser = WinForms.WebBrowser()
        browser.Dock = WinForms.DockStyle.Fill
        form.Controls.Add(browser)

        # 将 WinForms Form 嵌入 tkinter Frame
        tk_hwnd = parent_frame.winfo_id()
        ctypes.windll.user32.SetParent(form.Handle.ToInt32(), tk_hwnd)

        # 设置大小并显示
        form.Width = parent_frame.winfo_width() or 800
        form.Height = parent_frame.winfo_height() or 400
        form.Show()

        # 导航到 URL
        if url and url != "about:blank":
            browser.Navigate(url)

        return browser, form

    except Exception as e:
        print(f"EmbeddedBrowser error: {e}", flush=True)
        return None


def resize_embedded(form, width, height):
    """调整嵌入的浏览器大小。"""
    try:
        if form:
            form.Width = width
            form.Height = height
    except Exception:
        pass
