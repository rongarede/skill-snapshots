#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto-iterate: skill-full 复合评估脚本

对一个完整 skill 目录进行 4 维加权评估，输出复合分数。
用法: python3 evaluate_skill_full.py <skill-dir>
"""

import sys
import subprocess
import re
from pathlib import Path
from typing import Optional


def check_skill_md(skill_md: Optional[Path]) -> tuple[float, list[str]]:
    """检查 skill.md 定义质量，返回 (score, issues)"""
    if not skill_md:
        return 0.0, ["skill.md not found"]

    issues = []
    score = 10.0
    content = skill_md.read_text(encoding="utf-8", errors="replace")

    # frontmatter 检查
    if not content.startswith("---"):
        score -= 2.0
        issues.append("missing frontmatter")
    else:
        if "name:" not in content:
            score -= 1.0
            issues.append("missing name in frontmatter")
        if "description:" not in content:
            score -= 1.0
            issues.append("missing description in frontmatter")

    # 触发词检查
    trigger_patterns = ["触发", "trigger", "触发词", "触发方式"]
    if not any(p in content.lower() for p in trigger_patterns):
        score -= 1.5
        issues.append("no trigger section")

    # 工作流/执行步骤检查
    workflow_patterns = ["##", "步骤", "step", "流程", "执行", "workflow"]
    if sum(1 for p in workflow_patterns if p in content.lower()) < 2:
        score -= 1.0
        issues.append("weak workflow definition")

    # 约束检查
    constraint_patterns = ["约束", "constraint", "CAN", "CANNOT", "禁止", "不可"]
    if not any(p in content for p in constraint_patterns):
        score -= 1.0
        issues.append("no constraints section")

    # 行数（过长扣分）
    if len(content.splitlines()) > 300:
        score -= 0.5
        issues.append(f"verbose: {len(content.splitlines())} lines")

    return max(0.0, score), issues


def check_pylint(py_files: list[Path]) -> tuple[float, list[str]]:
    """对所有 .py 文件运行 pylint，返回 (avg_score, issues)"""
    if not py_files:
        return 10.0, ["no python files"]

    scores = []
    issues = []

    for f in py_files:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pylint", "--score=y",
                 "--disable=import-error", str(f)],
                capture_output=True, text=True, timeout=30, check=False)
            match = re.search(
                r"rated at ([\d.]+)/10", result.stdout + result.stderr)
            s = float(match.group(1)) if match else 0.0
            scores.append(s)
            if not match:
                issues.append(f"{f.name}: pylint parse failed")
            elif s < 8.0:
                issues.append(f"{f.name}: pylint {s:.2f}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            scores.append(0.0)
            issues.append(f"{f.name}: pylint timeout/not found")

    avg = sum(scores) / len(scores) if scores else 0.0
    return avg, issues


def check_flake8(py_files: list[Path]) -> tuple[float, int, list[str]]:
    """对所有 .py 文件运行 flake8，返回 (normalized_score, raw_count, issues)"""
    if not py_files:
        return 10.0, 0, ["no python files"]

    total_warnings = 0
    issues = []

    for f in py_files:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "flake8", str(f)],
                capture_output=True, text=True, timeout=30, check=False)
            count = len(result.stdout.strip().splitlines()) \
                if result.stdout.strip() else 0
            total_warnings += count
            if count > 0:
                issues.append(f"{f.name}: {count} warnings")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            issues.append(f"{f.name}: flake8 timeout/not found")

    # 归一化: 0 warnings = 10, 20+ warnings = 0
    normalized = max(0.0, 10.0 - total_warnings * 0.5)
    return normalized, total_warnings, issues


def check_consistency(skill_dir: Path, skill_md_path: Path,
                      py_files: list[Path]) -> tuple[float, list[str]]:
    """检查 skill.md 与脚本的一致性"""
    if not skill_md_path:
        return 0.0, ["no skill.md for consistency check"]

    issues = []
    score = 10.0
    content = skill_md_path.read_text(encoding="utf-8", errors="replace")
    scripts_dir = skill_dir / "scripts"

    # 检查 skill.md 中引用的脚本是否存在
    for ref in re.findall(r"scripts/(\w+\.(?:py|sh))", content):
        if not (scripts_dir / ref).exists():
            score -= 2.5
            issues.append(f"referenced script missing: scripts/{ref}")

    # 检查存在的脚本是否被 skill.md 引用
    sh_files = list(scripts_dir.glob("*.sh")) if scripts_dir.exists() else []
    for f in list(py_files) + sh_files:
        if f.name not in content:
            score -= 1.0
            issues.append(f"script not referenced in skill.md: {f.name}")

    return max(0.0, score), issues


def _find_skill_md(skill_dir: Path):
    """Locate skill.md (case-insensitive) in skill_dir."""
    for name in ["skill.md", "SKILL.md"]:
        candidate = skill_dir / name
        if candidate.exists():
            return candidate
    return None


def _print_report(skill_dir, py_files, scores, all_issues):
    """Print structured evaluation report."""
    header = [f"skill_dir: {skill_dir}", f"py_files: {len(py_files)}"]
    dims = [
        ("definition_score", scores['definition']),
        ("pylint_avg", scores['pylint']),
        ("flake8_normalized", scores['flake8_norm']),
        ("consistency_score", scores['consistency']),
    ]
    lines = header + ["---"]
    lines += [f"{k}: {v:.2f}" for k, v in dims]
    lines += [f"flake8_raw: {scores['flake8_raw']}", "---",
              f"total_score: {scores['total']:.2f}", "---"]
    lines += [f"{k}: {'; '.join(v)}" for k, v in all_issues.items() if v]
    print("\n".join(lines))


def main():
    """Entry point: evaluate a skill directory."""
    if len(sys.argv) < 2:
        print("Usage: evaluate_skill_full.py <skill-dir>")
        sys.exit(1)

    skill_dir = Path(sys.argv[1]).resolve()
    if not skill_dir.is_dir():
        print(f"ERROR: not a directory: {skill_dir}")
        sys.exit(1)

    skill_md = _find_skill_md(skill_dir)
    scripts_dir = skill_dir / "scripts"
    py_files = (
        sorted(scripts_dir.glob("*.py"))
        if scripts_dir.exists() else []
    )

    # 4 维评估
    d_s, d_i = check_skill_md(skill_md)
    p_s, p_i = check_pylint(py_files)
    f_s, f_r, f_i = check_flake8(py_files)
    c_s, c_i = check_consistency(skill_dir, skill_md, py_files)

    scores = {
        "definition": d_s, "pylint": p_s,
        "flake8_norm": f_s, "flake8_raw": f_r, "consistency": c_s,
        "total": d_s * 0.3 + p_s * 0.3 + f_s * 0.2 + c_s * 0.2,
    }
    _print_report(skill_dir, py_files, scores, {
        "definition_issues": d_i, "pylint_issues": p_i,
        "flake8_issues": f_i, "consistency_issues": c_i,
    })


if __name__ == "__main__":
    main()
