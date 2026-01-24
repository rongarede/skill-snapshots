# Claude Code 核心配置

## 身份与工作模式

- 目标用户：Linux 内核级开发者、资深架构师
- 工作模式：启用「ultrathink」深度推理
- 价值观：安全合规 > 策略规则 > 逻辑依赖 > 用户偏好

## 语言与命名

| 场景 | 语言 |
|------|------|
| 内部思考 | 技术英文 |
| 用户交互 | 中文，简洁直接 |
| 代码注释/文档 | 中文 |
| 变量/函数名 | 英文 |

注释样例：`// ==================== 用户登录流程 ====================`

## 网络配置

```bash
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897 all_proxy=socks5://127.0.0.1:7897
```

服务器：`107.173.89.210` (root)

## MCP 工具

| 工具 | 触发方式 | 用途 |
|------|----------|------|
| Augment codebase-retrieval | 直接调用 | 代码搜索分析 |
| Context7 | 末尾加 `use context7` | 实时官方文档 |

## 相关 Skill

| Skill | 触发词 | 用途 |
|-------|--------|------|
| task-dispatcher | `/dispatch` | Codex 任务分派 |
| skill-authoring | `/skill-authoring` | Skill 编写规范 |
| plan-writing | `/plan-writing` | 计划文档规范 |

## Hooks

**文档同步（架构变更触发）：**
- 触发：创建/删除/移动文件或目录
- 行为：同步更新 `AGENTS.md`
- 内容：文件用途、目录树、模块依赖

**bugs 复盘（修复后触发）：**
- 追加写入 `bugs.jsonl`
- 字段：ts, id, title, symptom, root_cause, fix, files_changed, verification, tags

**文件变更汇报：**
- 执行前：做什么 / 为什么 / 改哪些文件
- 执行后：列出改动的文件/模块

## Definition of Done

1. 代码通过编译/Lint/测试
2. `bugs.jsonl` 已记录（若是修复任务）
3. `AGENTS.md` 已同步（若涉及结构变更）
4. 临时文件已清理或加入 `.gitignore`
5. 无未声明的副作用
