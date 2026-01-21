---
name: codex-parser
description: "解析 Codex CLI 输出日志，快速理解执行结果。触发词：/codex-parse、分析 codex 输出、查看 codex 日志"
---

# Codex Parser - Codex 日志解析器

快速解析 Codex CLI 的 NDJSON 日志输出，无需全量读取。

## 触发条件

- `/codex-parse`
- `/codex-parser`
- 「分析 codex 输出」
- 「查看 codex 日志」
- 「codex 执行了什么」

## 前置条件

目标目录需要先运行索引生成脚本：

```bash
bash <codex-outputs>/scripts/codex-index.sh
```

生成文件：
- `INDEX.json` - 结构化索引
- `MANIFEST.md` - 可读摘要

## 工作流程

### 模式 1: 快速概览（默认）

**读取 MANIFEST.md 即可**，包含：
- 执行统计表格（命令数、失败数、Token 用量）
- 失败命令列表
- 文件变更汇总

```bash
cat <codex-outputs>/MANIFEST.md
```

### 模式 2: 查询特定批次

用户指定批次时，读取对应日志的索引：

```bash
jq '.logs[] | select(.file | contains("batch-1"))' <codex-outputs>/INDEX.json
```

### 模式 3: 查询失败命令

```bash
jq '.logs[] | select(.stats.failed_commands > 0) | {file, failed: .failed_commands_detail}' <codex-outputs>/INDEX.json
```

### 模式 4: 查询文件变更

```bash
jq '.logs[] | {file, files_changed}' <codex-outputs>/INDEX.json
```

### 模式 5: 深入分析单个日志

当需要详细分析时，读取原始 .log 文件：

```bash
# 提取推理过程
jq -r 'select(.type == "item.completed" and .item.type == "reasoning") | .item.text' <log_file>

# 提取命令执行
jq -c 'select(.type == "item.completed" and .item.type == "command_execution") | {cmd: .item.command, exit: .item.exit_code, out: .item.aggregated_output[0:200]}' <log_file>

# 提取文件变更
jq -r 'select(.type == "item.completed" and .item.type == "file_change") | .item.changes[] | "\(.kind): \(.path)"' <log_file>
```

## 响应格式

### 概览响应

```
## Codex 执行概览

| 批次 | 命令 | 失败 | 文件变更 | Token |
|------|------|------|----------|-------|
| batch-1 | 38 | 8 | 8 | 1.4M |
| batch-2 | 109 | 92 | 12 | 5.2M |

**总计**: 147 命令，100 失败，20 文件变更

### 失败命令 (Top 5)
1. `npm install spl-token-bankrun` → exit 1
2. ...

### 主要文件变更
- AGENTS.md (6 次更新)
- CHANGELOG.md (6 次更新)
- tests/integration/shared/* (3 个新文件)
```

### 详情响应

```
## batch-1/P1-T01-T02.log 详情

**Thread ID**: 019bdfab-d47e-7ac0-af06-4a391ed8e77d
**Token**: 575K 输入 / 8K 输出

### 推理摘要
1. 决定使用 sed 直接修改文件
2. 检查 package.json 依赖
3. ...

### 执行命令 (16 条)
| # | 命令 | 结果 |
|---|------|------|
| 1 | `ls` | ✅ |
| 2 | `npm install spl-token-bankrun` | ❌ exit 1 |
| ... |

### 文件变更 (5 个)
- [update] AGENTS.md
- [update] CHANGELOG.md
- [update] package.json
```

## 索引刷新

当有新的 Codex 执行后，重新运行索引脚本：

```bash
bash <codex-outputs>/scripts/codex-index.sh
```

## 注意事项

1. **优先读取索引**: MANIFEST.md > INDEX.json > 原始 .log
2. **按需深入**: 只有用户要求详情时才读取原始日志
3. **路径灵活**: 支持任意 codex-outputs 目录，不限于 ipflow-v3
4. **增量索引**: 脚本会覆盖旧索引，无需手动清理
