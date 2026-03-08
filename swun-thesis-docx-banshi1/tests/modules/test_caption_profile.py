"""Tests for caption profile driven formatting."""

from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.modules import docx_builder
from scripts.modules.caption_profile import extract_caption_profiles, profile_signature


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
REFERENCE_DOCX = Path("/Users/bit/LaTeX/SWUN_Thesis/网络与信息安全_高春琴.docx")


def _attrs(elem: ET.Element | None) -> dict[str, str]:
    if elem is None:
        return {}
    return {key.split("}")[-1]: value for key, value in elem.attrib.items()}


def test_make_caption_para_matches_reference_caption_paragraph_properties():
    """Caption paragraphs should match the reference thesis formatting baseline."""

    para = docx_builder._make_caption_para(  # noqa: SLF001
        NS,
        "a",
        "图2-1 数字水印模型图",
        keep_next=False,
    )

    p_style = para.find("./w:pPr/w:pStyle", NS)
    spacing = para.find("./w:pPr/w:spacing", NS)
    indent = para.find("./w:pPr/w:ind", NS)
    run_fonts = para.find("./w:r/w:rPr/w:rFonts", NS)
    run_size = para.find("./w:r/w:rPr/w:sz", NS)

    assert p_style is None, "Reference caption paragraphs do not carry an explicit paragraph style"
    assert _attrs(spacing) == {"line": "240", "lineRule": "auto"}
    assert _attrs(indent).get("firstLine") == "422"
    assert "firstLineChars" not in _attrs(indent)
    assert _attrs(run_fonts).get("ascii") == "Times New Roman"
    assert para.find("./w:r/w:rPr/w:b", NS) is not None
    assert _attrs(run_size).get("val") == "21"


def test_extract_caption_profiles_reads_reference_sample():
    """The reference sample should provide both figure and table caption presets."""

    profiles = extract_caption_profiles(REFERENCE_DOCX)

    assert set(profiles) == {"figure", "table"}
    figure_signature = profile_signature(profiles["figure"])
    assert figure_signature["style"] is None
    assert figure_signature["jc"] == "center"
    assert figure_signature["spacing"] == {"line": "240", "lineRule": "auto"}
    assert figure_signature["indent"] == {"firstLine": "422"}
    assert figure_signature["run_ascii"] == "Times New Roman"
    assert figure_signature["run_bold"] is True
    assert figure_signature["run_sz"] == "21"
