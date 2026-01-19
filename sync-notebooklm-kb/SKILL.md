---
name: sync-notebooklm-kb
description: 同步本地文章目录到 NotebookLM 知识库。运行分类脚本后，对比目录与 NotebookLM 笔记本，自动添加新文章。
---

# 同步 NotebookLM 知识库

将本地已发布文章目录与 NotebookLM 笔记本保持同步。支持环境自适应：有 Obsidian 的机器运行分类脚本，没有的机器从 Git 拉取。

## 触发词

- "同步知识库"、"同步 notebooklm"、"更新知识库"
- "sync kb"、"sync notebooklm"
- "/sync-notebooklm-kb"

## 目录结构

```
sync-notebooklm-kb/
├── SKILL.md
├── config.json          # 固定配置（Git URL、Notebook ID）
└── scripts/
    └── sync.sh          # 环境自适应同步脚本
```

## 环境自适应

脚本自动检测当前环境，选择合适的工作模式：

### Local 模式（有 Obsidian 的机器）

检测条件：
- 存在 `$HOME/Dropbox/markdown_converter/classify_published_articles.py`
- 存在 `$HOME/Dropbox/cn_articles_published/.git`

工作流程：
1. 运行分类脚本（Obsidian → R2 转换 → 输出目录）
2. Git push 分类结果到远端
3. 对比本地目录与 NotebookLM
4. 添加新文件

### Remote 模式（无 Obsidian 的机器，如 VPS）

检测条件：
- 未找到上述目录

工作流程：
1. 从 Git 仓库 clone/pull 文章目录
2. 对比本地目录与 NotebookLM
3. 添加新文件

## 执行方式

```bash
# 完整同步
bash ~/.claude/skills/sync-notebooklm-kb/scripts/sync.sh

# 跳过分类脚本（仅对比同步）
bash ~/.claude/skills/sync-notebooklm-kb/scripts/sync.sh --skip-classify

# 预览模式（不实际执行）
bash ~/.claude/skills/sync-notebooklm-kb/scripts/sync.sh --dry-run
```

## 配置说明

**首次使用前**，将 `config.json.example` 复制为 `config.json`，填写你自己的配置：

```json
{
  "articles_repo_url": "https://github.com/YOUR_USERNAME/YOUR_ARTICLES_REPO.git",
  "notebooklm_notebook_id": "your-notebook-uuid-here",
  "notebooklm_notebook_name": "你的笔记本名称"
}
```

获取 Notebook ID：
1. 在 NotebookLM 中打开目标笔记本
2. 查看 URL，格式如 `https://notebooklm.google.com/notebook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
3. 复制 UUID 部分

## 匹配规则

**严格匹配**：本地文件名必须与 NotebookLM source title 完全一致才视为已同步。

- 不做模糊匹配
- 不因细微差异（标点、空格等）自动添加
- 如有不一致需要人工处理

## 依赖

- `jq`：JSON 解析
- `notebooklm` CLI：NotebookLM 操作
- `git`：仓库操作
- （Local 模式）`python` + markdown_converter 项目依赖

## VPS 使用前准备

VPS 无图形界面，无法完成 Google 登录流程。认证文件已通过 chezmoi 加密同步。

在 VPS 上执行：

```bash
chezmoi update --apply
notebooklm list  # 验证认证生效
```

认证文件位置：`~/.notebooklm/storage_state.json`（由 chezmoi 自动解密部署）

## 示例输出

### Local 模式

```
======================================
同步 NotebookLM 知识库
======================================
笔记本: 我的文章知识库
模式: local
本地仓库: /Users/username/Dropbox/cn_articles_published
分类脚本: /Users/username/Dropbox/markdown_converter

[1/4] 运行文章分类脚本...
成功率: 51.3%

  推送分类结果到 Git...
  已推送到远端仓库

[2/4] 获取本地文件列表...
  本地文章: 216 篇

[3/4] 获取 NotebookLM sources 列表...
  NotebookLM sources: 213 篇

[4/4] 对比分析...
  发现 3 篇新文章需要添加：
    - 新文章1.md
    - 新文章2.md
    - 新文章3.md

  添加完成！

======================================
同步完成
======================================
```

### Remote 模式

```
======================================
同步 NotebookLM 知识库
======================================
笔记本: 我的文章知识库
模式: remote

[1/4] 从远端仓库拉取文章...
  克隆仓库...

[2/4] 获取本地文件列表...
  本地文章: 216 篇

[3/4] 获取 NotebookLM sources 列表...
  NotebookLM sources: 216 篇

[4/4] 对比分析...
  知识库已同步，无需添加新文件。

======================================
同步完成
======================================
```
