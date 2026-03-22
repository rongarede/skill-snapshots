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
    """返回带命名空间的 OOXML 标签名。"""
    return f"{{{W_NS}}}{local}"


def p_text(p: ET.Element) -> str:
    """提取段落元素中所有文本内容并拼接返回。"""
    return "".join((t.text or "") for t in p.iter(q("t")))


def p_style(p: ET.Element) -> str | None:
    """返回段落的样式 ID，若无则返回 None。"""
    p_pr = p.find(q("pPr"))
    if p_pr is None:
        return None
    ps = p_pr.find(q("pStyle"))
    if ps is None:
        return None
    return ps.get(q("val"))


def make_para(text: str, style: str | None = "a") -> ET.Element:
    """创建一个带指定样式和文本的段落 XML 元素。"""
    p = ET.Element(q("p"))
    p_pr = ET.SubElement(p, q("pPr"))
    if style is not None:
        ps = ET.SubElement(p_pr, q("pStyle"))
        ps.set(q("val"), style)
    if text:
        r = ET.SubElement(p, q("r"))
        t = ET.SubElement(r, q("t"))
        t.text = text
    return p


def make_cover_break_para() -> ET.Element:
    """创建封面分节符段落，用于隔离封面与正文页码格式。"""
    p = ET.Element(q("p"))
    p_pr = ET.SubElement(p, q("pPr"))
    sect_pr = ET.SubElement(p_pr, q("sectPr"))
    pg = ET.SubElement(sect_pr, q("pgNumType"))
    pg.set(q("fmt"), "decimal")
    return p


def make_final_body_sectpr() -> ET.Element:
    """创建正文节属性元素，页码从 1 开始的十进制格式。"""
    sect_pr = ET.Element(q("sectPr"))
    pg = ET.SubElement(sect_pr, q("pgNumType"))
    pg.set(q("fmt"), "decimal")
    pg.set(q("start"), "1")
    return sect_pr


def _build_test_body() -> ET.Element:
    """构建用于回归测试的最小 OOXML body 元素。"""
    root = ET.Element(q("document"))
    body = ET.SubElement(root, q("body"))
    body.append(make_para("附件4", "2"))
    body.append(make_cover_break_para())
    body.append(make_para("摘要", "1"))
    body.append(make_para("", "a"))  # blank between heading and first para
    body.append(make_para("车联网（V2X）环境下，中文摘要首段。", "a"))
    body.append(make_para("Abstract", "1"))
    body.append(make_para(
        "In Vehicle-to-Everything environments, first paragraph.", "a"))
    body.append(make_para(
        "This is the second paragraph of the English abstract.", "a"))
    body.append(make_para("绪论", "1"))
    body.append(make_final_body_sectpr())
    return body


def _is_roman_break(el: ET.Element) -> bool:
    """判断段落是否包含 lowerRoman 分节符。"""
    p_pr = el.find(q("pPr"))
    if p_pr is None:
        return False
    sect_pr = p_pr.find(q("sectPr"))
    if sect_pr is None:
        return False
    pg = sect_pr.find(q("pgNumType"))
    return pg is not None and pg.get(q("fmt")) == "lowerRoman"


def _scan_body_paragraphs(body: ET.Element) -> dict:
    """扫描 body 段落，收集标题位置和关键段落索引。

    Returns:
        dict with keys: heading_cn, heading_en, idx_main,
                        idx_en_second, idx_roman_break
    """
    heading_cn: list[int] = []
    heading_en: list[int] = []
    idx_main = None
    idx_en_second = None
    idx_roman_break = None

    for i, el in enumerate(body):
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
        if _is_roman_break(el):
            idx_roman_break = i

    return {
        "heading_cn": heading_cn,
        "heading_en": heading_en,
        "idx_main": idx_main,
        "idx_en_second": idx_en_second,
        "idx_roman_break": idx_roman_break,
    }


def _assert_scan_results(scan: dict) -> None:
    """校验扫描结果，不满足时抛出 SystemExit。"""
    heading_cn = scan["heading_cn"]
    heading_en = scan["heading_en"]
    idx_main = scan["idx_main"]
    idx_en_second = scan["idx_en_second"]
    idx_roman_break = scan["idx_roman_break"]

    if len(heading_cn) != 1:
        raise SystemExit(
            f"REGRESSION FAIL: 摘要 heading count={len(heading_cn)}, expected 1")
    if len(heading_en) != 1:
        raise SystemExit(
            "REGRESSION FAIL: Abstract heading count="
            f"{len(heading_en)}, expected 1")
    if idx_main is None or idx_en_second is None or idx_roman_break is None:
        raise SystemExit(
            "REGRESSION FAIL: missing main heading / en second paragraph"
            " / roman section break")
    if idx_roman_break != idx_main - 1:
        raise SystemExit(
            f"REGRESSION FAIL: Roman section break index={idx_roman_break},"
            f" expected immediately before main heading index={idx_main}")
    if idx_en_second > idx_roman_break:
        raise SystemExit(
            "REGRESSION FAIL: second English abstract paragraph was"
            " truncated into main section")


def main() -> int:
    """运行摘要节回归测试，验证中英文摘要标题不重复且英文摘要不被截断。"""
    ns = {"w": W_NS}
    body = _build_test_body()

    # pylint: disable=protected-access,no-member
    sect = builder._get_body_sectPr(ns, body)
    if sect is None:
        raise SystemExit("REGRESSION FAIL: missing body sectPr")
    sect_proto = copy.deepcopy(sect)
    builder._insert_abstract_chapters_and_sections(ns, body, sect_proto)
    # pylint: enable=protected-access,no-member

    scan = _scan_body_paragraphs(body)
    _assert_scan_results(scan)

    print("ABSTRACT REGRESSION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
