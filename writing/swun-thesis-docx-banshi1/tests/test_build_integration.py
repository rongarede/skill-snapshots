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
