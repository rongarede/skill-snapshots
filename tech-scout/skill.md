---
name: tech-scout
description: |
  技术探索调研工作流：将模糊想法转化为结构化调研，输出可复用的 Skill 或笔记。
  触发词：/tech-scout、技术调研、有没有现成实现、调研一下
thinking_mode: ultrathink
---

# Tech Scout - 技术探索调研

将「我想实现 X」转化为「这是最佳方案及其用法」。

## 执行要求

- **思考模式**: 强制使用 ultrathink / extended thinking
- **并行检索**: 阶段 2 使用 Task 子代理并行查询
- **用户确认**: 每个阶段转换前需用户确认

---

## 阶段 1: 意图澄清

收到调研请求后，依次询问（每次一个问题）：

**Q1 - 问题定义**
> 你想解决什么具体问题？请用一句话描述。

**Q2 - 技术偏好**（多选）
> 有技术栈偏好吗？
> 1. JavaScript/TypeScript
> 2. Python
> 3. Rust
> 4. Go
> 5. 无偏好

**Q3 - 成熟度要求**
> 对方案成熟度的要求？
> 1. 生产级（稳定、文档完善、社区活跃）
> 2. 成长期（可用但可能有坑）
> 3. 实验性也可以（愿意踩坑）

**Q4 - 集成约束**（可选）
> 需要与现有系统集成吗？如有，简述技术栈。

完成后生成「调研任务卡」：

```
┌─ 调研任务卡 ─────────────────────────┐
│ 问题: [用户描述]                     │
│ 技术栈: [偏好]                       │
│ 成熟度: [要求]                       │
│ 集成约束: [约束]                     │
│ 生成时间: [timestamp]                │
└──────────────────────────────────────┘
```

---

## 阶段 2: 广度检索

使用 Task 子代理并行执行。

### ⚠️ 子代理 WebFetch Fallback 规则（重要）

**子代理无法调用 Skill**，因此必须在 Task prompt 中内置以下 fallback 逻辑：

```markdown
## WebFetch 失败处理（必须遵守）

当 WebFetch 返回以下错误时：
- "Unable to verify if domain xxx is safe to fetch"
- "网络限制" / "access denied" / 任何失败

立即使用以下备选方案（按优先级）：

1. **WebSearch 替代**：搜索 "site:<domain> <关键词>" 获取摘要
2. **GitHub URL**：使用 Bash 执行 `gh api repos/<owner>/<repo>` 或 `gh repo view <owner>/<repo>`
3. **通用 URL**：使用 Bash 执行 `curl -sL "<URL>" | head -c 30000`
4. **如果 curl 也失败**：记录 URL，标记为"需主会话处理"，继续其他任务

示例：
- WebFetch github.com 失败 → `gh repo view owner/repo --json description,stargazerCount`
- WebFetch docs.example.com 失败 → `curl -sL "https://docs.example.com/guide" | head -c 30000`
```

### Agent 1: 搜索引擎
```
工具: WebSearch（主要）+ WebFetch（备选，带 fallback）
查询: [问题关键词] + [技术栈] + solution/library/framework
目标: 收集博客、教程、讨论帖

WebFetch 失败时：使用 WebSearch 搜索相同内容，或 curl 抓取
```

### Agent 2: GitHub 检索
```
工具: WebSearch + Bash (gh CLI)
查询: site:github.com [关键词] stars:>100
目标: 收集相关仓库，记录 stars/issues/last commit

⚠️ WebFetch 无法访问 github.com，必须使用：
- WebSearch: site:github.com [关键词]
- Bash: gh repo view <owner>/<repo> --json name,description,stargazerCount,updatedAt
- Bash: gh api repos/<owner>/<repo>
```

### Agent 3: 官方文档
```
工具: WebFetch（带 fallback）+ WebSearch
查询: [候选库名称] documentation
目标: 获取官方文档片段、快速入门指南

WebFetch 失败时：
1. WebSearch: "[库名] official documentation guide"
2. Bash: curl -sL "<doc-url>" | head -c 30000
```

### 结果聚合

去重后生成候选清单：

```
发现 N 个相关方案：

1. **[名称]** ⭐ [stars] | 📅 [最近更新]
   简介：[一句话]

2. **[名称]** ⭐ [stars] | 📅 [最近更新]
   简介：[一句话]

...

请选择要深入分析的方案（可多选，如 1,3,5）：
```

---

## 阶段 3: 深度评估

对用户选中的方案，逐一进行多维度分析：

### 评估维度

| 维度 | 检查项 | 数据来源 |
|------|--------|----------|
| 文档质量 | 是否有快速入门、API 文档、示例 | Context7 / `/fetch` skill |
| 社区活跃 | Issue 响应速度、PR 合并频率 | `/fetch` skill (GitHub URL) |
| 维护状态 | 最近 commit、release 频率 | `/fetch` skill (GitHub URL) |
| 上手难度 | 依赖复杂度、配置量 | 文档 + 代码 |
| 兼容性 | 与用户技术栈的集成难度 | 文档 + 经验 |

### 输出格式

```
## [方案名称] 深度分析

### 优势
- ...

### 劣势
- ...

### 快速上手示例
[代码片段]

### 评分
| 维度 | 评分 (1-5) | 备注 |
|------|------------|------|
| 文档质量 | 4 | ... |
| 社区活跃 | 5 | ... |
| ... | ... | ... |

### 结论
[是否推荐 + 适用场景]
```

---

## 阶段 4: 综合推荐

完成所有评估后，给出综合推荐：

```
## 调研结论

### 推荐方案: [名称]
推荐理由：...

### 备选方案: [名称]
适用场景：...

### 不推荐: [名称]
原因：...
```

---

## 阶段 5: 输出选择

询问用户输出格式：

> 调研完成！选择输出格式：
> 1. **生成 Skill** - 将此调研流程/最佳实践转为可复用 Skill
> 2. **生成技术笔记** - 保存为 Markdown 笔记（含代码示例）
> 3. **生成决策文档** - 保存方案对比表 + 推荐理由
> 4. **保存到 Memory** - 轻量记录，供后续对话调用
> 5. **不保存** - 仅本次对话使用

根据选择执行对应的输出适配器。

---

## 输出适配器

### 适配器 1: 生成 Skill

判断是否适合转 Skill：
- ✅ 调研发现了可复用的工作流
- ✅ 未来会多次执行类似任务
- ✅ 流程可参数化

生成路径: `~/.claude/skills/[skill-name]/skill.md`

### 适配器 2: 生成技术笔记

使用模板 `templates/note-output.md`：

保存路径: `docs/notes/YYYY-MM-DD-[topic].md` 或用户指定的 Obsidian vault

### 适配器 3: 生成决策文档

使用模板 `templates/decision-output.md`：

保存路径: `docs/decisions/YYYY-MM-DD-[topic].md`

### 适配器 4: 保存到 Memory

调用 Memory MCP 保存关键信息：
- 问题描述
- 推荐方案
- 关键结论
- 参考链接

---

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| MCP 不可用 | 降级到内置 WebSearch/WebFetch |
| 搜索无结果 | 扩展关键词，尝试相关领域 |
| **子代理 WebFetch 失败** | **使用内置 fallback（见阶段 2）** |
| **主会话 WebFetch 失败** | **调用 `/fetch` skill** |
| 用户中断 | 保存当前进度到 Memory |

### 子代理 WebFetch 失败处理（内置）

子代理**无法调用 Skill**，因此在启动 Task 时必须在 prompt 中包含以下 fallback 指令：

```markdown
## WebFetch Fallback（子代理必须遵守）

当 WebFetch 失败时，按以下顺序尝试：

1. **GitHub URL** → `gh repo view <owner>/<repo> --json name,description,stargazerCount`
2. **其他 URL** → `curl -sL "<URL>" | head -c 30000`
3. **都失败** → 使用 WebSearch 搜索相关内容
4. **仍失败** → 记录 URL，标记"需主会话处理"，继续其他任务
```

### 主会话 WebFetch 失败处理

当主会话中 WebFetch 返回以下错误时，**调用 `/fetch` skill**：
- `Unable to verify if domain xxx is safe to fetch`
- `网络限制或企业安全策略阻止`
- 任何域名访问失败

**调用方式：**
```
使用 Skill 工具调用 web-fetch-fallback:
skill: "web-fetch-fallback"
args: "<失败的 URL>"
```

`/fetch` skill 会自动选择最优的抓取方式（gh CLI / curl+pandoc / agent-browser）。

---

## MCP 依赖（可选增强）

| MCP | 用途 | 必需 |
|-----|------|------|
| Context7 | 官方文档拉取 | 否 |
| Perplexity | AI 增强搜索 | 否 |
| GitHub MCP | 仓库分析 | 否 |
| Memory | 知识持久化 | 否 |

无 MCP 时使用内置 WebSearch/WebFetch 降级执行。
