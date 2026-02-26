#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression samples for figure/table reference normalization.

This script validates the expected dot->hyphen behavior on representative
input shapes used by pandoc-generated DOCX text and hyperlink runs.
"""

from __future__ import annotations

import re


INLINE_RE = re.compile(r"((?:图|表)\s*)(\d+)\.(\d+)")
DOTTED_RE = re.compile(r"(?<!\d)(\d+)\.(\d+)(?!\d)")


def normalize_inline_ref(s: str) -> str:
    return INLINE_RE.sub(r"\1\2-\3", s)


def normalize_hyperlink_ref_text(s: str) -> str:
    return DOTTED_RE.sub(r"\1-\2", s)


def main() -> int:
    cases_inline = [
        ("如图3.16所示", "如图3-16所示"),
        ("见表4.2结果", "见表4-2结果"),
        ("图 3.7 与表 5.3 对比", "图 3-7 与表 5-3 对比"),
    ]
    for raw, exp in cases_inline:
        got = normalize_inline_ref(raw)
        if got != exp:
            raise SystemExit(f"REGRESSION FAIL inline: {raw!r} -> {got!r}, want {exp!r}")

    cases_hyperlink = [
        ("3.16", "3-16"),
        ("  12.4  ", "  12-4  "),
        ("3-16", "3-16"),
    ]
    for raw, exp in cases_hyperlink:
        got = normalize_hyperlink_ref_text(raw)
        if got != exp:
            raise SystemExit(
                f"REGRESSION FAIL hyperlink: {raw!r} -> {got!r}, want {exp!r}"
            )

    print("REF REGRESSION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

