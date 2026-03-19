---
name: auto-iterate
description: "Karpathy Loop 式自主迭代改进框架。对 skill/memory/code 执行「修改→评估→保留/回滚」无限循环。触发词：/auto-iterate、自动迭代、迭代改进、Karpathy Loop"
---

# auto-iterate

基于 [karpathy/autoresearch](https://github.com/karpathy/autoresearch) 的自主迭代改进框架。

给定一个目标，AI agent 自主执行「修改 → 评估 → 保留/回滚」循环，持续改进直到被中断。

## 触发方式

- `/auto-iterate <target-type> <target-path>`
- 「自动迭代 X」「迭代改进 X」「Karpathy Loop」

## 目标类型

| target-type | 目标 | 可修改内容 | 评估指标 |
|---|---|---|---|
| `skill` | 一个 SKILL.md 文件 | 触发词、流程、约束、结构 | 触发准确率 + 结构完整性 + 简洁性 |
| `memory` | 一个 agent 记忆目录 | 记忆文件增删改、索引更新 | 检索命中率 + 信噪比 + 索引完整性 |
| `code` | 一个代码文件 | 代码逻辑（用户指定边界） | 用户指定的测试命令输出 |

## Setup

1. **确认目标**：用户指定 target-type 和 target-path
2. **创建分支**：`git checkout -b auto-iterate/<date>-<target>` 从当前分支创建
3. **读取目标**：完整理解当前状态
4. **初始化 results.tsv**：在目标所在目录创建（不 git track）

```
commit	score	status	description
```

5. **建立 baseline**：第一次评估，记录为 baseline（status=keep）
6. **确认并开始循环**

## The Loop

> LOOP FOREVER — 循环开始后不暂停询问。持续迭代直到手动中断。

```
1. 读 git log + results.tsv，理解历史
2. 分析目标，提出一个聚焦的改进点
3. 修改目标文件
4. git commit -m "auto-iterate: <改动简述>"
5. 评估（见下方 Evaluation）
6. score 提升？ → keep（保留 commit）
   score 不变/下降？ → git reset --hard HEAD~1（回滚）
7. 追加一行到 results.tsv
8. 回到步骤 1
```

### 策略指导

- **先低垂果实**：从最明显的问题开始（缺失字段、冗余内容、错误约束）
- **单点改动**：每次只改一个方面，便于归因
- **简洁性标准**：同分数下改动更少更优。删代码且不降分 = 最佳结果
- **想法用尽时**：重读目标文件、回顾 results.tsv、尝试组合差点成功的方案、尝试激进改动
- **不要重复**：results.tsv 中 discard 的方案不要原样重试

## Evaluation

### Skill 评估（target-type = skill）

| 维度 | 权重 | 方法 | 评分 |
|---|---|---|---|
| **触发准确率** | 40% | 构造 3 个正例 + 2 个负例 prompt，判断是否正确匹配 | 0-10 |
| **结构完整性** | 30% | frontmatter 完整、触发词列表、执行步骤、输出格式、CAN/CANNOT | 0-10 |
| **简洁性** | 20% | 行数变化（减少加分，增加需合理性证明） | 0-10 |
| **约束清晰度** | 10% | 边界定义明确、无歧义 | 0-10 |

**总分** = 加权平均，保留一位小数。

**正例/负例模板**：

```
正例（应触发）：
1. "帮我改进这个 skill 的触发词"
2. "对 memory 做一轮自动迭代"
3. "/auto-iterate skill ~/.claude/skills/xxx/skill.md"

负例（不应触发）：
1. "帮我创建一个新 skill"（→ skill-authoring）
2. "审计这个 skill 的质量"（→ skill-stocktake）
```

### Memory 评估（target-type = memory）

| 维度 | 权重 | 方法 | 评分 |
|---|---|---|---|
| **检索命中率** | 50% | 3 个任务关键词执行 `cli.py retrieve`，判断 top-3 是否相关 | 0-10 |
| **信噪比** | 30% | 含反馈信号的文件数 / 总文件数（排除结构文件） | 0-10 |
| **索引完整性** | 20% | MEMORY.md 条目 vs 实际文件的一致性 | 0-10 |

### Code 评估（target-type = code）

用户在 setup 阶段指定评估命令，例如：

```bash
# 示例
eval_command: "uv run train.py > run.log 2>&1 && grep '^val_bpb:' run.log"
eval_command: "pytest --tb=short -q"
eval_command: "bash scripts/test.sh"
```

输出解析为数值分数。数值越低/越高由用户指定（默认：越低越好，同 val_bpb）。

## Results Logging

`results.tsv`（tab-separated，不 git track）：

```
commit	score	status	description
a1b2c3d	6.5	keep	baseline
b2c3d4e	7.2	keep	refined trigger words, added negative examples
c3d4e5f	6.5	discard	removed constraints section (lost clarity)
d4e5f6g	0.0	crash	syntax error in frontmatter
e5f6g7h	7.8	keep	simplified workflow, merged redundant steps
```

## Constraints

**CAN do：**
- 修改目标文件内容（增删改重构）
- 重组目标目录结构（memory 类型）
- 运行只读命令分析目标

**CANNOT do：**
- 修改评估方法本身（评估是 ground truth）
- 安装新依赖或修改 pyproject.toml
- 修改目标文件以外的文件
- 修改其他 skill 或系统配置

**Timeout**：每次迭代不超过 3 分钟。超过 5 分钟视为 crash。

**Crash 处理**：
- 语法错误/不可解析 → discard + 记录 crash
- 简单 typo → 修复后重试（计为同一次迭代）
- 连续 3 次 crash → 暂停，回顾策略

**NEVER STOP**：循环开始后不主动暂停。持续迭代直到被手动中断。如果想法用尽，重读目标、回顾历史、尝试组合方案、尝试激进改动。用户可能在睡觉，期望醒来看到改进结果。

## 与 /loop 配合

可与 `/loop` skill 配合实现定时迭代：

```
/loop 5m "/auto-iterate skill ~/.claude/skills/xxx/skill.md"
```

每轮 `/loop` 执行一次完整迭代（步骤 1-8），results.tsv 和 git log 提供跨轮次连续性。

## 灵感来源

[karpathy/autoresearch](https://github.com/karpathy/autoresearch) — "The Karpathy Loop"：
一个文件 + 一个指标 + 固定预算 = 约束下的自主创造力。
