---
name: task-dashboard
description: "扫描活跃项目提取任务并按紧急度排序。触发词：/task-dashboard、整理任务、每日任务、今日待办、任务看板"
---

# Task Dashboard

扫描 `100_Projects/Active/` 全部项目主页，提取带 deadline/status/priority 的任务，按紧急度排序，可写入当日日记。

## 触发方式

- `/task-dashboard`
- 「整理每日任务」
- 「今日待办」
- 「任务看板」
- 「整理 Active 的 task」

## 执行

```bash
python3 ~/.claude/skills/task-dashboard/scripts/scan_tasks.py --vault /Users/bit/Obsidian
```

JSON 输出（供程序消费）：
```bash
python3 ~/.claude/skills/task-dashboard/scripts/scan_tasks.py --vault /Users/bit/Obsidian --json
```

## 工作流程

### 第一步：扫描任务

运行 `scan_tasks.py`，脚本自动：

1. 遍历 `100_Projects/Active/Project_*/` 所有项目目录
2. 读取 `*项目主页.md` 的 frontmatter（deadline, status, priority）
3. 读取 `planning/`、`docs/` 子目录的规划文件
4. 提取所有未完成 `- [ ]` checkbox 任务
5. 提取表格中的时间线条目（阶段 | 截止 | 状态）

### 第二步：按紧急度分类

| 分类 | 条件 |
|------|------|
| 🔴 紧急 | 截止日期在本周内（7天） |
| 🟡 重要 | 截止日期在本月内（30天） |
| 🔵 长期 | 无截止日期或超过30天 |

排序规则：截止日期升序 → 有截止 > 无截止

### 第三步：写入日记（可选）

将输出插入当日日记的 `## 今日任务` 章节：

1. 检查 `500_Journal/Daily/{today}.md` 是否存在
2. 存在 → 替换 `## 今日任务` 到下一个 `##` 之间的内容
3. 不存在 → 创建日记并写入

## 输出示例

```markdown
### 🔴 紧急（本周截止）

- [ ] **求职** — GitHub Profile 优化 `截止 2026-03-16`
- [ ] **控制论** — 周记 W11: 反馈概念的 Agent 映射 `截止 2026-03-16`

### 🟡 重要（本月内）

- [ ] **求职** — 目标公司列表（Solana 生态 DeFi）`截止 2026-03-23`
- [ ] **SWUN_Thesis** — 6 处小节结尾句缺失（Ch2/Ch3/Ch4）

### 🔵 长期进行中（无截止日期）

- [ ] **AI基础** — Phase 1 数学基础
  - *...还有 25 项*

---
**共 42 项待办** | 紧急 4 | 重要 6 | 长期 32
```

## 与 daily-journal 联动

扫描结果可直接嵌入日记的 `## 今日任务` 章节。建议每日开工时执行一次。
