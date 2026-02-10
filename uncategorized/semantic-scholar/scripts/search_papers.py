#!/usr/bin/env python3
"""
Semantic Scholar 论文搜索 CLI
支持并发多关键词搜索、批量 ID 查询

用法:
  # 单关键词搜索
  python search_papers.py "blockchain consensus"

  # 并发多关键词搜索
  python search_papers.py "blockchain consensus" "DAG protocol" "BFT algorithm"

  # 按 DOI / ArXiv ID 批量查询
  python search_papers.py --ids "DOI:10.1145/3132747.3132757" "ARXIV:1803.05069"

  # 指定年份和最低引用数
  python search_papers.py "PBFT consensus" --year "2020-" --min-cite 10

  # 输出到文件
  python search_papers.py "HotStuff BFT" -o results.json
"""

import argparse
import asyncio
import json
import os
import sys

# 将 scripts 目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2_client import S2Client, DEFAULT_FIELDS, DETAIL_FIELDS, save_config, load_config, resolve_api_key, CONFIG_FILE


def format_paper(p: dict) -> str:
    """格式化单篇论文为可读文本"""
    if not p:
        return "  (未找到)"
    title = p.get("title", "N/A")
    year = p.get("year", "N/A")
    cite = p.get("citationCount", 0)
    venue = p.get("venue", "")
    authors = p.get("authors", [])
    author_str = ", ".join(a.get("name", "") for a in authors[:3])
    if len(authors) > 3:
        author_str += f" 等 ({len(authors)} 位作者)"

    ext = p.get("externalIds", {})
    doi = ext.get("DOI", "")
    arxiv = ext.get("ArXiv", "")

    lines = [f"  标题: {title}"]
    lines.append(f"  作者: {author_str}")
    lines.append(f"  年份: {year}  |  引用: {cite}")
    if venue:
        lines.append(f"  期刊/会议: {venue}")
    if doi:
        lines.append(f"  DOI: {doi}")
    if arxiv:
        lines.append(f"  ArXiv: {arxiv}")
    return "\n".join(lines)


async def _verify_key(key: str):
    """验证 API Key 是否有效"""
    client = S2Client(api_key=key, cache=False)
    try:
        result = await client.search("test", limit=1)
        if result and result.get("data") is not None:
            print("Key 验证成功")
        else:
            print("Key 验证失败：无法获取结果")
    except Exception as e:
        print(f"Key 验证失败：{e}")
    finally:
        await client.close()


async def run_search(args):
    """执行搜索"""
    client = S2Client(
        api_key=args.api_key,
        cache=not args.no_cache,
    )

    try:
        if args.ids:
            # 批量 ID 查询
            print(f"批量查询 {len(args.ids)} 篇论文...", file=sys.stderr)
            papers = await client.batch_papers(args.ids, fields=DETAIL_FIELDS)
            results = {"mode": "batch", "count": len(papers), "papers": papers}
            # 打印摘要
            for i, p in enumerate(papers):
                print(f"\n[{i+1}] {format_paper(p)}")
        else:
            # 关键词搜索
            queries = args.queries
            fields = DETAIL_FIELDS if args.detail else DEFAULT_FIELDS
            limit = args.limit

            kwargs = {}
            if args.year:
                kwargs["year"] = args.year
            if args.min_cite is not None:
                kwargs["min_citation_count"] = args.min_cite

            if len(queries) == 1:
                # 单关键词
                print(f"搜索: {queries[0]}", file=sys.stderr)
                result = await client.search(
                    queries[0], fields=fields, limit=limit, **kwargs
                )
                total = result.get("total", 0)
                data = result.get("data", [])
                print(f"共 {total} 条结果，返回 {len(data)} 条:\n")
                for i, p in enumerate(data):
                    print(f"[{i+1}] {format_paper(p)}\n")
                results = {"mode": "search", "query": queries[0], "total": total, "data": data}
            else:
                # 并发多关键词
                print(f"并发搜索 {len(queries)} 个关键词...", file=sys.stderr)
                multi = await client.search_concurrent(
                    queries, fields=fields, limit=limit, **kwargs
                )
                results = {"mode": "concurrent", "results": {}}
                for q, r in multi.items():
                    total = r.get("total", 0)
                    data = r.get("data", [])
                    print(f"\n{'='*60}")
                    print(f"关键词: {q}  (共 {total} 条，返回 {len(data)} 条)")
                    print(f"{'='*60}")
                    for i, p in enumerate(data):
                        print(f"  [{i+1}] {format_paper(p)}\n")
                    results["results"][q] = {"total": total, "data": data}

        # 输出 JSON
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到 {args.output}", file=sys.stderr)

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Semantic Scholar 论文搜索（支持并发）"
    )
    parser.add_argument(
        "queries", nargs="*", help="搜索关键词（多个则并发执行）"
    )
    parser.add_argument(
        "--ids", nargs="+",
        help="按 ID 批量查询（S2 ID / DOI:xxx / ARXIV:xxx）"
    )
    parser.add_argument(
        "-n", "--limit", type=int, default=5,
        help="每个查询返回的结果数 (默认 5, 最大 100)"
    )
    parser.add_argument(
        "--year", help="年份过滤，如 '2020-2024' 或 '2020-'"
    )
    parser.add_argument(
        "--min-cite", type=int, help="最低引用数过滤"
    )
    parser.add_argument(
        "--detail", action="store_true",
        help="返回详细字段（含摘要、开放获取信息）"
    )
    parser.add_argument(
        "--api-key", help="S2 API Key（也可设 S2_API_KEY 环境变量）"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="跳过缓存"
    )
    parser.add_argument(
        "--clear-cache", action="store_true", help="清除所有缓存后退出"
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="交互式配置 API Key（保存到 ~/.config/semantic-scholar/config.json）"
    )
    parser.add_argument(
        "-o", "--output", help="输出 JSON 文件路径"
    )

    args = parser.parse_args()

    # 特殊命令：配置 Key
    if args.setup:
        key = input("请输入 API Key: ").strip()
        if key:
            cfg = load_config()
            cfg["api_key"] = key
            save_config(cfg)
            print(f"已保存到 {CONFIG_FILE}")
            # 验证
            print("验证中...", end=" ")
            from s2_client import DiskCache
            asyncio.run(_verify_key(key))
        return

    # 特殊命令：清除缓存
    if args.clear_cache:
        from s2_client import DiskCache
        DiskCache(enabled=True).clear()
        print("缓存已清除")
        return

    if not args.queries and not args.ids:
        parser.error("请提供搜索关键词或 --ids 参数")

    asyncio.run(run_search(args))


if __name__ == "__main__":
    main()
