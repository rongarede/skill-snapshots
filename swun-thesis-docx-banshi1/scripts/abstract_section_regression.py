#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Regression checks for abstract section splitting behavior.

Covers:
1) Existing "摘要" heading separated from first CN paragraph by blank line
   must not trigger duplicate heading insertion.
2) Multi-paragraph English abstract must not be truncated by section break.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

import build_docx_banshi1 as builder


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def p_text(p: ET.Element) -> str:
    return "".join((t.text or "") for t in p.iter(q("t")))


def p_style(p: ET.Element) -> str | None:
    pPr = p.find(q("pPr"))
    if pPr is None:
        return None
    ps = pPr.find(q("pStyle"))
    if ps is None:
        return None
    return ps.get(q("val"))


def make_para(text: str, style: str | None = "a") -> ET.Element:
    p = ET.Element(q("p"))
    pPr = ET.SubElement(p, q("pPr"))
    if style is not None:
        ps = ET.SubElement(pPr, q("pStyle"))
        ps.set(q("val"), style)
    if text:
        r = ET.SubElement(p, q("r"))
        t = ET.SubElement(r, q("t"))
        t.text = text
    return p


def make_cover_break_para() -> ET.Element:
    p = ET.Element(q("p"))
    pPr = ET.SubElement(p, q("pPr"))
    sectPr = ET.SubElement(pPr, q("sectPr"))
    pg = ET.SubElement(sectPr, q("pgNumType"))
    pg.set(q("fmt"), "decimal")
    return p


def make_final_body_sectpr() -> ET.Element:
    sectPr = ET.Element(q("sectPr"))
    pg = ET.SubElement(sectPr, q("pgNumType"))
    pg.set(q("fmt"), "decimal")
    pg.set(q("start"), "1")
    return sectPr


def main() -> int:
    ns = {"w": W_NS}
    root = ET.Element(q("document"))
    body = ET.SubElement(root, q("body"))

    # Simulate a minimal frontmatter->main transition.
    body.append(make_para("附件4", "2"))
    body.append(make_cover_break_para())
    body.append(make_para("摘要", "1"))
    body.append(make_para("", "a"))  # blank line between heading and first paragraph
    body.append(make_para("车联网（V2X）环境下，中文摘要首段。", "a"))
    body.append(make_para("Abstract", "1"))
    body.append(make_para("In Vehicle-to-Everything environments, first paragraph.", "a"))
    body.append(make_para("This is the second paragraph of the English abstract.", "a"))
    body.append(make_para("绪论", "1"))
    body.append(make_final_body_sectpr())

    sect = builder._get_body_sectPr(ns, body)
    if sect is None:
        raise SystemExit("REGRESSION FAIL: missing body sectPr")
    sect_proto = copy.deepcopy(sect)
    builder._insert_abstract_chapters_and_sections(ns, body, sect_proto)

    children = list(body)
    heading_cn = []
    heading_en = []
    idx_main = None
    idx_en_second = None
    idx_roman_break = None
    for i, el in enumerate(children):
        if el.tag != q("p"):
            continue
        txt = p_text(el).strip()
        st = p_style(el)
        if st == "1" and txt == "摘要":
            heading_cn.append(i)
        if st == "1" and txt == "Abstract":
            heading_en.append(i)
        if st == "1" and txt == "绪论":
            idx_main = i
        if "second paragraph of the English abstract" in txt:
            idx_en_second = i
        pPr = el.find(q("pPr"))
        if pPr is None:
            continue
        sectPr = pPr.find(q("sectPr"))
        if sectPr is None:
            continue
        pg = sectPr.find(q("pgNumType"))
        if pg is not None and pg.get(q("fmt")) == "lowerRoman":
            idx_roman_break = i

    if len(heading_cn) != 1:
        raise SystemExit(f"REGRESSION FAIL: 摘要 heading count={len(heading_cn)}, expected 1")
    if len(heading_en) != 1:
        raise SystemExit(f"REGRESSION FAIL: Abstract heading count={len(heading_en)}, expected 1")
    if idx_main is None or idx_en_second is None or idx_roman_break is None:
        raise SystemExit("REGRESSION FAIL: missing main heading / en second paragraph / roman section break")
    if idx_roman_break != idx_main - 1:
        raise SystemExit(
            f"REGRESSION FAIL: Roman section break index={idx_roman_break}, expected immediately before main heading index={idx_main}"
        )
    if idx_en_second > idx_roman_break:
        raise SystemExit("REGRESSION FAIL: second English abstract paragraph was truncated into main section")

    print("ABSTRACT REGRESSION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

