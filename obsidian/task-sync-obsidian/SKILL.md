---
name: task-sync-obsidian
description: >
  Task 完成后，从 Daily 日报提取工作记录，同步到对应项目主页的迭代日志。
  触发条件：所有 TaskUpdate status=completed 后，主会话检查任务面板并派子代理执行同步。
---

# Task Sync to Obsidian

所有 Task 完成后，从 Daily 日报提取工作记录，同步到对应项目主页的迭代日志。

## 触发流程

```
TaskUpdate(completed) → hook 输出提醒
                              ↓
                    主会话检查 TaskList
                              ↓
                    所有 Task 已完成？
                        ↓ 是
            读取当日 Daily 日报 → 提取项目相关条目
                              ↓
                按项目分组 → 写入各项目主页迭代日志
```

## 自动触发

PostToolUse hook `task-sync-hook.py` 在 TaskUpdate(completed) 时输出提醒：
- `📋 任务「{subject}」已完成。所有任务完成后，请执行 Daily→项目日志同步。`

## 主会话响应

收到 hook 提醒后，主会话应：
1. 调用 TaskList 检查是否所有任务都已完成
2. 如果还有未完成任务，继续工作
3. 所有任务完成后，派子代理执行同步：
   a. 读取当日 Daily 日报（`500_Journal/Daily/YYYY-MM-DD.md`）
   b. 提取工作记录条目（commit 记录、任务完成记录等）
   c. 按项目关键词匹配到对应项目主页
   d. 写入项目主页

## 项目匹配规则

从 Daily 日报条目中提取项目关键词，匹配 `100_Projects/Active/Project_*` 下的项目：
1. 日报条目中包含项目名称（如「控制论」「SWUN_Thesis」）→ 匹配对应项目
2. 日报条目中包含项目相关文件路径 → 匹配对应项目
3. 无法匹配的条目 → 跳过（不强制归类）

项目主页搜索路径：
- `/Users/bit/Obsidian/100_Projects/Active/`
- `/Users/bit/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian/100_Projects/Active/`

## 写入规则

### Checkbox 匹配
1. 搜索项目主页中所有 `- [ ]` 行
2. 用 Daily 条目关键词模糊匹配
3. 命中 → `- [x]`
4. 未命中 → 不新增（避免噪音）

### 迭代日志追加
1. 定位项目主页中「迭代日志」或「进度记录」表格
2. 最后一行后追加 `| {date} | {summary} | 已完成 |`
3. summary 从 Daily 条目中提炼，保持简洁

## 依赖

- hook: `~/.claude/hooks/task-sync-hook.py`（PostToolUse, matcher: TaskUpdate）
- Daily 日报: `500_Journal/Daily/YYYY-MM-DD.md`
- 项目主页: `100_Projects/Active/Project_*/xxx_项目主页.md`
