"""
应用配置管理 —— 设置、窗口状态、搜索历史的持久化。
"""

import json
import os

DEFAULT_CONFIG = {
    "theme": "litera",
    "window_geometry": "1100x700",
    "search_history": [],
    "request_min_interval": 2.0,
    "request_max_interval": 5.0,
    "timeout": 15,
    "proxy": "",
    "max_pages": 3,
    "retry_count": 3,
}


class Config:
    """应用配置单例。"""

    def __init__(self, path="config.json"):
        self.path = path
        self.data = dict(DEFAULT_CONFIG)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.data.update(saved)
            except Exception:
                pass

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default if default is not None
                             else DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ---- 搜索历史 ----
    def add_search_history(self, keyword):
        hist = self.data.get("search_history", [])
        if keyword in hist:
            hist.remove(keyword)
        hist.insert(0, keyword)
        self.data["search_history"] = hist[:20]
        self.save()

    def get_search_history(self):
        return self.data.get("search_history", [])
