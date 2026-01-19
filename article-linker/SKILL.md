# Article Linker

将文章标题映射为已发布的外部链接。这是一个**通用服务 Skill**，供其他 Skill（如 nb-query、material-to-markdown）调用。

## 核心定位

**一句话定位**：给定文章标题，返回已发布的外部链接。

**设计理念**：
- 映射能力是**通用服务**，不应绑定在特定工具中
- 多个工具都需要「标题 → 链接」能力，抽取为独立 Skill 避免重复
- 支持精确匹配和模糊匹配，应对标题变体

## 触发条件

### 显式触发

- `/article-linker`
- `查找文章链接`
- `文章链接查询`
- `映射文章链接`
- `扫描是否可以添加已发布链接`
- `添加已发布链接`
- `扫描文章链接`

### 被其他 Skill 调用（主要场景）

本 Skill 主要作为**服务组件**被调用，而非用户直接使用：

| 调用方 | 调用时机 | 用途 |
|--------|----------|------|
| nb-query | 阶段 3（生成引用对照表后） | 为引用添加外部链接 |
| material-to-markdown | 素材整理时 | 验证链接映射结果 |
| 其他写作类 Skill | 写作完成后 | 为文中提到的文章添加链接 |

## 数据源

### 位置

```
~/.local/share/platform-sheets/platform_info.json
```

### 同步方式

由 `/sync-platform-sheets` Skill 维护：
- **主机器**（有 `~/Dropbox/markdown_converter`）：从 Google Sheets 同步
- **从机器**：从 GitHub 拉取

### 数据结构

```json
[
  {
    "标题": "如何高效使用 Claude Code",
    "微信": "https://mp.weixin.qq.com/s/xxx",
    "zsxq": "https://t.zsxq.com/xxx"
  }
]
```

## 平台优先级

按配置的 `PRIORITY` 列表顺序选择第一个非空 URL：

```python
# 默认优先级示例（可自定义）
PRIORITY = ['微信', 'zsxq']
```

- `微信` - 微信公众号（免费）
- `zsxq` - 知识星球（付费）
- 可根据你的发布平台自行扩展

**说明**：映射时优先选择免费平台，付费平台作为兜底。

## 三种模式

### 模式 1：单标题查询

**输入**：一个文章标题
**输出**：对应的 URL + 平台名

```
输入：如何高效使用 Claude Code
输出：
{
  "title": "如何高效使用 Claude Code",
  "url": "https://mp.weixin.qq.com/s/xxx",
  "platform": "微信",
  "match_type": "exact"
}
```

### 模式 2：批量查询

**输入**：文章标题列表（通常来自 nb-query 的引用对照表）
**输出**：映射表 + 统计

```
输入：["如何高效使用 Claude Code", "NotebookLM 入门指南", "未知文章"]
输出：
{
  "results": [
    {"num": 1, "title": "如何高效使用 Claude Code", "url": "https://...", "platform": "微信", "match": "exact"},
    {"num": 2, "title": "NotebookLM 入门指南", "url": "https://...", "platform": "知乎", "match": "fuzzy"},
    {"num": 3, "title": "未知文章", "url": null, "platform": null, "match": "none"}
  ],
  "stats": {
    "total": 3,
    "matched": 2,
    "unmatched": 1,
    "match_rate": "66.7%"
  }
}
```

### 模式 3：全文扫描

**输入**：一段文本（可能包含《文章标题》格式的引用）
**输出**：替换后的文本 + 替换记录

```
输入：
"我在《如何高效使用 Claude Code》这篇文章中提到过，Claude 的能力很强。"

输出：
{
  "text": "我在[《如何高效使用 Claude Code》](https://mp.weixin.qq.com/s/xxx)这篇文章中提到过，Claude 的能力很强。",
  "replacements": [
    {"original": "《如何高效使用 Claude Code》", "linked": "[《如何高效使用 Claude Code》](https://...)", "platform": "微信"}
  ]
}
```

### 模式 4：文件扫描并直接编辑（用户触发）

**触发词**：`扫描是否可以添加已发布链接`、`添加已发布链接`、`扫描文章链接`

**输入**：文件路径
**输出**：直接编辑文件，添加链接

#### 执行流程（BLOCKING - 严格顺序）

```
1. 同步平台数据 ──────────────────────────────────────────────
   │  python ~/.claude/skills/sync-platform-sheets/scripts/sync.py
   │  ⚠️ 必须先同步，确保数据最新
   ▼
2. 读取文件 ──────────────────────────────────────────────────
   │  识别所有《》书名号内的标题
   ▼
3. 检查已有链接 ──────────────────────────────────────────────
   │  跳过已经是 [《标题》](url) 格式的引用
   │  只处理纯文本《标题》
   ▼
4. 查找匹配 ──────────────────────────────────────────────────
   │  在 platform_info 中查找对应的发布链接
   ▼
5. 直接编辑 ──────────────────────────────────────────────────
   │  ⚠️ 完全匹配的：直接添加链接，不询问
   │  模糊匹配的：列出供用户确认
   │  未匹配的：报告但不处理
   ▼
6. 输出报告
```

#### 关键行为规范

| 场景 | 行为 | 原因 |
|------|------|------|
| 完全匹配 | **直接编辑，不询问** | 用户要求添加链接，匹配确定就执行 |
| 模糊匹配 | 列出供确认 | 避免误添加 |
| 已有链接 | 跳过 | 避免重复 |
| 未匹配 | 报告 | 可能是新文章或标题变体 |

#### 示例

用户：`扫描是否可以添加已发布链接：/path/to/article.md`

```
1. [同步] 从 Google Sheets 获取 636 条记录 ✓
2. [扫描] 发现 3 个《》引用
3. [检查]
   - 《文章A》→ 已有链接，跳过
   - 《文章B》→ 无链接，查找中...
   - 《示例》→ 示例文本，忽略
4. [匹配] 《文章B》→ 完全匹配 → 微信链接
5. [编辑] 已添加 1 处链接

完成：添加 1 处，跳过 1 处，忽略 1 处
```

## 匹配策略

### 1. 精确匹配（优先）

标题完全一致（忽略首尾空格）。

### 2. 标准化匹配

去除以下差异后匹配：
- 书名号：《》「」""
- 空格差异：多个空格 → 单个空格
- 标点差异：全角 → 半角

```python
def normalize(title):
    # 去除书名号
    title = re.sub(r'[《》「」"""]', '', title)
    # 标准化空格
    title = re.sub(r'\s+', ' ', title).strip()
    # 全角转半角标点
    title = title.replace('：', ':').replace('，', ',')
    return title
```

### 3. 包含匹配（兜底）

- platform_info 标题包含查询标题
- 或查询标题包含 platform_info 标题
- 取最短的匹配（避免误匹配）

### 4. 未匹配处理

返回 `null`，记录到未匹配列表供人工检查。

## 执行流程

### 依赖检查（BLOCKING）

```python
from pathlib import Path
import json

platform_file = Path.home() / ".local/share/platform-sheets/platform_info.json"

# 检查文件存在
if not platform_file.exists():
    raise RuntimeError(
        "❌ platform_info.json 不存在\n"
        "请先运行 /sync-platform-sheets 同步数据"
    )

# 加载数据
with open(platform_file, 'r', encoding='utf-8') as f:
    platform_data = json.load(f)

if len(platform_data) < 10:
    print(f"⚠️ 数据量偏少（{len(platform_data)} 条），可能需要同步")
```

### 构建映射表

```python
PRIORITY = ['微信', 'zsxq']  # 可根据你的发布平台自行扩展
SKIP_FIELDS = {'标题', 'monetize', 'id', 'date', 'tags', ''}

def build_title_to_url_map(platform_data):
    """构建标题 → (URL, 平台) 映射"""
    title_to_url = {}
    normalized_map = {}  # 标准化标题 → 原始标题

    for item in platform_data:
        title = item.get('标题', '').strip()
        if not title:
            continue

        # 按优先级查找 URL
        url = None
        platform = None
        for p in PRIORITY:
            u = item.get(p, '').strip()
            if u:
                url = u
                platform = p
                break

        # 回退：任意非空链接字段
        if not url:
            for k, v in item.items():
                if k not in SKIP_FIELDS and v and str(v).startswith('http'):
                    url = v.strip()
                    platform = k
                    break

        if url:
            title_to_url[title] = (url, platform)
            normalized_map[normalize(title)] = title

    return title_to_url, normalized_map
```

### 查询函数

```python
def resolve_title(query_title, title_to_url, normalized_map):
    """解析单个标题"""
    # 1. 精确匹配
    if query_title in title_to_url:
        url, platform = title_to_url[query_title]
        return {"url": url, "platform": platform, "match_type": "exact"}

    # 2. 标准化匹配
    normalized_query = normalize(query_title)
    if normalized_query in normalized_map:
        original_title = normalized_map[normalized_query]
        url, platform = title_to_url[original_title]
        return {"url": url, "platform": platform, "match_type": "normalized"}

    # 3. 包含匹配
    for title, (url, platform) in title_to_url.items():
        if query_title in title or title in query_title:
            return {"url": url, "platform": platform, "match_type": "fuzzy"}

    # 4. 未匹配
    return {"url": None, "platform": None, "match_type": "none"}
```

### 批量查询函数

```python
def resolve_batch(citation_map, title_to_url, normalized_map):
    """
    批量解析引用对照表
    citation_map: {1: '文章标题1', 2: '文章标题2', ...}
    """
    results = []
    matched = 0

    for num, title in sorted(citation_map.items()):
        result = resolve_title(title, title_to_url, normalized_map)
        results.append({
            "num": num,
            "title": title,
            "url": result["url"],
            "platform": result["platform"],
            "match": result["match_type"]
        })
        if result["url"]:
            matched += 1

    total = len(citation_map)
    return {
        "results": results,
        "stats": {
            "total": total,
            "matched": matched,
            "unmatched": total - matched,
            "match_rate": f"{matched/total*100:.1f}%" if total > 0 else "0%"
        }
    }
```

### 全文扫描函数

```python
import re

def scan_and_link(text, title_to_url, normalized_map):
    """扫描文本，为《标题》格式的引用添加链接"""
    replacements = []

    # 匹配书名号包裹的内容
    pattern = r'《([^》]+)》'

    for match in re.finditer(pattern, text):
        title = match.group(1)
        result = resolve_title(title, title_to_url, normalized_map)

        if result["url"]:
            original = match.group(0)  # 《标题》
            linked = f'[{original}]({result["url"]})'
            replacements.append({
                "original": original,
                "linked": linked,
                "platform": result["platform"]
            })

    # 逆序替换（避免位置偏移）
    for match in reversed(list(re.finditer(pattern, text))):
        title = match.group(1)
        result = resolve_title(title, title_to_url, normalized_map)
        if result["url"]:
            original = match.group(0)
            linked = f'[{original}]({result["url"]})'
            text = text[:match.start()] + linked + text[match.end():]

    return {"text": text, "replacements": replacements}
```

## 输出格式

### 模式 1：Markdown 表格（人类可读）

```markdown
## 链接映射结果

| 序号 | 文章标题 | 平台 | 链接 | 匹配 |
|:----:|----------|:----:|------|:----:|
| 1 | 如何高效使用 Claude Code | 微信 | [查看](https://...) | 精确 |
| 2 | NotebookLM 入门指南 | 知乎 | [查看](https://...) | 模糊 |
| 3 | 未知文章 | - | - | ❌ |

**统计**：共 3 条，匹配 2 条（66.7%），未匹配 1 条
```

### 模式 2：JSON（程序可读）

```json
{
  "results": [...],
  "stats": {...}
}
```

## 与其他 Skill 的集成

### nb-query 集成

在 nb-query 阶段 3（生成引用对照表）后调用：

```python
# nb-query 阶段 3 完成后
citation_map = {1: "文章标题1", 2: "文章标题2", ...}

# 调用 article-linker
link_results = resolve_batch(citation_map, title_to_url, normalized_map)

# 生成带链接的引用对照表
# 写入 03-citation-table.md，包含链接列
```

### 写作类 Skill 集成

写作完成后，调用全文扫描模式：

```python
# 读取写作完成的文章
with open('final.md', 'r') as f:
    article_text = f.read()

# 扫描并添加链接
result = scan_and_link(article_text, title_to_url, normalized_map)

# 保存带链接的版本
with open('final.md', 'w') as f:
    f.write(result["text"])
```

### material-to-markdown 集成

在整理素材时，验证链接映射是否完整：

```python
# 调用 article-linker 获取映射结果
# 在素材文档末尾添加「引用链接映射」表格
# 标记未匹配的条目供人工检查
```

## 错误处理

| 错误 | 处理方式 |
|------|----------|
| platform_info.json 不存在 | 提示运行 /sync-platform-sheets |
| 数据为空 | 警告，返回空结果 |
| 标题未匹配 | 记录到未匹配列表，不中断流程 |
| JSON 解析失败 | 报错，要求重新同步 |

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.1.0 | 2026-01-17 | 新增模式4：文件扫描并直接编辑，明确先同步再查找，完全匹配直接添加不询问 |
| v1.0.0 | 2026-01-16 | 初始版本：从 material-to-markdown 抽取映射能力 |

## 设计说明

### 为什么要独立成 Skill？

1. **避免重复**：nb-query、material-to-markdown 等多个 Skill 都需要映射能力
2. **单一职责**：映射逻辑集中管理，便于维护
3. **数据源统一**：所有工具使用同一份 platform_info.json
4. **扩展性**：未来新工具也可以调用

### 与原有流程的变化

**之前**：
```
nb-query → 引用对照表（无链接）
         ↓
material-to-markdown → 查 platform_info → 添加链接
```

**现在**：
```
nb-query → 调用 article-linker → 引用对照表（带链接）
         ↓
material-to-markdown → 直接使用（不再查映射）

写作类 Skill → 调用 article-linker → 全文扫描添加链接
```
