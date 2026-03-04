#!/usr/bin/env python3
"""
Gate-Loop Runner: 驱动 6 Phase DOCX 检测循环。

使用方法：
  python3 gate_loop_runner.py /path/to/thesis_dir [--phase N] [--max-retry 3]

  --phase N       仅运行指定 Phase（1-6）
  --max-retry N   每个 Phase 最大重试次数（默认 3）
  --gate-file     Gate 记录文件路径（默认 thesis_dir/gates.md）
  --skip-build    跳过首次 DOCX 构建（假设已有最新 DOCX）
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
GATE_LOOP_SCRIPTS = Path.home() / ".claude/skills/gate-loop-orchestrator/scripts"
CODEX_BRIDGE = Path.home() / ".claude/skills/collaborating-with-codex/scripts/codex_bridge.py"
BUILDER_PATH = SCRIPT_DIR / "modules/docx_builder.py"

PHASES = {
    1: {"name": "结构/分页", "module": "phase1_structure", "fix_target": "builder"},
    2: {"name": "样式/缩进", "module": "phase2_style", "fix_target": "builder"},
    3: {"name": "图表标题", "module": "phase3_caption", "fix_target": "builder"},
    4: {"name": "交叉引用", "module": "phase4_crossref", "fix_target": "builder"},
    5: {"name": "内容规范", "module": "phase5_content", "fix_target": "latex"},
    6: {"name": "视觉审查", "module": "phase6_visual", "fix_target": "mixed"},
}


def codex_fix(phase_id: int, errors: list[str], thesis_dir: str) -> bool:
    """调用 Codex CLI 修复错误，返回是否调用成功。"""
    phase = PHASES[phase_id]
    target = phase["fix_target"]
    error_list = "\n".join(f"- {e}" for e in errors[:10])

    if target == "builder":
        prompt = (
            f"修复 DOCX builder 中的以下问题（Phase {phase_id}: {phase['name']}）：\n\n"
            f"{error_list}\n\n"
            f"修复文件：{BUILDER_PATH}\n"
            f"修复后运行：bash {SCRIPT_DIR}/main.sh {thesis_dir} 验证修复。"
        )
        cd = str(SKILL_DIR)
    elif target == "latex":
        prompt = (
            f"修复 LaTeX 源文件中的以下内容规范问题（Phase {phase_id}: {phase['name']}）：\n\n"
            f"{error_list}\n\n"
            f"修复范围：{thesis_dir}/chapters/*.tex\n"
            "修复后运行：latexmk -xelatex -interaction=nonstopmode main.tex 验证编译。"
        )
        cd = thesis_dir
    else:
        print(f"  [FIX] Phase {phase_id} 需要人工判断修复目标", file=sys.stderr)
        return False

    if not CODEX_BRIDGE.exists():
        print(f"  [FIX] codex_bridge.py 不存在: {CODEX_BRIDGE}", file=sys.stderr)
        return False

    result = subprocess.run(
        [
            "python3",
            str(CODEX_BRIDGE),
            "--cd",
            cd,
            "--sandbox",
            "danger-full-access",
            "--skip-git-repo-check",
            "--PROMPT",
            prompt,
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if result.returncode != 0:
        print(f"  [FIX] Codex 修复失败:\n{result.stderr[-300:]}", file=sys.stderr)
        return False

    print("  [FIX] Codex 修复完成")
    return True


def build_docx(thesis_dir: str) -> bool:
    """构建 DOCX，返回是否成功。"""
    main_sh = SCRIPT_DIR / "main.sh"
    result = subprocess.run(
        ["bash", str(main_sh), thesis_dir],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        print(f"[BUILD] FAIL:\n{result.stderr[-500:]}", file=sys.stderr)
        return False
    print("[BUILD] OK")
    return True


def run_phase_check(phase_id: int, docx_path: str) -> list[str]:
    """运行指定 Phase 的检查，返回错误列表。"""
    module_name = PHASES[phase_id]["module"]

    sys.path.insert(0, str(SCRIPT_DIR / "phase_checks"))
    import importlib

    mod = importlib.import_module(module_name)

    if phase_id == 6:
        result = mod.run(docx_path)
        if result["status"] == "conversion_failed":
            return ["DOCX→PDF 转换失败，无法进行视觉审查（需要安装 libreoffice）"]
        return []

    return mod.run(docx_path)


def write_gate_record(gate_file: str, phase_id: int, errors: list[str]) -> None:
    """写入 Gate 记录。"""
    script = GATE_LOOP_SCRIPTS / "write_gate_record.sh"
    if not script.exists():
        with open(gate_file, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            status = "FAIL" if errors else "PASS"
            f.write(f"\n### Gate-{phase_id} Attempt {ts}\n\n")
            f.write(f"- 状态：`{status}`\n")
            f.write(f"- Phase: {PHASES[phase_id]['name']}\n")
            if errors:
                f.write(f"- 错误数: {len(errors)}\n")
                f.write("- Must-Fix：\n")
                for e in errors[:10]:
                    f.write(f"  - {e}\n")
            f.write("\n")
        return

    status = "FAIL" if errors else "PASS"
    critical = str(len([e for e in errors if "missing" in e.lower() or "fail" in e.lower()]))
    major = str(len(errors) - int(critical))
    must_fix = "; ".join(errors[:5]) if errors else ""
    evidence = f"{len(errors)} errors found" if errors else "all checks passed"

    subprocess.run(
        [
            "bash",
            str(script),
            "--gate-file",
            gate_file,
            "--phase",
            str(phase_id),
            "--status",
            status,
            "--decision",
            f"Phase {phase_id} ({PHASES[phase_id]['name']}): {status}",
            "--critical",
            critical,
            "--major",
            major,
            "--minor",
            "0",
            "--must-fix",
            must_fix,
            "--evidence",
            evidence,
        ],
        check=False,
    )


def run_gate_loop(
    thesis_dir: str,
    phase_ids: list[int],
    max_retry: int,
    gate_file: str,
    skip_build: bool,
) -> dict[int, str]:
    """运行 gate loop，返回每个 Phase 的结果。"""
    docx_path = os.path.join(thesis_dir, "main_版式1.docx")
    results: dict[int, str] = {}

    if not skip_build:
        if not build_docx(thesis_dir):
            print("[GATE-LOOP] 首次构建失败，终止。", file=sys.stderr)
            return {p: "SKIP" for p in phase_ids}

    for phase_id in phase_ids:
        phase = PHASES[phase_id]
        print(f"\n{'=' * 60}")
        print(f"[PHASE {phase_id}] {phase['name']}")
        print(f"{'=' * 60}")

        passed = False
        for attempt in range(1, max_retry + 1):
            print(f"  [Attempt {attempt}/{max_retry}]")

            errors = run_phase_check(phase_id, docx_path)
            write_gate_record(gate_file, phase_id, errors)

            if not errors:
                print(f"  [PHASE {phase_id}] PASS")
                passed = True
                break

            print(f"  [PHASE {phase_id}] FAIL ({len(errors)} errors)")
            for e in errors[:5]:
                print(f"    - {e}")

            if attempt < max_retry:
                print(f"  [FIX] 调用 Codex 自动修复 (target={phase['fix_target']})")
                fix_ok = codex_fix(phase_id, errors, thesis_dir)
                if not fix_ok:
                    print("  [FIX] 修复失败，跳过重试")
                    break
                print("  [REBUILD] 重新构建 DOCX...")
                if not build_docx(thesis_dir):
                    print("  [REBUILD] 构建失败")
                    break

        results[phase_id] = "PASS" if passed else "FAIL"
        if not passed:
            print(f"\n[GATE-LOOP] Phase {phase_id} 未通过，后续 Phase 跳过。")
            for remaining in phase_ids[phase_ids.index(phase_id) + 1:]:
                results[remaining] = "SKIP"
            break

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate-Loop DOCX 6-Phase 检测")
    parser.add_argument("thesis_dir", help="论文根目录")
    parser.add_argument("--phase", type=int, help="仅运行指定 Phase (1-6)")
    parser.add_argument("--max-retry", type=int, default=1, help="每个 Phase 单次运行（修复在外部编排）")
    parser.add_argument("--gate-file", help="Gate 记录文件路径")
    parser.add_argument("--skip-build", action="store_true", help="跳过 DOCX 构建")
    args = parser.parse_args()

    thesis_dir = args.thesis_dir
    gate_file = args.gate_file or os.path.join(thesis_dir, "gates.md")

    if args.phase:
        if args.phase not in PHASES:
            print(f"无效 Phase: {args.phase}，有效范围 1-6", file=sys.stderr)
            return 2
        phase_ids = [args.phase]
    else:
        phase_ids = list(PHASES.keys())

    results = run_gate_loop(thesis_dir, phase_ids, args.max_retry, gate_file, args.skip_build)

    print(f"\n{'=' * 60}")
    print("[GATE-LOOP SUMMARY]")
    for pid, status in results.items():
        print(f"  Phase {pid} ({PHASES[pid]['name']}): {status}")

    all_pass = all(s == "PASS" for s in results.values())
    if all_pass:
        print("\n全部 PASS，可以 commit。")
        return 0

    failed = [f"Phase {p}" for p, s in results.items() if s == "FAIL"]
    print(f"\n未通过: {', '.join(failed)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
