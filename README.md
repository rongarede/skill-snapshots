# Skill Snapshots

Claude Code 技能快照私有备份仓库。

## 仓库结构

```
├── <skill-name>/
│   └── v<n>/
│       └── skill.md
```

Tags 格式: `<skill-name>/v<n>`

---

# 📖 Skill Catalog - 技能目录

汇总当前所有可用的 Claude Code Skills，按类别分组。

## 技能分类总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 📝 学术写作 | 5 | 论文映射、逆向工程、段落分析、PDF转MD、LaTeX 转换 |
| 📚 知识管理 | 5 | NotebookLM、Obsidian、日记 |
| 🛠️ 开发工具 | 4 | Codex 集成、任务分派、规划 |
| 🔧 技能管理 | 3 | 快照、复盘、目录 |
| 🌐 浏览器与数据 | 2 | 浏览器自动化、RSS |
| 📄 文件处理 | 1 | PDF 重命名 |
| 🎨 特定框架 | 1 | Makepad 开发 |

---

## 📝 学术写作类

### paper-mapping
**论文段落级仿写映射工具**

在同领域同思想框架前提下，建立论文段落间的结构、逻辑、方法映射关系。

- **触发词**: `/mapping`、论文映射、段落映射
- **输出**: `<目标文件>_mapping.md`
- **核心功能**: 四大映射维度判断、段落级定位

### paper-readbook
**论文逆向工程工具**

将学术论文逆向拆解为三份可迁移仿写的技术文档。

- **触发词**: `/readbook`、论文逆向、论文拆解
- **输出**: 设计画布.md、逆向提纲.md、论证挖掘.md
- **核心功能**: 分层逆向拆解、图尔敏论证分析

### paragraph-move-analysis
**段落写作动作分析工具**

逐句拆解论文段落的说服动作，输出可迁移的仿写模板。

- **触发词**: `/paragraph-analysis`、段落拆解、写作动作分析
- **输出**: `{论文名}_{章节名}_提纲.md`
- **核心功能**: 逐句动作类型标注、写作心法揭秘、完形填空模板

### pdf2md-academic
**学术 PDF 转 Markdown 工具**

将含公式、图表、引用的学术论文 PDF 转换为排版整洁的 Markdown。

- **触发词**: `/pdf2md`、PDF转Markdown、论文转MD
- **核心功能**: 公式转换、引用格式化、算法标准化、罗马数字列表

### word-to-tex
**Word 转 LaTeX 工具**

将从 Word 复制的内容转换为标准 LaTeX 格式并保存。

- **触发词**: `/wordtotex`、Word转LaTeX、转换为TeX
- **输入**: `/wordtotex <filename.tex> [内容]`
- **核心功能**: 标题级次、公式、列表、特殊字符转换

---

## 📚 知识管理类

### notebooklm
**NotebookLM 自动化**

自动化操作 Google NotebookLM，创建笔记本、添加来源、生成播客/视频/测验。

- **触发词**: `/notebooklm`、create a podcast about X
- **核心功能**: 笔记本管理、播客生成、内容下载

### nb-query
**NotebookLM 深度查询**

超富集模式查询，自动存储中间产物，外部检索核查准确性，本地图片溯源。

- **触发词**: `/nb-query`、智能笔记本查询
- **核心功能**: 超富集查询、引用溯源、事实核查

### sync-notebooklm-kb
**同步本地文章到 NotebookLM**

对比本地文章目录与 NotebookLM 笔记本，自动添加新文章。

- **触发词**: 同步知识库、sync notebooklm
- **核心功能**: 目录对比、增量同步

### article-linker
**文章链接映射服务**

将文章标题映射为已发布的外部链接，供其他 Skill 调用。

- **触发词**: `/article-linker`、查找文章链接
- **核心功能**: 标题→链接映射、精确/模糊匹配

### daily-journal
**每日日记工具**

自动创建/追加当日日记，智能定位章节。

- **触发词**: `/daily-journal`、记录日记、写日报
- **核心功能**: 日记创建、章节定位、格式统一

---

## 🛠️ 开发工具类

### task-dispatcher
**任务自动分派**（主动触发）

自动识别任务类型，路由到 Claude 或 Codex 执行。

- **触发条件**: 检测到开发任务关键词时自动触发
- **Claude 任务**: 分析、设计、规划、调试、决策
- **Codex 任务**: 实现、编写、修复、重构、测试、文档

### codex-cli-runner
**Codex CLI 执行指南**

OpenAI Codex CLI 非交互模式执行最佳实践。

- **触发词**: codex exec、Codex 执行
- **核心功能**: 配置验证、执行模式、JSON 解析

### planning-with-files
**文件驱动规划**

使用 Manus 风格的持久化 Markdown 文件进行规划、进度追踪、知识存储。

- **触发词**: 规划、planning、组织工作
- **核心功能**: 任务规划、进度追踪、结构化输出

### obsidian-markdown
**Obsidian Markdown 语法**

创建和编辑 Obsidian 风格的 Markdown，支持 wikilinks、embeds、callouts、properties。

- **触发词**: wikilinks、callouts、Obsidian 笔记
- **核心功能**: Obsidian 专有语法支持

### obsidian-bases
**Obsidian Bases 管理**

创建和编辑 Obsidian Bases（.base 文件），支持视图、过滤器、公式、汇总。

- **触发词**: .base 文件、Bases、表格视图
- **核心功能**: 数据库视图、公式、过滤器

### json-canvas
**JSON Canvas 编辑**

创建和编辑 JSON Canvas 文件（.canvas），支持节点、边、分组。

- **触发词**: .canvas 文件、Canvas、思维导图
- **核心功能**: 可视化画布、流程图、思维导图

---

## 🔧 技能管理类

### skill-snapshot
**技能快照管理**

为 Claude Code 技能创建快照，支持版本回退，存储在 GitHub 私有仓库。

- **触发词**: `/skill-snapshot`、快照、备份技能
- **命令**: init、scan、save、restore、list、diff

### skill-retrospective
**技能迭代复盘**

回顾当前会话的 Skill 使用情况，生成迭代建议。

- **触发词**: `/skill复盘`、`/迭代清单`
- **核心功能**: 使用统计、负反馈识别、迭代建议

### skill-catalog
**技能目录汇总**

汇总所有可用 Skills 的目录与使用指南。

- **触发词**: `/skills`、技能目录、有哪些技能
- **核心功能**: 分类展示、快速查找

---

## 🌐 浏览器与数据类

### agent-browser
**浏览器自动化**

自动化浏览器交互，支持网页测试、表单填写、截图、数据提取。

- **触发词**: 浏览器操作、网页交互、截图
- **核心功能**: 页面导航、表单填写、数据提取

### rss-daily-digest
**RSS 日报抓取**

抓取 RSS feeds，生成今日新闻摘要。

- **触发词**: `/rss日报`、今日新闻、抓取RSS
- **核心功能**: RSS 抓取、主题分类、摘要生成

---

## 📄 文件处理类

### rename-pdf
**PDF 自动重命名**

提取 PDF 元数据标题，清理非法字符，静默重命名。

- **触发词**: `/renamepdf`、重命名PDF、PDF改名
- **核心功能**: 元数据提取、字符清理、静默执行

---

## 🎨 特定框架类

### makepad-evolution
**Makepad 自进化开发系统**

Makepad 开发的自改进技能系统，支持知识积累、错误自修正、准确性验证。

- **触发词**: Makepad 开发
- **核心功能**: 自进化、自修正、版本适配、风格个性化

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
| 让 Codex 执行代码任务 | task-dispatcher |
| 备份/恢复技能 | skill-snapshot |
| 复盘技能使用情况 | skill-retrospective |
| 自动化浏览器操作 | agent-browser |
| 获取今日 RSS 新闻 | rss-daily-digest |
| 重命名 PDF 文件 | rename-pdf |
| 创建 Obsidian Canvas | json-canvas |
| 编辑 Obsidian Bases | obsidian-bases |

---

## 维护说明

此仓库由 `skill-snapshot` 技能自动管理。

当新增或修改 Skill 时，请同步更新：
1. 本 README
2. `~/.claude/skills/skill-catalog/skill.md`
