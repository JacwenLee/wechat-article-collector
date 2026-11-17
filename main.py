"""
微信文章收藏器 —— 入口
通过搜狗微信搜索 (weixin.sogou.com) 搜索公众号文章，支持收藏、标签管理、导出。
"""

import os
import sys


def main():
    # 确保工作目录为脚本所在目录（PyInstaller 打包后数据库创建在 exe 同目录）
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    db_path = os.path.join(base_dir, "articles.db")

    from gui.main_window import MainWindow
    app = MainWindow(db_path=db_path)
    app.run()


if __name__ == "__main__":
    main()
