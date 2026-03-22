#!/usr/bin/env python3
"""Phase 4: 交叉引用检查。"""
from __future__ import annotations
from verification.report_generator import check_phase4_crossref

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(docx_path: str) -> list[str]:
    """运行 Phase 4 检查，返回错误列表。"""
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        return check_phase4_crossref(doc)
    except FileNotFoundError:
        return [f"DOCX file not found: {docx_path}"]
    except zipfile.BadZipFile:
        return [f"invalid DOCX archive: {docx_path}"]
    except KeyError as exc:
        return [f"DOCX missing required OOXML part: {exc}"]
    except Exception as exc:
        return [f"phase4 runtime error: {exc}"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: phase4_crossref.py /path/to/main_版式1.docx", file=sys.stderr)
        sys.exit(2)
    errors = run(sys.argv[1])
    if errors:
        print("PHASE 4 (交叉引用): FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PHASE 4 (交叉引用): PASS")
