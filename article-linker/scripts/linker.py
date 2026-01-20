#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
article-linker: 文章标题 → 发布链接映射工具

用法:
    linker.py query "文章标题"              # 单标题查询
    linker.py batch titles.json             # 批量查询（JSON 数组）
    linker.py scan article.md               # 全文扫描，输出替换建议
    linker.py scan article.md --edit        # 全文扫描并直接编辑文件
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ==================== 配置 ====================
PLATFORM_FILE = Path.home() / ".local/share/platform-sheets/platform_info.json"
PRIORITY = ['微信', 'zsxq']
SKIP_FIELDS = {'标题', 'monetize', 'id', 'date', 'tags', ''}


# ==================== 工具函数 ====================
def load_platform_data():
    """加载平台数据"""
    if not PLATFORM_FILE.exists():
        raise RuntimeError(
            f"❌ {PLATFORM_FILE} 不存在\n"
            "请先运行 /sync-platform-sheets 同步数据"
        )
    with open(PLATFORM_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if len(data) < 10:
        print(f"⚠️ 数据量偏少（{len(data)} 条），可能需要同步", file=sys.stderr)
    return data


def normalize(title):
    """标准化标题"""
    # 去除书名号
    title = re.sub(r'[《》「」"""]', '', title)
    # 标准化空格
    title = re.sub(r'\s+', ' ', title).strip()
    # 全角转半角标点
    title = title.replace('：', ':').replace('，', ',')
    return title


def build_mapping(data):
    """构建标题→URL映射"""
    title_to_url = {}
    normalized_map = {}  # 标准化标题 → 原始标题

    for item in data:
        title = item.get('标题', '').strip()
        if not title:
            continue

        # 按优先级查找 URL
        url, platform = None, None
        for p in PRIORITY:
            u = item.get(p, '').strip()
            if u:
                url, platform = u, p
                break

        # 回退：任意非空链接字段
        if not url:
            for k, v in item.items():
                if k not in SKIP_FIELDS and v and str(v).startswith('http'):
                    url, platform = v.strip(), k
                    break

        if url:
            title_to_url[title] = (url, platform)
            normalized_map[normalize(title)] = title

    return title_to_url, normalized_map


def resolve(query, title_to_url, normalized_map):
    """解析单个标题"""
    # 1. 精确匹配
    if query in title_to_url:
        url, platform = title_to_url[query]
        return {"url": url, "platform": platform, "match": "exact"}

    # 2. 标准化匹配
    norm = normalize(query)
    if norm in normalized_map:
        orig = normalized_map[norm]
        url, platform = title_to_url[orig]
        return {"url": url, "platform": platform, "match": "normalized"}

    # 3. 包含匹配
    for title, (url, platform) in title_to_url.items():
        if query in title or title in query:
            return {"url": url, "platform": platform, "match": "fuzzy"}

    # 4. 未匹配
    return {"url": None, "platform": None, "match": "none"}


# ==================== 命令处理 ====================
def cmd_query(args, title_to_url, normalized_map):
    """单标题查询"""
    result = resolve(args.title, title_to_url, normalized_map)
    result["title"] = args.title
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_batch(args, title_to_url, normalized_map):
    """批量查询"""
    with open(args.file, 'r', encoding='utf-8') as f:
        titles = json.load(f)

    results = []
    matched = 0
    for i, title in enumerate(titles, 1):
        r = resolve(title, title_to_url, normalized_map)
        results.append({
            "num": i,
            "title": title,
            "url": r["url"],
            "platform": r["platform"],
            "match": r["match"]
        })
        if r["url"]:
            matched += 1

    total = len(titles)
    output = {
        "results": results,
        "stats": {
            "total": total,
            "matched": matched,
            "unmatched": total - matched,
            "match_rate": f"{matched/total*100:.1f}%" if total > 0 else "0%"
        }
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_scan(args, title_to_url, normalized_map):
    """全文扫描"""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    # 匹配《标题》，但排除已有链接的情况
    # 已有链接格式：[《标题》](url)
    pattern = r'(?<!\[)《([^》]+)》(?!\]\()'
    replacements = []

    for match in re.finditer(pattern, text):
        title = match.group(1)
        result = resolve(title, title_to_url, normalized_map)
        if result["url"]:
            orig = match.group(0)
            linked = f'[{orig}]({result["url"]})'
            replacements.append({
                "original": orig,
                "linked": linked,
                "platform": result["platform"],
                "match": result["match"]
            })

    if args.edit and replacements:
        # 逆序替换，避免位置偏移
        for match in reversed(list(re.finditer(pattern, text))):
            title = match.group(1)
            result = resolve(title, title_to_url, normalized_map)
            if result["url"]:
                orig = match.group(0)
                linked = f'[{orig}]({result["url"]})'
                text = text[:match.start()] + linked + text[match.end():]

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"✓ 已添加 {len(replacements)} 处链接")
        for r in replacements:
            print(f"  - {r['original']} → {r['platform']}")
    else:
        output = {
            "file": str(file_path),
            "replacements": replacements,
            "count": len(replacements)
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))


# ==================== 主入口 ====================
def main():
    parser = argparse.ArgumentParser(
        description="文章标题 → 发布链接映射工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    %(prog)s query "如何高效使用 Claude Code"
    %(prog)s batch titles.json
    %(prog)s scan article.md
    %(prog)s scan article.md --edit
"""
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # query 子命令
    p_query = subparsers.add_parser("query", help="查询单个标题的链接")
    p_query.add_argument("title", help="文章标题")

    # batch 子命令
    p_batch = subparsers.add_parser("batch", help="批量查询标题列表")
    p_batch.add_argument("file", help="包含标题数组的 JSON 文件")

    # scan 子命令
    p_scan = subparsers.add_parser("scan", help="扫描文件中的《标题》并添加链接")
    p_scan.add_argument("file", help="要扫描的 Markdown 文件")
    p_scan.add_argument("--edit", action="store_true", help="直接编辑文件（否则只输出替换建议）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 加载数据
    try:
        data = load_platform_data()
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    title_to_url, normalized_map = build_mapping(data)
    print(f"[加载] {len(title_to_url)} 条映射", file=sys.stderr)

    # 分发命令
    if args.command == "query":
        cmd_query(args, title_to_url, normalized_map)
    elif args.command == "batch":
        cmd_batch(args, title_to_url, normalized_map)
    elif args.command == "scan":
        cmd_scan(args, title_to_url, normalized_map)


if __name__ == "__main__":
    main()
