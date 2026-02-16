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

    # --- Flatten subfigures so pandoc counts only main figure captions ---
    s = _flatten_subfigures(s)

    return s


def _flatten_subfigures(s: str) -> str:
    """Replace subfigure \\ref with parent figure \\ref and strip subfigure captions/labels.

    Pandoc counts every \\caption inside subfigure as a separate figure, inflating
    the figure counter.  This function:
    1. Builds a mapping: subfigure_label -> parent_figure_label
    2. Replaces \\ref{subfig_label} with \\ref{parent_label} everywhere
    3. Strips \\caption and \\label inside subfigure environments
    4. Removes \\begin{subfigure}/\\end{subfigure} wrappers (keeps \\includegraphics)
    5. Deduplicates adjacent identical refs (e.g. "图~\\ref{X}和图~\\ref{X}" -> "图~\\ref{X}")
    """
    # Step 1: extract subfigure labels and their parent figure labels
    subfig_to_parent: dict[str, str] = {}

    # Find each figure environment and its subfigures
    fig_re = re.compile(
        r"\\begin\{figure\}.*?\\end\{figure\}", re.DOTALL
    )
    subfig_label_re = re.compile(
        r"\\begin\{subfigure\}.*?\\label\{([^}]+)\}.*?\\end\{subfigure\}", re.DOTALL
    )
    # Parent label: \label{...} that is NOT inside a subfigure block
    # We find it by looking for \label after the last \end{subfigure} but before \end{figure}
    parent_label_re = re.compile(r"\\label\{([^}]+)\}")

    for fig_m in fig_re.finditer(s):
        fig_block = fig_m.group(0)
        # Collect subfigure labels
        sub_labels = [m.group(1) for m in subfig_label_re.finditer(fig_block)]
        if not sub_labels:
            continue  # no subfigures in this figure

        # Find parent label: the \label that is outside any subfigure
        # Remove all subfigure blocks to find the parent label
        stripped = re.sub(
            r"\\begin\{subfigure\}.*?\\end\{subfigure\}", "", fig_block, flags=re.DOTALL
        )
        parent_m = parent_label_re.search(stripped)
        if not parent_m:
            continue
        parent_label = parent_m.group(1)

        for sl in sub_labels:
            subfig_to_parent[sl] = parent_label

    if not subfig_to_parent:
        return s

    # Step 2: replace \ref{subfig_label} with \ref{parent_label}
    for sub_lbl, par_lbl in subfig_to_parent.items():
        s = s.replace(f"\\ref{{{sub_lbl}}}", f"\\ref{{{par_lbl}}}")

    # Step 3: strip \caption and \label inside subfigure environments
    def _strip_subfig_internals(m: re.Match) -> str:
        block = m.group(0)
        # Remove \caption{...} lines
        block = re.sub(r"\\caption\{[^}]*\}\s*", "", block)
        # Remove \label{...} lines
        block = re.sub(r"\\label\{[^}]*\}\s*", "", block)
        return block

    s = re.sub(
        r"\\begin\{subfigure\}.*?\\end\{subfigure\}",
        _strip_subfig_internals,
        s,
        flags=re.DOTALL,
    )

    # Step 4: remove \begin{subfigure}[...]{...} and \end{subfigure} wrappers
    s = re.sub(r"\\begin\{subfigure\}(\[[^\]]*\])?\{[^}]*\}", "", s)
    s = re.sub(r"\\end\{subfigure\}", "", s)

    # Step 5: deduplicate adjacent identical figure refs
    # "图~\ref{X}和图~\ref{X}" or "图 \ref{X} 与图 \ref{X}" -> single ref
    s = re.sub(
        r"(图[~\s]*)\\ref\{([^}]+)\}\s*[与和及]\s*图[~\s]*\\ref\{\2\}",
        r"\1\\ref{\2}",
        s,
    )

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


def _remove_page_break_before(ns: dict[str, str], p: ET.Element) -> None:
    w_pageBreakBefore = _qn(ns, "w", "pageBreakBefore")
    pPr = p.find(_qn(ns, "w", "pPr"))
    if pPr is None:
        return
    pbb = pPr.find(w_pageBreakBefore)
    if pbb is not None:
        pPr.remove(pbb)


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
    _remove_page_break_before(ns, children[cn_idx])

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
    _remove_page_break_before(ns, children[en_idx])

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


def _fix_ref_dot_to_hyphen(ns: dict[str, str], body: ET.Element) -> None:
    """Replace dot-format figure/table refs (图3.1, 表4.2) with hyphen format (图3-1, 表4-2).

    Handles two cases:
    1. Reference within a single <w:t>: "如图3.1所示" or "图 3.7 与图 3.8"
    2. Split across runs: <w:t>图 </w:t> + <w:t>3.1</w:t>
    """
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")

    # Pattern for refs inside a single text node
    inline_re = re.compile(r"((?:图|表)\s*)(\d+)\.(\d+)")
    # Pattern for a standalone number at the start of a text node
    num_re = re.compile(r"^(\s*)(\d+)\.(\d+)")

    for p in body.iter(w_p):
        # Pass 1: fix refs contained in a single <w:t>
        for t in p.iter(w_t):
            if t.text and inline_re.search(t.text):
                t.text = inline_re.sub(r"\1\2-\3", t.text)

        # Pass 2: fix split refs (图/表 at end of one run, number in a later run)
        # Pandoc often splits as: [..."图"] [" "] ["3.7"] [" "]
        runs = list(p.findall(f".//{w_r}"))
        for i in range(len(runs) - 1):
            cur_texts = list(runs[i].iter(w_t))
            if not cur_texts:
                continue
            tail = (cur_texts[-1].text or "").rstrip()
            if not tail.endswith(("图", "表")):
                continue
            # Look ahead, skipping whitespace-only runs
            for j in range(i + 1, min(i + 4, len(runs))):
                nxt_texts = list(runs[j].iter(w_t))
                if not nxt_texts:
                    continue
                nxt_val = nxt_texts[0].text or ""
                if nxt_val.strip() == "":
                    continue  # skip whitespace-only run
                if num_re.match(nxt_val):
                    nxt_texts[0].text = num_re.sub(r"\1\2-\3", nxt_val, count=1)
                break  # stop at first non-whitespace run


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


def _first_table_style_id(styles_xml: bytes) -> str | None:
    ns = _collect_ns(styles_xml)
    if "w" not in ns:
        return None
    w_uri = ns["w"]
    q_style = f"{{{w_uri}}}style"
    q_type = f"{{{w_uri}}}type"
    q_styleId = f"{{{w_uri}}}styleId"
    root = ET.fromstring(styles_xml)
    for st in root.findall(q_style):
        if st.get(q_type) != "table":
            continue
        sid = st.get(q_styleId)
        if sid:
            return sid
    return None


def _ensure_tbl_pr(ns: dict[str, str], tbl: ET.Element) -> ET.Element:
    w_tblPr = _qn(ns, "w", "tblPr")
    pr = tbl.find(w_tblPr)
    if pr is None:
        pr = ET.Element(w_tblPr)
        tbl.insert(0, pr)
    return pr


def _set_border_el(ns: dict[str, str], parent: ET.Element, edge: str, val: str, sz: str) -> None:
    w_val = _qn(ns, "w", "val")
    w_sz = _qn(ns, "w", "sz")
    w_space = _qn(ns, "w", "space")
    w_color = _qn(ns, "w", "color")
    el = parent.find(_qn(ns, "w", edge))
    if el is None:
        el = ET.SubElement(parent, _qn(ns, "w", edge))
    el.attrib.clear()
    el.set(w_val, val)
    if val != "nil":
        el.set(w_sz, sz)
        el.set(w_space, "0")
        el.set(w_color, "auto")


def _is_data_table(ns: dict[str, str], tbl: ET.Element) -> bool:
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tblCaption = _qn(ns, "w", "tblCaption")
    w_val = _qn(ns, "w", "val")

    pr = tbl.find(w_tblPr)
    if pr is None:
        return False
    st = pr.find(w_tblStyle)
    st_val = st.get(w_val) if st is not None else None
    has_caption = pr.find(w_tblCaption) is not None
    # Pandoc uses FigureTable for figure layout tables; never treat them as data tables.
    if st_val == "FigureTable":
        return False
    return has_caption or st_val == "Table"


def _visual_text_len(s: str) -> int:
    n = 0
    for ch in s:
        if ch.isspace():
            continue
        n += 1 if ord(ch) < 128 else 2
    return n


def _table_col_count(ns: dict[str, str], tbl: ET.Element) -> int:
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_val = _qn(ns, "w", "val")

    grid = tbl.find(w_tblGrid)
    if grid is not None:
        cols = len(grid.findall(w_gridCol))
        if cols > 0:
            return cols

    max_cols = 0
    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is not None:
                gs = tcPr.find(w_gridSpan)
                if gs is not None:
                    try:
                        span = max(1, int(gs.get(w_val) or "1"))
                    except ValueError:
                        span = 1
            col += span
        max_cols = max(max_cols, col)
    return max_cols


def _table_col_weights(ns: dict[str, str], tbl: ET.Element, ncols: int) -> list[int]:
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_val = _qn(ns, "w", "val")
    w_t = _qn(ns, "w", "t")

    if ncols <= 0:
        return []

    weights = [1] * ncols
    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is not None:
                gs = tcPr.find(w_gridSpan)
                if gs is not None:
                    try:
                        span = max(1, int(gs.get(w_val) or "1"))
                    except ValueError:
                        span = 1
            txt = "".join((t.text or "") for t in tc.iter(w_t)).strip()
            score = max(1, _visual_text_len(txt))
            per_col = max(1, int(round(score / max(1, span))))
            for k in range(span):
                idx = col + k
                if idx >= ncols:
                    break
                weights[idx] = max(weights[idx], per_col)
            col += span
    return weights


def _normalize_widths_to_total(weights: list[int], total_w: int) -> list[int]:
    n = len(weights)
    if n == 0:
        return []
    if total_w <= 0:
        return [0] * n

    min_col = max(240, min(720, total_w // n))
    s = sum(max(1, w) for w in weights)
    widths = [max(min_col, int(round(total_w * max(1, w) / s))) for w in weights]

    diff = total_w - sum(widths)
    if diff > 0:
        order = sorted(range(n), key=lambda i: weights[i], reverse=True)
        if not order:
            order = list(range(n))
        k = 0
        while diff > 0:
            idx = order[k % len(order)]
            widths[idx] += 1
            diff -= 1
            k += 1
    elif diff < 0:
        order = sorted(range(n), key=lambda i: widths[i], reverse=True)
        k = 0
        guard = 0
        while diff < 0 and guard < n * max(total_w, 1):
            idx = order[k % len(order)]
            if widths[idx] > min_col:
                widths[idx] -= 1
                diff += 1
            k += 1
            guard += 1
        # Last resort: force exact total on the widest column.
        if diff != 0 and widths:
            widest = max(range(n), key=lambda i: widths[i])
            widths[widest] = max(min_col, widths[widest] + diff)

    return widths


def _set_table_full_width_and_columns(
    ns: dict[str, str], tbl: ET.Element, text_w: int
) -> None:
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblW = _qn(ns, "w", "tblW")
    w_tblLayout = _qn(ns, "w", "tblLayout")
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcW = _qn(ns, "w", "tcW")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_type = _qn(ns, "w", "type")
    w_val = _qn(ns, "w", "val")
    w_w = _qn(ns, "w", "w")

    ncols = _table_col_count(ns, tbl)
    if ncols <= 0:
        return
    weights = _table_col_weights(ns, tbl, ncols)
    widths = _normalize_widths_to_total(weights, text_w)
    if not widths:
        return

    pr = _ensure_tbl_pr(ns, tbl)
    tblW = pr.find(w_tblW)
    if tblW is None:
        tblW = ET.SubElement(pr, w_tblW)
    tblW.set(w_type, "dxa")
    tblW.set(w_w, str(text_w))

    layout = pr.find(w_tblLayout)
    if layout is None:
        layout = ET.SubElement(pr, w_tblLayout)
    layout.set(w_type, "fixed")

    tblGrid = tbl.find(w_tblGrid)
    if tblGrid is None:
        tblGrid = ET.Element(w_tblGrid)
        insert_at = 0
        for i, child in enumerate(list(tbl)):
            if child.tag == w_tblPr:
                insert_at = i + 1
                break
        tbl.insert(insert_at, tblGrid)
    for gc in list(tblGrid.findall(w_gridCol)):
        tblGrid.remove(gc)
    for wv in widths:
        gc = ET.SubElement(tblGrid, w_gridCol)
        gc.set(w_w, str(wv))

    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                tcPr = ET.SubElement(tc, w_tcPr)
            gs = tcPr.find(w_gridSpan)
            if gs is not None:
                try:
                    span = max(1, int(gs.get(w_val) or "1"))
                except ValueError:
                    span = 1
            cell_w = 0
            for k in range(span):
                idx = col + k
                if idx < len(widths):
                    cell_w += widths[idx]
            if cell_w <= 0 and col < len(widths):
                cell_w = widths[col]

            tcW = tcPr.find(w_tcW)
            if tcW is None:
                tcW = ET.SubElement(tcPr, w_tcW)
            tcW.set(w_type, "dxa")
            tcW.set(w_w, str(max(1, cell_w)))
            col += span


def _set_p_style(ns: dict[str, str], p: ET.Element, style: str) -> None:
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    pPr = _ensure_ppr(ns, p)
    ps = pPr.find(w_pStyle)
    if ps is None:
        ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)


def _set_paragraph_text(ns: dict[str, str], p: ET.Element, txt: str) -> None:
    _clear_paragraph_runs_and_text(ns, p)
    p.append(_make_run_text(ns, txt))


def _clean_table_title(txt: str) -> str:
    s = (txt or "").strip()
    s = re.sub(r"^表[\s\xa0]*\d+(?:[\-\.．]\d+)?[\s\xa0:：、.]*", "", s)
    return s.strip()


def _is_table_caption_para(ns: dict[str, str], p: ET.Element) -> bool:
    style = _p_style(ns, p)
    txt = _p_text(ns, p).strip()
    if style == "TableCaption":
        return True
    return bool(re.match(r"^表[\s\xa0]*\d+(?:[\-\.．]\d+)?", txt))


def _find_caption_idx_near_table(
    ns: dict[str, str], children: list[ET.Element], tbl_idx: int, direction: int
) -> int | None:
    w_p = _qn(ns, "w", "p")
    step = -1 if direction < 0 else 1
    rng = range(tbl_idx + step, -1, -1) if step < 0 else range(tbl_idx + 1, len(children))
    checked = 0
    for j in rng:
        el = children[j]
        if el.tag != w_p:
            continue
        txt = _p_text(ns, el).strip()
        if not txt:
            continue
        checked += 1
        if _is_table_caption_para(ns, el):
            return j
        # Stop at first non-caption paragraph near the table.
        if checked >= 1:
            break
    return None


def _apply_three_line_tables(
    ns: dict[str, str], root: ET.Element, body: ET.Element, table_style_id: str | None
) -> None:
    """
    Enforce three-line tables and normalize table layout/captions:
    - table top + bottom border
    - header separator line (bottom border of last header row)
    - no vertical borders and no inner horizontal borders for body rows
    - table width fills full text width; column widths are redistributed by content
    - table captions are ordered by chapter and placed below each table
    """
    w_tbl = _qn(ns, "w", "tbl")
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tblCaption = _qn(ns, "w", "tblCaption")
    w_tr = _qn(ns, "w", "tr")
    w_trPr = _qn(ns, "w", "trPr")
    w_tblHeader = _qn(ns, "w", "tblHeader")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcBorders = _qn(ns, "w", "tcBorders")
    w_tblBorders = _qn(ns, "w", "tblBorders")
    w_p = _qn(ns, "w", "p")
    w_val = _qn(ns, "w", "val")

    # Word border size unit is 1/8 pt. Template examples use w:sz="6" (0.75pt).
    rule_sz = "6"
    text_w = _sect_text_width_dxa(ns, root) or 9356
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    chapter_no = 0
    table_no = 0
    global_no = 0

    i = 0
    children = list(body)
    while i < len(children):
        el = children[i]
        if el.tag == w_p and _p_style(ns, el) == "1":
            title = _p_text(ns, el).strip()
            if title and title not in excluded_h1:
                chapter_no += 1
                table_no = 0
            i += 1
            continue
        if el.tag != w_tbl:
            i += 1
            continue

        tbl = el
        if not _is_data_table(ns, tbl):
            i += 1
            continue

        global_no += 1
        if chapter_no > 0:
            table_no += 1
            table_prefix = f"表{chapter_no}-{table_no}"
        else:
            table_prefix = f"表{global_no}"

        pr = tbl.find(w_tblPr)
        if pr is None:
            i += 1
            continue

        st = pr.find(w_tblStyle)
        st_val = st.get(w_val) if st is not None else None
        pr = _ensure_tbl_pr(ns, tbl)

        # Make tblStyle valid (pandoc sometimes emits an undefined styleId like "Table").
        if table_style_id and (st_val in (None, "", "Table")):
            if st is None:
                st = ET.SubElement(pr, w_tblStyle)
            st.set(w_val, table_style_id)

        _set_table_full_width_and_columns(ns, tbl, text_w)

        # Remove any existing cell borders to avoid unwanted gridlines.
        for tc in tbl.iter(w_tc):
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                continue
            tcBorders = tcPr.find(w_tcBorders)
            if tcBorders is not None:
                tcPr.remove(tcBorders)

        # Table-level borders: only top and bottom.
        borders = pr.find(w_tblBorders)
        if borders is not None:
            pr.remove(borders)
        borders = ET.SubElement(pr, w_tblBorders)
        _set_border_el(ns, borders, "top", "single", rule_sz)
        _set_border_el(ns, borders, "bottom", "single", rule_sz)
        _set_border_el(ns, borders, "left", "nil", rule_sz)
        _set_border_el(ns, borders, "right", "nil", rule_sz)
        _set_border_el(ns, borders, "insideH", "nil", rule_sz)
        _set_border_el(ns, borders, "insideV", "nil", rule_sz)

        # Header separator: bottom border of the last header row at the top of table.
        trs = tbl.findall(w_tr)
        if not trs:
            continue

        header_end = None
        for i, tr in enumerate(trs):
            trPr = tr.find(w_trPr)
            if trPr is not None and trPr.find(w_tblHeader) is not None:
                header_end = i
                continue
            break
        if header_end is None:
            header_end = 0

        header_tr = trs[header_end]
        for tc in header_tr.findall(w_tc):
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                tcPr = ET.SubElement(tc, w_tcPr)
            tcBorders = tcPr.find(w_tcBorders)
            if tcBorders is None:
                tcBorders = ET.SubElement(tcPr, w_tcBorders)
            _set_border_el(ns, tcBorders, "bottom", "single", rule_sz)

        # Normalize caption text and ensure caption paragraph is below the table.
        children = list(body)
        tbl_idx = children.index(tbl)
        prev_cap_idx = _find_caption_idx_near_table(ns, children, tbl_idx, direction=-1)
        next_cap_idx = _find_caption_idx_near_table(ns, children, tbl_idx, direction=1)

        cap_par = None
        if next_cap_idx is not None:
            cap_par = children[next_cap_idx]
        elif prev_cap_idx is not None:
            cap_par = children[prev_cap_idx]

        tbl_cap = pr.find(w_tblCaption)
        title_raw = ""
        if tbl_cap is not None:
            title_raw = tbl_cap.get(w_val) or ""
        if not title_raw and cap_par is not None:
            title_raw = _p_text(ns, cap_par).strip()
        title = _clean_table_title(title_raw) or title_raw.strip()

        if not title:
            i += 1
            continue

        if tbl_cap is None:
            tbl_cap = ET.SubElement(pr, w_tblCaption)
        tbl_cap.set(w_val, title)

        if cap_par is None:
            cap_par = _make_empty_para(ns, "TableCaption")
        else:
            # Remove nearby old caption paragraphs (both above and below) to avoid duplicates.
            remove_idx = [x for x in [prev_cap_idx, next_cap_idx] if x is not None]
            for idx in sorted(set(remove_idx), reverse=True):
                try:
                    body.remove(children[idx])
                except ValueError:
                    pass
            children = list(body)
            tbl_idx = children.index(tbl)

        _set_p_style(ns, cap_par, "TableCaption")
        _set_para_center(ns, cap_par)
        _set_para_keep_lines(ns, cap_par)
        _set_paragraph_text(ns, cap_par, f"{table_prefix} {title}")
        body.insert(tbl_idx + 1, cap_par)

        children = list(body)
        i = children.index(tbl) + 2


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
    m_uri = None
    for k, v in ns.items():
        if k == "m":
            m_uri = v
            break
    if not m_uri:
        return
    m_oMathPara = f"{{{m_uri}}}oMathPara"
    m_oMath = f"{{{m_uri}}}oMath"

    text_w = _sect_text_width_dxa(ns, root)
    if text_w is None or text_w == 0:
        # Fallback to A4 template expected content width if section props are missing.
        # A4 11907, margins left 1417 right 1134 => 9356
        text_w = 9356

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    chapter_no = 0
    eq_no = 0

    children = list(body)
    def is_display_math_para(p: ET.Element) -> bool:
        if p.tag != w_p:
            return False
        if p.find(m_oMathPara) is not None:
            return True
        # Some pandoc runs emit OMML as <m:oMath> directly in the paragraph; only treat it
        # as display math if the paragraph has no visible text runs.
        if p.find(m_oMath) is not None and not _p_text(ns, p).strip():
            return True
        return False

    math_paras = [p for p in children if is_display_math_para(p)]

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

    def _ensure_display_math_para_centered(p: ET.Element) -> None:
        # Display math must be standalone and centered. We implement this via a leading tab
        # to a centered tab stop, keeping the equation number aligned with a right tab stop.
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # Insert a leading tab run (idempotent) so the math starts at the center tab stop.
        children2 = list(p)
        insert_idx = 0
        if children2 and children2[0].tag == _qn(ns, "w", "pPr"):
            insert_idx = 1

        has_leading_tab = False
        for el in children2[insert_idx:]:
            # first content element decides; if it isn't a run tab, we will add one
            if el.tag == _qn(ns, "w", "r"):
                if el.find(_qn(ns, "w", "tab")) is not None:
                    has_leading_tab = True
                break
            # If math comes first, we still want a leading tab.
            break

        if not has_leading_tab:
            p.insert(insert_idx, _make_run_tab(ns))

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

        if not is_display_math_para(p):
            continue

        # Consume numbering flag for each display math paragraph to keep alignment stable.
        num_flag = should_number()

        # Always center display equations and keep them standalone.
        _ensure_display_math_para_centered(p)

        if chapter_no <= 0:
            continue

        if not num_flag:
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
        table_style_id = _first_table_style_id(styles_xml) if styles_xml else None

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
        _apply_three_line_tables(doc_ns, root, body, table_style_id)
        _ensure_indent_for_body_paragraphs(doc_ns, body)
        _ensure_hanging_indent_for_bibliography(doc_ns, body)
        _fix_figure_captions(doc_ns, body)
        _fix_ref_dot_to_hyphen(doc_ns, body)
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
