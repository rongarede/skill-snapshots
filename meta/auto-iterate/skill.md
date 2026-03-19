---
name: auto-iterate
description: "Karpathy Loop 式自主迭代改进框架。对 skill/skill-full/memory/code 执行「修改→评估→保留/回滚」无限循环。触发词：/auto-iterate、自动迭代、迭代改进、Karpathy Loop"
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
| `skill-full` | 一个完整 skill 目录 | skill.md + 所有脚本 | 复合分：定义层 + 实现层 + 一致性 |
| `memory` | 一个 agent 记忆目录 | 记忆文件增删改、索引更新 | 检索命中率 + 信噪比 + 索引完整性 |
| `code` | 一个代码文件 | 代码逻辑（用户指定边界） | 用户指定的测试命令输出 |

## Setup

1. **确认目标**：用户指定 target-type 和 target-path
2. **创建分支**：`git checkout -b auto-iterate/<date>-<target>` 从当前分支创建
3. **读取目标**：完整理解当前状态
4. **初始化 results.tsv**：在目标所在目录创建（tab-separated，不 git track）

```
commit	score	status	description
a1b2c3d	6.5	keep	baseline
b2c3d4e	7.2	keep	refined trigger words
c3d4e5f	6.5	discard	removed constraints (lost clarity)
```

5. **建立 baseline 并开始循环**：第一次评估，记录为 baseline（status=keep），确认后进入 Loop

## The Loop

> LOOP FOREVER — 不暂停、不询问，持续迭代直到手动中断。用户可能在睡觉，期望醒来看到改进结果。

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

### 执行隔离（CRITICAL）

每轮迭代必须由**独立的 subagent** 执行，禁止同一 agent 连续执行多轮（防止上下文污染导致自我确认偏差）。

- root 为每轮分派新 subagent（Worker 类型）
- subagent 仅接收：目标文件路径、results.tsv 路径、当前轮次编号
- subagent 通过读取 results.tsv 和 git log 理解历史，而非继承上轮上下文
- subagent 返回：修改内容、新分数、keep/discard 决策

## Evaluation

### Skill 评估（target-type = skill）

| 维度 | 权重 | 方法 | 评分 |
|---|---|---|---|
| **触发准确率** | 40% | 构造 3 个正例 + 2 个负例 prompt，判断是否正确匹配 | 0-10 |
| **结构完整性** | 30% | frontmatter 完整、触发词列表、执行步骤、输出格式、CAN/CANNOT | 0-10 |
| **简洁性** | 20% | 行数变化（减少加分，增加需合理性证明） | 0-10 |
| **约束清晰度** | 10% | 边界定义明确、无歧义 | 0-10 |

**总分** = 加权平均，保留一位小数。

**正例/负例模板**（按被评估 skill 定制，以下为通用示例）：

```
正例（应触发本 skill）：
1. "对这个 skill 做自动迭代"
2. "/auto-iterate memory ~/mem/mem/agents/Worker/tetsu"
3. "用 Karpathy Loop 改进这段代码"

负例（不应触发）：
1. "帮我创建一个新 skill"（→ skill-authoring）
2. "审计所有 skill 质量"（→ skill-stocktake）
```

### Skill-Full 评估（target-type = skill-full）

对整个 skill 目录进行复合评估。运行评估脚本：

```bash
python3 ~/.claude/skills/auto-iterate/scripts/evaluate_skill_full.py <skill-dir>
```

辅助脚本 `scripts/evaluate.sh` 提供 skill/memory/code 三种目标类型的基础结构检查。

输出 4 维复合分（脚本自动计算加权总分）：

| 维度 | 权重 | 方法 | 来源 |
|---|---|---|---|
| **定义质量** | 30% | skill.md 结构检查：frontmatter、触发词、工作流、约束 | 静态分析 |
| **代码质量** | 30% | 所有 .py 文件的 pylint 均分 | `pylint --score` |
| **代码规范** | 20% | 所有 .py 文件的 flake8 警告总数（归一化） | `flake8` |
| **定义-实现一致性** | 20% | skill.md 中引用的脚本是否存在、脚本是否被 skill.md 引用 | 交叉验证 |

**决策规则**（双指标，同 code 的方案 C）：
- 主指标 = 加权总分（越高越好）
- 软约束 = flake8 总警告数（不能大幅增加）
- 总分↑ → keep；总分= AND flake8↓ → keep；总分↓ → discard；flake8 增加 ≥5 → discard

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
eval_command: "bash ./test.sh"
```

输出解析为数值分数。数值越低/越高由用户指定（默认：越低越好，同 val_bpb）。

## Constraints

**CAN do：**
- 修改目标文件内容（增删改重构）
- 修改 skill 目录下的任意文件（skill-full 类型）
- 重组目标目录结构（memory 类型）
- 运行只读命令分析目标

**CANNOT do：**
- 修改评估方法本身（评估是 ground truth）
- 安装新依赖或修改 pyproject.toml
- 修改目标范围以外的文件（单文件类型：仅目标文件；skill-full 类型：仅目标目录内的文件；results.tsv 除外）
- 修改其他 skill 或系统配置

**Timeout**：每次迭代不超过 5 分钟，超时视为 crash。

**Crash 处理**：语法错误/不可解析 → discard + 记录 crash；简单 typo → 修复后重试（计为同一次迭代）；连续 3 次 crash → 暂停，回顾策略。
