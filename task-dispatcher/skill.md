---
name: task-dispatcher
description: "路由开发任务到 Codex 执行。触发词：/dispatch、任务分派。默认 Codex 执行，自动拆分任务、设置验证、支持并发分派。"
---

# Task Dispatcher

**核心策略**：任务细分 → 验证定义 → 并发分派 → Codex 执行 → 结果验收

## 触发方式

- `/dispatch <任务描述>`
- `/task-dispatcher`
- 检测到开发任务时自动触发

## 核心原则

| 原则 | 描述 |
|------|------|
| 先拆分，后执行 | 任务必须细分到单一职责 |
| 先验证，后分派 | 每个子任务必须有验证命令 |
| 可并发则并发 | 无依赖的任务并行执行 |
| 失败有回退 | 预定义失败处理策略 |

## 工作流程

```
用户请求 → 是否需要深度推理？
              │
      ┌───────┴───────┐
      ▼ 是            ▼ 否
  Claude 推理    任务拆分 → 定义验证 → 依赖分析 → 并发分派
      │               │
      └───────┬───────┘
              ▼
         验证结果 → 通过/失败回退
```

## 第一步：任务拆分

### 拆分原则

| 原则 | 示例 |
|------|------|
| 单一职责 | ❌ "实现并测试登录" → ✅ "实现登录" + "测试登录" |
| 单文件 | ❌ "重构 A 和 B" → ✅ "重构 A" + "重构 B" |
| 可验证 | 每个子任务必须有对应的验证命令 |
| 原子性 | 执行失败可独立回退 |

### 拆分判断

使用脚本判断是否需要拆分：

```bash
python ~/.claude/skills/task-dispatcher/scripts/task-logic.py should-split "任务描述"
```

**必须拆分的情况**：
- 包含「并」「和」「+」连接词
- 涉及多个文件
- 包含多个动词（实现、测试、重构...）
- 预估变更超过 100 行

## 第二步：定义验证

每个子任务必须有验证命令，参考 `templates/verification-reference.md`

| 任务类型 | 验证命令 |
|----------|----------|
| TypeScript | `tsc --noEmit` |
| Rust | `cargo check` |
| 单测 | `npm test -- --grep '{pattern}'` |
| API | `curl -s {url} \| jq .{field}` |

## 第三步：依赖分析

使用脚本分析依赖关系，生成执行批次：

```bash
python ~/.claude/skills/task-dispatcher/scripts/task-logic.py analyze-deps '[{"id":1,"deps":[]},{"id":2,"deps":[1]}]'
```

### 并发规则

| 条件 | 并发? |
|------|-------|
| 无依赖 | ✅ 并发 |
| 不同文件 | ✅ 并发 |
| 同文件不同函数 | ⚠️ 串行 |
| 有显式依赖 | ❌ 串行 |

## 第四步：并发分派

在**单个消息**中调用多个 Task 实现并发：

```
批次 1 (并发):
- Task(subagent_type="codex-executor", prompt=任务1)
- Task(subagent_type="codex-executor", prompt=任务2)

等待批次 1 完成...

批次 2 (并发):
- Task(subagent_type="codex-executor", prompt=任务3)
```

## 第五步：失败回退

| 失败类型 | 策略 |
|----------|------|
| 编译错误 | Codex 重试 + 错误信息 |
| 测试失败 | Codex 重试 + 失败用例 |
| 连续 2 次失败 | Claude 接管分析 |

重试时使用 `templates/codex-retry.md` 模板。

## 委托模板

| 模板 | 用途 |
|------|------|
| `templates/codex-task.md` | 标准 Codex 任务 |
| `templates/codex-task-optimized.md` | 优化版（限制读取范围） |
| `templates/codex-retry.md` | 重试任务 |
| `templates/dispatch-report.md` | 分派报告 |

## Token 优化

**默认约束（添加到每个 Codex prompt）**：
- 禁止读取 node_modules 目录
- 禁止读取 target、dist、build 目录
- 单次任务读取文件不超过 20 个

**优化策略**：
- 内联参考代码（不要说「参考 sdk.ts」，直接贴代码）
- 限定文件范围（明确列出路径 + 行号）
- 给出实现骨架

### Token 检查

| input_tokens | 状态 | 行动 |
|--------------|------|------|
| < 500K | ✅ 正常 | 继续 |
| 500K - 1M | ⚠️ 警告 | 检查不必要文件 |
| > 1M | 🔴 异常 | 优化 prompt |
| > 5M | 🚨 严重 | 立即终止 |

## 目录结构

```
task-dispatcher/
├── skill.md                    # 本文件
├── scripts/
│   └── task-logic.py           # 拆分/依赖/验证逻辑
└── templates/
    ├── codex-task.md           # 标准任务模板
    ├── codex-task-optimized.md # 优化版任务模板
    ├── codex-retry.md          # 重试任务模板
    ├── dispatch-report.md      # 分派报告模板
    └── verification-reference.md # 验证命令参考
```

## 注意事项

1. **必须拆分**: 复杂任务必须拆分，禁止直接分派
2. **必须验证**: 每个子任务必须有验证命令
3. **优先并发**: 无依赖任务必须并发执行
4. **及时回退**: 连续失败立即 Claude 介入
5. **用户可见**: 显示完整分派报告
