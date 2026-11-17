"""
导出工具 —— 将已收藏文章导出为 Markdown / HTML 单文件。
"""

import os
import re
from datetime import datetime


class Exporter:
    """文章导出器。"""

    # ------------------------------------------------------------------
    @staticmethod
    def to_markdown(articles, filepath):
        """
        导出为 Markdown 文件。
        :param articles: list[dict] 文章记录
        :param filepath: 输出路径
        """
        lines = []
        lines.append(f"# 微信文章收藏导出\n")
        lines.append(f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 共 {len(articles)} 篇文章\n")
        lines.append("---\n")

        for i, art in enumerate(articles, 1):
            title = art.get("title", "无标题")
            author = art.get("author", "")
            pub_date = art.get("pub_date", "")
            collected = art.get("collected_at", "")
            url = art.get("url", "")
            summary = art.get("summary", "")
            content_text = art.get("content_text", "")
            tags = art.get("tags", [])
            note = art.get("note", "")

            lines.append(f"## {i}. {title}\n")
            meta_parts = []
            if author:
                meta_parts.append(f"公众号: **{author}**")
            if pub_date:
                meta_parts.append(f"发布: {pub_date}")
            if collected:
                meta_parts.append(f"收藏: {collected}")
            if tags:
                meta_parts.append(f"标签: {', '.join(tags)}")
            if meta_parts:
                lines.append(" | ".join(meta_parts) + "\n")
            if url:
                lines.append(f"原文链接: <{url}>\n")
            if note:
                lines.append(f"> 备注: {note}\n")
            if summary and not content_text:
                lines.append(f"**摘要**: {summary}\n")
            if content_text:
                lines.append(content_text + "\n")
            lines.append("---\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    # ------------------------------------------------------------------
    @staticmethod
    def to_html(articles, filepath):
        """
        导出为 HTML 单文件（含内联样式，可离线查看）。
        :param articles: list[dict] 文章记录
        :param filepath: 输出路径
        """
        cards = []
        for i, art in enumerate(articles, 1):
            title = _esc(art.get("title", "无标题"))
            author = _esc(art.get("author", ""))
            pub_date = _esc(art.get("pub_date", ""))
            url = art.get("url", "")
            summary = _esc(art.get("summary", ""))
            content_html = art.get("content", "")  # 原始 HTML
            content_text = _esc(art.get("content_text", ""))
            tags = art.get("tags", [])
            note = _esc(art.get("note", ""))
            cover = art.get("cover_img", "")

            meta = []
            if author:
                meta.append(f'<span class="meta-item">公众号: <b>{author}</b></span>')
            if pub_date:
                meta.append(f'<span class="meta-item">发布: {pub_date}</span>')
            if tags:
                tag_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
                meta.append(f'<span class="meta-item">标签: {tag_html}</span>')

            body = ""
            if content_html:
                body = content_html
            elif content_text:
                body = f'<div class="text-content">{content_text}</div>'
            elif summary:
                body = f'<div class="summary">摘要: {summary}</div>'

            cover_html = f'<img class="cover" src="{_esc(cover)}">' if cover else ""
            note_html = f'<div class="note">备注: {note}</div>' if note else ""
            link_html = f'<a class="source-link" href="{_esc(url)}" target="_blank">查看原文</a>' if url else ""

            cards.append(f"""
            <article class="article-card">
                <h2>{i}. {title}</h2>
                <div class="meta">{"".join(meta)}</div>
                {cover_html}
                {note_html}
                <div class="content">{body}</div>
                {link_html}
            </article>
            """)

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>微信文章收藏导出</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
       background: #f5f5f5; color: #333; line-height: 1.8; }}
.container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
h1 {{ text-align: center; margin: 20px 0 10px; color: #1a73e8; }}
.export-info {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 14px; }}
.article-card {{ background: #fff; border-radius: 8px; padding: 24px;
                 margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.article-card h2 {{ font-size: 20px; margin-bottom: 12px; color: #1a1a1a; }}
.meta {{ font-size: 13px; color: #888; margin-bottom: 16px; }}
.meta-item {{ margin-right: 16px; }}
.tag {{ display: inline-block; background: #e8f0fe; color: #1a73e8;
        padding: 2px 8px; border-radius: 4px; margin: 0 2px; font-size: 12px; }}
.cover {{ max-width: 100%; border-radius: 4px; margin: 12px 0; }}
.note {{ background: #fff8e1; padding: 8px 12px; border-radius: 4px;
         margin: 12px 0; font-size: 14px; color: #856404; }}
.content {{ margin-top: 16px; }}
.content img {{ max-width: 100%; border-radius: 4px; }}
.content p {{ margin-bottom: 12px; }}
.text-content {{ white-space: pre-wrap; }}
.summary {{ color: #666; font-style: italic; }}
.source-link {{ display: inline-block; margin-top: 16px; color: #1a73e8;
                text-decoration: none; font-size: 14px; }}
.source-link:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<div class="container">
    <h1>微信文章收藏导出</h1>
    <p class="export-info">导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 共 {len(articles)} 篇</p>
    {"".join(cards)}
</div>
</body>
</html>"""

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        return filepath


def _esc(text):
    """HTML 转义。"""
    if not text:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace('"', "&quot;").replace("'", "&#39;")
    return text
