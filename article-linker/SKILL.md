---
name: article-linker
description: "文章标题→发布链接映射工具。触发词：/article-linker、查找文章链接、添加已发布链接、扫描文章链接"
---

# Article Linker

将文章标题映射为已发布的外部链接。这是一个**通用服务 Skill**，供其他 Skill（如 nb-query）调用。

## 触发方式

- `/article-linker`
- 「查找文章链接」
- 「添加已发布链接」
- 「扫描文章链接」

## 执行脚本

```bash
# 单标题查询
python3 ~/.claude/skills/article-linker/scripts/linker.py query "文章标题"

# 批量查询（JSON 数组文件）
python3 ~/.claude/skills/article-linker/scripts/linker.py batch titles.json

# 全文扫描（输出替换建议）
python3 ~/.claude/skills/article-linker/scripts/linker.py scan article.md

# 全文扫描并直接编辑
python3 ~/.claude/skills/article-linker/scripts/linker.py scan article.md --edit
```

## 数据源

```
~/.local/share/platform-sheets/platform_info.json
```

由 `/sync-platform-sheets` 同步维护。

## 功能说明

| 模式 | 功能 | 输出 |
|------|------|------|
| query | 单标题查询 | JSON（url, platform, match） |
| batch | 批量查询 | JSON（results, stats） |
| scan | 全文扫描 | JSON 替换建议 |
| scan --edit | 扫描并编辑 | 直接修改文件 |

## 匹配策略

1. **精确匹配** - 标题完全一致
2. **标准化匹配** - 去除书名号、标准化空格和标点
3. **包含匹配** - 标题互相包含

## 平台优先级

```
微信 > zsxq > 其他
```

## 输出示例

**单标题查询**：
```json
{
  "title": "如何高效使用 Claude Code",
  "url": "https://mp.weixin.qq.com/s/xxx",
  "platform": "微信",
  "match": "exact"
}
```

**批量查询**：
```json
{
  "results": [...],
  "stats": {
    "total": 3,
    "matched": 2,
    "unmatched": 1,
    "match_rate": "66.7%"
  }
}
```

**扫描编辑**：
```
✓ 已添加 2 处链接
  - 《文章A》→ 微信
  - 《文章B》→ zsxq
```

## 与其他 Skill 集成

| 调用方 | 调用时机 | 用途 |
|--------|----------|------|
| nb-query | 阶段 3 | 为引用添加外部链接 |
| 写作类 Skill | 写作完成后 | 全文扫描添加链接 |
