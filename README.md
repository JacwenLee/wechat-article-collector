# 微信文章收藏器

> 通过[搜狗微信搜索](https://weixin.sogou.com/)搜索微信公众号文章，支持一键收藏、标签管理、全文阅读与导出的桌面工具。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🔍 **关键词搜索** | 调用搜狗微信搜索 (`weixin.sogou.com/weixin?type=2`)，支持翻页 |
| 📥 **一键收藏** | 选中文章 → 自动抓取微信真实链接 → 存入本地 SQLite 数据库 |
| 🏷 **标签管理** | 收藏时选择/新建标签，支持按标签筛选、编辑、重命名、删除 |
| 📖 **全文阅读** | 弹窗阅读已收藏文章，支持备注、复制全文、标记已读 |
| 🔗 **浏览器打开** | 双击或按钮在默认浏览器中打开原文 |
| 📤 **导出** | 导出为 Markdown 或 HTML 单文件（含样式，可离线查看） |
| 🔎 **本地搜索** | SQLite FTS5 全文搜索（trigram 分词，支持中文） |
| 🛡 **反爬策略** | 随机 UA 轮换、请求间隔 2-5 秒、Cookie 管理、验证码检测 |

## 🖥 界面布局

```
┌──────────────────────────────────────────────────────┐
│  微信文章收藏器                          [设置] [关于] │
├────────────┬─────────────────────────────────────────┤
│            │  🔍 [关键词输入框        ] [搜索]         │
│  📋 全部   │─────────────────────────────────────────│
│  🔔 未读   │  ┌──┬──────────────────────────────┐    │
│  ✅ 已读   │  │  │ 标题                公众号 日期 │    │
│  ─────── │  ├──┼──────────────────────────────┤    │
│  🏷 科技   │  │☑ │ AI大模型最新进展...  机器之心 11/16│    │
│  🏷 投资   │  │  │ 新能源行业深度报告...  财联社 11/15│    │
│  ─────── │  └──┴──────────────────────────────┘    │
│  + 新标签  │  [全选] [收藏] [打开] [导出] [删除]      │
├────────────┴─────────────────────────────────────────┤
│  状态栏: 就绪 | 收藏库: 23篇 (未读5/已读18) | 标签: 3个 │
└──────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Windows / macOS / Linux

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动应用

```bash
python main.py
```

首次运行会在程序同目录自动创建 `articles.db` 数据库文件。

## 📖 使用指南

### 搜索文章

1. 在顶部搜索框输入关键词（如「AI智能体」）
2. 点击「搜索」或按回车
3. 使用「上一页/下一页」翻页浏览更多结果

### 收藏文章

1. 在搜索结果中勾选一篇文章（或多篇）
2. 点击「📥 收藏选中」
3. 在弹出的收藏对话框中：
   - 勾选已有标签，或输入新标签名
   - 点击「✅ 确认收藏」
4. 收藏进度实时显示（✓成功 / 已更新 / ✗失败）
5. 收藏完成后自动切换到收藏库视图

### 阅读文章

- **收藏库中双击文章** → 打开阅读窗口
- 阅读窗口中点击「🔗 打开原文」→ 在浏览器中打开完整文章
- 支持添加个人备注、复制全文

### 标签管理

- **新建标签**：点击左侧「+ 新建标签」，输入名称后回车
- **编辑标签**：收藏库中右键文章 →「🏷 编辑标签」
- **管理标签**：菜单「标签 → 管理标签」，支持重命名和删除
- **按标签筛选**：点击左侧侧边栏中的标签名

### 导出文章

- 选中文章 → 点击「📤 导出」→ 选择 Markdown 或 HTML 格式
- 菜单「文件 → 导出全部」→ 导出所有收藏文章

## 📂 项目结构

```
wechat_doc/
├── main.py                  # 入口，启动 GUI
├── requirements.txt         # 依赖清单
├── build.spec               # PyInstaller 打包配置
├── LICENSE                  # MIT 开源协议
├── core/
│   ├── database.py          # SQLite 数据层 (CRUD + FTS5 全文搜索)
│   ├── searcher.py          # 搜狗微信搜索 + HTML 解析
│   └── fetcher.py           # 文章全文抓取 (JS 链接解析 → 微信真实页)
├── gui/
│   ├── main_window.py       # 主窗口 (侧边栏 + 搜索面板 + 状态栏)
│   ├── search_panel.py      # 搜索栏 + 结果列表 + 操作按钮
│   ├── reader_window.py     # 文章阅读弹窗
│   └── dialogs.py           # 收藏/标签编辑/新建标签 对话框
├── utils/
│   ├── http_client.py       # 带随机 UA/Cookie/请求间隔的 HTTP 封装
│   └── exporter.py          # Markdown / HTML 导出
└── assets/
    └── icon.ico             # 应用图标（打包时使用）
```

## 🛠 技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| GUI | Tkinter + ttkbootstrap | Python 自带 + 美化主题 |
| 网络 | requests + BeautifulSoup4 | 搜索 + HTML 解析 |
| 数据库 | sqlite3 (Python 内置) | 零依赖，单文件，FTS5 全文搜索 |
| 反爬 | 随机 UA + 请求间隔 + Cookie | 降低被拦截概率 |
| 打包 | PyInstaller | `--onefile` 生成单个 exe |

## 📦 打包为 EXE

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller build.spec
```

产出：`dist/微信文章收藏器.exe`（约 30-50MB，双击即用，数据库自动创建在 exe 同目录）

## ⚠️ 注意事项

- **搜狗验证码**：频繁搜索可能触发搜狗验证码，工具会提示并暂停，请稍后重试
- **微信反爬**：服务器 IP 抓取微信全文可能被拦截，此时收藏会保存链接和摘要，可点击「打开原文」在浏览器中阅读
- **临时链接时效**：搜狗搜索结果中的临时链接有时效性（约数小时），建议搜索后尽快收藏
- **数据安全**：所有数据存储在 `articles.db` 单文件中，可手动复制备份

## 🧪 开发

```bash
# 克隆仓库
git clone https://github.com/jacwenlee/wechat-article-collector.git
cd wechat-article-collector

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 数据库结构

```sql
articles (id, title, author, account_id, summary, content, content_text,
          url, cover_img, pub_date, collected_at, is_read, note)
tags (id, name)
article_tags (article_id, tag_id)
articles_fts (FTS5 虚拟表, trigram 分词)
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改和分发。
