#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task-dashboard: 扫描活跃项目，提取任务，按紧急度排序输出"""

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ==================== 配置 ====================
DEFAULT_VAULT = "/Users/bit/Obsidian"
ACTIVE_DIR = "100_Projects/Active"
TODAY = datetime.now().date()

# ==================== YAML 解析 ====================

def parse_frontmatter(content: str) -> dict:
    """从 markdown 内容中提取 YAML frontmatter"""
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            fm[key] = val
    return fm


# ==================== 任务提取 ====================

def extract_tasks(content: str) -> list[dict]:
    """提取所有未完成的 checkbox 任务"""
    tasks = []
    lines = content.splitlines()
    current_section = ""
    for line in lines:
        # 跟踪当前章节
        hm = re.match(r"^(#{1,3})\s+(.+)", line)
        if hm:
            current_section = hm.group(2).strip()
            continue
        # 匹配未完成 checkbox
        tm = re.match(r"^\s*-\s+\[\s\]\s+(.+)", line)
        if tm:
            task_text = tm.group(1).strip()
            # 提取内联截止日期 `截止 YYYY-MM-DD` 或 `截止 M/DD`
            deadline = None
            dm = re.search(r"`截止\s+([\d\-/]+)`", task_text)
            if dm:
                deadline = dm.group(1)
            tasks.append({
                "text": task_text,
                "section": current_section,
                "deadline": deadline,
            })
    return tasks


def extract_timeline(content: str) -> list[dict]:
    """提取表格中的时间线（阶段 | 目标日期 | 状态）"""
    entries = []
    in_table = False
    for line in content.splitlines():
        if re.match(r"\|\s*阶段\s*\|", line):
            in_table = True
            continue
        if in_table and line.startswith("|"):
            if re.match(r"\|\s*[-:]+", line):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 3:
                entries.append({
                    "phase": cols[0],
                    "deadline": cols[1],
                    "status": cols[2],
                })
        elif in_table and not line.startswith("|"):
            in_table = False
    return entries


# ==================== 项目扫描 ====================

def find_project_pages(vault: str) -> list[Path]:
    """查找所有活跃项目的主页和规划文件"""
    active = Path(vault) / ACTIVE_DIR
    if not active.exists():
        print(f"错误: 目录不存在 {active}", file=sys.stderr)
        sys.exit(1)
    files = []
    for md in active.rglob("*.md"):
        files.append(md)
    return files


def scan_project(project_dir: Path) -> dict:
    """扫描单个项目目录，提取项目信息和任务"""
    project_name = project_dir.name.replace("Project_", "")
    main_pages = list(project_dir.glob("*项目主页.md")) + list(project_dir.glob("*_项目主页.md"))

    result = {
        "name": project_name,
        "path": str(project_dir),
        "status": "active",
        "deadline": None,
        "priority": None,
        "tasks": [],
        "timeline": [],
    }

    # 扫描主页
    for page in main_pages:
        content = page.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm.get("deadline"):
            result["deadline"] = fm["deadline"]
        if fm.get("priority"):
            result["priority"] = fm["priority"]
        if fm.get("status"):
            result["status"] = fm["status"]
        result["tasks"].extend(extract_tasks(content))
        result["timeline"].extend(extract_timeline(content))

    # 扫描 planning/ docs/ 子目录
    for subdir in ["planning", "docs", "docs/plans"]:
        d = project_dir / subdir
        if d.exists():
            for md in d.glob("*.md"):
                content = md.read_text(encoding="utf-8")
                fm = parse_frontmatter(content)
                tasks = extract_tasks(content)
                for t in tasks:
                    t["source"] = md.name
                result["tasks"].extend(tasks)

    return result


# ==================== 紧急度排序 ====================

def parse_date(s: str):
    """尝试解析日期字符串"""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d", "%m-%d"):
        try:
            d = datetime.strptime(s.strip(), fmt).date()
            # 补全年份
            if d.year == 1900:
                d = d.replace(year=TODAY.year)
            return d
        except ValueError:
            continue
    return None


def urgency_key(task: dict):
    """排序键：有截止日期的按日期升序，无截止日期的排最后"""
    dl = parse_date(task.get("deadline"))
    if dl:
        return (0, dl)
    return (1, datetime.max.date())


# ==================== 输出格式化 ====================

def format_output(projects: list[dict], mode: str = "markdown") -> str:
    """格式化输出"""
    lines = []

    # 收集所有任务并标注项目
    urgent = []     # 本周内截止
    important = []  # 本月内截止或有截止日期
    ongoing = []    # 无截止日期

    week_end = TODAY + timedelta(days=7)
    month_end = TODAY + timedelta(days=30)

    for proj in projects:
        proj_deadline = parse_date(proj.get("deadline"))

        for task in proj["tasks"]:
            task_dl = parse_date(task.get("deadline"))
            effective_dl = task_dl or proj_deadline

            entry = {
                "project": proj["name"],
                "text": task["text"],
                "deadline": task.get("deadline") or (proj.get("deadline") if not task_dl else None),
                "deadline_date": effective_dl,
                "section": task.get("section", ""),
            }

            if effective_dl and effective_dl <= week_end:
                urgent.append(entry)
            elif effective_dl and effective_dl <= month_end:
                important.append(entry)
            else:
                ongoing.append(entry)

        # 时间线条目也转为任务
        for tl in proj.get("timeline", []):
            if tl["status"] in ("待开始", "进行中"):
                tl_dl = parse_date(tl["deadline"])
                entry = {
                    "project": proj["name"],
                    "text": tl["phase"],
                    "deadline": tl["deadline"],
                    "deadline_date": tl_dl,
                    "section": "时间线",
                }
                if tl_dl and tl_dl <= week_end:
                    urgent.append(entry)
                elif tl_dl and tl_dl <= month_end:
                    important.append(entry)

    # 去重（按 project+text）
    def dedup(items):
        seen = set()
        result = []
        for item in items:
            key = (item["project"], item["text"][:50])
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    urgent = dedup(sorted(urgent, key=urgency_key))
    important = dedup(sorted(important, key=urgency_key))
    ongoing = dedup(ongoing)

    # 输出
    lines.append("### 🔴 紧急（本周截止）\n")
    if urgent:
        for t in urgent:
            dl = f"`截止 {t['deadline']}`" if t["deadline"] else ""
            lines.append(f"- [ ] **{t['project']}** — {t['text']} {dl}")
    else:
        lines.append("（无）")

    lines.append("\n### 🟡 重要（本月内）\n")
    if important:
        for t in important:
            dl = f"`截止 {t['deadline']}`" if t["deadline"] else ""
            lines.append(f"- [ ] **{t['project']}** — {t['text']} {dl}")
    else:
        lines.append("（无）")

    lines.append("\n### 🔵 长期进行中（无截止日期）\n")
    if ongoing:
        # 按项目分组，只显示前 3 个任务
        by_proj = {}
        for t in ongoing:
            by_proj.setdefault(t["project"], []).append(t)
        for proj_name, tasks in by_proj.items():
            shown = tasks[:3]
            remaining = len(tasks) - len(shown)
            for t in shown:
                lines.append(f"- [ ] **{proj_name}** — {t['text']}")
            if remaining > 0:
                lines.append(f"  - *...还有 {remaining} 项*")
    else:
        lines.append("（无）")

    # 统计
    total = len(urgent) + len(important) + len(ongoing)
    lines.append(f"\n---\n**共 {total} 项待办** | 紧急 {len(urgent)} | 重要 {len(important)} | 长期 {len(ongoing)}")

    return "\n".join(lines)


# ==================== 主逻辑 ====================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="扫描活跃项目任务")
    parser.add_argument("--vault", default=DEFAULT_VAULT, help="Obsidian vault 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = parser.parse_args()

    vault = args.vault
    active_path = Path(vault) / ACTIVE_DIR
    if not active_path.exists():
        print(f"错误: {active_path} 不存在", file=sys.stderr)
        sys.exit(1)

    projects = []
    for d in sorted(active_path.iterdir()):
        if d.is_dir() and d.name.startswith("Project_"):
            proj = scan_project(d)
            if proj["tasks"] or proj["timeline"]:
                projects.append(proj)

    if args.json:
        import json
        print(json.dumps(projects, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_output(projects))


if __name__ == "__main__":
    main()
