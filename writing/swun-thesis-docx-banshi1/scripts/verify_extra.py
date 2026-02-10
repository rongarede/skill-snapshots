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


def _iter_paragraphs(doc_xml: str) -> list[str]:
    # Good enough for checks (Word XML is regular; paragraphs aren't nested).
    return re.findall(r"(<w:p[\s\S]*?</w:p>)", doc_xml)

def _p_text(p_xml: str) -> str:
    # Join all text runs within a paragraph. This avoids false negatives when punctuation
    # is split across <w:t> nodes.
    parts = re.findall(r"<w:t[^>]*>([\s\S]*?)</w:t>", p_xml)
    return "".join(parts)


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

    # Sectioned page numbering: expect Roman + Arabic page formats.
    if 'w:fmt="lowerRoman"' not in doc:
        errors.append('missing Roman page numbering (w:pgNumType w:fmt="lowerRoman") for abstracts section')
    if 'w:fmt="decimal"' not in doc or 'w:start="1"' not in doc:
        errors.append('missing Arabic page numbering restart (w:pgNumType w:fmt="decimal" w:start="1") for main body')

    paras = _iter_paragraphs(doc)
    texts = [_p_text(p) for p in paras]

    # Abstract keywords: required with a blank line before.
    if not any("关键词：" in t for t in texts):
        errors.append("missing Chinese abstract keywords line (expected '关键词：...')")
    if not any("Keywords:" in t for t in texts):
        errors.append("missing English abstract keywords line (expected 'Keywords: ...')")

    # Best-effort: ensure there is an empty paragraph right before each keywords line.
    for marker in ["关键词：", "Keywords:"]:
        for i, t in enumerate(texts):
            if marker not in t:
                continue
            if i == 0:
                errors.append(f"keywords line '{marker}' is the first paragraph; expected a blank line before it")
                continue
            prev_t = texts[i - 1].strip()
            if prev_t:
                errors.append(f"missing blank line before keywords line '{marker}' (previous paragraph contains text)")
            break

    # Best-effort: ensure 3-4 groups (<= 3 separators) for both CN and EN.
    # We only check locally around the marker to avoid over-parsing OOXML.
    def _check_groups(marker: str, sep: str, max_sep: int = 3) -> None:
        for t in texts:
            if marker not in t:
                continue
            tail = t.split(marker, 1)[1]
            if tail.count(sep) > max_sep:
                errors.append(f"too many keyword separators near '{marker}' (expected 3-4 groups)")
            return

    _check_groups("关键词：", "；", 3)
    _check_groups("Keywords:", ";", 3)

    # Bibliography hanging indent: should be present for entries.
    if "参考文献" in doc and "hangingChars" not in doc:
        errors.append("missing hanging indent for bibliography entries (w:hangingChars)")

    # Citations should appear as [n] and often superscript.
    if "vertAlign" not in doc and not re.search(r"\[[0-9]{1,3}\]", doc):
        errors.append("no obvious citation markers found (expected [n] possibly superscript)")

    # Figure captions: expect "图{章}-{序号} ..."
    cap_re = re.compile(r"图\d+-\d+\s+")
    cap_paras = []
    for p in _iter_paragraphs(doc):
        if cap_re.search(p):
            cap_paras.append(p)

    if not cap_paras:
        errors.append("no numbered figure captions found (expected '图{章}-{序号} ...')")
    else:
        # Captions should be centered.
        not_centered = [p for p in cap_paras if 'w:jc w:val="center"' not in p]
        if not_centered:
            errors.append("some figure captions are not centered (missing w:jc center)")

    # Equation numbering: expect some display-math paras to end with '(章-序号)'.
    eq_re = re.compile(r"\(\d+-\d+\)")
    math_paras = [p for p in _iter_paragraphs(doc) if "<m:oMathPara" in p]
    numbered_math_paras = [p for p in math_paras if eq_re.search(p)]
    if math_paras and not numbered_math_paras:
        errors.append("no equation numbers found on display-math paragraphs (expected '(章-序号)')")

    # Ensure we don't accidentally number the universal-quantifier display line.
    for p in math_paras:
        if "<m:t>∀</m:t>" in p and eq_re.search(p):
            errors.append("found an equation number on a quantifier-only display math paragraph (should be unnumbered)")
            break

    # KeepTogether hints for figures (best-effort).
    if "<w:keepNext" not in doc:
        errors.append("missing keepNext in document.xml (expected for figure paragraphs)")

    if errors:
        print("EXTRA VERIFY: FAIL")
        for e in errors:
            print(f"- {e}")
        return 1

    print("EXTRA VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
