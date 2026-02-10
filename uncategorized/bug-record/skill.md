---
name: bug-record
description: "记录 bug 修复到 bugs.jsonl。触发词：/bug、记录bug、bug复盘"
---

# Bug Record Skill

在项目目录下记录 bug 修复信息到 `bugs.jsonl` 文件。

## 触发条件

- `/bug` - 手动记录 bug
- `/记录bug`
- `/bug复盘`
- 会话结束时自动提示（Stop hook）

## 核心规则

1. **JSONL 格式**: 每行一条 JSON 记录
2. **追加写入**: 不覆盖已有记录
3. **必填字段**: ts, id, title, symptom, root_cause, fix, files_changed
4. **可选字段**: repro_steps, verification, impact, prevention, tags, followups

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| ts | string | 是 | ISO 8601 时间戳 |
| id | string | 是 | 唯一标识（自动生成） |
| title | string | 是 | Bug 标题 |
| symptom | string | 是 | 症状描述 |
| root_cause | string | 是 | 根本原因 |
| fix | string | 是 | 修复方案 |
| files_changed | string | 是 | 修改的文件（逗号分隔） |
| repro_steps | string | 否 | 复现步骤 |
| verification | string | 否 | 验证方式与结果 |
| impact | string | 否 | 影响范围 |
| prevention | string | 否 | 预防措施 |
| tags | string | 否 | 标签（3-8 个短标签） |
| followups | string | 否 | 后续任务 |

## 执行脚本

```bash
bash ~/.claude/skills/bug-record/scripts/append-bug.sh \
  "工作目录" \
  "Bug 标题" \
  "症状描述" \
  "根本原因" \
  "修复方案" \
  "修改的文件" \
  "复现步骤" \
  "验证结果" \
  "影响范围" \
  "预防措施" \
  "标签" \
  "后续任务"
```

## 使用示例

### 示例 1：完整记录

```bash
bash ~/.claude/skills/bug-record/scripts/append-bug.sh \
  "." \
  "USDT 支付未校验 vault 账户归属" \
  "用户可以零成本支付或错误退款" \
  "USDT 相关账户仅校验 mint 与用户 owner，未校验 vault_token_account.owner" \
  "在 request_mint/refund 增加 vault_token_account.owner == vault.key() 校验" \
  "request_mint.rs,refund.rs" \
  "1. 创建恶意 token 账户 2. 调用 request_mint" \
  "单元测试通过，手动测试验证" \
  "高危：资金安全" \
  "添加账户归属校验到 checklist" \
  "security,solana,token,vault" \
  "审计所有 token 账户校验逻辑"
```

### 示例 2：简化记录

```bash
bash ~/.claude/skills/bug-record/scripts/append-bug.sh \
  "." \
  "登录页面白屏" \
  "用户打开登录页面显示白屏" \
  "React 组件未正确导入" \
  "修复 import 语句" \
  "LoginPage.tsx"
```

## Claude 使用指南

当你完成一个 bug 修复后，请执行以下步骤：

1. **收集信息**：
   - 症状：用户看到了什么问题？
   - 根因：为什么会出现这个问题？
   - 修复：你做了什么修改？
   - 文件：修改了哪些文件？

2. **执行脚本**：
   ```bash
   bash ~/.claude/skills/bug-record/scripts/append-bug.sh \
     "$(pwd)" \
     "Bug 标题" \
     "症状" \
     "根因" \
     "修复" \
     "文件列表"
   ```

3. **验证记录**：
   ```bash
   tail -1 bugs.jsonl | jq .
   ```

## 查看历史

```bash
# 查看所有 bug 记录
cat bugs.jsonl | jq .

# 查看最近 5 条
tail -5 bugs.jsonl | jq .

# 按标签搜索
grep "security" bugs.jsonl | jq .

# 统计数量
wc -l bugs.jsonl
```
