"""Tests for header_handler."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.modules.header_handler import CN_TITLE, EN_TITLE, add_thesis_headers


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = f"{{{W_NS}}}"


def _header_text(header_xml: bytes) -> str:
    root = ET.fromstring(header_xml)
    return "".join(text or "" for text in (el.text for el in root.iter(f"{W}t")))


def _header_run_props(header_xml: bytes) -> dict[str, str | None]:
    root = ET.fromstring(header_xml)
    run_fonts = root.find(".//w:rPr/w:rFonts", {"w": W_NS})
    run_size = root.find(".//w:rPr/w:sz", {"w": W_NS})
    run_size_cs = root.find(".//w:rPr/w:szCs", {"w": W_NS})
    run_spacing = root.find(".//w:rPr/w:spacing", {"w": W_NS})
    return {
        "ascii": None if run_fonts is None else run_fonts.get(f"{{{W_NS}}}ascii"),
        "hAnsi": None if run_fonts is None else run_fonts.get(f"{{{W_NS}}}hAnsi"),
        "eastAsia": None if run_fonts is None else run_fonts.get(f"{{{W_NS}}}eastAsia"),
        "cs": None if run_fonts is None else run_fonts.get(f"{{{W_NS}}}cs"),
        "sz": None if run_size is None else run_size.get(f"{{{W_NS}}}val"),
        "szCs": None if run_size_cs is None else run_size_cs.get(f"{{{W_NS}}}val"),
        "spacing": None if run_spacing is None else run_spacing.get(f"{{{W_NS}}}val"),
    }


def _header_paragraph_spacing(header_xml: bytes) -> dict[str, str | None]:
    root = ET.fromstring(header_xml)
    spacing = root.find(".//w:pPr/w:spacing", {"w": W_NS})
    return {
        "before": None if spacing is None else spacing.get(f"{{{W_NS}}}before"),
        "after": None if spacing is None else spacing.get(f"{{{W_NS}}}after"),
        "line": None if spacing is None else spacing.get(f"{{{W_NS}}}line"),
        "lineRule": None if spacing is None else spacing.get(f"{{{W_NS}}}lineRule"),
    }


def _make_document_xml() -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">',
        "<w:body>",
    ]
    for idx in range(5):
        parts.append("<w:p><w:pPr><w:sectPr>")
        parts.append(
            f'<w:headerReference w:type="default" r:id="rId{idx + 1}"/>'
        )
        parts.append("</w:sectPr></w:pPr></w:p>")
    parts.append("</w:body></w:document>")
    return "".join(parts).encode("utf-8")


def _make_rels_xml() -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for idx in range(5):
        parts.append(
            f'<Relationship Id="rId{idx + 1}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
            f'Target="header{idx + 1}.xml"/>'
        )
    parts.append("</Relationships>")
    return "".join(parts).encode("utf-8")


def _make_header_xml(text: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:hdr xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        "<w:p><w:r><w:t>"
        f"{text}"
        "</w:t></w:r></w:p></w:hdr>"
    ).encode("utf-8")


def test_toc_section_uses_cn_title_header() -> None:
    file_data = {
        "word/document.xml": _make_document_xml(),
        "word/_rels/document.xml.rels": _make_rels_xml(),
    }
    for idx in range(5):
        file_data[f"word/header{idx + 1}.xml"] = _make_header_xml()

    add_thesis_headers(file_data, file_data["word/document.xml"])

    assert _header_text(file_data["word/header1.xml"]) == ""
    assert _header_text(file_data["word/header2.xml"]) == CN_TITLE
    assert _header_text(file_data["word/header3.xml"]) == CN_TITLE
    assert _header_text(file_data["word/header4.xml"]) == EN_TITLE
    assert _header_text(file_data["word/header5.xml"]) == CN_TITLE


def test_header_font_size_matches_body_scale() -> None:
    file_data = {
        "word/document.xml": _make_document_xml(),
        "word/_rels/document.xml.rels": _make_rels_xml(),
    }
    for idx in range(5):
        file_data[f"word/header{idx + 1}.xml"] = _make_header_xml()

    add_thesis_headers(file_data, file_data["word/document.xml"])

    props = _header_run_props(file_data["word/header2.xml"])
    assert props["ascii"] == "Times New Roman"
    assert props["hAnsi"] == "Times New Roman"
    assert props["eastAsia"] == "宋体"
    assert props["cs"] == "Times New Roman"
    assert props["sz"] == "24"
    assert props["szCs"] == "24"


def test_english_header_keeps_font_size_and_uses_character_condense() -> None:
    file_data = {
        "word/document.xml": _make_document_xml(),
        "word/_rels/document.xml.rels": _make_rels_xml(),
    }
    for idx in range(5):
        file_data[f"word/header{idx + 1}.xml"] = _make_header_xml()

    add_thesis_headers(file_data, file_data["word/document.xml"])

    chinese_props = _header_run_props(file_data["word/header2.xml"])
    english_props = _header_run_props(file_data["word/header4.xml"])

    assert chinese_props["sz"] == "24"
    assert chinese_props["szCs"] == "24"
    assert chinese_props["spacing"] is None
    assert english_props["sz"] == "24"
    assert english_props["szCs"] == "24"
    assert english_props["spacing"] == "-6"


def test_header_paragraph_spacing_removes_blank_line_below_border() -> None:
    file_data = {
        "word/document.xml": _make_document_xml(),
        "word/_rels/document.xml.rels": _make_rels_xml(),
    }
    for idx in range(5):
        file_data[f"word/header{idx + 1}.xml"] = _make_header_xml()

    add_thesis_headers(file_data, file_data["word/document.xml"])

    spacing = _header_paragraph_spacing(file_data["word/header2.xml"])
    assert spacing == {
        "before": "0",
        "after": "0",
        "line": "240",
        "lineRule": "auto",
    }
