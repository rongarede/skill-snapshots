#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build SWUN thesis DOCX (Format 1) from LaTeX using the official reference template.

Pipeline (per AGENTS.md):
1) latexpand main.tex -> .main.flat.tex
2) preprocess: replace '\\<' -> '<', drop/normalize a few LaTeX constructs pandoc drops
3) pandoc -> intermediate docx (with citeproc + GB/T CSL)
4) OOXML postprocess:
   - insert Word TOC field before the first Heading 1 chapter
   - add page breaks before each Heading 1 (except when already preceded by a page break)
   - add first-line indent for body paragraphs (BodyText/FirstParagraph/Compact)
   - add hanging indent for bibliography entries ([n]...) inside the references section
   - fix mixed Chinese/Arabic section numbers by adding w:isLgl for ilvl>=1 (abstractNumId=0)
"""

from __future__ import annotations

import datetime as _dt
import copy
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path("/Users/bit/LaTeX/SWUN_Thesis")

SCRIPT_DIR = Path(__file__).resolve().parent

TEMPLATE_DOCX = Path(
    os.environ.get(
        "SWUN_TEMPLATE_DOCX",
        "/Users/bit/LaTeX/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx",
    )
).expanduser()
MAIN_TEX = ROOT / "main.tex"
CSL = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
BIB = ROOT / "backmatter" / "references.bib"

FLAT_TEX = ROOT / ".main.flat.tex"
INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
OUTPUT_DOCX = ROOT / "main_版式1.docx"


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _preprocess_latex(s: str) -> str:
    # Pandoc LaTeX reader doesn't recognize \\< escape sequence.
    s = s.replace("\\<", "<")

    # Let citeproc generate the references section; avoid a literal \printbibliography in output.
    s = re.sub(
        r"\\printbibliography\s*(\[[^\]]*\])?",
        "",
        s,
        flags=re.MULTILINE,
    )

    # Pandoc may drop titlepage env; make it a normal block so cover content survives.
    s = s.replace("\\begin{titlepage}", "")
    s = s.replace("\\end{titlepage}", "")

    # ulem's \ul can get dropped; keep visible placeholders.
    # Common in declaration pages: \ul{　　　　　}
    s = re.sub(r"\\ul\\{[^}]*\\}", "__________", s)

    return s


def _extract_display_math_number_flags(latex: str) -> list[bool]:
    """
    Return a sequence aligned with pandoc's display-math paragraphs order.

    - Numbered: equation/align/gather/multline environments without '*'
    - Unnumbered: starred variants and \\[ ... \\] blocks
    """
    blocks: list[tuple[int, bool]] = []

    env_re = re.compile(
        r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}[\s\S]*?\\end\{\1\}"
    )
    for m in env_re.finditer(latex):
        env = m.group(1)
        blocks.append((m.start(), not env.endswith("*")))

    # Match display-math \[ ... \] but not line breaks \\[0.5em] in tabular, etc.
    br_re = re.compile(r"(?<!\\)\\\[[\s\S]*?\\\]")
    for m in br_re.finditer(latex):
        blocks.append((m.start(), False))

    blocks.sort(key=lambda x: x[0])
    return [b for _, b in blocks]


def _extract_keywords(latex: str) -> tuple[str | None, str | None]:
    def last_group(pattern: str) -> str | None:
        ms = list(re.finditer(pattern, latex, flags=re.DOTALL))
        if not ms:
            return None
        val = ms[-1].group(1)
        val = re.sub(r"\s+", " ", val).strip()
        return val or None

    cn = last_group(r"\\cnkeywords\{([^}]*)\}")
    en = last_group(r"\\enkeywords\{([^}]*)\}")
    return cn, en


def _split_keywords(raw: str, max_groups: int = 4, lang: str = "cn") -> str:
    """
    Split keywords into 3-4 groups (default max 4) without dropping information.

    If there are more than `max_groups` items, merge items from the last group onward.
    """

    def merge_tail_cn(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]}与{items[1]}"
        return "、".join(items)

    def merge_tail_en(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])} and {items[-1]}"

    # Split on common delimiters then join with Chinese semicolons (matches existing source).
    parts = [p.strip() for p in re.split(r"[;；,，]\s*", raw) if p.strip()]
    if len(parts) > max_groups:
        head = parts[: max_groups - 1]
        tail = parts[max_groups - 1 :]
        merged = merge_tail_en(tail) if lang == "en" else merge_tail_cn(tail)
        parts = [p for p in head + [merged] if p]
    return "；".join(parts)


def _collect_ns(xml_bytes: bytes) -> dict[str, str]:
    ns: dict[str, str] = {}
    for event, item in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = item
        ns[prefix or ""] = uri
    return ns


def _register_ns(ns: dict[str, str]) -> None:
    for prefix, uri in ns.items():
        if prefix:  # ElementTree doesn't support registering default namespace cleanly.
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                # Skip invalid prefixes; Word namespaces should be fine.
                pass


def _qn(ns: dict[str, str], prefix: str, local: str) -> str:
    uri = ns[prefix]
    return f"{{{uri}}}{local}"


def _p_text(ns: dict[str, str], p: ET.Element) -> str:
    w_t = _qn(ns, "w", "t")
    parts = []
    for t in p.iter(w_t):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _ensure_ppr(ns: dict[str, str], p: ET.Element) -> ET.Element:
    w_pPr = _qn(ns, "w", "pPr")
    pPr = p.find(w_pPr)
    if pPr is None:
        pPr = ET.Element(w_pPr)
        p.insert(0, pPr)
    return pPr


def _p_style(ns: dict[str, str], p: ET.Element) -> str | None:
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    pPr = p.find(w_pPr)
    if pPr is None:
        return None
    pStyle = pPr.find(w_pStyle)
    if pStyle is None:
        return None
    return pStyle.get(w_val)


def _p_has_page_break(ns: dict[str, str], p: ET.Element) -> bool:
    w_br = _qn(ns, "w", "br")
    w_type = _qn(ns, "w", "type")
    for br in p.iter(w_br):
        if br.get(w_type) == "page":
            return True
    return False


def _p_has_sectPr(ns: dict[str, str], p: ET.Element) -> bool:
    w_sectPr = _qn(ns, "w", "sectPr")
    pPr = p.find(_qn(ns, "w", "pPr"))
    return pPr is not None and pPr.find(w_sectPr) is not None


def _make_page_break_p(ns: dict[str, str]) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_br = _qn(ns, "w", "br")
    w_type = _qn(ns, "w", "type")
    p = ET.Element(w_p)
    r = ET.SubElement(p, w_r)
    br = ET.SubElement(r, w_br)
    br.set(w_type, "page")
    return p


def _get_body_sectPr(ns: dict[str, str], body: ET.Element) -> ET.Element | None:
    # Usually a direct child of <w:body>.
    w_sectPr = _qn(ns, "w", "sectPr")
    for el in list(body):
        if el.tag == w_sectPr:
            return el
    # Fallback: sectPr in the last paragraph pPr.
    w_p = _qn(ns, "w", "p")
    for el in reversed(list(body)):
        if el.tag != w_p:
            continue
        pPr = el.find(_qn(ns, "w", "pPr"))
        if pPr is None:
            continue
        sectPr = pPr.find(w_sectPr)
        if sectPr is not None:
            return sectPr
    return None


def _set_sect_pgnum(
    ns: dict[str, str], sectPr: ET.Element, fmt: str, start: int | None
) -> None:
    w_pgNumType = _qn(ns, "w", "pgNumType")
    w_fmt = _qn(ns, "w", "fmt")
    w_start = _qn(ns, "w", "start")
    # Remove existing pgNumType(s)
    for el in list(sectPr.findall(w_pgNumType)):
        sectPr.remove(el)
    pg = ET.Element(w_pgNumType)
    pg.set(w_fmt, fmt)
    if start is not None:
        pg.set(w_start, str(start))
    # Put near top for readability (after header/footer refs if present).
    insert_at = 0
    for i, child in enumerate(list(sectPr)):
        if child.tag.endswith("headerReference") or child.tag.endswith("footerReference"):
            insert_at = i + 1
    sectPr.insert(insert_at, pg)


def _set_sect_break_next_page(ns: dict[str, str], sectPr: ET.Element) -> None:
    w_type = _qn(ns, "w", "type")
    w_val = _qn(ns, "w", "val")
    t = sectPr.find(w_type)
    if t is None:
        t = ET.Element(w_type)
        sectPr.insert(0, t)
    t.set(w_val, "nextPage")


def _make_section_break_paragraph(ns: dict[str, str], sectPr: ET.Element) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_sectPr = _qn(ns, "w", "sectPr")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    # sectPr must be a child of pPr for a section break paragraph.
    sp = copy.deepcopy(sectPr)
    sp.tag = w_sectPr
    pPr.append(sp)
    return p


def _make_unnumbered_heading1(ns: dict[str, str], title: str) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_numPr = _qn(ns, "w", "numPr")
    w_numId = _qn(ns, "w", "numId")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")

    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, "1")
    jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")
    numPr = ET.SubElement(pPr, w_numPr)
    numId = ET.SubElement(numPr, w_numId)
    numId.set(w_val, "0")
    r = ET.SubElement(p, w_r)
    t = ET.SubElement(r, w_t)
    t.text = title
    return p


def _prepend_template_cover_pages(
    ns: dict[str, str],
    body: ET.Element,
    template_docx: Path,
    *,
    marker_text: str = "研究生学位论文排版格式（版式1）",
    end_before_text: str = "学位论文版权使用授权书",
) -> None:
    """
    Prepend the first two pages from the official template docx *verbatim*.

    Heuristic:
    - Extract elements from template body start until the first paragraph whose text
      contains `end_before_text` (this begins page 3 in the provided template).
    - Skip if we already see `marker_text` very early in the document.
    """
    w_p = _qn(ns, "w", "p")

    # Idempotency: if marker appears in first ~40 paragraphs, assume cover already prepended.
    children = list(body)
    early = []
    for el in children[:80]:
        if el.tag != w_p:
            continue
        early.append(_p_text(ns, el))
    if marker_text in "".join(early):
        return

    if not template_docx.exists():
        return

    with zipfile.ZipFile(template_docx, "r") as zt:
        t_doc_xml = zt.read("word/document.xml")
    t_ns = _collect_ns(t_doc_xml)
    if "w" not in t_ns:
        return
    _register_ns(t_ns)

    t_root = ET.fromstring(t_doc_xml)
    t_body = t_root.find(_qn(t_ns, "w", "body"))
    if t_body is None:
        return

    t_children = list(t_body)
    cutoff = None
    # Prefer cutting at the start of template page-3, which begins with a standalone date line
    # ("日期：  年  月  日") in the provided SWUN template. This yields exactly the first two pages.
    # Be tolerant of fullwidth spaces used by Word.
    date_line_re = re.compile(r"^日期：[\s\u3000]*年[\s\u3000]*月[\s\u3000]*日$")
    for i, el in enumerate(t_children):
        if el.tag != _qn(t_ns, "w", "p"):
            continue
        txt = _p_text(t_ns, el).strip()
        if date_line_re.match(txt):
            cutoff = i
            break
        if end_before_text in txt:
            cutoff = i
            break
    if cutoff is None or cutoff <= 0:
        return

    # Insert in original order at the start of output body.
    insert_at = 0
    for el in t_children[:cutoff]:
        body.insert(insert_at, copy.deepcopy(el))
        insert_at += 1

    # Ensure a hard boundary after template cover pages without creating a blank page in LO:
    # Apply pageBreakBefore to the first paragraph of the thesis content (not the template pages).
    w_pageBreakBefore = _qn(ns, "w", "pageBreakBefore")
    children = list(body)
    for i in range(insert_at, len(children)):
        el = children[i]
        if el.tag != w_p:
            continue
        # Prefer the first paragraph with visible content.
        if not _p_text(ns, el).strip():
            continue
        pPr = _ensure_ppr(ns, el)
        if pPr.find(w_pageBreakBefore) is None:
            ET.SubElement(pPr, w_pageBreakBefore)
        break


def _insert_abstract_chapters_and_sections(
    ns: dict[str, str], body: ET.Element, sectPr_proto: ET.Element
) -> None:
    """
    Requirement:
    - Chinese/English abstracts are separate major chapters (Heading 1, unnumbered).
    - Abstract pages use Roman numerals in footer; the rest uses Arabic.

    Implementation:
    - Insert a section break before the Chinese abstract to start section 2.
    - Insert "摘要" and "Abstract" as unnumbered Heading 1.
    - Insert a section break after English abstract that ends section 2, setting pgNumType=lowerRoman start=1.
    - Ensure the final section (rest of the doc) uses decimal start=1.
    """
    w_p = _qn(ns, "w", "p")

    cn_anchor = "在车联网（V2X）环境中"
    en_anchor = "In the Vehicular-to-Everything"

    # Find Chinese abstract paragraph.
    children = list(body)
    cn_idx = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if cn_anchor in _p_text(ns, el):
            cn_idx = i
            break
    if cn_idx is None:
        return

    # Find English abstract paragraph (search after CN).
    children = list(body)
    en_idx = None
    for i in range(cn_idx, len(children)):
        el = children[i]
        if el.tag != w_p:
            continue
        if en_anchor in _p_text(ns, el):
            en_idx = i
            break
    if en_idx is None:
        return

    # Section break before Chinese abstract (ends previous section).
    sect1 = copy.deepcopy(sectPr_proto)
    _set_sect_break_next_page(ns, sect1)
    # Keep default as decimal; no explicit start so it won't force restarts.
    _set_sect_pgnum(ns, sect1, fmt="decimal", start=None)
    sb_before = _make_section_break_paragraph(ns, sect1)

    # Insert: [section break] [摘要 heading] [cn abstract...]
    body.insert(cn_idx, sb_before)
    body.insert(cn_idx + 1, _make_unnumbered_heading1(ns, "摘要"))

    # Recompute indices after insertions.
    children = list(body)
    # Find English anchor again.
    en_idx2 = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if en_anchor in _p_text(ns, el):
            en_idx2 = i
            break
    if en_idx2 is None:
        return

    body.insert(en_idx2, _make_unnumbered_heading1(ns, "Abstract"))

    # Insert section break after the English abstract paragraph (ends section 2 with roman numerals).
    # Locate the English abstract paragraph again (after Abstract heading insertion).
    children = list(body)
    en_p_idx = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if en_anchor in _p_text(ns, el):
            en_p_idx = i
            break
    if en_p_idx is None:
        return

    sect2 = copy.deepcopy(sectPr_proto)
    _set_sect_break_next_page(ns, sect2)
    _set_sect_pgnum(ns, sect2, fmt="lowerRoman", start=1)
    sb_after = _make_section_break_paragraph(ns, sect2)
    body.insert(en_p_idx + 1, sb_after)


def _sect_text_width_dxa(ns: dict[str, str], root: ET.Element) -> int | None:
    """Compute writable text width in dxa from section properties if available."""
    w_sectPr = _qn(ns, "w", "sectPr")
    w_pgSz = _qn(ns, "w", "pgSz")
    w_pgMar = _qn(ns, "w", "pgMar")
    w_w = _qn(ns, "w", "w")
    w_left = _qn(ns, "w", "left")
    w_right = _qn(ns, "w", "right")

    sectPr = root.find(f".//{w_sectPr}")
    if sectPr is None:
        return None
    pgSz = sectPr.find(w_pgSz)
    pgMar = sectPr.find(w_pgMar)
    if pgSz is None or pgMar is None:
        return None
    try:
        page_w = int(pgSz.get(w_w) or "0")
        mar_l = int(pgMar.get(w_left) or "0")
        mar_r = int(pgMar.get(w_right) or "0")
    except ValueError:
        return None
    if page_w <= 0:
        return None
    return max(0, page_w - mar_l - mar_r)


def _p_has_drawing(ns: dict[str, str], p: ET.Element) -> bool:
    w_drawing = _qn(ns, "w", "drawing")
    w_pict = _qn(ns, "w", "pict")
    return p.find(f".//{w_drawing}") is not None or p.find(f".//{w_pict}") is not None


def _set_para_center(ns: dict[str, str], p: ET.Element) -> None:
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    pPr = _ensure_ppr(ns, p)
    jc = pPr.find(w_jc)
    if jc is None:
        jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")


def _set_para_keep_next(ns: dict[str, str], p: ET.Element) -> None:
    w_keepNext = _qn(ns, "w", "keepNext")
    pPr = _ensure_ppr(ns, p)
    if pPr.find(w_keepNext) is None:
        ET.SubElement(pPr, w_keepNext)


def _set_para_keep_lines(ns: dict[str, str], p: ET.Element) -> None:
    w_keepLines = _qn(ns, "w", "keepLines")
    pPr = _ensure_ppr(ns, p)
    if pPr.find(w_keepLines) is None:
        ET.SubElement(pPr, w_keepLines)


def _set_para_tabs_for_equation(ns: dict[str, str], p: ET.Element, text_w: int) -> None:
    """Set center + right tab stops for equation numbering."""
    w_tabs = _qn(ns, "w", "tabs")
    w_tab = _qn(ns, "w", "tab")
    w_val = _qn(ns, "w", "val")
    w_pos = _qn(ns, "w", "pos")

    mid = max(0, text_w // 2)
    right = max(0, text_w)

    pPr = _ensure_ppr(ns, p)
    tabs = pPr.find(w_tabs)
    if tabs is None:
        tabs = ET.SubElement(pPr, w_tabs)

    # Avoid duplicating tabs if script is rerun.
    existing = {(t.get(w_val), t.get(w_pos)) for t in tabs.findall(w_tab)}
    if ("center", str(mid)) not in existing:
        t = ET.SubElement(tabs, w_tab)
        t.set(w_val, "center")
        t.set(w_pos, str(mid))
    if ("right", str(right)) not in existing:
        t = ET.SubElement(tabs, w_tab)
        t.set(w_val, "right")
        t.set(w_pos, str(right))


def _make_run_tab(ns: dict[str, str]) -> ET.Element:
    w_r = _qn(ns, "w", "r")
    w_tab = _qn(ns, "w", "tab")
    r = ET.Element(w_r)
    ET.SubElement(r, w_tab)
    return r


def _make_run_text(ns: dict[str, str], text: str) -> ET.Element:
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    r = ET.Element(w_r)
    t = ET.SubElement(r, w_t)
    t.text = text
    return r


def _clear_paragraph_runs_and_text(ns: dict[str, str], p: ET.Element) -> None:
    """Remove existing w:r children (keeps math, drawings, etc)."""
    w_r = _qn(ns, "w", "r")
    for r in list(p.findall(w_r)):
        p.remove(r)


def _fix_figure_captions(ns: dict[str, str], body: ET.Element) -> None:
    """Prefix figure captions with chapter-based numbering and center-align."""
    w_p = _qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}

    chapter_no = 0
    fig_no = 0

    children = list(body)
    to_remove: list[ET.Element] = []

    for el in children:
        if el.tag != w_p:
            continue
        style = _p_style(ns, el)
        txt = _p_text(ns, el).strip()

        if style == "1":
            title = txt
            if title and title not in excluded_h1:
                chapter_no += 1
                fig_no = 0
            continue

        if style == "CaptionedFigure" or _p_has_drawing(ns, el):
            _set_para_center(ns, el)
            # Keep caption together with the figure.
            _set_para_keep_next(ns, el)
            _set_para_keep_lines(ns, el)
            continue

        if style != "ImageCaption":
            continue

        if not txt:
            # Pandoc sometimes generates empty caption paragraphs; remove them.
            to_remove.append(el)
            continue

        # If already numbered like "图2-1 ..." then keep.
        if re.match(r"^图\\s*\\d+[-\\.]\\d+\\s*", txt):
            _set_para_center(ns, el)
            continue

        if chapter_no <= 0:
            # Before first real chapter: skip numbering.
            _set_para_center(ns, el)
            continue

        fig_no += 1
        new_txt = f"图{chapter_no}-{fig_no} {txt}"

        _set_para_center(ns, el)
        _set_para_keep_lines(ns, el)
        _clear_paragraph_runs_and_text(ns, el)
        el.append(_make_run_text(ns, new_txt))

    for el in to_remove:
        try:
            body.remove(el)
        except ValueError:
            pass


def _make_empty_para(ns: dict[str, str], style: str = "a") -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)
    return p


def _insert_abstract_keywords(
    ns: dict[str, str],
    body: ET.Element,
    cn_keywords: str | None,
    en_keywords: str | None,
) -> None:
    """
    Insert keywords lines for Chinese/English abstracts:
    - leave one blank line before keywords
    - keep 3-4 groups (truncate to 4 by default)
    """
    w_p = _qn(ns, "w", "p")

    def find_heading_idx(title: str) -> int | None:
        for i, el in enumerate(list(body)):
            if el.tag != w_p:
                continue
            if _p_style(ns, el) == "1" and _p_text(ns, el).strip() == title:
                return i
        return None

    def already_has_kw(start: int, end: int, marker: str) -> bool:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if marker in _p_text(ns, el):
                return True
        return False

    def insert_kw_block(after_idx: int, line: str) -> None:
        # Blank line then keywords paragraph.
        body.insert(after_idx + 1, _make_empty_para(ns, "a"))
        p = _make_empty_para(ns, "a")
        _clear_paragraph_runs_and_text(ns, p)
        p.append(_make_run_text(ns, line))
        body.insert(after_idx + 2, p)

    children = list(body)
    cn_h = find_heading_idx("摘要")
    en_h = find_heading_idx("Abstract")
    if cn_h is None or en_h is None or cn_h >= en_h:
        return

    # Chinese keywords: insert just before "Abstract" heading, after last non-empty para in CN block.
    if cn_keywords:
        if not already_has_kw(cn_h, en_h, "关键词"):
            cn_kw = _split_keywords(cn_keywords, max_groups=4, lang="cn")
            last = None
            children = list(body)
            for i in range(en_h - 1, cn_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if _p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                insert_kw_block(last, f"关键词：{cn_kw}")

    # English keywords: insert before the section break paragraph after English abstract if present,
    # else before the next Heading 1.
    if en_keywords:
        # recompute indices after possible insertions
        children = list(body)
        en_h = find_heading_idx("Abstract")
        if en_h is None:
            return
        # locate end bound
        end = len(children)
        for i in range(en_h + 1, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_has_sectPr(ns, el):
                end = i
                break
            if _p_style(ns, el) == "1":
                end = i
                break

        if not already_has_kw(en_h, end, "Keywords"):
            en_kw = _split_keywords(en_keywords, max_groups=4, lang="en")
            last = None
            children = list(body)
            for i in range(end - 1, en_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if _p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                insert_kw_block(last, f"Keywords: {en_kw.replace('；', '; ')}")


def _number_display_equations(
    ns: dict[str, str],
    root: ET.Element,
    body: ET.Element,
    display_math_flags: list[bool] | None,
) -> None:
    """Add chapter-based equation numbers to paragraphs containing m:oMathPara."""
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    m_uri = None
    for k, v in ns.items():
        if k == "m":
            m_uri = v
            break
    if not m_uri:
        return
    m_oMathPara = f"{{{m_uri}}}oMathPara"

    text_w = _sect_text_width_dxa(ns, root)
    if text_w is None or text_w == 0:
        # Fallback to A4 template expected content width if section props are missing.
        # A4 11907, margins left 1417 right 1134 => 9356
        text_w = 9356

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    chapter_no = 0
    eq_no = 0

    children = list(body)
    math_paras = [p for p in children if p.tag == w_p and p.find(m_oMathPara) is not None]

    # Use LaTeX-derived flags if available and aligned; otherwise number all display math.
    if (
        isinstance(display_math_flags, list)
        and all(isinstance(x, bool) for x in display_math_flags)
        and len(display_math_flags) == len(math_paras)
    ):
        flag_iter = iter(display_math_flags)
    else:
        flag_iter = None

    def should_number() -> bool:
        if flag_iter is None:
            return True
        try:
            return next(flag_iter)
        except StopIteration:
            return True

    for p in children:
        if p.tag != w_p:
            continue
        style = _p_style(ns, p)
        txt = _p_text(ns, p).strip()

        if style == "1":
            if txt and txt not in excluded_h1:
                chapter_no += 1
                eq_no = 0
            continue

        if p.find(m_oMathPara) is None:
            continue

        if chapter_no <= 0:
            continue

        if not should_number():
            # Ensure display math paragraphs don't inherit body first-line indent.
            pPr = _ensure_ppr(ns, p)
            ind = pPr.find(_qn(ns, "w", "ind"))
            if ind is not None:
                for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                    ind.attrib.pop(_qn(ns, "w", attr), None)
                if not ind.attrib:
                    pPr.remove(ind)
            continue

        # Avoid double-numbering if already contains something like (2-1).
        if re.search(r"\\(\\d+[-\\.]\\d+\\)\\s*$", txt):
            continue

        eq_no += 1
        num_txt = f"({chapter_no}-{eq_no})"

        # Display math paragraphs should not have first-line indents.
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # Append tab + number.
        p.append(_make_run_tab(ns))
        p.append(_make_run_text(ns, num_txt))


def _insert_toc_before_first_chapter(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_numPr = _qn(ns, "w", "numPr")
    w_numId = _qn(ns, "w", "numId")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_fldChar = _qn(ns, "w", "fldChar")
    w_fldCharType = _qn(ns, "w", "fldCharType")
    w_instrText = _qn(ns, "w", "instrText")

    children = list(body)
    first_h1_idx = None
    unnumbered = {"目录", "摘要", "Abstract"}
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if _p_style(ns, el) == "1":
            # Insert TOC before the first *numbered* chapter, not before abstract/TOC headings.
            if _p_text(ns, el).strip() in unnumbered:
                continue
            first_h1_idx = i
            break
    if first_h1_idx is None:
        return

    # TOC title paragraph: use Heading 1 style but suppress numbering per-paragraph (numId=0).
    toc_title_p = ET.Element(w_p)
    pPr = ET.SubElement(toc_title_p, w_pPr)
    pStyle = ET.SubElement(pPr, w_pStyle)
    pStyle.set(w_val, "1")
    jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")
    numPr = ET.SubElement(pPr, w_numPr)
    numId = ET.SubElement(numPr, w_numId)
    numId.set(w_val, "0")
    r = ET.SubElement(toc_title_p, w_r)
    t = ET.SubElement(r, w_t)
    t.text = "目录"

    # TOC field paragraph (Word field code). Users can right-click -> Update Field.
    toc_field_p = ET.Element(w_p)
    r1 = ET.SubElement(toc_field_p, w_r)
    fld_begin = ET.SubElement(r1, w_fldChar)
    fld_begin.set(w_fldCharType, "begin")

    r2 = ET.SubElement(toc_field_p, w_r)
    instr = ET.SubElement(r2, w_instrText)
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '

    r3 = ET.SubElement(toc_field_p, w_r)
    fld_sep = ET.SubElement(r3, w_fldChar)
    fld_sep.set(w_fldCharType, "separate")

    r4 = ET.SubElement(toc_field_p, w_r)
    t4 = ET.SubElement(r4, w_t)
    t4.text = "（右键此处，选择“更新域”以生成目录）"

    r5 = ET.SubElement(toc_field_p, w_r)
    fld_end = ET.SubElement(r5, w_fldChar)
    fld_end.set(w_fldCharType, "end")

    # Page break after TOC so first chapter starts on a new page.
    pb = _make_page_break_p(ns)

    body.insert(first_h1_idx, toc_title_p)
    body.insert(first_h1_idx + 1, toc_field_p)
    body.insert(first_h1_idx + 2, pb)


def _add_page_breaks_before_h1(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    children = list(body)
    i = 0
    while i < len(children):
        el = children[i]
        if el.tag == w_p and _p_style(ns, el) == "1":
            title = _p_text(ns, el).strip()
            if title == "目录":
                i += 1
                continue
            if i == 0:
                i += 1
                continue
            prev = children[i - 1]
            if prev.tag == w_p and (_p_has_page_break(ns, prev) or _p_has_sectPr(ns, prev)):
                i += 1
                continue
            # Insert a separate page-break paragraph to avoid blank pages at document start.
            pb = _make_page_break_p(ns)
            body.insert(i, pb)
            children.insert(i, pb)
            i += 2
            continue
        i += 1


def _ensure_indent_for_body_paragraphs(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_ind = _qn(ns, "w", "ind")
    w_firstLineChars = _qn(ns, "w", "firstLineChars")

    body_styles = {"BodyText", "FirstParagraph", "Compact"}

    for p in body.iter(w_p):
        style = _p_style(ns, p)
        if style not in body_styles:
            continue
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(w_ind)
        if ind is None:
            ind = ET.SubElement(pPr, w_ind)
        # Keep other indentation attributes intact; only enforce first-line indent.
        ind.set(w_firstLineChars, "200")


def _ensure_hanging_indent_for_bibliography(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_ind = _qn(ns, "w", "ind")
    w_hangingChars = _qn(ns, "w", "hangingChars")

    children = list(body)
    ref_idx = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if _p_text(ns, el).strip() == "参考文献":
            ref_idx = i
            break
    if ref_idx is None:
        return

    # Typical GB/T numeric entries start with "[1]" (ASCII) or "［1］" (fullwidth).
    bib_entry_re = re.compile(r"^(\[[0-9]{1,4}\]|［[0-9]{1,4}］)")
    i = ref_idx + 1
    while i < len(children):
        el = children[i]
        if el.tag != w_p:
            i += 1
            continue
        style = _p_style(ns, el)
        if style == "1" and _p_text(ns, el).strip() not in {"参考文献"}:
            break
        txt = _p_text(ns, el).strip()
        if bib_entry_re.match(txt):
            pPr = _ensure_ppr(ns, el)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            ind.set(w_hangingChars, "200")
        i += 1


def _fix_numbering_isLgl(ns: dict[str, str], numbering_xml: bytes) -> bytes:
    ns2 = _collect_ns(numbering_xml)
    if "w" not in ns2:
        return numbering_xml
    _register_ns(ns2)
    w_uri = ns2["w"]
    w_abstractNum = f"{{{w_uri}}}abstractNum"
    w_abstractNumId = f"{{{w_uri}}}abstractNumId"
    w_lvl = f"{{{w_uri}}}lvl"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_isLgl = f"{{{w_uri}}}isLgl"
    w_start = f"{{{w_uri}}}start"

    root = ET.fromstring(numbering_xml)

    target = None
    for absn in root.findall(w_abstractNum):
        if absn.get(w_abstractNumId) == "0":
            target = absn
            break
    if target is None:
        return numbering_xml

    changed = False
    for lvl in target.findall(w_lvl):
        ilvl = lvl.get(w_ilvl)
        if ilvl is None:
            continue
        try:
            ilvl_i = int(ilvl)
        except ValueError:
            continue
        if ilvl_i < 1:
            continue
        if lvl.find(w_isLgl) is not None:
            continue
        isLgl = ET.Element(w_isLgl)
        # Insert after <w:start> if present, else as first child.
        start = lvl.find(w_start)
        if start is not None:
            idx = list(lvl).index(start) + 1
            lvl.insert(idx, isLgl)
        else:
            lvl.insert(0, isLgl)
        changed = True

    if not changed:
        return numbering_xml
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _collect_style_ids(styles_xml: bytes) -> set[str]:
    ns = _collect_ns(styles_xml)
    if "w" not in ns:
        return set()
    w_uri = ns["w"]
    q_style = f"{{{w_uri}}}style"
    q_styleId = f"{{{w_uri}}}styleId"
    root = ET.fromstring(styles_xml)
    out: set[str] = set()
    for st in root.findall(q_style):
        sid = st.get(q_styleId)
        if sid:
            out.add(sid)
    return out


def _normalize_unknown_pstyles(
    ns: dict[str, str], body: ET.Element, known_styles: set[str]
) -> None:
    """Map paragraphs that reference non-existent styles back to Normal ('a')."""
    w_p = _qn(ns, "w", "p")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")

    # Pandoc may emit these pStyle values even when the reference template doesn't define them.
    # Prefer mapping them to template Normal (styleId 'a') to keep formatting stable.
    candidates = {
        "BodyText",
        "FirstParagraph",
        "Compact",
        "ImageCaption",
        "CaptionedFigure",
        "Bibliography",
        "Caption",
    }

    for p in body.iter(w_p):
        pPr = p.find(_qn(ns, "w", "pPr"))
        if pPr is None:
            continue
        ps = pPr.find(w_pStyle)
        if ps is None:
            continue
        val = ps.get(w_val)
        if not val:
            continue
        if val in known_styles:
            continue
        if val in candidates:
            ps.set(w_val, "a")


def _postprocess_docx(
    input_docx: Path,
    output_docx: Path,
    display_math_flags: list[bool] | None,
    cn_keywords: str | None,
    en_keywords: str | None,
) -> None:
    with zipfile.ZipFile(input_docx, "r") as zin:
        files = zin.namelist()

        doc_xml = zin.read("word/document.xml")
        doc_ns = _collect_ns(doc_xml)
        if "w" not in doc_ns:
            raise RuntimeError("word/document.xml missing w namespace")
        _register_ns(doc_ns)

        root = ET.fromstring(doc_xml)
        w_body = _qn(doc_ns, "w", "body")
        body = root.find(w_body)
        if body is None:
            raise RuntimeError("word/document.xml missing w:body")

        _prepend_template_cover_pages(doc_ns, body, TEMPLATE_DOCX)

        styles_xml = zin.read("word/styles.xml") if "word/styles.xml" in files else b""
        known_styles = _collect_style_ids(styles_xml) if styles_xml else set()

        sectPr = _get_body_sectPr(doc_ns, body)
        if sectPr is not None:
            sectPr_proto = copy.deepcopy(sectPr)
        else:
            sectPr_proto = None

        if sectPr_proto is not None:
            _insert_abstract_chapters_and_sections(doc_ns, body, sectPr_proto)

        _insert_abstract_keywords(doc_ns, body, cn_keywords, en_keywords)

        _insert_toc_before_first_chapter(doc_ns, body)
        _add_page_breaks_before_h1(doc_ns, body)
        _ensure_indent_for_body_paragraphs(doc_ns, body)
        _ensure_hanging_indent_for_bibliography(doc_ns, body)
        _fix_figure_captions(doc_ns, body)
        _number_display_equations(doc_ns, root, body, display_math_flags)
        if known_styles:
            _normalize_unknown_pstyles(doc_ns, body, known_styles)

        # Ensure the final/main section uses Arabic page numbers starting at 1.
        sectPr2 = _get_body_sectPr(doc_ns, body)
        if sectPr2 is not None:
            _set_sect_pgnum(doc_ns, sectPr2, fmt="decimal", start=1)

        new_doc_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        numbering_xml = zin.read("word/numbering.xml") if "word/numbering.xml" in files else None
        new_numbering_xml = (
            _fix_numbering_isLgl(doc_ns, numbering_xml) if numbering_xml else None
        )

        # Write a new docx, copying everything else verbatim.
        tmp_out = output_docx.with_suffix(".docx.tmp")
        if tmp_out.exists():
            tmp_out.unlink()
        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in files:
                data = zin.read(name)
                if name == "word/document.xml":
                    data = new_doc_xml
                elif name == "word/numbering.xml" and new_numbering_xml is not None:
                    data = new_numbering_xml
                zout.writestr(name, data)
        tmp_out.replace(output_docx)


def _resolve_paths(thesis_dir: Path) -> None:
    """Rebind module-level paths to point at the provided thesis directory."""
    global ROOT, MAIN_TEX, CSL, BIB, FLAT_TEX, INTERMEDIATE_DOCX, OUTPUT_DOCX  # noqa: PLW0603

    ROOT = thesis_dir
    MAIN_TEX = ROOT / "main.tex"

    # Prefer project-local CSL; fallback to the copy bundled with this skill.
    default_csl = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
    if default_csl.exists():
        CSL = default_csl
    else:
        CSL = SCRIPT_DIR / "china-national-standard-gb-t-7714-2015-numeric.csl"

    BIB = Path(os.environ.get("SWUN_BIB", str(ROOT / "backmatter" / "references.bib"))).expanduser()

    FLAT_TEX = ROOT / ".main.flat.tex"
    INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
    OUTPUT_DOCX = ROOT / "main_版式1.docx"


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Default: use current working directory if it looks like a thesis root, else fallback.
    if argv:
        thesis_dir = Path(argv[0]).expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        thesis_dir = cwd if (cwd / "main.tex").exists() else Path("/Users/bit/LaTeX/SWUN_Thesis")

    _resolve_paths(thesis_dir)

    # Allow overriding CSL via env after we bind thesis dir (keeps old behavior).
    csl_override = os.environ.get("SWUN_CSL")
    if csl_override:
        global CSL  # noqa: PLW0603
        CSL = Path(csl_override).expanduser()

    for p in [TEMPLATE_DOCX, MAIN_TEX, CSL, BIB]:
        if not p.exists():
            raise SystemExit(f"missing required file: {p}")

    # Backup existing output.
    if OUTPUT_DOCX.exists():
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = OUTPUT_DOCX.with_suffix(f".docx.bak_{ts}")
        shutil.copy2(OUTPUT_DOCX, bak)

    # 1) latexpand -> flat tex
    # latexpand writes to stdout; capture ourselves to keep errors visible.
    flat = subprocess.run(
        ["latexpand", str(MAIN_TEX)],
        cwd=str(ROOT),
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8", errors="ignore")

    flat = _preprocess_latex(flat)
    FLAT_TEX.write_text(flat, encoding="utf-8")
    display_math_flags = _extract_display_math_number_flags(flat)
    cn_kw, en_kw = _extract_keywords(flat)

    # 2) pandoc -> intermediate docx
    if INTERMEDIATE_DOCX.exists():
        INTERMEDIATE_DOCX.unlink()
    _run(
        [
            "pandoc",
            str(FLAT_TEX),
            "--from=latex",
            "--to=docx",
            f"--reference-doc={TEMPLATE_DOCX}",
            f"--csl={CSL}",
            f"--bibliography={BIB}",
            "--citeproc",
            '--metadata=reference-section-title:参考文献',
            '--resource-path=.:./media:./figures',
            f"-o",
            str(INTERMEDIATE_DOCX),
        ],
        cwd=ROOT,
    )

    # 3) OOXML postprocess -> final docx
    _postprocess_docx(INTERMEDIATE_DOCX, OUTPUT_DOCX, display_math_flags, cn_kw, en_kw)

    # Optional cleanup: keep FLAT_TEX for debugging, remove intermediate.
    if INTERMEDIATE_DOCX.exists():
        INTERMEDIATE_DOCX.unlink()
    if FLAT_TEX.exists():
        FLAT_TEX.unlink()

    print(f"OK: {OUTPUT_DOCX}")


if __name__ == "__main__":
    main()
