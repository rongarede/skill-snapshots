---
name: task-dispatcher
description: Automatically route tasks between Claude and Codex based on task type. Use when starting any development task to determine the optimal execution strategy.
---

# Task Dispatcher

自动识别任务类型，路由到 Claude 或 Codex 执行。

## 触发条件

- 开始新的开发任务时
- 需要决定由谁执行时
- `/dispatch` 或 `/任务分派`

## 路由规则

### Claude 专属 (需要深度推理)

| 关键词 | 任务类型 |
|--------|----------|
| 分析、理解、评估 | 需求分析 |
| 设计、架构、方案 | 技术设计 |
| 规划、拆分、优先级 | 任务规划 |
| 决策、选择、权衡 | 技术决策 |
| 调试、根因、诊断 | 复杂调试 |
| 审查、验收、评审 | 代码审查 |

### Codex 专属 (需要快速执行)

| 关键词 | 任务类型 |
|--------|----------|
| 实现、编写、创建 | 代码生成 |
| 修复、修改、更新 | 代码修改 |
| 重构、优化、简化 | 代码重构 |
| 测试、覆盖、mock | 测试编写 |
| 文档、注释、README | 文档生成 |
| 格式化、规范、lint | 代码规范 |

### 双重验证 (Claude + Codex)

| 关键词 | 任务类型 |
|--------|----------|
| 安全、审计、漏洞 | 安全审计 |
| 性能、优化、瓶颈 | 性能优化 |
| review、PR、合并 | 代码审查 |

## 工作流程

### 第一步：识别任务类型

分析用户输入，提取关键词，匹配路由规则。

### 第二步：生成执行计划

```markdown
## 任务分派结果

**任务**: {task_description}
**类型**: {task_type}
**执行者**: Claude / Codex / 双重验证

### 执行计划

1. [Claude/Codex] {step_1}
2. [Claude/Codex] {step_2}
...
```

### 第三步：执行并协调

#### Claude 执行模式
直接在主会话中执行，输出详细推理过程。

#### Codex 执行模式
调用 codex-executor subagent：
```bash
codex exec --yolo --json "{task_prompt}"
```

#### 双重验证模式
1. Claude 先执行分析
2. 调用 Codex 获取第二意见
3. Claude 整合两方结果

## 委托模板

### 代码实现委托

```
[委托给 Codex]

任务: {task_description}
文件: {target_files}
规格:
  - 输入: {input_spec}
  - 输出: {output_spec}
  - 约束: {constraints}

请实现并返回完整代码。
```

### Bug 修复委托

```
[委托给 Codex]

问题: {bug_description}
位置: {file}:{line}
根因: {root_cause} (Claude 已分析)
修复方案: {fix_approach}

请实现修复并添加回归测试。
```

### 代码审查委托

```
[委托给 Codex]

审查范围: {files}
关注点:
  - 代码风格和最佳实践
  - 性能优化机会
  - 潜在的边界情况

请返回结构化的审查意见。
```

## 输出格式

```markdown
## 任务分派

| 项目 | 值 |
|------|-----|
| 任务 | {description} |
| 类型 | {type} |
| 路由 | {handler} |

### 执行计划

| 步骤 | 执行者 | 内容 |
|------|--------|------|
| 1 | Claude | {step} |
| 2 | Codex | {step} |
| ... | ... | ... |

### 开始执行

{execution_output}
```

## 示例

### 示例 1: 新功能开发

```
用户: 实现用户登录功能

分派结果:
- 类型: 新功能开发
- 路由: Claude 规划 + Codex 实现

执行计划:
1. [Claude] 设计 API 接口和认证流程
2. [Codex] 实现 AuthService.login()
3. [Codex] 编写单元测试
4. [Claude] 代码审查
5. [Codex] 修复问题
```

### 示例 2: Bug 修复

```
用户: 修复登录时 token 过期的问题

分派结果:
- 类型: Bug 修复
- 路由: Claude 分析 + Codex 修复

执行计划:
1. [Claude] 分析根因
2. [Claude] 制定修复方案
3. [Codex] 实现修复
4. [Codex] 添加测试
```

### 示例 3: 代码审查

```
用户: 审查最近的提交

分派结果:
- 类型: 代码审查
- 路由: 双重验证

执行计划:
1. [Claude] 审查逻辑正确性
2. [Codex] 审查风格和性能
3. [Claude] 整合意见并决策
```

## 注意事项

1. **明确边界**: 不确定时默认由 Claude 处理
2. **保持协调**: Claude 始终作为协调者
3. **验证结果**: Codex 输出需要 Claude 验收
4. **记录过程**: 保留分派和执行记录
