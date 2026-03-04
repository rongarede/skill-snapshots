#!/usr/bin/env python3
"""Phase 2: 样式/缩进检查。"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verification.report_generator import check_phase2_style


def run(docx_path: str) -> list[str]:
    """运行 Phase 2 检查，返回错误列表。"""
    with zipfile.ZipFile(docx_path, "r") as zf:
        doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")
    return check_phase2_style(doc)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: phase2_style.py /path/to/main_版式1.docx", file=sys.stderr)
        sys.exit(2)
    errors = run(sys.argv[1])
    if errors:
        print("PHASE 2 (样式/缩进): FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PHASE 2 (样式/缩进): PASS")
