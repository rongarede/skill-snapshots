"""Tests for template_loader."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.modules.template_loader import insert_toc_before_first_chapter


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = f"{{{W_NS}}}"


def _make_sectpr_xml() -> ET.Element:
    sectpr = ET.Element(f"{W}sectPr")
    ET.SubElement(sectpr, f"{W}type").set(f"{W}val", "nextPage")
    return sectpr


def _make_body_with_summary_heading() -> ET.Element:
    body = ET.Element(f"{W}body")
    p = ET.SubElement(body, f"{W}p")
    pPr = ET.SubElement(p, f"{W}pPr")
    pStyle = ET.SubElement(pPr, f"{W}pStyle")
    pStyle.set(f"{W}val", "1")
    r = ET.SubElement(p, f"{W}r")
    t = ET.SubElement(r, f"{W}t")
    t.text = "摘要"
    body.append(_make_sectpr_xml())
    return body


def test_toc_section_starts_roman_page_numbering() -> None:
    ns = {"w": W_NS, "r": R_NS}
    body = _make_body_with_summary_heading()
    sectpr_proto = _make_sectpr_xml()

    insert_toc_before_first_chapter(ns, body, sectpr_proto)

    sect_breaks = [el for el in list(body) if el.tag == f"{W}p" and el.find(f"./w:pPr/w:sectPr", ns) is not None]
    assert sect_breaks, "expected an inserted TOC section break paragraph"

    toc_sectpr = sect_breaks[0].find("./w:pPr/w:sectPr", ns)
    assert toc_sectpr is not None
    pgnum = toc_sectpr.find("./w:pgNumType", ns)
    assert pgnum is not None
    assert pgnum.get(f"{W}fmt") == "lowerRoman"
    assert pgnum.get(f"{W}start") == "1"
