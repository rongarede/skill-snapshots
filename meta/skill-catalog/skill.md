---
name: skill-catalog
description: "汇总所有 Claude Code Skills 的目录与使用指南，支持检查 GitHub 更新。触发词：/skills、技能目录、skill列表、有哪些技能、检查更新"
---

# Skill Catalog - 技能目录

汇总当前所有可用的 Claude Code Skills，按类别分组，方便查找与使用。支持检查 GitHub plugins 更新。

## 触发方式

- `/skills` 或 `/skill-catalog` - 显示技能目录
- `/skills check` 或 `检查技能更新` - 检查 GitHub plugins 更新
- 「有哪些技能」「技能目录」「skill 列表」

## 技能分类总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 📝 学术写作 | 5 | 论文映射、逆向工程、段落分析、PDF转MD、LaTeX 转换 |
| 📚 知识管理 | 5 | NotebookLM、Obsidian、日记 |
| 🛠️ 开发工具 | 5 | Codex/Gemini 集成、任务分派、规划 |
| 🔧 技能管理 | 5 | 快照、复盘、目录、编写规范、计划规范 |
| 🌐 浏览器与数据 | 2 | 浏览器自动化、RSS |
| 📄 文件处理 | 1 | PDF 重命名 |
| 🎨 特定框架 | 1 | Makepad 开发 |

---

## 📝 学术写作类

### paper-mapping
**论文段落级仿写映射工具**

在同领域同思想框架前提下，建立论文段落间的结构、逻辑、方法映射关系。

| 项目 | 内容 |
|------|------|
| 触发词 | `/mapping`、论文映射、段落映射 |
| 输出 | `<目标文件>_mapping.md` |
| 核心功能 | 四大映射维度判断、段落级定位 |

---

### paper-readbook
**论文逆向工程工具**

将学术论文逆向拆解为三份可迁移仿写的技术文档。

| 项目 | 内容 |
|------|------|
| 触发词 | `/readbook`、论文逆向、论文拆解 |
| 输出 | 设计画布.md、逆向提纲.md、论证挖掘.md |
| 核心功能 | 分层逆向拆解、图尔敏论证分析 |

---

### paragraph-move-analysis
**段落写作动作分析工具**

逐句拆解论文段落的说服动作，输出可迁移的仿写模板。

| 项目 | 内容 |
|------|------|
| 触发词 | `/paragraph-analysis`、段落拆解、写作动作分析 |
| 输出 | `{论文名}_{章节名}_提纲.md` |
| 核心功能 | 逐句动作类型标注、写作心法揭秘、完形填空模板 |

---

### pdf2md-academic
**学术 PDF 转 Markdown 工具**

将含公式、图表、引用的学术论文 PDF 转换为排版整洁的 Markdown。

| 项目 | 内容 |
|------|------|
| 触发词 | `/pdf2md`、PDF转Markdown、论文转MD |
| 核心功能 | 公式转换、引用格式化、算法标准化、罗马数字列表 |

---

### word-to-tex
**Word 转 LaTeX 工具**

将从 Word 复制的内容转换为标准 LaTeX 格式并保存。

| 项目 | 内容 |
|------|------|
| 触发词 | `/wordtotex`、Word转LaTeX、转换为TeX |
| 输入 | `/wordtotex <filename.tex> [内容]` |
| 核心功能 | 标题级次、公式、列表、特殊字符转换 |

---

## 📚 知识管理类

### notebooklm
**NotebookLM 自动化**

自动化操作 Google NotebookLM，创建笔记本、添加来源、生成播客/视频/测验。

| 项目 | 内容 |
|------|------|
| 触发词 | `/notebooklm`、create a podcast about X |
| 核心功能 | 笔记本管理、播客生成、内容下载 |

---

### nb-query
**NotebookLM 深度查询**

超富集模式查询，自动存储中间产物，外部检索核查准确性，本地图片溯源。

| 项目 | 内容 |
|------|------|
| 触发词 | `/nb-query`、智能笔记本查询 |
| 核心功能 | 超富集查询、引用溯源、事实核查 |

---

### sync-notebooklm-kb
**同步本地文章到 NotebookLM**

对比本地文章目录与 NotebookLM 笔记本，自动添加新文章。

| 项目 | 内容 |
|------|------|
| 触发词 | 同步知识库、sync notebooklm |
| 核心功能 | 目录对比、增量同步 |

---

### article-linker
**文章链接映射服务**

将文章标题映射为已发布的外部链接，供其他 Skill 调用。

| 项目 | 内容 |
|------|------|
| 触发词 | `/article-linker`、查找文章链接 |
| 核心功能 | 标题→链接映射、精确/模糊匹配 |

---

### daily-journal
**每日日记工具**

自动创建/追加当日日记，智能定位章节。

| 项目 | 内容 |
|------|------|
| 触发词 | `/daily-journal`、记录日记、写日报 |
| 核心功能 | 日记创建、章节定位、格式统一 |

---

## 🛠️ 开发工具类

### collaborating-with-gemini
**Gemini CLI 非交互式集成**

在 Claude Code 中非交互式调用 Gemini CLI，支持会话保存、上下文注入、Agent 角色注入。

| 项目 | 内容 |
|------|------|
| 触发词 | `/gemini`、gemini 协作、调用 gemini |
| 核心功能 | 非交互调用、会话保存、上下文注入、Agent 注入 |
| 会话存储 | `~/.claude/skills/collaborating-with-gemini/sessions/` |
| 命令 | `gemini-agent.sh`、`gemini-sessions.sh` |

---

### task-dispatcher
**任务细分与并发分派**

默认 Codex 执行，自动拆分任务、设置验证、支持并发分派。

| 项目 | 内容 |
|------|------|
| 触发词 | `/dispatch`、任务分派 |
| 核心流程 | 任务细分 → 验证定义 → 依赖分析 → 并发分派 → 结果验收 |
| 拆分原则 | 单一职责、单文件、可验证、原子性 |
| 失败回退 | Codex 重试 (2次) → Claude 接管分析 |
| Claude 触发 | 仅当包含：分析/设计/规划/调试/决策 |

---

### codex-cli-runner
**Codex CLI 执行指南**

OpenAI Codex CLI 非交互模式执行最佳实践。

| 项目 | 内容 |
|------|------|
| 触发词 | codex exec、Codex 执行 |
| 核心功能 | 配置验证、执行模式、JSON 解析 |

---

### planning-with-files
**文件驱动规划**

使用 Manus 风格的持久化 Markdown 文件进行规划、进度追踪、知识存储。

| 项目 | 内容 |
|------|------|
| 触发词 | 规划、planning、组织工作 |
| 核心功能 | 任务规划、进度追踪、结构化输出 |

---

### obsidian-markdown
**Obsidian Markdown 语法**

创建和编辑 Obsidian 风格的 Markdown，支持 wikilinks、embeds、callouts、properties。

| 项目 | 内容 |
|------|------|
| 触发词 | wikilinks、callouts、Obsidian 笔记 |
| 核心功能 | Obsidian 专有语法支持 |

---

### obsidian-bases
**Obsidian Bases 管理**

创建和编辑 Obsidian Bases（.base 文件），支持视图、过滤器、公式、汇总。

| 项目 | 内容 |
|------|------|
| 触发词 | .base 文件、Bases、表格视图 |
| 核心功能 | 数据库视图、公式、过滤器 |

---

### json-canvas
**JSON Canvas 编辑**

创建和编辑 JSON Canvas 文件（.canvas），支持节点、边、分组。

| 项目 | 内容 |
|------|------|
| 触发词 | .canvas 文件、Canvas、思维导图 |
| 核心功能 | 可视化画布、流程图、思维导图 |

---

## 🔧 技能管理类

### skill-snapshot
**技能快照管理**

为 Claude Code 技能创建快照，支持版本回退，存储在 GitHub 私有仓库。

| 项目 | 内容 |
|------|------|
| 触发词 | `/skill-snapshot`、快照、备份技能 |
| 命令 | init、scan、save、restore、list、diff |

---

### skill-retrospective
**技能迭代复盘**

回顾当前会话的 Skill 使用情况，生成迭代建议。

| 项目 | 内容 |
|------|------|
| 触发词 | `/skill复盘`、`/迭代清单` |
| 核心功能 | 使用统计、负反馈识别、迭代建议 |

---

### skill-catalog（本 Skill）
**技能目录与更新检查**

汇总所有可用 Skills 的目录与使用指南，支持检查 GitHub plugins 更新。

| 项目 | 内容 |
|------|------|
| 触发词 | `/skills`、技能目录、有哪些技能、`/skills check`、检查技能更新 |
| 核心功能 | 分类展示、快速查找、**检查 GitHub 更新** |

---

### skill-authoring
**Skill 编写规范**

Skill 编写最佳实践，脚本优先、目录结构、模板规范。

| 项目 | 内容 |
|------|------|
| 触发词 | `/skill-authoring`、编写 skill、创建技能 |
| 核心功能 | 脚本模板、目录结构、决策树 |

---

### plan-writing
**计划文档格式规范**

计划文档编写规范，描述性优先，禁止代码块。

| 项目 | 内容 |
|------|------|
| 触发词 | `/plan-writing`、写计划、计划文档规范 |
| 核心功能 | Task 格式、验证标准、检查清单 |

---

## 🌐 浏览器与数据类

### agent-browser
**浏览器自动化**

自动化浏览器交互，支持网页测试、表单填写、截图、数据提取。

| 项目 | 内容 |
|------|------|
| 触发词 | 浏览器操作、网页交互、截图 |
| 核心功能 | 页面导航、表单填写、数据提取 |

---

### rss-daily-digest
**RSS 日报抓取**

抓取 RSS feeds，生成今日新闻摘要。

| 项目 | 内容 |
|------|------|
| 触发词 | `/rss日报`、今日新闻、抓取RSS |
| 核心功能 | RSS 抓取、主题分类、摘要生成 |

---

## 📄 文件处理类

### rename-pdf
**PDF 自动重命名**

提取 PDF 元数据标题，清理非法字符，静默重命名。

| 项目 | 内容 |
|------|------|
| 触发词 | `/renamepdf`、重命名PDF、PDF改名 |
| 核心功能 | 元数据提取、字符清理、静默执行 |

---

## 🎨 特定框架类

### makepad-evolution
**Makepad 自进化开发系统**

Makepad 开发的自改进技能系统，支持知识积累、错误自修正、准确性验证。

| 项目 | 内容 |
|------|------|
| 触发词 | Makepad 开发 |
| 核心功能 | 自进化、自修正、版本适配、风格个性化 |

---

## 快速查找表

| 我想要... | 使用 Skill |
|-----------|------------|
| 分析论文结构 | paper-readbook |
| 建立论文段落映射 | paper-mapping |
| 逐句分析段落写作动作 | paragraph-move-analysis |
| 学术 PDF 转 Markdown | pdf2md-academic |
| 转换 Word 到 LaTeX | word-to-tex |
| 查询 NotebookLM 知识库 | nb-query |
| 生成播客 | notebooklm |
| 同步文章到知识库 | sync-notebooklm-kb |
| 记录今日工作 | daily-journal |
| **调用 Gemini CLI** | **collaborating-with-gemini** |
| 拆分任务并分派给 Codex | task-dispatcher |
| 并发执行多个独立任务 | task-dispatcher |
| 备份/恢复技能 | skill-snapshot |
| 复盘技能使用情况 | skill-retrospective |
| 自动化浏览器操作 | agent-browser |
| 获取今日 RSS 新闻 | rss-daily-digest |
| 重命名 PDF 文件 | rename-pdf |
| 创建 Obsidian Canvas | json-canvas |
| 编辑 Obsidian Bases | obsidian-bases |
| 编写新 Skill | skill-authoring |
| 写计划文档 | plan-writing |
| **检查 skill/plugin 更新** | **skill-catalog** (`/skills check`) |

---

## 检查 GitHub 更新

当触发 `/skills check` 或「检查技能更新」时，执行脚本：

```bash
bash ~/.claude/skills/skill-catalog/scripts/check-updates.sh
```

### 脚本功能

| 功能 | 说明 |
|------|------|
| 已安装 Plugins | 读取 `~/.claude/plugins/installed_plugins.json`，显示版本和 commit |
| Marketplaces 状态 | 读取 `~/.claude/plugins/known_marketplaces.json`，查询 GitHub API |
| 版本对比 | 对比本地 commit 与远程最新 commit |
| 更新建议 | 列出需要更新的 plugin 及命令 |

### 输出示例

```
=== 🔄 GitHub Skill/Plugin 更新检查 ===

【已安装 Plugins】

Plugin                              本地版本     安装日期     Commit
----------------------------------- ------------ ------------ --------
superpowers@superpowers-marketplace 4.0.3        2026-01-10   b9e16498
code-simplifier@claude-plugins-off  1.0.0        2026-01-10   N/A

【Marketplaces 远程状态】

Marketplace               GitHub 仓库                         最新 Commit 更新日期     说明
------------------------- ----------------------------------- ---------- ------------ --------------------
claude-plugins-official   anthropics/claude-plugins-official  96276205   2026-01-15   Add plugin directory...
superpowers-marketplace   obra/superpowers-marketplace        d466ee35   2025-12-27   Update superpowers t...

【更新建议】

  ✅ 所有已安装 plugins 均为最新版本

=== 检查完成 ===
```

### 手动更新命令

```bash
/plugins update superpowers@superpowers-marketplace
/plugins update code-simplifier@claude-plugins-official
```

### 代理配置

脚本自动检测 `https_proxy` 环境变量。如需代理：

```bash
export https_proxy=http://127.0.0.1:7897
bash ~/.claude/skills/skill-catalog/scripts/check-updates.sh
```

---

## 维护说明

本目录由 `skill-catalog` Skill 维护。当新增或修改 Skill 时，请同步更新：

1. 本 Skill（`~/.claude/skills/skill-catalog/skill.md`）
2. 远端 README（`~/.claude/skill-snapshots/README.md`）
3. 执行快照：`/skill-snapshot save skill-catalog`
