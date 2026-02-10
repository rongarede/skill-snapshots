#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extra validations for the produced SWUN DOCX.
This avoids relying on styleId string-matching in styles.xml, which can vary across templates.
"""

from __future__ import annotations

import re
import sys
import zipfile


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_extra.py /path/to/main_版式1.docx", file=sys.stderr)
        return 2

    docx_path = sys.argv[1]
    with zipfile.ZipFile(docx_path, "r") as zf:
        doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        num = zf.read("word/numbering.xml").decode("utf-8", errors="ignore")

    errors: list[str] = []

    if " TOC " not in doc:
        errors.append("missing Word TOC field (instrText contains ' TOC ')")

    if "目录" not in doc:
        errors.append("missing TOC title text '目录'")

    # Ensure page breaks exist (chapters start on new page).
    if 'w:type="page"' not in doc:
        errors.append("missing page breaks (w:br w:type=page)")

    # Numbering fix for mixed Chinese/Arabic at lower levels.
    if "w:abstractNumId=\"0\"" in num and "w:isLgl" not in num:
        errors.append("missing w:isLgl in numbering.xml (abstractNumId=0)")

    # Bibliography hanging indent: should be present for entries.
    if "参考文献" in doc and "hangingChars" not in doc:
        errors.append("missing hanging indent for bibliography entries (w:hangingChars)")

    # Citations should appear as [n] and often superscript.
    if "vertAlign" not in doc and not re.search(r"\[[0-9]{1,3}\]", doc):
        errors.append("no obvious citation markers found (expected [n] possibly superscript)")

    if errors:
        print("EXTRA VERIFY: FAIL")
        for e in errors:
            print(f"- {e}")
        return 1

    print("EXTRA VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

