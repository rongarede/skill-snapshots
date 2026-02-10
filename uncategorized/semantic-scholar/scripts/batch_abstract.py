#!/usr/bin/env python3
"""
批量补全 Semantic Scholar 搜索结果中缺失的摘要

用法:
  # 补全指定目录下所有 layer_*_raw.json
  python batch_abstract.py /path/to/results/

  # 补全指定文件
  python batch_abstract.py layer_1_raw.json layer_2_raw.json

  # 仅检查缺失情况，不实际请求
  python batch_abstract.py /path/to/results/ --dry-run
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from s2_client import S2Client


# ── JSON 读写 ─────────────────────────────────────────────


def find_json_files(paths: list[str]) -> list[Path]:
    """从参数中解析出所有 raw JSON 文件"""
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(path.glob("layer_*_raw.json")))
        elif path.is_file() and path.suffix == ".json":
            files.append(path)
        else:
            print(f"跳过: {p}（不是目录或 JSON 文件）", file=sys.stderr)
    return files


def extract_papers(data: dict) -> list[dict]:
    """从 raw JSON 中提取所有论文对象的引用（原地修改用）"""
    papers = []
    # 格式 A: {"mode": ..., "results": {"query": {"total": N, "data": [...]}}}
    if "results" in data:
        for query_result in data["results"].values():
            papers.extend(query_result.get("data", []))
    # 格式 B: {"query": [papers]}
    else:
        for val in data.values():
            if isinstance(val, list):
                papers.extend(val)
    return papers


def collect_missing(papers: list[dict]) -> list[str]:
    """收集缺少 abstract 的 paperId（去重）"""
    seen = set()
    missing = []
    for p in papers:
        pid = p.get("paperId")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        if "abstract" not in p or p.get("abstract") is None:
            missing.append(pid)
    return missing


# ── 异步主逻辑 ────────────────────────────────────────────

async def run(args):
    files = find_json_files(args.paths)
    if not files:
        print("未找到任何 JSON 文件", file=sys.stderr)
        return

    # 第一步：扫描所有文件，收集缺失的 paperId
    file_data = {}  # {path: (raw_data, papers)}
    all_missing = []

    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        papers = extract_papers(raw)
        missing = collect_missing(papers)
        file_data[f] = (raw, papers)
        all_missing.extend(missing)
        print(f"{f.name}: {len(papers)} 篇论文，{len(missing)} 篇缺少摘要")

    # 去重
    unique_missing = list(dict.fromkeys(all_missing))
    print(f"\n共需补全 {len(unique_missing)} 篇（去重后）")

    if args.dry_run:
        print("(dry-run 模式，不实际请求)")
        return

    if not unique_missing:
        print("所有论文已有摘要，无需请求")
        return

    # 第二步：通过 S2Client 批量获取摘要
    client = S2Client(api_key=args.api_key, cache=False)
    try:
        print("\n正在从 Semantic Scholar API 获取摘要...")
        results = await client.batch_papers(unique_missing, fields="abstract")
    finally:
        await client.close()

    # 构建 paperId → abstract 映射
    abstracts = {}
    for item in results:
        if item and "paperId" in item:
            abstracts[item["paperId"]] = item.get("abstract")

    fetched = sum(1 for v in abstracts.values() if v is not None)
    print(f"成功获取 {fetched} 篇有效摘要，"
          f"{len(abstracts) - fetched} 篇确认无摘要")

    # 第三步：写回 JSON 文件
    print("\n正在更新 JSON 文件...")
    for f, (raw, papers) in file_data.items():
        updated = 0
        for p in papers:
            pid = p.get("paperId")
            if pid in abstracts and ("abstract" not in p or p.get("abstract") is None):
                p["abstract"] = abstracts[pid]
                updated += 1
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(raw, fp, ensure_ascii=False, indent=2)
        print(f"  {f.name}: 更新了 {updated} 篇")

    print("\n完成！")


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="批量补全 Semantic Scholar 搜索结果中缺失的摘要"
    )
    parser.add_argument(
        "paths", nargs="+",
        help="目录路径（自动扫描 layer_*_raw.json）或具体 JSON 文件路径"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅检查缺失情况，不实际请求 API"
    )
    parser.add_argument(
        "--api-key", help="S2 API Key（也可设 S2_API_KEY 环境变量）"
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
