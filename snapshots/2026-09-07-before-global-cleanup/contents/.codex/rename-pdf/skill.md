---
name: rename-pdf
description: "自动重命名PDF文件：提取PDF元数据标题，清理非法字符，静默重命名。触发词：/renamepdf、重命名PDF、PDF改名"
---

# PDF 自动重命名工具

根据 PDF 元数据标题自动重命名文件。

## 触发方式

- `/renamepdf <PDF文件路径>`
- 「重命名这个 PDF」
- 「用标题重命名 PDF」

## 执行流程

### 1. 提取元数据
获取目标 PDF 的 Title 字段。

```bash
# 使用 exiftool 提取标题
exiftool -Title "<PDF文件>"

# 或使用 pdfinfo
pdfinfo "<PDF文件>" | grep "Title:"
```

### 2. 校验并清理
- 如果标题不存在或为 "(null)"，停止任务并告知用户
- 如果存在，将标题中的非法字符替换为 "-"：
  - 非法字符：`/ \ : * ? " < > |`

### 3. 静默重命名
使用工具将文件重命名为 `标题.pdf`，保持在原目录。

```bash
mv "<原文件>" "<目录>/标题.pdf"
```

## 核心要求

- **静默执行**：直接调用工具完成，不输出 Bash 代码或脚本
- **错误处理**：仅在致命错误时向用户报告
- **保持原位**：重命名后文件保持在原目录
- **字符清理**：确保新文件名在所有操作系统上合法

## 示例

**输入**：
```
/renamepdf /Users/bit/Downloads/paper.pdf
```

**执行**：
1. 提取 Title: "A Novel Approach to BFT Consensus"
2. 清理字符（本例无需清理）
3. 重命名为: `/Users/bit/Downloads/A Novel Approach to BFT Consensus.pdf`

**输出**：
```
✓ 已重命名为: A Novel Approach to BFT Consensus.pdf
```
