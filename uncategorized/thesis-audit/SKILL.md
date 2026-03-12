---
name: thesis-audit
description: 论文完整 gate-loop 审计流程：审计→修复→重审→编译→提交→日记。触发词：/thesis-audit、论文审计、审计门禁、gate audit
---

# Thesis Audit Gate Loop

完整的论文质量门禁闭环，禁止跳过任何步骤。

## 流程

```
编译 → 审计(academic-writing + peer-review) → 修复 → 重新编译 → 重新审计 → 通过 → 提交 → 日记
                                                  ↑                    |
                                                  └─── 未通过 ────────┘
                                                  (最多 3 轮循环)
```

## 步骤（严格按序执行）

### Step 1: 编译验证
```bash
cd /Users/bit/LaTeX/SWUN_Thesis && latexmk -xelatex -interaction=nonstopmode main.tex
```
- 编译失败 → 修复后重新编译，不进入审计

### Step 2: Academic-Writing 审计
- 调用 `academic-writing` skill 检查目标文件
- 检查项：术语一致性、句式流畅度、逻辑衔接、AI 痕迹
- 同时对照 `~/.claude/skills/ai-vibe-writing-skills/.ai_context/error_log.md` 逐项审计

### Step 3: Peer-Review 审计
- 调用 `requesting-code-review` skill 或等效审查子代理
- 检查项：内容正确性、引用规范（位置规则+首次原则+禁止堆叠）、浮动体规则

### Step 4: 修复（如审计发现问题）
- 通过子代理修复所有审计问题
- **禁止在主会话中直接修改 .tex 文件**

### Step 5: 重新编译 + 重新审计（关键步骤，禁止跳过）
- 修复后必须重新执行 Step 1-3
- 验证所有问题已解决
- 最多循环 3 轮，超过则报告剩余问题并请求用户决策

### Step 6: 提交
- 两项审计均通过后自动 commit
- commit message 格式：`round-N: <简要描述改动内容>`

### Step 7: 日记记录
- 将本轮改动摘要写入当日日记 `changelog/YYYY-MM-DD.md`
- 内容：涉及文件、改动要点、审计轮数、最终结果

## 调用方式

### 交互式
```
/thesis-audit chapters/chapter3.tex
/thesis-audit chapters/chapter2.tex chapters/chapter4.tex
/thesis-audit  （无参数=全部章节）
```

### Headless 批处理
```bash
claude -p 'Run /thesis-audit on chapters/chapter3.tex chapters/chapter4.tex' \
  --allowedTools 'Edit,Read,Bash,Grep,Glob,Agent,Skill'
```

## 硬性约束

- **禁止跳过重审步骤**（Step 5），这是最常见的遗漏
- **禁止主会话直接修改 .tex**，修复必须通过子代理
- **禁止跳过日记记录**（Step 7）
- 审计期间发现 error_log.md 中的禁用模式 → 必须修正，不得放过
