---
name: changelog
description: "在当前工作目录创建 changelog 文件夹，每日新增一个以日期命名的变更记录文件。触发词：/changelog、记录变更、更新日志、changelog"
---

# Changelog Skill

在项目目录下自动管理每日变更记录，每个工作目录独立维护 `changelog/` 文件夹。

## 触发条件

- `/changelog`
- `/记录变更`
- 「记录此次改动」
- 「更新 changelog」
- 任务完成后自动触发（见 hooks 配置）

## 核心规则

1. **目录隔离**: 每个项目目录独立维护 `changelog/` 文件夹
2. **日期分片**: 每天一个文件，格式 `YYYY-MM-DD.md`
3. **追加写入**: 同一天多次变更追加到同一文件
4. **时间戳**: 每条记录包含精确时间 `HH:MM:SS`

## 目录结构

```
your-project/
├── src/
├── package.json
└── changelog/           # 自动创建
    ├── 2026-01-18.md
    ├── 2026-01-19.md
    └── 2026-01-20.md    # 今日变更
```

## 执行脚本

```bash
bash ~/.claude/skills/changelog/scripts/append-changelog.sh \
  "工作目录" \
  "任务名称" \
  "改动点1,改动点2" \
  "file1.ts,file2.ts" \
  "验证结果" \
  "遗留问题"
```

## 参数说明

| 参数 | 位置 | 必填 | 说明 |
|------|------|------|------|
| work_dir | $1 | 否 | 工作目录，默认当前目录 |
| task_name | $2 | 是 | 任务名称 |
| changes | $3 | 否 | 关键改动，逗号分隔 |
| files | $4 | 否 | 涉及文件，逗号分隔 |
| verification | $5 | 否 | 验证方式与结果 |
| issues | $6 | 否 | 遗留问题 |

## 输出格式

每日 changelog 文件内容：

```markdown
# Changelog - 2026-01-20

> 本文件记录 2026-01-20 的所有变更。

---

## 10:30:00 - 实现用户登录功能

**关键改动:**
- 添加 login API
- 集成 JWT 认证
- 前端表单验证

**涉及文件:**
- `src/api/auth.ts`
- `src/components/LoginForm.tsx`

**验证:** npm test 通过，手动测试登录流程正常

---

## 14:20:00 - 修复 Token 过期问题

**关键改动:**
- 增加 token 刷新机制

**涉及文件:**
- `src/utils/auth.ts`

**验证:** 复现步骤验证通过

**遗留问题:** 需监控生产环境 token 刷新频率

---
```

## CLAUDE.md hooks 配置（可直接复制）

将以下内容添加到项目 `CLAUDE.md` 的 `<hooks>` 区块：

```markdown
CHANGELOG（任务完成后强制追加）：

- **触发条件：** 完成一个明确的任务/子任务后
- **强制行为：** 执行 changelog skill 记录变更
- **执行命令：**
  ```bash
  bash ~/.claude/skills/changelog/scripts/append-changelog.sh \
    "$(pwd)" \
    "任务名称" \
    "改动点1,改动点2,改动点3" \
    "涉及文件1,涉及文件2" \
    "验证方式与结果" \
    "遗留问题（如有）"
  ```
- **必填字段：** 工作目录、任务名称、关键改动点、涉及文件、验证结果
- **可选字段：** 遗留问题与下一步
- **存储位置：** `{工作目录}/changelog/{YYYY-MM-DD}.md`
- **原则：** 信息不足标注 TODO，严禁编造
```

## 使用示例

### 示例 1：开发任务记录

```bash
bash ~/.claude/skills/changelog/scripts/append-changelog.sh \
  "/Users/bit/projects/myapp" \
  "实现用户登录功能" \
  "添加 login API,集成 JWT 认证,前端表单验证" \
  "src/api/auth.ts,src/components/LoginForm.tsx" \
  "npm test 通过，手动测试登录流程正常"
```

### 示例 2：Bug 修复记录

```bash
bash ~/.claude/skills/changelog/scripts/append-changelog.sh \
  "." \
  "修复 Token 过期问题" \
  "增加 token 刷新机制,优化错误提示" \
  "src/utils/auth.ts" \
  "复现步骤验证通过" \
  "需监控生产环境 token 刷新频率"
```

### 示例 3：配置变更记录

```bash
bash ~/.claude/skills/changelog/scripts/append-changelog.sh \
  "." \
  "升级 TypeScript 到 5.3" \
  "更新 tsconfig,修复类型错误" \
  "tsconfig.json,package.json" \
  "tsc --noEmit 通过"
```

## 查看历史

```bash
# 查看今日变更
cat changelog/$(date +%Y-%m-%d).md

# 查看所有变更文件
ls -la changelog/

# 搜索特定关键词
grep -r "关键词" changelog/
```

## 注意事项

1. **Git 管理**: 建议将 `changelog/` 目录纳入版本控制
2. **格式一致**: 脚本自动保证格式统一，避免手动编辑
3. **时区**: 时间戳自动包含时区信息（如 +08:00）
4. **编码**: 文件使用 UTF-8 编码
