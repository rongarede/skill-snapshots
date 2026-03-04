"""Integration tests that verify end-to-end build behavior."""
import hashlib
import re
import subprocess
import zipfile
from pathlib import Path

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
