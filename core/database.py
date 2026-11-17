"""
SQLite 数据层 —— 文章收藏、标签管理、全文搜索(FTS5)。
零外部依赖，单文件数据库。
"""

import os
import sqlite3
import threading
from datetime import datetime

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    author        TEXT,
    account_id    TEXT,
    summary       TEXT,
    content       TEXT,
    content_text  TEXT,
    url           TEXT,
    cover_img     TEXT,
    pub_date      TEXT,
    collected_at  TEXT NOT NULL,
    is_read       INTEGER DEFAULT 0,
    note          TEXT
);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id INTEGER NOT NULL,
    tag_id     INTEGER NOT NULL,
    PRIMARY KEY (article_id, tag_id),
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)     REFERENCES tags(id)     ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_articles_author ON articles(author);
CREATE INDEX IF NOT EXISTS idx_articles_collected ON articles(collected_at);
CREATE INDEX IF NOT EXISTS idx_article_tags_tag ON article_tags(tag_id);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title, content_text, author,
    content='articles', content_rowid='id',
    tokenize='trigram'
);
"""

FTS_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, content_text, author)
    VALUES (new.id, new.title, new.content_text, new.author);
END;
CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, content_text, author)
    VALUES ('delete', old.id, old.title, old.content_text, old.author);
END;
CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, content_text, author)
    VALUES ('delete', old.id, old.title, old.content_text, old.author);
    INSERT INTO articles_fts(rowid, title, content_text, author)
    VALUES (new.id, new.title, new.content_text, new.author);
END;
"""


class Database:
    """文章收藏数据库管理器。"""

    def __init__(self, db_path="articles.db"):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self):
        cur = self._conn.cursor()
        cur.executescript(SCHEMA_SQL)
        # FTS5 可能在不支持的 SQLite 版本上报错，单独 try
        try:
            cur.executescript(FTS_SQL)
            cur.executescript(FTS_TRIGGERS)
        except sqlite3.OperationalError:
            pass  # FTS5 不可用时静默降级，仍可用 LIKE 搜索
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ==================================================================
    #  文章 CRUD
    # ==================================================================
    def add_article(self, title, author="", account_id="", summary="",
                    content="", content_text="", url="", cover_img="",
                    pub_date="", note=""):
        """插入一篇文章，返回新 id。若 url 已存在则更新并返回已有 id。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            # 原子操作：查重 + 插入/更新
            if url:
                row = self._conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (url,)
                ).fetchone()
                if row:
                    self._conn.execute(
                        """UPDATE articles SET title=?, author=?, account_id=?,
                           summary=?, content=?, content_text=?, cover_img=?,
                           pub_date=?, note=?
                           WHERE id=?""",
                        (title, author, account_id, summary, content,
                         content_text, cover_img, pub_date, note, row["id"]),
                    )
                    self._conn.commit()
                    return row["id"]
            cur = self._conn.execute(
                """INSERT INTO articles
                   (title, author, account_id, summary, content, content_text,
                    url, cover_img, pub_date, collected_at, note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (title, author, account_id, summary, content, content_text,
                 url, cover_img, pub_date, now, note),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_article_by_url(self, url):
        """按 URL 查询文章是否存在，返回 id 或 None。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM articles WHERE url=?", (url,)
            ).fetchone()
            return row["id"] if row else None

    def get_article(self, article_id):
        """获取单篇文章（含标签名列表）。"""
        row = self._conn.execute(
            "SELECT * FROM articles WHERE id=?", (article_id,)
        ).fetchone()
        if not row:
            return None
        article = dict(row)
        article["tags"] = self.get_article_tags(article_id)
        return article

    def update_article(self, article_id, **fields):
        """更新文章指定字段。"""
        allowed = {"title", "author", "summary", "content", "content_text",
                   "url", "cover_img", "pub_date", "is_read", "note"}
        sets, vals = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(article_id)
        self._conn.execute(
            f"UPDATE articles SET {', '.join(sets)} WHERE id=?", vals
        )
        self._conn.commit()

    def delete_article(self, article_id):
        """删除文章（显式清理标签关联 + FTS 索引）。"""
        with self._lock:
            self._conn.execute("DELETE FROM article_tags WHERE article_id=?", (article_id,))
            self._conn.execute("DELETE FROM articles WHERE id=?", (article_id,))
            self._conn.commit()

    def list_articles(self, tag_id=None, search="", read_filter=None,
                      sort_by="collected_at", sort_desc=True, limit=500):
        """
        列出已收藏文章。
        - tag_id: 按标签筛选
        - search: 在标题/作者/摘要中模糊搜索
        - read_filter: None=全部, True=已读, False=未读
        - sort_by: collected_at / title / author / pub_date
        """
        sql = "SELECT DISTINCT a.* FROM articles a"
        params = []
        joins = []
        wheres = []
        if tag_id is not None:
            joins.append("JOIN article_tags at ON at.article_id = a.id")
            wheres.append("at.tag_id = ?")
            params.append(tag_id)
        if search:
            esc = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            kw = f"%{esc}%"
            wheres.append(
                "(a.title LIKE ? ESCAPE '\\' OR a.author LIKE ? ESCAPE '\\' "
                "OR a.summary LIKE ? ESCAPE '\\')")
            params.extend([kw, kw, kw])
        if read_filter is not None:
            wheres.append("a.is_read = ?")
            params.append(1 if read_filter else 0)
        if joins:
            sql += " " + " ".join(joins)
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        # 排序
        valid_sorts = {"collected_at", "title", "author", "pub_date"}
        sb = sort_by if sort_by in valid_sorts else "collected_at"
        sql += f" ORDER BY a.{sb} {'DESC' if sort_desc else 'ASC'}"
        sql += f" LIMIT {int(limit)}"
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_articles(self):
        return self._conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def fulltext_search(self, query):
        """
        FTS5 全文搜索，返回匹配文章列表。
        trigram tokenizer 需要 ≥3 字符；短查询降级为 LIKE。
        """
        if len(query) < 3:
            return self.list_articles(search=query)
        try:
            rows = self._conn.execute(
                """SELECT a.* FROM articles_fts f
                   JOIN articles a ON a.id = f.rowid
                   WHERE articles_fts MATCH ?
                   ORDER BY rank""",
                (query,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return self.list_articles(search=query)

    # ==================================================================
    #  标签管理
    # ==================================================================
    def add_tag(self, name):
        """添加标签，返回 tag_id。已存在则返回已有 id。"""
        name = name.strip()
        if not name:
            return None
        row = self._conn.execute(
            "SELECT id FROM tags WHERE name=?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cur = self._conn.execute("INSERT INTO tags(name) VALUES(?)", (name,))
        self._conn.commit()
        return cur.lastrowid

    def delete_tag(self, tag_id):
        self._conn.execute("DELETE FROM tags WHERE id=?", (tag_id,))
        self._conn.commit()

    def list_tags(self):
        """返回 [(id, name, count), ...] 按名称排序。"""
        rows = self._conn.execute(
            """SELECT t.id, t.name,
               (SELECT COUNT(*) FROM article_tags at WHERE at.tag_id=t.id) AS cnt
               FROM tags t ORDER BY t.name"""
        ).fetchall()
        return [dict(r) for r in rows]

    def set_article_tags(self, article_id, tag_names):
        """替换文章的所有标签（原子操作）。"""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "DELETE FROM article_tags WHERE article_id=?", (article_id,)
                )
                for name in tag_names:
                    tid = self.add_tag(name)
                    if tid:
                        self._conn.execute(
                            "INSERT OR IGNORE INTO article_tags(article_id, tag_id) VALUES(?,?)",
                            (article_id, tid),
                        )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def rename_tag(self, tag_id, new_name):
        """重命名标签。"""
        with self._lock:
            self._conn.execute("UPDATE tags SET name=? WHERE id=?", (new_name, tag_id))
            self._conn.commit()

    def get_article_tags(self, article_id):
        """返回文章的标签名列表。"""
        rows = self._conn.execute(
            """SELECT t.name FROM tags t
               JOIN article_tags at ON at.tag_id=t.id
               WHERE at.article_id=? ORDER BY t.name""",
            (article_id,),
        ).fetchall()
        return [r["name"] for r in rows]

    # ==================================================================
    #  统计
    # ==================================================================
    def stats(self):
        row = self._conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(is_read=0) AS unread,
                      SUM(is_read=1) AS read_cnt,
                      (SELECT COUNT(*) FROM tags) AS tags
               FROM articles"""
        ).fetchone()
        return {
            "total": row["total"] or 0,
            "unread": row["unread"] or 0,
            "read": row["read_cnt"] or 0,
            "tags": row["tags"] or 0,
        }
