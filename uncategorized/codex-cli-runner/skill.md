---
name: codex-cli-runner
description: Use when running OpenAI Codex CLI in non-interactive mode, executing tasks with full access, or parsing JSON output from codex exec.
---

# Codex CLI Runner

OpenAI Codex CLI 非交互模式执行工具。

## 触发条件

- 使用 `codex exec` 执行任务
- 需要 full access 或 yolo 模式
- 解析 Codex JSON 输出

## 执行脚本

```bash
# 执行任务，输出完整 JSON
bash ~/.claude/skills/codex-cli-runner/scripts/run.sh "任务描述"

# 只提取最终消息
bash ~/.claude/skills/codex-cli-runner/scripts/run.sh "任务描述" --extract message

# 只提取退出码
bash ~/.claude/skills/codex-cli-runner/scripts/run.sh "任务描述" --extract exit_code
```

## 直接使用 Codex（不用脚本）

```bash
# 标准执行
codex exec --yolo "任务描述"

# JSON 输出
codex exec --yolo --json "任务描述"
```

## 执行模式

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| Auto | `codex exec "..."` | 工作目录内操作 |
| Full Auto | `codex exec --full-auto "..."` | 工作目录内自动操作 |
| Full Access | `codex exec --sandbox danger-full-access "..."` | 需要网络或跨目录 |
| YOLO | `codex exec --yolo "..."` | 完全信任，无限制 |

## JSON 输出解析

使用 jq 提取关键信息：

```bash
# 提取最终消息
codex exec --yolo --json "..." | jq -s 'map(select(.msg.type == "agent_message")) | last | .msg.message'

# 提取命令退出码
codex exec --yolo --json "..." | jq 'select(.msg.type == "exec_command_end") | .msg.exit_code'

# 提取 token 用量
codex exec --yolo --json "..." | jq 'select(.msg.type == "token_count") | .msg.info.total_token_usage'
```

## 常见问题

| 错误 | 修复 |
|------|------|
| `unknown variant xhigh` | 编辑 `~/.codex/config.toml`，将 `model_reasoning_effort` 改为有效值 |
| `fetch failed` | 检查代理配置 |
| `sandbox blocked write` | 使用 `--yolo` 或 `--sandbox danger-full-access` |
| `workspace not trusted` | 在 config.toml 添加项目信任配置 |

## 依赖

- codex CLI
- jq（用于 JSON 解析）
