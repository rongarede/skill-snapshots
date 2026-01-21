#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
task-dispatcher: 任务拆分与依赖分析
"""

import json
import re
import sys
from typing import List, Dict, Any

# ==================== 任务拆分 ====================

def should_split(task: str) -> bool:
    """
    判断任务是否需要拆分
    """
    # 必须拆分的情况
    if "并" in task or "和" in task or "+" in task:
        return True
    if count_target_files(task) > 1:
        return True
    if has_multiple_verbs(task):
        return True
    if estimated_lines_changed(task) > 100:
        return True
    return False


def count_target_files(task: str) -> int:
    """
    估算任务涉及的文件数量
    """
    # 简单启发式：文件路径模式
    file_patterns = re.findall(r'\b[\w/]+\.(ts|js|rs|py|go|java)\b', task)
    return len(set(file_patterns))


def has_multiple_verbs(task: str) -> bool:
    """
    检查任务是否包含多个动词（多个操作）
    """
    verbs = ["实现", "测试", "重构", "修复", "添加", "删除", "更新", "创建", "优化", "编写"]
    count = sum(1 for v in verbs if v in task)
    return count > 1


def estimated_lines_changed(task: str) -> int:
    """
    估算代码变更行数
    """
    # 简单启发式：根据任务复杂度关键词
    complexity_markers = {
        "模块": 200,
        "系统": 300,
        "功能": 100,
        "函数": 50,
        "方法": 30,
        "修复": 20,
        "配置": 10,
    }
    for marker, lines in complexity_markers.items():
        if marker in task:
            return lines
    return 50  # 默认


# ==================== 依赖分析 ====================

def analyze_dependencies(subtasks: List[Dict[str, Any]]) -> List[List[int]]:
    """
    分析子任务依赖关系，返回执行批次

    输入: [{"id": 1, "deps": []}, {"id": 2, "deps": [1]}, ...]
    输出: [[1], [2, 3], [4]]  # 每个内层列表是一个可并发批次
    """
    # 构建依赖图
    graph = {t["id"]: set(t.get("deps", [])) for t in subtasks}
    all_ids = set(graph.keys())

    batches = []
    completed = set()

    while len(completed) < len(all_ids):
        # 找出所有依赖已满足的任务
        ready = [
            tid for tid in all_ids
            if tid not in completed and graph[tid].issubset(completed)
        ]

        if not ready:
            # 检测循环依赖
            remaining = all_ids - completed
            raise ValueError(f"检测到循环依赖: {remaining}")

        batches.append(ready)
        completed.update(ready)

    return batches


# ==================== 验证结果 ====================

def is_verification_failed(exit_code: int, stdout: str, expected_pattern: str = None) -> bool:
    """
    判断验证是否失败
    """
    # 明确失败
    if exit_code != 0:
        return True

    # 输出包含错误标记
    error_markers = ["FAIL", "Error", "error:", "FAILED", "panic", "Exception"]
    if any(err in stdout for err in error_markers):
        return True

    # 预期内容缺失
    if expected_pattern and expected_pattern not in stdout:
        return True

    return False


# ==================== 拆分输出 ====================

def format_subtasks_yaml(subtasks: List[Dict[str, Any]]) -> str:
    """
    格式化子任务为 YAML
    """
    lines = ["子任务:"]
    for t in subtasks:
        lines.append(f"  - id: {t['id']}")
        lines.append(f"    描述: {t['desc']}")
        lines.append(f"    文件: {t['file']}")
        lines.append(f"    验证: \"{t['verify']}\"")
        deps = t.get("deps", [])
        lines.append(f"    依赖: {deps}")
        lines.append("")
    return "\n".join(lines)


def format_batches(batches: List[List[int]]) -> str:
    """
    格式化执行批次
    """
    lines = []
    for i, batch in enumerate(batches, 1):
        parallel_mark = "并发" if len(batch) > 1 else "串行"
        tasks = ", ".join(f"任务 {tid}" for tid in batch)
        lines.append(f"批次 {i} ({parallel_mark}): [{tasks}]")
    return "\n".join(lines)


# ==================== CLI ====================

def main():
    if len(sys.argv) < 2:
        print("用法: python task-logic.py <command> [args]")
        print("命令:")
        print("  should-split <task>       判断任务是否需要拆分")
        print("  analyze-deps <json>       分析依赖关系 (JSON 格式)")
        print("  verify <exit_code> <stdout> [expected]  判断验证是否失败")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "should-split":
        task = sys.argv[2] if len(sys.argv) > 2 else ""
        result = should_split(task)
        print(json.dumps({"should_split": result}))

    elif cmd == "analyze-deps":
        subtasks_json = sys.argv[2] if len(sys.argv) > 2 else "[]"
        subtasks = json.loads(subtasks_json)
        batches = analyze_dependencies(subtasks)
        print(json.dumps({"batches": batches}))
        print(format_batches(batches))

    elif cmd == "verify":
        exit_code = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        stdout = sys.argv[3] if len(sys.argv) > 3 else ""
        expected = sys.argv[4] if len(sys.argv) > 4 else None
        result = is_verification_failed(exit_code, stdout, expected)
        print(json.dumps({"failed": result}))

    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
