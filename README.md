# Skill Snapshots

Claude Code 技能快照私有备份仓库，按功能分类组织。

## 仓库结构

```
skill-snapshots/
├── ai-collaboration/          # AI 协作工具
│   ├── collaborating-with-codex/
│   ├── collaborating-with-gemini/
│   ├── collaborating-with-kimi/
│   └── task-dispatcher/
├── development/               # 开发模式
│   ├── backend-patterns/
│   ├── clickhouse-io/
│   ├── coding-standards/
│   ├── frontend-patterns/
│   ├── postgres-patterns/
│   ├── security-review/
│   └── tdd-workflow/
├── meta/                      # 元技能管理
│   ├── continuous-learning/
│   ├── continuous-learning-v2/
│   ├── eval-harness/
│   ├── skill-authoring/
│   ├── skill-catalog/
│   └── skill-retrospective/
├── obsidian/                  # Obsidian 相关
│   ├── json-canvas/
│   ├── nb-query/
│   ├── notebooklm/
│   ├── obsidian-bases/
│   ├── obsidian-markdown/
│   └── sync-notebooklm-kb/
├── utilities/                 # 工具类
│   ├── agent-browser/
│   ├── diagram-indexer/
│   ├── iterative-retrieval/
│   ├── makepad-evolution/
│   ├── project-guidelines-example/
│   ├── strategic-compact/
│   ├── verification-loop/
│   └── web-fetch-fallback/
├── workflow/                  # 工作流程
│   ├── changelog/
│   ├── daily-journal/
│   ├── planning-with-files/
│   ├── rename-pdf/
│   └── rss-daily-digest/
├── writing/                   # 写作与文档
│   ├── article-linker/
│   ├── paper-mapping/
│   ├── paper-readbook/
│   ├── paragraph-move-analysis/
│   ├── pdf2md-academic/
│   ├── plan-writing/
│   └── word-to-tex/
├── uncategorized/             # 未分类
│   ├── codex-cli-runner/
│   ├── codex-parser/
│   ├── skill-snapshot/
│   └── tech-scout/
├── agents/                    # Agent 配置
└── claude-configs/            # CLAUDE.md 配置备份
```

**Tags 格式**: `<category>/<skill-name>/v<n>` (如 `writing/paper-mapping/v2`)

---

## 分类说明

| 分类 | 说明 | 技能数 |
|------|------|--------|
| **ai-collaboration** | AI 协作工具（Codex、Gemini、Kimi 集成） | 4 |
| **development** | 开发模式（编码规范、设计模式、TDD、安全审查） | 7 |
| **meta** | 元技能管理（技能创建、目录、复盘、学习） | 6 |
| **obsidian** | Obsidian 相关（NotebookLM、Canvas、Bases） | 6 |
| **utilities** | 工具类（浏览器、网页抓取、图表索引） | 8 |
| **workflow** | 工作流程（日志、RSS、文件重命名） | 5 |
| **writing** | 写作与文档（论文写作、文档转换） | 7 |
| **uncategorized** | 未分类 | 4 |

---

## 📖 Skill Catalog - 技能目录

共 **47** 个 Skills，按 **8** 类分组。

### 快速查找

| 触发词 | Skill | 分类 | 功能 |
|--------|-------|------|------|
| `/gemini` | collaborating-with-gemini | ai-collaboration | Gemini CLI 非交互集成 |
| `/dispatch` | task-dispatcher | ai-collaboration | 任务拆分并发分派 |
| `/mapping` | paper-mapping | writing | 论文段落级仿写映射 |
| `/readbook` | paper-readbook | writing | 论文逆向拆解 |
| `/paragraph-analysis` | paragraph-move-analysis | writing | 逐句写作动作分析 |
| `/pdf2md` | pdf2md-academic | writing | 学术 PDF → Markdown |
| `/wordtotex` | word-to-tex | writing | Word → LaTeX |
| `/notebooklm` | notebooklm | obsidian | NotebookLM 自动化 |
| `/nb-query` | nb-query | obsidian | NotebookLM 深度查询 |
| `/article-linker` | article-linker | writing | 文章标题→链接映射 |
| `/daily-journal` | daily-journal | workflow | 每日日记 |
| `/skill-snapshot` | skill-snapshot | uncategorized | 技能快照备份 |
| `/skill复盘` | skill-retrospective | meta | 技能使用复盘 |
| `/skills` | skill-catalog | meta | 技能目录 |
| `/skills check` | skill-catalog | meta | 检查 GitHub 更新 |
| `/rss日报` | rss-daily-digest | workflow | RSS 新闻抓取 |
| `/renamepdf` | rename-pdf | workflow | PDF 自动重命名 |

---

## 分类配置

技能分类定义在 `~/.claude/skills/skill-snapshot/categories.conf`：

```conf
# 格式: skill-name=category
collaborating-with-codex=ai-collaboration
paper-mapping=writing
obsidian-bases=obsidian
coding-standards=development
planning-with-files=workflow
skill-authoring=meta
agent-browser=utilities
```

新增技能时，需在此文件中添加分类配置。

---

## 维护

此仓库由 `skill-snapshot` 技能自动管理。

**更新时同步**：
1. 本 README (`~/.claude/skill-snapshots/README.md`)
2. 技能目录 (`~/.claude/skills/skill-catalog/skill.md`)
3. 分类配置 (`~/.claude/skills/skill-snapshot/categories.conf`)

**常用命令**：
```bash
# 扫描技能状态
/skill-snapshot scan

# 保存快照
/skill-snapshot save <skill-name> "说明"

# 恢复版本
/skill-snapshot restore <skill-name> v1

# 查看快照列表
/skill-snapshot list
```
# auto-push test 2026年 3月19日 星期四 21时25分21秒 CST
