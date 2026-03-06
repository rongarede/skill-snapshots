"""Integration tests that verify end-to-end build behavior."""
import hashlib
import re
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

SKILL_DIR = Path(__file__).parent.parent
GOLDEN_OUTPUT = SKILL_DIR / "tests/golden_outputs/main_版式1.docx"


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
    paragraphs = root.findall(".//w:body/w:p", ns)
    return ns, paragraphs


def _paragraph_text(paragraph: ET.Element, ns: dict[str, str]) -> str:
    return "".join(t.text or "" for t in paragraph.findall(".//w:t", ns)).strip()


def _paragraph_indent(paragraph: ET.Element, ns: dict[str, str]) -> dict[str, str]:
    ind = paragraph.find("./w:pPr/w:ind", ns)
    if ind is None:
        return {}
    return {key.split("}")[-1]: value for key, value in ind.attrib.items()}


def _find_paragraph_index(paragraphs: list[ET.Element], ns: dict[str, str], predicate) -> int:
    for idx, paragraph in enumerate(paragraphs):
        if predicate(_paragraph_text(paragraph, ns), paragraph):
            return idx
    pytest.fail("Expected paragraph was not found in document.xml")


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
        lambda text, _: text.startswith("HotStuff[38]"),
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
