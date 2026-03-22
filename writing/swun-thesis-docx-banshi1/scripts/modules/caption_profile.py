"""Reference-driven caption format extraction and application."""

from __future__ import annotations

import copy
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}

CAPTION_PATTERNS = {
    "figure": re.compile(r"^图\s*\d+[\-\.．]\d+\b"),
    "table": re.compile(r"^表\s*\d+[\-\.．]\d+\b"),
}


def _qn(local: str) -> str:
    return f"{{{W_NS}}}{local}"


def _paragraph_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS)).strip()


def _first_nonempty_run(p: ET.Element) -> ET.Element | None:
    for run in p.findall("w:r", NS):
        if _paragraph_text(run):
            return run
    return None


def _clone_children(parent: ET.Element | None,
     names: set[str] | None = None) -> list[ET.Element]:
    if parent is None:
        return []
    children: list[ET.Element] = []
    for child in list(parent):
        local = child.tag.split("}", 1)[-1]
        if names is not None and local not in names:
            continue
        children.append(copy.deepcopy(child))
    return children


def _bool_child_present(children: list[ET.Element], local_name: str) -> bool:
    return any(child.tag == _qn(local_name) for child in children)


def _find_child(children: list[ET.Element],
     local_name: str) -> ET.Element | None:
    for child in children:
        if child.tag == _qn(local_name):
            return child
    return None


def _attrs(elem: ET.Element | None) -> dict[str, str] | None:
    if elem is None:
        return None
    return {key.split("}")[-1]: value for key, value in elem.attrib.items()}


@dataclass
class CaptionFormatProfile:
    kind: str
    style: str | None
    paragraph_props: list[ET.Element]
    run_props: list[ET.Element]


def extract_caption_profiles(
    docx_path: Path) -> dict[str, CaptionFormatProfile]:
    """Extract figure/table caption profiles from a reference DOCX."""
    if not docx_path.exists():
        raise FileNotFoundError(
    f"caption profile source not found: {docx_path}")

    with zipfile.ZipFile(docx_path, "r") as zf:
        root = ET.fromstring(zf.read("word/document.xml"))

    body = root.find(".//w:body", NS)
    if body is None:
        raise RuntimeError(
    f"caption profile source missing w:body: {docx_path}")

    profiles: dict[str, CaptionFormatProfile] = {}
    for kind, pattern in CAPTION_PATTERNS.items():
        for paragraph in body.findall("w:p", NS):
            if not pattern.match(_paragraph_text(paragraph)):
                continue
            p_pr = paragraph.find("w:pPr", NS)
            p_style = None
            if p_pr is not None:
                style = p_pr.find("w:pStyle", NS)
                if style is not None:
                    p_style = style.get(_qn("val"))
            run = _first_nonempty_run(paragraph)
            r_pr = run.find("w:rPr", NS) if run is not None else None
            profiles[kind] = CaptionFormatProfile(
    kind=kind,
    style=p_style,
    paragraph_props=_clone_children(
        p_pr,
        names={
            "jc",
            "spacing",
            "ind",
            "keepNext",
            "keepLines",
            "rPr"},
            ),
            run_props=_clone_children(r_pr),
             )
            break
        if kind not in profiles:
            raise RuntimeError(
     f"failed to extract {kind} caption profile from reference DOCX: {docx_path}" )

    return profiles


def build_caption_paragraph(
    ns: dict[str, str],
    text: str,
    profile: CaptionFormatProfile,
    *,
    keep_next: bool,
) -> ET.Element:
    """Build a caption paragraph using a reference-derived profile."""
    w_p = f"{{{ns['w']}}}p"
    w_pPr = f"{{{ns['w']}}}pPr"
    w_pStyle = f"{{{ns['w']}}}pStyle"
    w_r = f"{{{ns['w']}}}r"
    w_rPr = f"{{{ns['w']}}}rPr"
    w_t = f"{{{ns['w']}}}t"
    w_val = f"{{{ns['w']}}}val"

    para = ET.Element(w_p)
    p_pr = ET.SubElement(para, w_pPr)

    if profile.style:
        p_style = ET.SubElement(p_pr, w_pStyle)
        p_style.set(w_val, profile.style)

    for child in profile.paragraph_props:
        local = child.tag.split("}", 1)[-1]
        if local == "keepNext":
            continue
        p_pr.append(copy.deepcopy(child))

    if keep_next:
        ET.SubElement(p_pr, f"{{{ns['w']}}}keepNext")

    run = ET.SubElement(para, w_r)
    if profile.run_props:
        r_pr = ET.SubElement(run, w_rPr)
        for child in profile.run_props:
            r_pr.append(copy.deepcopy(child))

    text_node = ET.SubElement(run, w_t)
    text_node.text = text
    if text and (text[0] == " " or text[-1] == " "):
        text_node.set(
    "{http://www.w3.org/XML/1998/namespace}space",
     "preserve")
    return para


def paragraph_signature(paragraph: ET.Element,
                        ns: dict[str, str]) -> dict[str, object]:
    """Return the key signature used to compare caption formatting."""
    p_style = paragraph.find("./w:pPr/w:pStyle", NS)
    spacing = paragraph.find("./w:pPr/w:spacing", NS)
    indent = paragraph.find("./w:pPr/w:ind", NS)
    jc = paragraph.find("./w:pPr/w:jc", NS)
    run_fonts = paragraph.find("./w:r/w:rPr/w:rFonts", NS)
    run_size = paragraph.find("./w:r/w:rPr/w:sz", NS)
    return {
        "style": None if p_style is None else p_style.get(f"{{{ns['w']}}}val"),
        "spacing": _attrs(spacing),
        "indent": _attrs(indent),
        "jc": None if jc is None else jc.get(f"{{{ns['w']}}}val"),
        "run_ascii": None if run_fonts is None else run_fonts.get(f"{{{ns['w']}}}ascii"),
        "run_eastAsia": None if run_fonts is None else run_fonts.get(f"{{{ns['w']}}}eastAsia"),
        "run_bold": paragraph.find("./w:r/w:rPr/w:b", NS) is not None,
        "run_sz": None if run_size is None else run_size.get(f"{{{ns['w']}}}val"),
    }


def profile_signature(profile: CaptionFormatProfile) -> dict[str, object]:
    """Return the signature expected from a reference-derived profile."""
    return {
        "style": profile.style,
        "spacing": _attrs(_find_child(profile.paragraph_props, "spacing")),
        "indent": _attrs(_find_child(profile.paragraph_props, "ind")),
        "jc": (
            None
            if _find_child(profile.paragraph_props, "jc") is None
            else _find_child(profile.paragraph_props, "jc").get(_qn("val"))
        ),
        "run_ascii": (
            None
            if _find_child(profile.run_props, "rFonts") is None
            else _find_child(profile.run_props, "rFonts").get(_qn("ascii"))
        ),
        "run_eastAsia": (
            None
            if _find_child(profile.run_props, "rFonts") is None
            else _find_child(profile.run_props, "rFonts").get(_qn("eastAsia"))
        ),
        "run_bold": _bool_child_present(profile.run_props, "b"),
        "run_sz": (
            None
            if _find_child(profile.run_props, "sz") is None
            else _find_child(profile.run_props, "sz").get(_qn("val"))
        ),
    }
