"""Tests for footer_handler."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.modules.footer_handler import replace_wps_footers


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
W = f"{{{W_NS}}}"


def _footer_text(footer_xml: bytes) -> str:
    root = ET.fromstring(footer_xml)
    return "".join(text or "" for text in (el.text for el in root.iter(f"{W}t")))


def _make_document_xml() -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">',
        "<w:body>",
    ]
    for idx in range(2):
        parts.append("<w:p><w:pPr><w:sectPr>")
        parts.append(
            f'<w:footerReference w:type="default" r:id="rId{idx + 1}"/>'
        )
        parts.append("</w:sectPr></w:pPr></w:p>")
    parts.append("</w:body></w:document>")
    return "".join(parts).encode("utf-8")


def _make_rels_xml() -> bytes:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for idx in range(2):
        parts.append(
            f'<Relationship Id="rId{idx + 1}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" '
            f'Target="footer{idx + 1}.xml"/>'
        )
    parts.append("</Relationships>")
    return "".join(parts).encode("utf-8")


def _make_footer_xml(text: str = "") -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:ftr xmlns:w="{W_NS}" xmlns:r="{R_NS}">'
        "<w:p><w:r><w:t>"
        f"{text}"
        "</w:t></w:r></w:p></w:ftr>"
    ).encode("utf-8")


def test_toc_section_uses_page_footer() -> None:
    file_data = {
        "word/document.xml": _make_document_xml(),
        "word/_rels/document.xml.rels": _make_rels_xml(),
        "word/footer1.xml": _make_footer_xml(),
        "word/footer2.xml": _make_footer_xml(),
    }

    replace_wps_footers(file_data, file_data["word/document.xml"])

    assert _footer_text(file_data["word/footer1.xml"]) == ""
    assert "PAGE" in file_data["word/footer2.xml"].decode("utf-8")
