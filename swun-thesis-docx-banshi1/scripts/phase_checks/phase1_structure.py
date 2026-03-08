#!/usr/bin/env python3
"""Phase 1: 结构/分页检查。"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verification.report_generator import check_phase1_structure


def run(docx_path: str) -> list[str]:
    """运行 Phase 1 检查，返回错误列表。"""
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")
            num = zf.read("word/numbering.xml").decode("utf-8", errors="ignore")
        return check_phase1_structure(doc, num)
    except FileNotFoundError:
        return [f"DOCX file not found: {docx_path}"]
    except zipfile.BadZipFile:
        return [f"invalid DOCX archive: {docx_path}"]
    except KeyError as exc:
        return [f"DOCX missing required OOXML part: {exc}"]
    except Exception as exc:  # defensive fallback for gate recording
        return [f"phase1 runtime error: {exc}"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: phase1_structure.py /path/to/main_版式1.docx", file=sys.stderr)
        sys.exit(2)
    errors = run(sys.argv[1])
    if errors:
        print("PHASE 1 (结构/分页): FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PHASE 1 (结构/分页): PASS")
