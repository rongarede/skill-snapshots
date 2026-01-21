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

共 **21** 个 Skills，按 **7** 类分组。

## 分类总览

| 类别 | Skills |
|------|--------|
| 📝 学术写作 | paper-mapping, paper-readbook, paragraph-move-analysis, pdf2md-academic, word-to-tex |
| 📚 知识管理 | notebooklm, nb-query, sync-notebooklm-kb, article-linker, daily-journal |
| 🛠️ 开发工具 | task-dispatcher, codex-cli-runner, planning-with-files, obsidian-markdown, obsidian-bases, json-canvas |
| 🔧 技能管理 | skill-snapshot, skill-retrospective, skill-catalog |
| 🌐 浏览器与数据 | agent-browser, rss-daily-digest |
| 📄 文件处理 | rename-pdf |
| 🎨 特定框架 | makepad-evolution |

---

## 快速查找

| 触发词 | Skill | 功能 |
|--------|-------|------|
| `/mapping` | paper-mapping | 论文段落级仿写映射 |
| `/readbook` | paper-readbook | 论文逆向拆解 |
| `/paragraph-analysis` | paragraph-move-analysis | 逐句写作动作分析 |
| `/pdf2md` | pdf2md-academic | 学术 PDF → Markdown |
| `/wordtotex` | word-to-tex | Word → LaTeX |
| `/notebooklm` | notebooklm | NotebookLM 自动化 |
| `/nb-query` | nb-query | NotebookLM 深度查询 |
| `/article-linker` | article-linker | 文章标题→链接映射 |
| `/daily-journal` | daily-journal | 每日日记 |
| `/dispatch` | task-dispatcher | 任务拆分并发分派 |
| `/skill-snapshot` | skill-snapshot | 技能快照备份 |
| `/skill复盘` | skill-retrospective | 技能使用复盘 |
| `/skills` | skill-catalog | 技能目录 |
| `/skills check` | skill-catalog | 检查 GitHub 更新 |
| `/rss日报` | rss-daily-digest | RSS 新闻抓取 |
| `/renamepdf` | rename-pdf | PDF 自动重命名 |

---

## 维护

此仓库由 `skill-snapshot` 技能自动管理。

更新时同步：
1. 本 README
2. `~/.claude/skills/skill-catalog/skill.md`
