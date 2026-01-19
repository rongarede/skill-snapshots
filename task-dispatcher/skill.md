---
name: task-dispatcher
description: "PROACTIVE: Automatically route tasks between Claude and Codex based on task type. MUST be invoked for ANY development task (implement, fix, refactor, test, review, optimize) to determine whether Claude or Codex should execute."
---

# Task Dispatcher

**自动**识别任务类型，路由到 Claude 或 Codex 执行。

## 自动触发规则

<IMPORTANT>
此 Skill 必须在以下情况**自动触发**，无需用户显式调用：

1. 用户请求**实现/编写**任何代码
2. 用户请求**修复/修改**任何代码
3. 用户请求**重构/优化**任何代码
4. 用户请求**测试/覆盖**任何代码
5. 用户请求**审查/review**任何代码
6. 用户请求**文档/注释**任何代码

**识别关键词**（中/英文）：
- 实现、implement、编写、write、创建、create
- 修复、fix、修改、modify、更新、update
- 重构、refactor、优化、optimize、简化、simplify
- 测试、test、覆盖、coverage、mock
- 审查、review、评审、audit
- 文档、document、注释、comment
</IMPORTANT>

## 路由决策树

```
用户请求
    │
    ▼
┌─────────────────────────────────────────┐
│ 是否包含 Codex 关键词？                  │
│ (实现/编写/修复/重构/测试/文档)          │
└─────────────────────────────────────────┘
    │                           │
    ▼ 是                        ▼ 否
┌─────────────┐          ┌─────────────┐
│ 是否需要    │          │ Claude 执行  │
│ 深度推理？  │          └─────────────┘
└─────────────┘
    │         │
    ▼ 是      ▼ 否
┌────────┐  ┌────────────────┐
│ Claude │  │ 委托给 Codex   │
│ 规划   │  │ codex-executor │
│   ↓    │  └────────────────┘
│ Codex  │
│ 执行   │
└────────┘
```

## 路由规则

### → Codex 执行（快速编码任务）

**直接委托给 Codex**，Claude 仅做验收：

| 任务类型 | 关键词 | 示例 |
|----------|--------|------|
| 代码生成 | 实现、编写、创建、添加 | "实现 login 函数" |
| 代码修改 | 修复、修改、更新、改 | "修复这个 bug" |
| 代码重构 | 重构、简化、提取、合并 | "重构这个类" |
| 测试编写 | 测试、单测、覆盖、mock | "写单元测试" |
| 文档生成 | 文档、注释、README | "添加注释" |

**执行方式**：
```bash
# Claude 调用 codex-executor subagent
Task(subagent_type="codex-executor", prompt="...")
```

### → Claude 执行（深度推理任务）

**Claude 直接处理**：

| 任务类型 | 关键词 | 示例 |
|----------|--------|------|
| 需求分析 | 分析、理解、解释、为什么 | "分析这段代码" |
| 技术设计 | 设计、架构、方案、如何 | "设计 API 结构" |
| 任务规划 | 规划、拆分、步骤、计划 | "规划实现步骤" |
| 复杂调试 | 调试、根因、诊断、排查 | "诊断性能问题" |
| 技术决策 | 选择、比较、权衡、推荐 | "推荐技术方案" |

### → 双重验证（Claude + Codex）

**先 Claude 后 Codex**：

| 任务类型 | 流程 |
|----------|------|
| 安全审计 | Claude 分析威胁模型 → Codex 扫描代码 |
| 性能优化 | Claude 分析瓶颈 → Codex 实现优化 |
| 代码审查 | Claude 审查逻辑 → Codex 审查风格 |

## 自动执行流程

### 第一步：识别任务类型

```python
# 伪代码
def classify_task(user_input):
    codex_keywords = ["实现", "编写", "修复", "重构", "测试", "文档",
                      "implement", "write", "fix", "refactor", "test", "doc"]
    claude_keywords = ["分析", "设计", "规划", "调试", "决策", "解释",
                       "analyze", "design", "plan", "debug", "decide", "explain"]

    if any(kw in user_input for kw in codex_keywords):
        if needs_planning(user_input):  # 复杂任务
            return "claude_then_codex"
        return "codex"
    return "claude"
```

### 第二步：显示分派结果

```markdown
## 🔀 任务分派

| 项目 | 值 |
|------|-----|
| 任务 | {task} |
| 类型 | {type} |
| 执行 | **{executor}** |

{开始执行...}
```

### 第三步：执行任务

#### Codex 执行模式

```
[委托给 Codex]

cd {project_dir} && codex exec --yolo --json "
{task_description}

工作目录: {cwd}
目标文件: {files}
要求: {requirements}
"
```

#### Claude 执行模式

直接在主会话执行，输出详细推理。

#### Claude → Codex 模式

1. Claude 完成规划/分析
2. 将具体实现委托给 Codex
3. Claude 验收 Codex 结果

## 委托模板

### 代码实现

```
任务: {description}
目录: {project_path}
文件: {target_files}

规格:
- 功能: {function_spec}
- 输入: {input}
- 输出: {output}
- 约束: {constraints}

请用中文回复，实现完整代码。
```

### Bug 修复

```
问题: {bug_description}
文件: {file}:{line}
根因: {root_cause}
方案: {fix_approach}

请实现修复并添加回归测试。
```

### 代码重构

```
目标: {refactor_goal}
范围: {files}
约束:
- 保持 API 兼容
- 不改变行为
- 添加必要测试

请执行重构。
```

## 示例

### 示例 1: 简单实现 → Codex

```
用户: 实现一个计算斐波那契数列的函数

分派: → Codex
原因: 简单编码任务，无需深度规划

执行:
[调用 codex-executor]
codex exec --yolo "实现 fibonacci 函数..."
```

### 示例 2: 复杂功能 → Claude + Codex

```
用户: 实现用户认证系统

分派: → Claude 规划 + Codex 实现
原因: 需要架构设计

执行:
1. [Claude] 设计认证流程、API 接口、数据模型
2. [Codex] 实现 AuthService
3. [Codex] 实现中间件
4. [Codex] 编写测试
5. [Claude] 验收审查
```

### 示例 3: 分析任务 → Claude

```
用户: 分析这段代码为什么性能差

分派: → Claude
原因: 需要深度推理

执行:
[Claude 直接分析]
1. 阅读代码
2. 识别瓶颈
3. 给出优化建议
```

## 注意事项

1. **自动触发**: 检测到开发任务关键词时自动分派
2. **显示分派**: 始终告知用户当前执行者
3. **Claude 协调**: Claude 始终作为协调者和验收者
4. **失败回退**: Codex 失败时由 Claude 接管
5. **用户覆盖**: 用户可显式指定执行者
