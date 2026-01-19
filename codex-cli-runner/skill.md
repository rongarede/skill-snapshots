---
name: codex-cli-runner
description: Use when running OpenAI Codex CLI in non-interactive mode, executing tasks with full access, or parsing JSON output from codex exec.
---

# Codex CLI Runner

OpenAI Codex CLI 非交互模式执行指南。

## 触发条件

- 使用 `codex exec` 执行任务
- 需要 full access 或 yolo 模式
- 解析 Codex JSON 输出
- Codex CLI 配置错误排查

## 前置检查

### 1. 验证配置文件

```bash
cat ~/.codex/config.toml
```

**常见配置错误：**

| 字段 | 错误值 | 有效值 |
|------|--------|--------|
| `model_reasoning_effort` | `xhigh` | `minimal`, `low`, `medium`, `high` |
| `model` | 过时模型名 | 检查 OpenAI 文档获取最新模型 |

### 2. 检查项目信任级别

确保工作目录已配置为 trusted：

```toml
[projects."/path/to/project"]
trust_level = "trusted"
```

## 执行模式

### 模式选择

| 模式 | 命令 | 适用场景 |
|------|------|----------|
| **Auto** (默认) | `codex exec "..."` | 工作目录内操作，无网络 |
| **Full Auto** | `codex exec --full-auto "..."` | 工作目录内自动操作 |
| **Full Access** | `codex exec --sandbox danger-full-access "..."` | 需要网络或跨目录 |
| **YOLO** | `codex exec --yolo "..."` | 完全信任，无任何限制 |

### 推荐命令模板

```bash
# 标准执行（需要网络）
cd /path/to/project
codex exec --yolo "任务描述"

# JSON 输出（用于解析）
codex exec --yolo --json "任务描述"

# 指定输出文件
codex exec --yolo -o result.txt "任务描述"
```

## JSON 输出解析

### 输出结构

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 配置信息（首行）                                          │
│    model, sandbox, approval, workdir                        │
├─────────────────────────────────────────────────────────────┤
│ 2. 事件流（JSONL 格式）                                      │
│    • task_started       - 任务开始                          │
│    • agent_reasoning    - Agent 推理过程                    │
│    • exec_command_begin - 命令执行开始                      │
│    • exec_command_end   - 命令执行结束（含 exit_code）       │
│    • token_count        - Token 用量统计                    │
│    • agent_message      - 最终回复                          │
└─────────────────────────────────────────────────────────────┘
```

### jq 解析示例

```bash
# 提取最终 agent 消息
codex exec --yolo --json "..." | jq 'select(.msg.type == "agent_message") | .msg.message'

# 提取命令执行结果
codex exec --yolo --json "..." | jq 'select(.msg.type == "exec_command_end") | .msg'

# 提取 exit_code
codex exec --yolo --json "..." | jq 'select(.msg.type == "exec_command_end") | .msg.exit_code'

# 提取 token 使用量
codex exec --yolo --json "..." | jq 'select(.msg.type == "token_count") | .msg.info.total_token_usage'

# 完整日志 + 提取最终消息
codex exec --yolo --json "..." | tee full_log.jsonl | jq -s 'map(select(.msg.type == "agent_message")) | last'
```

### 事件类型详解

| 事件类型 | 字段 | 说明 |
|----------|------|------|
| `task_started` | `model_context_window` | 上下文窗口大小 |
| `agent_reasoning` | `text` | 推理过程文本 |
| `exec_command_begin` | `command`, `cwd` | 执行的命令和目录 |
| `exec_command_end` | `exit_code`, `stdout`, `stderr`, `duration` | 执行结果 |
| `token_count` | `total_token_usage` | 输入/输出 token 统计 |
| `agent_message` | `message` | Agent 最终回复 |

## 常见问题排查

### 1. 配置反序列化错误

```
Error: unknown variant `xhigh`, expected one of `minimal`, `low`, `medium`, `high`
in `model_reasoning_effort`
```

**修复：** 编辑 `~/.codex/config.toml`，将无效值改为有效选项。

### 2. 网络请求失败

```
TypeError: fetch failed
```

**原因：** Codex 内部使用 Node.js 原生 fetch，不自动使用 HTTP_PROXY。

**解决：**
- 方案 A：Codex 会自动设置代理（如果 shell 环境已配置）
- 方案 B：确保 `~/.zshrc` 或 `~/.bashrc` 中已配置代理

### 3. 权限不足

```
Error: sandbox blocked write outside workspace
```

**修复：** 使用 `--yolo` 或 `--sandbox danger-full-access`。

### 4. 项目未信任

```
Error: workspace not trusted
```

**修复：** 在 `~/.codex/config.toml` 添加项目信任配置。

## 最佳实践

1. **先验证配置**：执行前检查 `config.toml` 有效性
2. **选择最小权限**：优先 `--full-auto`，仅在需要时用 `--yolo`
3. **保存 JSON 日志**：用 `tee` 保存完整日志便于调试
4. **明确任务描述**：提示词要具体，说明期望输出格式

## 示例工作流

```bash
# 1. 进入项目目录
cd /path/to/project

# 2. 执行任务并保存日志
codex exec --yolo --json "运行测试并返回失败用例" 2>/dev/null | tee codex_output.jsonl

# 3. 提取关键信息
cat codex_output.jsonl | jq 'select(.msg.type == "agent_message") | .msg.message'

# 4. 检查执行状态
cat codex_output.jsonl | jq 'select(.msg.type == "exec_command_end") | {cmd: .msg.command, exit: .msg.exit_code}'
```
