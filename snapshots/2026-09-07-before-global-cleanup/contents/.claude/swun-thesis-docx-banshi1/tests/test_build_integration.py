"""Integration tests that verify end-to-end build behavior."""
import hashlib
import os
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from scripts.verification import report_generator

SKILL_DIR = Path(__file__).parent.parent
GOLDEN_OUTPUT = SKILL_DIR / "tests/golden_outputs/main_版式1.docx"
REFERENCE_CAPTION_DOCX = Path("/Users/bit/LaTeX/SWUN_Thesis/网络与信息安全_高春琴.docx")


def _normalize_core_xml(data: bytes) -> bytes:
    """Normalize volatile timestamp fields in docProps/core.xml."""
    xml = data.decode("utf-8", errors="ignore")
    xml = re.sub(
        r"<dcterms:created[^>]*>.*?</dcterms:created>",
        "<dcterms:created xsi:type=\"dcterms:W3CDTF\">NORMALIZED</dcterms:created>",
        xml,
        flags=re.DOTALL,
    )
    xml = re.sub(
        r"<dcterms:modified[^>]*>.*?</dcterms:modified>",
        "<dcterms:modified xsi:type=\"dcterms:W3CDTF\">NORMALIZED</dcterms:modified>",
        xml,
        flags=re.DOTALL,
    )
    return xml.encode("utf-8")


def get_docx_semantic_hash(filepath: Path) -> str:
    """Calculate hash while ignoring volatile ZIP/XML timestamp differences."""
    sha256_hash = hashlib.sha256()
    with zipfile.ZipFile(filepath, "r") as zf:
        members = sorted(i.filename for i in zf.infolist() if not i.is_dir())
        for name in members:
            data = zf.read(name)
            if name == "docProps/core.xml":
                data = _normalize_core_xml(data)
            sha256_hash.update(name.encode("utf-8"))
            sha256_hash.update(b"\0")
            sha256_hash.update(data)
            sha256_hash.update(b"\0")
    return sha256_hash.hexdigest()


def _build_swun_docx() -> Path:
    """Build the SWUN DOCX and return the generated path."""
    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts/build_docx_banshi1.py")],
        cwd="/Users/bit/LaTeX/SWUN_Thesis",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Build failed: {result.stderr}"

    output = Path("/Users/bit/LaTeX/SWUN_Thesis/main_版式1.docx")
    assert output.exists(), "Output DOCX not found"
    return output


def _load_document_paragraphs(docx_path: Path) -> tuple[dict[str, str], list[ET.Element]]:
    """Return document.xml paragraph nodes from a built DOCX."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = root.findall(".//w:body//w:p", ns)
    return ns, paragraphs


def _load_document_body_children(docx_path: Path) -> tuple[dict[str, str], list[ET.Element]]:
    """Return top-level body children from document.xml."""
    with zipfile.ZipFile(docx_path, "r") as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    body = root.find(".//w:body", ns)
    assert body is not None, "document.xml is missing w:body"
    return ns, list(body)


def _paragraph_text(paragraph: ET.Element, ns: dict[str, str]) -> str:
    return "".join(t.text or "" for t in paragraph.findall(".//w:t", ns)).strip()


def _paragraph_indent(paragraph: ET.Element, ns: dict[str, str]) -> dict[str, str]:
    ind = paragraph.find("./w:pPr/w:ind", ns)
    if ind is None:
        return {}
    return {key.split("}")[-1]: value for key, value in ind.attrib.items()}


def _paragraph_props(paragraph: ET.Element, ns: dict[str, str]) -> dict[str, object]:
    p_style = paragraph.find("./w:pPr/w:pStyle", ns)
    spacing = paragraph.find("./w:pPr/w:spacing", ns)
    indent = paragraph.find("./w:pPr/w:ind", ns)
    jc = paragraph.find("./w:pPr/w:jc", ns)
    run_fonts = paragraph.find("./w:r/w:rPr/w:rFonts", ns)
    run_size = paragraph.find("./w:r/w:rPr/w:sz", ns)
    return {
        "style": None if p_style is None else p_style.get("{%s}val" % ns["w"]),
        "spacing": None if spacing is None else {
            key.split("}")[-1]: value for key, value in spacing.attrib.items()
        },
        "indent": None if indent is None else {
            key.split("}")[-1]: value for key, value in indent.attrib.items()
        },
        "jc": None if jc is None else jc.get("{%s}val" % ns["w"]),
        "run_ascii": None if run_fonts is None else run_fonts.get("{%s}ascii" % ns["w"]),
        "run_eastAsia": None if run_fonts is None else run_fonts.get("{%s}eastAsia" % ns["w"]),
        "run_bold": paragraph.find("./w:r/w:rPr/w:b", ns) is not None,
        "run_sz": None if run_size is None else run_size.get("{%s}val" % ns["w"]),
    }


def _find_paragraph_index(paragraphs: list[ET.Element], ns: dict[str, str], predicate) -> int:
    for idx, paragraph in enumerate(paragraphs):
        if predicate(_paragraph_text(paragraph, ns), paragraph):
            return idx
    pytest.fail("Expected paragraph was not found in document.xml")


def _find_first_caption_props(docx_path: Path, prefix: str) -> dict[str, object]:
    ns, paragraphs = _load_document_paragraphs(docx_path)
    idx = _find_paragraph_index(
        paragraphs,
        ns,
        lambda text, _: text.startswith(prefix),
    )
    return _paragraph_props(paragraphs[idx], ns)


def _text_starts_with(element: ET.Element, ns: dict[str, str], prefix: str) -> bool:
    text = "".join(t.text or "" for t in element.findall(".//w:t", ns)).strip()
    return text.startswith(prefix)


def test_build_produces_identical_output():
    """Golden test: refactored code must produce semantically identical DOCX."""

    # Run build
    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts/build_docx_banshi1.py")],
        cwd="/Users/bit/LaTeX/SWUN_Thesis",
        capture_output=True,
        text=True
    )

    assert result.returncode == 0, f"Build failed: {result.stderr}"

    # Compare hash with golden output
    output = Path("/Users/bit/LaTeX/SWUN_Thesis/main_版式1.docx")
    assert output.exists(), "Output DOCX not found"

    output_hash = get_docx_semantic_hash(output)
    golden_hash = get_docx_semantic_hash(GOLDEN_OUTPUT)
    assert output_hash == golden_hash, f"Output semantic hash mismatch: {output_hash} != {golden_hash}"

def test_build_script_exists():
    """Verify build script exists."""
    build_script = SKILL_DIR / "scripts/build_docx_banshi1.py"
    assert build_script.exists()
    assert build_script.is_file()


def test_build_fails_when_caption_profile_source_is_missing(tmp_path):
    """Caption profile source should be mandatory once preset extraction is enabled."""

    env = os.environ.copy()
    env["SWUN_CAPTION_PROFILE_DOCX"] = str(tmp_path / "missing-caption-source.docx")

    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts/build_docx_banshi1.py")],
        cwd="/Users/bit/LaTeX/SWUN_Thesis",
        capture_output=True,
        text=True,
        env=env,
    )

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode != 0
    assert "SWUN_CAPTION_PROFILE_DOCX" in output or "caption profile" in output.lower()


def test_build_uses_real_chapter2_figure_path():
    """The DOCX build should embed the actual chapter figure path for Fig. 2-5."""

    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts/build_docx_banshi1.py")],
        cwd="/Users/bit/LaTeX/SWUN_Thesis",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Build failed: {result.stderr}"

    output = Path("/Users/bit/LaTeX/SWUN_Thesis/main_版式1.docx")
    assert output.exists(), "Output DOCX not found"

    with zipfile.ZipFile(output, "r") as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")

    assert "figures/ch2/dag_figure.png" in document_xml
    assert "lightdag_baseline__" not in document_xml
    assert "Danezis_Narwhal_Tusk" not in document_xml
    assert "Spiegelman_Shoal" not in document_xml


def test_build_figure_caption_properties_match_reference_sample():
    """Generated figure captions should inherit the same key properties as the reference sample."""

    output = _build_swun_docx()
    generated = _find_first_caption_props(output, "图")
    reference = _find_first_caption_props(REFERENCE_CAPTION_DOCX, "图")

    assert generated == reference


def test_build_wraps_figure_table_and_bilingual_caption_into_atomic_container():
    """Long bilingual figure captions should live in the same unsplittable wrapper as the figure block."""

    output = _build_swun_docx()
    ns, body_children = _load_document_body_children(output)

    wrapper = None
    for child in body_children:
        if child.tag != "{%s}tbl" % ns["w"]:
            continue
        nested_figure_tables = child.findall(".//w:tblPr/w:tblStyle[@w:val='FigureTable']", ns)
        if not nested_figure_tables:
            continue
        if not _text_starts_with(child, ns, "图3-6"):
            continue
        wrapper = child
        break

    assert wrapper is not None, "Expected a wrapper table that contains Figure 3-6 and its bilingual caption"

    rows = wrapper.findall("./w:tr", ns)
    assert len(rows) == 1, "Figure wrapper should use a single row so the whole block paginates together"
    assert rows[0].find("./w:trPr/w:cantSplit", ns) is not None, "Figure wrapper row must be marked non-splittable"

    wrapper_text = "".join(t.text or "" for t in wrapper.findall(".//w:t", ns)).strip()
    assert "图3-6 节点数对吞吐量与延迟的影响（weak scaling: batch=16n）" in wrapper_text
    assert "Figure 3-6 Impact of Node Count on Throughput and Latency (weak scaling: batch=16n)" in wrapper_text

    top_level_caption_paras = [
        child
        for child in body_children
        if child.tag == "{%s}p" % ns["w"] and _text_starts_with(child, ns, "图3-6")
    ]
    assert not top_level_caption_paras, "Wrapped figure captions should no longer remain as body-level paragraphs"


def test_phase3_caption_check_accepts_wrapped_figure_captions():
    """Phase 3 verification should still pass when figure captions move inside wrapper tables."""

    output = _build_swun_docx()
    with zipfile.ZipFile(output, "r") as zf:
        document_xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")

    assert report_generator.check_phase3_caption(document_xml, str(output)) == []


def test_build_deduplicates_anchor_bookmark_names():
    """Word-facing fig/tab/tbl anchors should remain unique after DOCX postprocess."""

    result = subprocess.run(
        ["python3", str(SKILL_DIR / "scripts/build_docx_banshi1.py")],
        cwd="/Users/bit/LaTeX/SWUN_Thesis",
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Build failed: {result.stderr}"

    output = Path("/Users/bit/LaTeX/SWUN_Thesis/main_版式1.docx")
    assert output.exists(), "Output DOCX not found"

    with zipfile.ZipFile(output, "r") as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    names = [
        el.get("{%s}name" % ns["w"])
        for el in root.findall(".//w:bookmarkStart", ns)
        if el.get("{%s}name" % ns["w"])
    ]
    anchor_names = [n for n in names if n.startswith(("fig:", "tab:", "tbl:"))]
    dup_names = [(name, count) for name, count in Counter(anchor_names).items() if count > 1]

    assert "fig:dag_structure" in anchor_names
    assert not dup_names, f"Duplicate anchor bookmark names found: {dup_names}"


def test_build_clears_indent_for_equation_explanation_but_keeps_following_body_indent():
    """The explanation paragraph after a display equation should not keep body first-line indent."""

    output = _build_swun_docx()
    ns, paragraphs = _load_document_paragraphs(output)

    eq_idx = _find_paragraph_index(
        paragraphs,
        ns,
        lambda text, _: text in {"(2-1)", "（2-1）"},
    )
    explanation_idx = _find_paragraph_index(
        paragraphs[eq_idx + 1:],
        ns,
        lambda text, _: text.startswith("其中"),
    )
    explanation_idx += eq_idx + 1

    followup_idx = _find_paragraph_index(
        paragraphs[explanation_idx + 1:],
        ns,
        lambda text, _: text.startswith("HotStuff 是一种基于部分同步模型"),
    )
    followup_idx += explanation_idx + 1

    explanation_indent = _paragraph_indent(paragraphs[explanation_idx], ns)
    followup_indent = _paragraph_indent(paragraphs[followup_idx], ns)

    assert explanation_indent.get("firstLine") == "0", (
        "The chapter2 '(2-1)' explanation paragraph should clear w:firstLine in document.xml"
    )
    assert explanation_indent.get("firstLineChars") == "0", (
        "The chapter2 '(2-1)' explanation paragraph should clear w:firstLineChars in document.xml"
    )
    assert followup_indent.get("firstLineChars") not in {None, "0"}, (
        "A later true body paragraph should retain its normal first-line indent"
    )
