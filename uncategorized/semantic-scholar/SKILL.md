---
name: semantic-scholar
description: 使用 Semantic Scholar API 检索和验证学术论文。支持并发多关键词搜索、批量 ID/DOI 查询、引用分析。覆盖 2.14 亿+ 学术论文，无需 API Key 即可使用。触发词：论文检索、论文验证、Semantic Scholar、S2 搜索、查论文
allowed-tools: [Bash, Read, Write, Edit]
---

# Semantic Scholar 论文检索与验证

## 概述

基于 Semantic Scholar Academic Graph API 的论文检索工具，支持：
- **并发搜索**：同时查询多个关键词
- **批量验证**：通过 DOI / ArXiv ID / S2 ID 批量查询论文详情
- **引用分析**：获取引用数、被引论文
- **开放获取**：识别 OA 论文和 PDF 链接

覆盖 214M+ 学术论文，免费无需注册。

## 使用场景

- 按关键词检索论文标题、作者、年份
- 验证论文是否存在及其元数据是否正确
- 批量查询一组 DOI 对应的论文信息
- 与 OpenAlex 交叉验证检索结果
- 查找某领域高引论文

## 快速开始

### 依赖安装

```bash
pip install aiohttp
```

无需 API Key。申请免费 Key 可提升速率至 10 req/s：
https://www.semanticscholar.org/product/api#api-key-form

### CLI 用法

```bash
SCRIPTS=~/.agents/skills/semantic-scholar/scripts

# 单关键词搜索
python $SCRIPTS/search_papers.py "blockchain consensus"

# 并发多关键词搜索
python $SCRIPTS/search_papers.py "HotStuff BFT" "DAG consensus" "PBFT protocol"

# 按 DOI 批量查询
python $SCRIPTS/search_papers.py --ids "DOI:10.1145/3293611.3331591" "ARXIV:1803.05069"

# 年份 + 引用数过滤
python $SCRIPTS/search_papers.py "consensus algorithm" --year "2020-" --min-cite 50

# 输出到 JSON
python $SCRIPTS/search_papers.py "BFT consensus" -n 20 -o results.json
```

### Python API 用法

```python
import asyncio
from scripts.s2_client import S2Client

async def main():
    client = S2Client()  # 或 S2Client(api_key="your-key")

    # 单次搜索
    result = await client.search("blockchain consensus", limit=5)
    for p in result["data"]:
        print(f"{p['title']} ({p['year']}) - 引用: {p['citationCount']}")

    # 并发搜索多个关键词
    queries = ["HotStuff BFT", "DAG consensus", "PBFT protocol"]
    results = await client.search_concurrent(queries, limit=5)
    for q, r in results.items():
        print(f"\n== {q} ({r['total']} 条) ==")
        for p in r["data"]:
            print(f"  {p['title']}")

    # 批量 ID 查询
    papers = await client.batch_papers([
        "DOI:10.1145/3293611.3331591",
        "ARXIV:1803.05069",
    ])
    for p in papers:
        if p:
            print(f"{p['title']} ({p['year']})")

    await client.close()

asyncio.run(main())
```

## API 端点

| 端点 | 方法 | 用途 | 限制 |
|------|------|------|------|
| `/paper/search` | GET | 关键词搜索 | 100 条/页, offset ≤ 9999 |
| `/paper/search/bulk` | GET | 大规模搜索 | 1000 条/页, token 分页 |
| `/paper/batch` | POST | 批量 ID 查询 | 500 ID/次 |
| `/paper/{id}` | GET | 单篇详情 | - |

## 支持的论文 ID 格式

| 格式 | 示例 |
|------|------|
| S2 Paper ID | `204e3073870fae3d05bcbc2f6a8e263d9b72e776` |
| DOI | `DOI:10.1145/3293611.3331591` |
| ArXiv | `ARXIV:1803.05069` |
| Corpus ID | `CorpusId:13756489` |
| PubMed | `PMID:12345678` |
| ACL | `ACL:P18-1234` |

## 返回字段

### 基础字段 (DEFAULT_FIELDS)
`title, authors, year, citationCount, externalIds, venue`

### 详细字段 (DETAIL_FIELDS)
`title, authors, year, citationCount, externalIds, venue, abstract, referenceCount, isOpenAccess, openAccessPdf`

## 速率限制

| 模式 | 速率 | 日限额 |
|------|------|--------|
| 无 Key | 1 req/s | 5000/5min |
| 有 Key | 10 req/s | 无硬限制 |

设置 Key：
```bash
export S2_API_KEY="your-key-here"
```

## 与 OpenAlex 交叉验证

```python
# 1. 用 OpenAlex 搜索
openalex_results = openalex_client.search_works(search="HotStuff BFT")

# 2. 提取 DOI 列表
dois = [f"DOI:{w['doi'].split('doi.org/')[-1]}"
        for w in openalex_results if w.get('doi')]

# 3. 用 Semantic Scholar 批量验证
s2_papers = await s2_client.batch_papers(dois)

# 4. 对比标题、年份、引用数
for oa, s2 in zip(openalex_results, s2_papers):
    if s2:
        match = oa['title'].lower() == s2['title'].lower()
        print(f"{'✓' if match else '✗'} {oa['title']}")
```

## 脚本说明

### s2_client.py
异步 API 客户端，核心功能：
- `search()` — 单次关键词搜索
- `search_concurrent()` — 并发多关键词搜索
- `batch_papers()` — 批量 ID 查询（自动分批，每批 500）
- `paper_detail()` — 单篇详情
- `bulk_search()` — 大规模搜索（token 分页）
- 内置令牌桶速率限制 + 指数退避重试

### search_papers.py
CLI 搜索工具：
- 支持多关键词并发
- 支持 `--ids` 批量查询
- 支持 `--year`、`--min-cite` 过滤
- 输出格式化文本或 JSON
