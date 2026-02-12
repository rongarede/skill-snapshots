---
name: task-checkpoint
description: "任务完成后自动更新 plan + TODO + commit + push。触发词：/checkpoint、任务检查点、完成任务"
---

# Task Checkpoint

任务完成后的自动检查点：更新计划文件、更新 TODO、提交并推送。

## 触发方式

- `/checkpoint`
- 每个任务完成后自动触发（无需用户手动调用）
- 「完成任务」「任务检查点」

## 自动触发条件

当以下任一条件满足时，**必须**自动执行 checkpoint：
1. 一个编号任务（如 T-FIX-02、T-WRITE-01）的全部验证通过
2. 用户明确说「完成了」「搞定了」「done」
3. 实验批次全部跑完并验证

## 工作流程

### Step 1: 确认任务完成

验证当前任务的 DoD（Definition of Done）：
- 产出物是否齐全
- 验证是否通过
- 无遗留错误

### Step 2: 更新 Plan 文件

读取当前 plan 文件，执行以下更新：
1. 将完成的任务从「待完成」移到「已完成」区域
2. 更新 Context 段落的「当前状态」
3. 更新执行顺序中的 ✅ 标记和「← 当前」指针
4. 如有新 commit，追加到 Commit 记录表

**Plan 文件位置：** 读取 `~/.claude/plans/` 下最新的 plan 文件

### Step 3: 更新 TODO 文件

读取项目 TODO 文件，执行以下更新：
1. 状态看板：将任务 ID 移到「已完成」列表
2. 对应任务条目：状态改为 `已完成 ✅`，补充完成时间
3. 追加执行日志（Section N+1）：
   - 执行时间
   - 执行内容摘要
   - 关键产出物
   - 验证结果

**TODO 文件定位：** 在项目 `docs/todo/` 目录下查找与当前工作相关的 TODO 文件

### Step 4: Git Commit + Push

```bash
bash ~/.claude/skills/task-checkpoint/scripts/checkpoint.sh \
  "<task-id>" \
  "<commit-message>" \
  [file1 file2 ...]
```

参数说明：
- `task-id`：任务编号（如 T-FIX-02）
- `commit-message`：提交信息（遵循 conventional commits）
- `file1 file2 ...`：要暂存的文件列表（可选，默认暂存所有已修改的跟踪文件）

### Step 5: 确认输出

输出检查点摘要：

```
✅ Checkpoint: <task-id>
  - Plan 已更新
  - TODO 已更新
  - Commit: <hash> <message>
  - Push: <branch> → <remote>
```

## Commit Message 格式

```
<type>(<task-id>): <description>

- <变更项1>
- <变更项2>
```

type 选择：
- `feat`：新功能/新实验数据
- `fix`：Bug 修复
- `docs`：文档/TODO/plan 更新
- `refactor`：重构
- `chore`：杂项

## 注意事项

1. **不要遗漏 plan 更新**：这是用户明确要求的，每次任务完成必须更新
2. **只提交相关文件**：不要 `git add -A`，只暂存与当前任务相关的文件
3. **push 前确认分支**：确认在正确的分支上
4. **大文件警告**：如果暂存文件超过 10MB，提醒用户确认
5. **冲突处理**：push 失败时提示用户手动处理
