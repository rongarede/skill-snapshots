---
name: daily-journal
description: Use when user wants to record tasks to daily journal, write daily report, or mentions "记录日记", "写日报", "today's journal"
---

# Daily Journal

自动创建或追加当日日记，按统一格式记录任务。

## 触发条件

- `/daily-journal`
- `/日记`
- 「记录到今日日记」
- 「写入日报」
- 「记录此任务」

## 配置

```yaml
journal_path: /Users/bit/Obsidian/500_Journal/Daily
date_format: YYYY-MM-DD
filename_pattern: "{date}.md"
```

## 工作流程

### 第一步：确定日期与路径

1. 获取当前日期（格式：`YYYY-MM-DD`）
2. 构建日记文件路径：`{journal_path}/{date}.md`
3. 检查文件是否存在

### 第二步：文件不存在 → 创建新日记

使用以下模板创建：

```markdown
---
title: "{date}"
date: {date}
tags:
  - daily
up: "[[500_Journal/Daily/]]"
---

# {date} 日报

## 日志导航

- 前一天: [[500_Journal/Daily/{yesterday}]]
- 后一天: [[500_Journal/Daily/{tomorrow}]]

## 概述

{summary}

## {section_title}

### {task_title}

- **时间**: {time}
- **目标**: {goal}
{task_details}

## 总结

{achievements}

## 明日计划

- [ ] {next_task}
```

### 第三步：文件已存在 → 追加内容

1. 读取现有日记内容
2. 定位合适的插入位置：
   - 若有对应章节（如「Claude Code 技能管理」），追加到该章节
   - 若无对应章节，在「总结」之前新建章节
3. 按格式追加任务记录

### 第四步：格式化任务记录

根据任务类型生成内容：

**开发任务格式：**
```markdown
### {task_title}

- **时间**: {time}
- **目标**: {goal}
- **修改文件**:
  - `{file_path}` - {description}
- **验证**: {verification}
```

**安装/配置任务格式：**
```markdown
### {task_title}

- **时间**: {time}
- **目标**: {goal}
- **安装来源**: {source}
- **安装路径**: {path}
- **功能**:
  - {feature_1}
  - {feature_2}
```

**表格汇总格式（批量操作）：**
```markdown
### {task_title}

{description}

| 项目 | 状态 | 备注 |
|------|------|------|
| {item} | {status} | {note} |
```

## 使用示例

### 示例 1：记录当前任务

```
用户: 记录此任务到今日日记
Claude: [检查日记 → 追加任务记录]
输出: 已追加到 /Users/bit/Obsidian/500_Journal/Daily/2026-01-19.md
```

### 示例 2：创建新日记并记录

```
用户: 把今天做的事情写到日记
Claude: [创建日记 → 写入概述和任务]
输出: 已创建 2026-01-20.md 并记录今日任务
```

### 示例 3：指定内容记录

```
用户: 记录日记：完成了 SDK 重构，支持 ESM/CJS 双模块
Claude: [定位章节 → 追加记录]
输出: 已追加到「SDK 开发」章节
```

## 章节分类规则

根据任务内容自动归类：

| 关键词 | 章节名称 |
|--------|----------|
| skill, Claude Code, 技能 | Claude Code 技能管理 |
| SDK, API, 后端, 前端 | {项目名}项目开发 |
| Obsidian, 笔记, 知识库 | Obsidian 知识库 |
| 配置, 安装, 部署 | 环境配置 |
| 其他 | 杂项 |

## 注意事项

1. **保持格式一致**: 严格遵循现有日记的 Markdown 格式
2. **时间戳**: 使用 24 小时制（如 10:50），**必须来自实际时间**
3. **Wikilink 格式**: 使用 `[[path/to/note]]` 格式的内部链接
4. **YAML Frontmatter**: 必须包含 title, date, tags, up 字段
5. **导航链接**: 自动计算前一天/后一天日期

## 时间记录规则

⚠️ **强制要求：时间字段必须使用实际时间，禁止估算或编造**

**获取方式：**

在写入任何包含「时间」字段的日记条目前，必须先执行：

```bash
date "+%H:%M"
```

将返回值作为「时间」字段的值。

**正确示例：**
1. 执行 `date "+%H:%M"` → 返回 `12:11`
2. 写入 `- **时间**: 12:11`

**禁止行为：**
- ❌ 根据任务顺序推测时间
- ❌ 使用「大约」「估计」等模糊时间
- ❌ 编造未来时间（如当前 12:00 却写 15:00）
- ❌ 复用之前条目的时间
