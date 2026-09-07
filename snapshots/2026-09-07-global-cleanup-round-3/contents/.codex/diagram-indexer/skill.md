---
name: diagram-indexer
description: 流程图精确索引工具：增量解析 Mermaid 和 Canvas 文件，避免全量读取。触发词：/diagram-index、流程图索引、图表索引
---

# Diagram Indexer - 流程图精确索引

对大型流程图文档进行精确索引，支持增量更新，避免全量读取。

## 触发方式

- `/diagram-index`
- 「索引流程图」
- 「更新图表索引」

## 支持格式

| 格式 | 文件类型 | 解析方式 |
|------|----------|----------|
| Mermaid | `.md` 内嵌 | 正则提取 + mermaid.parse() |
| Obsidian Canvas | `.canvas` | 直接 JSON 解析 |

## 核心原则

1. **增量优先**：仅处理修改时间变更的文件
2. **节点级索引**：建立 [文件 → 节点ID] 映射
3. **零第三方依赖**：Canvas 直接 JSON 解析，不引入停更库

## 索引文件结构

```json
{
  "version": "1.0",
  "updated": "2026-01-20T17:00:00+08:00",
  "files": {
    "docs/CALL_FLOW/03-sequence.md": {
      "mtime": 1705312345,
      "type": "mermaid",
      "diagrams": [
        {
          "type": "sequenceDiagram",
          "line": 15,
          "participants": ["User", "Frontend", "Contract"],
          "messages": 12
        }
      ]
    },
    "docs/CALL_FLOW/01-architecture.canvas": {
      "mtime": 1705312400,
      "type": "canvas",
      "nodes": ["node-1", "node-2", "node-3"],
      "edges": [{"from": "node-1", "to": "node-2"}]
    }
  }
}
```

## 工作流程

```
1. 扫描目标目录
   ↓
2. 比对文件 mtime 与索引记录
   ↓
3. 仅解析变更文件
   ├─ .md  → 提取 Mermaid 代码块 → 解析节点/边
   └─ .canvas → JSON.parse → 提取 nodes/edges
   ↓
4. 更新索引文件
   ↓
5. 返回变更摘要
```

## 使用示例

### 场景 1：首次构建索引

```bash
# 执行索引脚本
bun ~/.claude/skills/diagram-indexer/scripts/index.ts docs/CALL_FLOW
```

### 场景 2：查询特定节点所在文件

```typescript
import { findNodeLocation } from './index';

// 查找节点 "User" 在哪些文件中出现
const locations = findNodeLocation(index, "User");
// 返回: [{ file: "docs/CALL_FLOW/03-sequence.md", line: 15 }]
```

### 场景 3：增量更新

```bash
# 仅更新变更文件
bun ~/.claude/skills/diagram-indexer/scripts/index.ts docs/CALL_FLOW --incremental
```

## 命令参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<dir>` | 目标目录 | 必填 |
| `--incremental` | 增量模式 | false |
| `--output <file>` | 索引输出路径 | `./diagram-index.json` |
| `--verbose` | 详细输出 | false |

## 与 Claude Code 集成

在对话中直接使用：

```
用户: 帮我更新 docs/CALL_FLOW 的流程图索引
Claude: [执行 diagram-indexer skill]
        已扫描 17 个文件，更新 3 个变更文件
        - 03-sequence.md: 新增 2 个参与者
        - 01-architecture.canvas: 移动 1 个节点
```

## 注意事项

- Mermaid 解析依赖 `mermaid` npm 包（如需验证语法）
- Canvas 文件为纯 JSON，无需额外依赖
- 索引文件建议加入 `.gitignore`
