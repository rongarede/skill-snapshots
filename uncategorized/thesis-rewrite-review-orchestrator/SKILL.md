---
name: thesis-rewrite-review-orchestrator
description: 学位论文章节循环改写编排器。用于“改写与评审上下文隔离 + subagent 分工 + peer-review/academic-writing/supportability 三重门禁 + 通过后才结束 round”的工作流。
---

# Thesis Rewrite Review Orchestrator

用于论文单章（如 `chapter2.tex`）的多轮改写与评审闭环，核心约束是：

- 改写与评审上下文必须隔离
- 改写、评审、支撑性评估必须由不同 subagent 执行
- 仅当三重门禁全部通过，round 才可结束

## 触发场景

- “循环改写直到评审通过”
- “改写与 review 上下文隔离”
- “peer review + academic writing 双评审”
- “评估 chapter2 能否支撑 chapter3/chapter4”

## 固定角色

- `rewrite-agent`：只负责改写，不做通过判定
- `peer-review-agent`：使用 `peer-review`，输出 `Critical/Major/Minor` 与 `must_fix`
- `academic-writing-agent`：使用 `academic-writing`，输出学术表达与论证链问题
- `supportability-agent`：输出 `chapter2 -> chapter3/chapter4` 映射矩阵与 `Missing` 计数

## 目录约定

每轮目录固定为：

- `tmp/ch2_rounds/round-<n>/rewrite/`
- `tmp/ch2_rounds/round-<n>/review/`
- `tmp/ch2_rounds/round-<n>/support/`
- `tmp/ch2_rounds/round-<n>/gate/`

上下文固定为：

- `rewrite/context.md`
- `review/context_peer.md`
- `review/context_academic.md`
- `support/context.md`

## 执行脚本

```bash
bash ~/.claude/skills/thesis-rewrite-review-orchestrator/scripts/main.sh <command> [args]
```

### 命令 1：初始化

```bash
bash ~/.claude/skills/thesis-rewrite-review-orchestrator/scripts/main.sh init \
  --target chapters/chapter2.tex \
  --out tmp/ch2_rounds \
  --max-rounds 6 \
  --round 1
```

作用：创建 round 目录、隔离上下文模板与执行记录文件。

### 命令 2：准备某一轮

```bash
bash ~/.claude/skills/thesis-rewrite-review-orchestrator/scripts/main.sh prep-round \
  --out tmp/ch2_rounds \
  --round 2
```

作用：补建/修复该轮目录与上下文模板。

### 命令 3：门禁判定

```bash
bash ~/.claude/skills/thesis-rewrite-review-orchestrator/scripts/main.sh gate \
  --out tmp/ch2_rounds \
  --round 2 \
  --max-rounds 6
```

默认读取：

- `review/peer_report.md`
- `review/academic_report.md`
- `support/supportability_report.md`

判定规则：

- peer-review: `decision: PASS`
- academic-writing: `decision: PASS`
- supportability: `decision: PASS` 且 `Missing count = 0`

输出：

- `gate/decision.md`
- `gate/must_fix.md`

若未通过且未达最大轮次，自动创建下一轮目录。

### 命令 4：查看状态

```bash
bash ~/.claude/skills/thesis-rewrite-review-orchestrator/scripts/main.sh status \
  --out tmp/ch2_rounds
```

作用：汇总各轮 gate 状态（PASS/FAIL/PENDING）。

## 使用流程

1. 执行 `init`，生成 round-1 模板。
2. 运行 4 个 subagent 分别写入改写、双评审、支撑性报告。
3. 执行 `gate`。
4. 若 FAIL：读取 `gate/must_fix.md`，仅回流结构化字段给下一轮 `rewrite-agent`。
5. 重复直到 PASS 或达到最大轮次。

## Guardrails

- 禁止在上下文包中互相复制 agent 的完整推理文本。
- 仅允许跨 agent 传递结构化字段：`must_fix[]`、`optional_fix[]`、`resolved[]`、`blockers[]`。
- 不改动 `\cite{}` / `\ref{}` / `\label{}` 键值。
- 不引入与论文主题无关领域内容。
