"""Tests for style_processor."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from scripts.modules.style_processor import align_styles_to_reference


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"


def _attrs(element: ET.Element | None) -> dict[str, str]:
    if element is None:
        return {}
    return {key.split("}")[-1]: value for key, value in element.attrib.items()}


def _style_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:pPr>
      <w:spacing w:before="0" w:after="120" w:afterAutospacing="1"/>
    </w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:pPr>
      <w:spacing w:before="260" w:after="260" w:line="415"/>
    </w:pPr>
  </w:style>
</w:styles>
""".encode("utf-8")


def test_heading1_uses_half_line_after_spacing() -> None:
    styles_xml = align_styles_to_reference(_style_xml())
    root = ET.fromstring(styles_xml)

    heading1 = root.find(".//w:style[@w:styleId='Heading1']", {"w": W_NS})
    assert heading1 is not None
    spacing = heading1.find("./w:pPr/w:spacing", {"w": W_NS})
    assert spacing is not None
    assert _attrs(spacing).get("afterLines") == "50"
    assert _attrs(spacing).get("after") == "0"
    assert "afterAutospacing" not in _attrs(spacing)


def test_heading3_spacing_remains_unchanged() -> None:
    styles_xml = align_styles_to_reference(_style_xml())
    root = ET.fromstring(styles_xml)

    heading3 = root.find(".//w:style[@w:styleId='Heading3']", {"w": W_NS})
    assert heading3 is not None
    spacing = heading3.find("./w:pPr/w:spacing", {"w": W_NS})
    assert spacing is not None
    assert _attrs(spacing) == {"before": "260", "after": "260", "line": "415"}
