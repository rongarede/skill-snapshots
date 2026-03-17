#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图表标题+三线表模块。"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    from utils.ooxml import (
        qn,
        p_text,
        p_style,
        ensure_ppr,
        block_has_drawing,
        is_centered_paragraph,
        set_para_center,
        set_para_keep_next,
        set_para_keep_lines,
        make_run_text,
        set_p_style,
        set_paragraph_text,
        make_empty_para,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import (
        qn,
        p_text,
        p_style,
        ensure_ppr,
        block_has_drawing,
        is_centered_paragraph,
        set_para_center,
        set_para_keep_next,
        set_para_keep_lines,
        make_run_text,
        set_p_style,
        set_paragraph_text,
        make_empty_para,
    )

try:
    from modules.caption_profile import build_caption_paragraph, CaptionFormatProfile, extract_caption_profiles
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.modules.caption_profile import build_caption_paragraph, CaptionFormatProfile, extract_caption_profiles

try:
    from modules.equation_handler import make_equation_number_run, sect_text_width_dxa
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.modules.equation_handler import make_equation_number_run, sect_text_width_dxa

CAPTION_PROFILE_DOCX = Path(
    os.environ.get(
        "SWUN_CAPTION_PROFILE_DOCX",
        "/Users/bit/LaTeX/SWUN_Thesis/网络与信息安全_高春琴.docx",
    )
).expanduser()

_DEFAULT_CAPTION_PROFILES: dict[str, CaptionFormatProfile] | None = None
W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def load_caption_profiles(profile_docx: Path) -> dict[str, CaptionFormatProfile]:
    try:
        return extract_caption_profiles(profile_docx)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"missing caption profile source: {profile_docx} "
            "(override with SWUN_CAPTION_PROFILE_DOCX)"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"failed to extract caption profile from {profile_docx}: {exc}"
        ) from exc


def default_caption_profiles() -> dict[str, CaptionFormatProfile]:
    global _DEFAULT_CAPTION_PROFILES  # noqa: PLW0603
    if _DEFAULT_CAPTION_PROFILES is None:
        _DEFAULT_CAPTION_PROFILES = load_caption_profiles(CAPTION_PROFILE_DOCX)
    return _DEFAULT_CAPTION_PROFILES


def infer_caption_kind(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith(("表", "Table")):
        return "table"
    return "figure"


def fix_figure_captions(ns: dict[str, str], body: ET.Element) -> None:
    """Prefix figure captions with chapter-based numbering and center-align."""
    w_p = qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}

    chapter_no = 0
    fig_no = 0

    children = list(body)
    to_remove: list[ET.Element] = []

    for el in children:
        if el.tag != w_p:
            continue
        style = p_style(ns, el)
        txt = p_text(ns, el).strip()

        if style == "1":
            title = txt
            if title and title not in excluded_h1:
                chapter_no += 1
                fig_no = 0
            continue

        if style == "CaptionedFigure" or block_has_drawing(ns, el):
            set_para_center(ns, el)
            # Keep caption together with the figure.
            set_para_keep_next(ns, el)
            set_para_keep_lines(ns, el)
            continue

        # Fallback for caption-like paragraphs that already carry figure numbering
        # but are not mapped to the expected ImageCaption style by pandoc/template mapping.
        m_prefixed = re.match(r"^图[\s\u00a0]*(\d+)[\-\.．](\d+)\s*(.*)$", txt)
        if m_prefixed:
            chap = m_prefixed.group(1)
            seq = m_prefixed.group(2)
            title = (m_prefixed.group(3) or "").strip()
            new_txt = f"图{chap}-{seq}" + (f" {title}" if title else "")
            set_para_center(ns, el)
            set_para_keep_lines(ns, el)
            for hl in list(el.findall(qn(ns, "w", "hyperlink"))):
                el.remove(hl)
            set_paragraph_text(ns, el, new_txt)
            continue

        if style != "ImageCaption":
            continue

        if not txt:
            # Pandoc sometimes generates empty caption paragraphs; remove them.
            to_remove.append(el)
            continue

        # If already numbered like "图2-1 ..." then keep.
        if re.match(r"^图\\s*\\d+[-\\.]\\d+\\s*", txt):
            set_para_center(ns, el)
            continue

        if chapter_no <= 0:
            # Before first real chapter: skip numbering.
            set_para_center(ns, el)
            continue

        fig_no += 1
        new_txt = f"图{chapter_no}-{fig_no} {txt}"

        set_para_center(ns, el)
        set_para_keep_lines(ns, el)
        set_paragraph_text(ns, el, new_txt)

    for el in to_remove:
        try:
            body.remove(el)
        except ValueError:
            pass

def inject_captions_from_meta(
    ns: dict[str, str],
    body: ET.Element,
    caption_meta: dict[str, Any],
    caption_profiles: dict[str, CaptionFormatProfile],
) -> None:
    placements, chapter_by_index = collect_anchor_block_positions(ns, body)
    if not placements:
        return

    errors: list[str] = []
    numbered: list[tuple[str, str, int, int, int, Any]] = []
    counters: dict[tuple[int, str], int] = {}

    for kind, label, block_idx in placements:
        chapter_no = chapter_by_index.get(block_idx)
        if not chapter_no:
            continue
        meta = caption_meta.get(label)
        if meta is None:
            errors.append(f"missing caption metadata for anchor '{label}'")
            continue
        if meta.kind != kind:
            errors.append(
                f"anchor kind mismatch for '{label}': anchor={kind}, latex_meta={meta.kind}"
            )
            continue
        key = (chapter_no, kind)
        seq = counters.get(key, 0) + 1
        counters[key] = seq
        numbered.append((kind, label, block_idx, chapter_no, seq, meta))

    if errors:
        msg = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError("DOCX build blocked: cannot map figure/table anchors to caption metadata:\n" + msg)

    for kind, label, block_idx, chapter_no, seq, meta in reversed(numbered):
        children = list(body)
        if block_idx < 0 or block_idx >= len(children):
            continue
        block = children[block_idx]
        cn_title = normalize_caption_title(meta.cn_title, kind, "cn")
        en_title = normalize_caption_title(meta.en_title or "", kind, "en")
        if meta.source == "bilingualcaption" and not en_title:
            raise RuntimeError(
                "DOCX build blocked: bilingual caption is missing English line after normalization "
                f"(label='{label}')"
            )

        if kind == "figure":
            cn_line = f"图{chapter_no}-{seq}" + (f" {cn_title}" if cn_title else "")
            en_line = (
                f"Figure {chapter_no}-{seq}" + (f" {en_title}" if en_title else "")
                if meta.source == "bilingualcaption"
                else ""
            )
            lines = [cn_line] + ([en_line] if en_line else [])
            profile = caption_profiles["figure"]
            style = profile.style
            insert_after = True
        else:
            cn_line = f"表{chapter_no}-{seq}" + (f" {cn_title}" if cn_title else "")
            en_line = (
                f"Table {chapter_no}-{seq}" + (f" {en_title}" if en_title else "")
                if meta.source == "bilingualcaption"
                else ""
            )
            lines = [cn_line] + ([en_line] if en_line else [])
            profile = caption_profiles["table"]
            style = profile.style
            insert_after = False
            if block.tag == qn(ns, "w", "tbl"):
                set_tbl_caption_value(ns, block, cn_title)

        remove_adjacent_caption_paragraphs(ns, body, block_idx, kind)
        children = list(body)
        block_idx = children.index(block)

        if insert_after:
            caption_paras: list[ET.Element] = []
            for i, line in enumerate(lines):
                caption_paras.append(
                    make_caption_para(
                        ns,
                        style,
                        line,
                        keep_next=(i < len(lines) - 1),
                        profile=profile,
                    )
                )
            if is_figure_table_block(ns, block):
                wrap_figure_with_captions(ns, body, block_idx, block, caption_paras)
            else:
                pos = block_idx + 1
                for para in caption_paras:
                    body.insert(pos, para)
                    pos += 1
        else:
            for i, line in enumerate(reversed(lines)):
                keep_next = True  # caption above table should stay with following lines/table
                para = make_caption_para(ns, style, line, keep_next=keep_next, profile=profile)
                body.insert(block_idx, para)

def wrap_figure_with_captions(
    ns: dict[str, str],
    body: ET.Element,
    block_idx: int,
    figure_block: ET.Element,
    caption_paragraphs: list[ET.Element],
) -> None:
    """Replace body-level figure+caption siblings with a single wrapper table."""
    wrapper = build_figure_caption_wrapper(ns, figure_block, caption_paragraphs)
    body.remove(figure_block)
    body.insert(block_idx, wrapper)

def build_figure_caption_wrapper(
    ns: dict[str, str],
    figure_block: ET.Element,
    caption_paragraphs: list[ET.Element],
) -> ET.Element:
    """Wrap a figure block plus its caption lines into one non-splittable outer table."""
    w_tbl = qn(ns, "w", "tbl")
    w_tblPr = qn(ns, "w", "tblPr")
    w_tblW = qn(ns, "w", "tblW")
    w_tblLayout = qn(ns, "w", "tblLayout")
    w_jc = qn(ns, "w", "jc")
    w_tblGrid = qn(ns, "w", "tblGrid")
    w_gridCol = qn(ns, "w", "gridCol")
    w_tr = qn(ns, "w", "tr")
    w_tc = qn(ns, "w", "tc")
    w_tcPr = qn(ns, "w", "tcPr")
    w_tcW = qn(ns, "w", "tcW")
    w_tblBorders = qn(ns, "w", "tblBorders")
    w_val = qn(ns, "w", "val")
    w_type = qn(ns, "w", "type")
    w_w = qn(ns, "w", "w")

    width = table_width_dxa(ns, figure_block) or 8640
    width_str = str(width)

    outer = ET.Element(w_tbl)
    tblPr = ET.SubElement(outer, w_tblPr)
    tblW = ET.SubElement(tblPr, w_tblW)
    tblW.set(w_type, "dxa")
    tblW.set(w_w, width_str)
    layout = ET.SubElement(tblPr, w_tblLayout)
    layout.set(w_type, "fixed")
    jc = ET.SubElement(tblPr, w_jc)
    jc.set(w_val, "center")
    borders = ET.SubElement(tblPr, w_tblBorders)
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        edge = ET.SubElement(borders, qn(ns, "w", side))
        edge.set(w_val, "nil")

    grid = ET.SubElement(outer, w_tblGrid)
    col = ET.SubElement(grid, w_gridCol)
    col.set(w_w, width_str)

    tr = ET.SubElement(outer, w_tr)
    set_row_cant_split(ns, tr)
    tc = ET.SubElement(tr, w_tc)
    tcPr = ET.SubElement(tc, w_tcPr)
    tcW = ET.SubElement(tcPr, w_tcW)
    tcW.set(w_type, "dxa")
    tcW.set(w_w, width_str)

    tc.append(figure_block)
    for para in caption_paragraphs:
        tc.append(para)
    return outer

def make_caption_para(
    ns: dict[str, str],
    style: str | None,
    text: str,
    keep_next: bool,
    profile: CaptionFormatProfile | None = None,
) -> ET.Element:
    """Build a caption paragraph from the reference-derived profile."""
    _ = style  # legacy argument kept for compatibility with existing call sites/tests
    profile = profile or default_caption_profiles()[infer_caption_kind(text)]
    return build_caption_paragraph(ns, text, profile, keep_next=keep_next)

def make_caption_run(
    ns: dict[str, str], text: str, profile: CaptionFormatProfile | None = None
) -> ET.Element:
    """Create a caption run using the reference-derived profile."""
    profile = profile or default_caption_profiles()[infer_caption_kind(text)]
    paragraph = build_caption_paragraph(ns, text, profile, keep_next=False)
    run = paragraph.find(qn(ns, "w", "r"))
    if run is None:
        raise RuntimeError("caption profile application failed to create a run")
    return run

def main_body_context(
    ns: dict[str, str], body: ET.Element
) -> tuple[list[ET.Element], int, int, dict[int, int]]:
    """Return body children, main-body [start,end), and block-index -> chapter number."""
    w_p = qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    children = list(body)
    in_main_body = False
    chapter_no = 0
    chapter_by_index: dict[int, int] = {}
    start = 0
    end = len(children)
    started = False

    for i, el in enumerate(children):
        if el.tag == w_p and p_style(ns, el) == "1":
            txt = p_text(ns, el).strip()
            if txt in stop_h1:
                if in_main_body and end == len(children):
                    end = i
                in_main_body = False
            elif txt and txt not in excluded_h1:
                if not started:
                    start = i
                    started = True
                in_main_body = True
                chapter_no += 1

        if in_main_body:
            chapter_by_index[i] = chapter_no

    if not started:
        start = 0
        end = 0
    return children, start, end, chapter_by_index

def iter_anchor_names_in_element(ns: dict[str, str], el: ET.Element) -> list[str]:
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_name = qn(ns, "w", "name")
    out: list[str] = []
    seen: set[str] = set()
    for bm in el.iter(w_bookmarkStart):
        name = (bm.get(w_name) or bm.get("name") or "").strip()
        if not name or name in seen:
            continue
        if not name.startswith(("fig:", "tab:", "tbl:")):
            continue
        seen.add(name)
        out.append(name)
    return out

def find_next_anchor_target_block(
    ns: dict[str, str], children: list[ET.Element], start_idx: int, end_idx: int, kind: str
) -> int | None:
    w_p = qn(ns, "w", "p")
    w_tbl = qn(ns, "w", "tbl")
    fallback: int | None = None
    for j in range(start_idx, end_idx):
        el = children[j]
        if el.tag == w_tbl:
            has_draw = block_has_drawing(ns, el)
            if kind == "figure":
                return j
            if kind == "table" and not has_draw:
                return j
            if fallback is None:
                fallback = j
            continue
        if el.tag == w_p and kind == "figure" and block_has_drawing(ns, el):
            return j
    return fallback

def collect_anchor_block_positions(
    ns: dict[str, str], body: ET.Element
) -> tuple[list[tuple[str, str, int]], dict[int, int]]:
    """Collect (kind, label, block_idx) for main-body fig/tab/tbl anchors."""
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_name = qn(ns, "w", "name")
    w_p = qn(ns, "w", "p")
    w_tbl = qn(ns, "w", "tbl")

    children, start, end, chapter_by_index = main_body_context(ns, body)
    if end <= start:
        return [], chapter_by_index

    best: dict[str, tuple[int, int]] = {}

    def kind_of(label: str) -> str:
        return "figure" if label.startswith("fig:") else "table"

    def score(kind: str, block: ET.Element, from_inline: bool) -> int:
        s = 2 if from_inline else 1
        has_draw = block_has_drawing(ns, block)
        if kind == "figure":
            if has_draw:
                s += 4
            if block.tag == w_tbl:
                s += 1
        else:
            if block.tag == w_tbl:
                s += 4
            if has_draw:
                s -= 2
        return s

    for i in range(start, end):
        el = children[i]
        if el.tag not in {w_p, w_tbl}:
            continue
        for label in iter_anchor_names_in_element(ns, el):
            k = kind_of(label)
            if k == "table" and el.tag != w_tbl:
                continue
            if k == "figure" and not block_has_drawing(ns, el) and el.tag != w_tbl:
                continue
            cand = (score(k, el, True), i)
            prev = best.get(label)
            if prev is None or cand[0] > prev[0]:
                best[label] = cand

    for i in range(start, end):
        el = children[i]
        if el.tag != w_bookmarkStart:
            continue
        label = (el.get(w_name) or el.get("name") or "").strip()
        if not label.startswith(("fig:", "tab:", "tbl:")):
            continue
        k = kind_of(label)
        j = find_next_anchor_target_block(ns, children, i + 1, end, k)
        if j is None:
            continue
        block = children[j]
        cand = (score(k, block, False), j)
        prev = best.get(label)
        if prev is None or cand[0] > prev[0]:
            best[label] = cand

    placements: list[tuple[str, str, int]] = []
    for label, (_score, idx) in best.items():
        placements.append((kind_of(label), label, idx))
    placements.sort(key=lambda x: (x[2], x[1]))
    return placements, chapter_by_index

def dedupe_body_level_anchor_bookmarks(ns: dict[str, str], body: ET.Element) -> int:
    """Remove duplicate top-level fig/tab/tbl bookmarks when the same anchor exists inside a block.

    Pandoc may emit two bookmarks for the same LaTeX label:
    1. a body-level ``w:bookmarkStart``/``w:bookmarkEnd`` pair around the figure/table block
    2. an inline bookmark nested inside the actual drawing/table block

    Word is stricter about duplicate bookmark names than LibreOffice, so keep the
    block-local bookmark and remove the top-level duplicate pair.
    """
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_bookmarkEnd = qn(ns, "w", "bookmarkEnd")
    w_name = qn(ns, "w", "name")
    w_id = qn(ns, "w", "id")
    prefixes = ("fig:", "tab:", "tbl:")

    children = list(body)
    nested_names: set[str] = set()
    for el in children:
        if el.tag in {w_bookmarkStart, w_bookmarkEnd}:
            continue
        for bm in el.iter(w_bookmarkStart):
            name = (bm.get(w_name) or bm.get("name") or "").strip()
            if name.startswith(prefixes):
                nested_names.add(name)

    remove_ids: set[str] = set()
    remove_nodes: list[ET.Element] = []
    for el in children:
        if el.tag != w_bookmarkStart:
            continue
        name = (el.get(w_name) or el.get("name") or "").strip()
        if not name.startswith(prefixes):
            continue
        if name not in nested_names:
            continue
        bid = el.get(w_id) or el.get("id") or ""
        if not bid:
            continue
        remove_ids.add(bid)
        remove_nodes.append(el)

    if not remove_ids:
        return 0

    for el in children:
        if el.tag != w_bookmarkEnd:
            continue
        bid = el.get(w_id) or el.get("id") or ""
        if bid in remove_ids:
            remove_nodes.append(el)

    removed = 0
    for el in remove_nodes:
        try:
            body.remove(el)
            removed += 1
        except ValueError:
            pass
    return removed

def clean_table_title(txt: str) -> str:
    s = (txt or "").strip()
    s = re.sub(r"^表[\s\xa0]*\d+(?:[\-\.．]\d+)?[\s\xa0:：、.]*", "", s)
    return s.strip()

def is_table_caption_para(ns: dict[str, str], p: ET.Element) -> bool:
    style = p_style(ns, p)
    txt = p_text(ns, p).strip()
    if style == "TableCaption":
        return True
    return bool(re.match(r"^(表[\s\xa0]*\d+(?:[\-\.．]\d+)?|Table\s+\d+[\-\.－]\d+)", txt, re.IGNORECASE))

def find_caption_idx_near_table(
    ns: dict[str, str], children: list[ET.Element], tbl_idx: int, direction: int
) -> int | None:
    w_p = qn(ns, "w", "p")
    step = -1 if direction < 0 else 1
    rng = range(tbl_idx + step, -1, -1) if step < 0 else range(tbl_idx + 1, len(children))
    checked = 0
    for j in rng:
        el = children[j]
        if el.tag != w_p:
            continue
        txt = p_text(ns, el).strip()
        if not txt:
            continue
        checked += 1
        if is_table_caption_para(ns, el):
            return j
        # Stop at first non-caption paragraph near the table.
        if checked >= 1:
            break
    return None

def is_caption_paragraph_near_block(ns: dict[str, str], p: ET.Element, kind: str) -> bool:
    txt = p_text(ns, p).strip()
    if not txt:
        return False
    style = p_style(ns, p) or ""
    if kind == "figure":
        if style in {"ImageCaption", "CaptionedFigure"}:
            return True
        if not is_centered_paragraph(ns, p):
            return False
        return bool(re.match(r"^(图\s*\d+[\-\.．]\d+|Figure\s+\d+[\-\.．]\d+)\b", txt, flags=re.IGNORECASE))
    if style == "TableCaption":
        return True
    if not is_centered_paragraph(ns, p):
        return False
    return bool(re.match(r"^(表\s*\d+[\-\.．]\d+|Table\s+\d+[\-\.．]\d+)\b", txt, flags=re.IGNORECASE))

def remove_adjacent_caption_paragraphs(ns: dict[str, str], body: ET.Element, block_idx: int, kind: str) -> None:
    w_p = qn(ns, "w", "p")
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_bookmarkEnd = qn(ns, "w", "bookmarkEnd")

    children = list(body)
    remove: set[int] = set()

    for step in (-1, 1):
        j = block_idx + step
        while 0 <= j < len(children):
            el = children[j]
            if el.tag in {w_bookmarkStart, w_bookmarkEnd}:
                j += step
                continue
            if el.tag != w_p:
                break
            txt = p_text(ns, el).strip()
            if not txt:
                if remove:
                    remove.add(j)
                    j += step
                    continue
                break
            if is_caption_paragraph_near_block(ns, el, kind):
                remove.add(j)
                j += step
                continue
            break

    for idx in sorted(remove, reverse=True):
        try:
            body.remove(children[idx])
        except ValueError:
            pass

def strip_latex_escapes_for_docx(s: str) -> str:
    """移除 caption 文本中的 LaTeX 转义符号，使其适合 DOCX 纯文本显示。"""
    # $n=25$ → n=25（去掉数学模式定界符）
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    # \% → %，\& → &，\_ → _，\# → #
    s = re.sub(r"\\([%&_#])", r"\1", s)
    # \textbf{...} → ...，\textit{...} → ...
    s = re.sub(r"\\text(?:bf|it|rm|tt)\{([^}]*)\}", r"\1", s)
    return s

def normalize_caption_title(title: str, kind: str, lang: str) -> str:
    s = re.sub(r"\s+", " ", (title or "").strip())
    if not s:
        return s
    # 移除 LaTeX 转义符号
    s = strip_latex_escapes_for_docx(s)
    if kind == "figure" and lang == "cn":
        s = re.sub(r"^图\s*\d+[\-\.．]\d+\s*", "", s)
    elif kind == "figure" and lang == "en":
        s = re.sub(r"^Figure\s+\d+[\-\.．]\d+\s*", "", s, flags=re.IGNORECASE)
    elif kind == "table" and lang == "cn":
        s = re.sub(r"^表\s*\d+[\-\.．]\d+\s*", "", s)
    else:
        s = re.sub(r"^Table\s+\d+[\-\.．]\d+\s*", "", s, flags=re.IGNORECASE)
    return s.strip()

def set_tbl_caption_value(ns: dict[str, str], tbl: ET.Element, cn_title: str) -> None:
    w_tblCaption = qn(ns, "w", "tblCaption")
    w_val = qn(ns, "w", "val")
    pr = ensure_tbl_pr(ns, tbl)
    cap = pr.find(w_tblCaption)
    if cap is None:
        cap = ET.SubElement(pr, w_tblCaption)
    cap.set(w_val, cn_title)

def apply_three_line_tables(
    ns: dict[str, str], root: ET.Element, body: ET.Element, table_style_id: str | None,
    latex_col_ratios: dict[str, list[float]] | None = None,
) -> None:
    """
    Enforce three-line tables and normalize table layout:
    - table top + bottom border
    - header separator line (bottom border of last header row)
    - no vertical borders and no inner horizontal borders for body rows
    - table width fills full text width; column widths are redistributed by content
      (or by LaTeX source ratios when available)
    """
    w_tbl = qn(ns, "w", "tbl")
    w_tblPr = qn(ns, "w", "tblPr")
    w_tblStyle = qn(ns, "w", "tblStyle")
    w_tr = qn(ns, "w", "tr")
    w_trPr = qn(ns, "w", "trPr")
    w_tblHeader = qn(ns, "w", "tblHeader")
    w_tc = qn(ns, "w", "tc")
    w_tcPr = qn(ns, "w", "tcPr")
    w_tcBorders = qn(ns, "w", "tcBorders")
    w_tblBorders = qn(ns, "w", "tblBorders")
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")
    w_rPr = qn(ns, "w", "rPr")
    w_rFonts = qn(ns, "w", "rFonts")
    w_ascii = qn(ns, "w", "ascii")
    w_hAnsi = qn(ns, "w", "hAnsi")
    w_eastAsia = qn(ns, "w", "eastAsia")
    w_sz = qn(ns, "w", "sz")
    w_szCs = qn(ns, "w", "szCs")
    w_val = qn(ns, "w", "val")

    # Word border size unit is 1/8 pt. Template examples use w:sz="6" (0.75pt).
    rule_sz = "6"
    table_run_sz = "21"  # 五号 10.5pt in half-points
    text_w = sect_text_width_dxa(ns, root) or 9356

    # 预构建 tbl body index → [labels] 映射，用于匹配 LaTeX 列宽比例
    tbl_label_map = build_tbl_label_map(ns, body) if latex_col_ratios else {}

    i = 0
    children = list(body)
    while i < len(children):
        el = children[i]
        if el.tag != w_tbl:
            i += 1
            continue

        tbl = el
        if not is_data_table(ns, tbl):
            i += 1
            continue

        pr = tbl.find(w_tblPr)
        if pr is None:
            i += 1
            continue

        st = pr.find(w_tblStyle)
        st_val = st.get(w_val) if st is not None else None
        pr = ensure_tbl_pr(ns, tbl)

        # Make tblStyle valid (pandoc sometimes emits an undefined styleId like "Table").
        if table_style_id and (st_val in (None, "", "Table")):
            if st is None:
                st = ET.SubElement(pr, w_tblStyle)
            st.set(w_val, table_style_id)

        # 通过预构建映射查找表格 label，匹配 LaTeX 列宽比例
        matched_ratios: list[float] | None = None
        if latex_col_ratios and tbl_label_map:
            tbl_idx = children.index(tbl)
            for label in tbl_label_map.get(tbl_idx, []):
                if label in latex_col_ratios:
                    matched_ratios = latex_col_ratios[label]
                    break

        set_table_full_width_and_columns(ns, tbl, text_w, col_ratios=matched_ratios)

        # Remove any existing cell borders to avoid unwanted gridlines.
        for tc in tbl.iter(w_tc):
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                continue
            tcBorders = tcPr.find(w_tcBorders)
            if tcBorders is not None:
                tcPr.remove(tcBorders)
            # Restrict font-size normalization to text runs inside data-table cells.
            for r in tc.iter(w_r):
                if r.find(w_t) is None:
                    continue
                rPr = r.find(w_rPr)
                if rPr is None:
                    rPr = ET.SubElement(r, w_rPr)
                rFonts = rPr.find(w_rFonts)
                if rFonts is None:
                    rFonts = ET.SubElement(rPr, w_rFonts)
                rFonts.set(w_ascii, "Times New Roman")
                rFonts.set(w_hAnsi, "Times New Roman")
                rFonts.set(w_eastAsia, "宋体")
                # 清除 theme 字体属性，防止主题覆盖显式字体
                for theme_attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                    attr_qn = qn(ns, "w", theme_attr)
                    if attr_qn in rFonts.attrib:
                        del rFonts.attrib[attr_qn]
                sz = rPr.find(w_sz)
                if sz is None:
                    sz = ET.SubElement(rPr, w_sz)
                sz.set(w_val, table_run_sz)
                szCs = rPr.find(w_szCs)
                if szCs is None:
                    szCs = ET.SubElement(rPr, w_szCs)
                szCs.set(w_val, table_run_sz)

        # Table-level borders: only top and bottom.
        borders = pr.find(w_tblBorders)
        if borders is not None:
            pr.remove(borders)
        borders = ET.SubElement(pr, w_tblBorders)
        set_border_el(ns, borders, "top", "single", rule_sz)
        set_border_el(ns, borders, "bottom", "single", rule_sz)
        set_border_el(ns, borders, "left", "nil", rule_sz)
        set_border_el(ns, borders, "right", "nil", rule_sz)
        set_border_el(ns, borders, "insideH", "nil", rule_sz)
        set_border_el(ns, borders, "insideV", "nil", rule_sz)

        # Header separator: bottom border of the last header row at the top of table.
        trs = tbl.findall(w_tr)
        if not trs:
            i += 1
            continue

        header_end = None
        for tr_idx, tr in enumerate(trs):
            trPr = tr.find(w_trPr)
            if trPr is not None and trPr.find(w_tblHeader) is not None:
                header_end = tr_idx
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
            set_border_el(ns, tcBorders, "bottom", "single", rule_sz)
        children = list(body)
        i = children.index(tbl) + 1

def first_table_style_id(styles_xml: bytes) -> str | None:
    q_style = f"{{{W_URI}}}style"
    q_type = f"{{{W_URI}}}type"
    q_styleId = f"{{{W_URI}}}styleId"
    root = ET.fromstring(styles_xml)
    for st in root.findall(q_style):
        if st.get(q_type) != "table":
            continue
        sid = st.get(q_styleId)
        if sid:
            return sid
    return None

def ensure_tbl_pr(ns: dict[str, str], tbl: ET.Element) -> ET.Element:
    w_tblPr = qn(ns, "w", "tblPr")
    pr = tbl.find(w_tblPr)
    if pr is None:
        pr = ET.Element(w_tblPr)
        tbl.insert(0, pr)
    return pr

def set_border_el(ns: dict[str, str], parent: ET.Element, edge: str, val: str, sz: str) -> None:
    w_val = qn(ns, "w", "val")
    w_sz = qn(ns, "w", "sz")
    w_space = qn(ns, "w", "space")
    w_color = qn(ns, "w", "color")
    el = parent.find(qn(ns, "w", edge))
    if el is None:
        el = ET.SubElement(parent, qn(ns, "w", edge))
    el.attrib.clear()
    el.set(w_val, val)
    if val != "nil":
        el.set(w_sz, sz)
        el.set(w_space, "0")
        el.set(w_color, "auto")

def is_data_table(ns: dict[str, str], tbl: ET.Element) -> bool:
    w_tblPr = qn(ns, "w", "tblPr")
    w_tblStyle = qn(ns, "w", "tblStyle")
    w_tblCaption = qn(ns, "w", "tblCaption")
    w_val = qn(ns, "w", "val")

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

def visual_text_len(s: str) -> int:
    n = 0
    for ch in s:
        if ch.isspace():
            continue
        n += 1 if ord(ch) < 128 else 2
    return n

def table_col_count(ns: dict[str, str], tbl: ET.Element) -> int:
    w_tblGrid = qn(ns, "w", "tblGrid")
    w_gridCol = qn(ns, "w", "gridCol")
    w_tr = qn(ns, "w", "tr")
    w_tc = qn(ns, "w", "tc")
    w_tcPr = qn(ns, "w", "tcPr")
    w_gridSpan = qn(ns, "w", "gridSpan")
    w_val = qn(ns, "w", "val")

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

def table_col_weights(ns: dict[str, str], tbl: ET.Element, ncols: int) -> list[int]:
    w_tr = qn(ns, "w", "tr")
    w_tc = qn(ns, "w", "tc")
    w_tcPr = qn(ns, "w", "tcPr")
    w_gridSpan = qn(ns, "w", "gridSpan")
    w_val = qn(ns, "w", "val")
    w_t = qn(ns, "w", "t")

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
            score = max(1, visual_text_len(txt))
            per_col = max(1, int(round(score / max(1, span))))
            for k in range(span):
                idx = col + k
                if idx >= ncols:
                    break
                weights[idx] = max(weights[idx], per_col)
            col += span
    return weights

def normalize_widths_to_total(weights: list[int], total_w: int) -> list[int]:
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

def apply_latex_col_ratios(
    ns: dict[str, str], tbl: ET.Element, ncols: int,
    col_ratios: list[float], total_w: int,
) -> list[int]:
    """根据 LaTeX 列宽比例计算 DOCX 列宽（dxa 单位）。

    col_ratios 约定：
    - >0：显式比例（p{0.22\\linewidth}）
    - -1.0：tabularX X 列（等分剩余宽度）
    - 0.0：混合表中的自动列（l/c/r），用文本推算
    """
    has_auto = any(r == 0.0 for r in col_ratios)
    has_x = any(r < 0 for r in col_ratios)

    if not has_auto and not has_x:
        # 纯显式比例 → 归一化后直接分配
        total_r = sum(col_ratios)
        if total_r <= 0:
            return normalize_widths_to_total(
                table_col_weights(ns, tbl, ncols), total_w
            )
        raw = [int(round(r / total_r * total_w)) for r in col_ratios]
        # 修正舍入误差
        diff = total_w - sum(raw)
        if diff != 0 and raw:
            idx = max(range(len(raw)), key=lambda i: col_ratios[i])
            raw[idx] += diff
        return raw

    # 混合模式：自动列用文本推算，X 列等分剩余
    weights = table_col_weights(ns, tbl, ncols)

    # 显式列占用的宽度
    explicit_indices = [i for i, r in enumerate(col_ratios) if r > 0]
    auto_indices = [i for i, r in enumerate(col_ratios) if r == 0.0]
    x_indices = [i for i, r in enumerate(col_ratios) if r < 0]

    explicit_ratio_sum = sum(col_ratios[i] for i in explicit_indices)
    explicit_w = int(round(explicit_ratio_sum * total_w)) if explicit_indices else 0

    # 自动列：按文本权重在剩余空间中分配一个合理份额
    remaining_for_flex = total_w - explicit_w
    auto_weight_sum = sum(weights[i] for i in auto_indices) if auto_indices else 0
    x_count = len(x_indices)

    if auto_indices and x_count > 0:
        # 自动列和 X 列共享剩余空间
        # 自动列按文本权重占比，但不超过剩余空间的 40%
        total_flex_weight = auto_weight_sum + sum(weights[i] for i in x_indices)
        auto_share = auto_weight_sum / max(1, total_flex_weight)
        auto_share = min(auto_share, 0.4)
        auto_w = int(round(remaining_for_flex * auto_share))
        x_total_w = remaining_for_flex - auto_w
    elif auto_indices:
        auto_w = remaining_for_flex
        x_total_w = 0
    else:
        auto_w = 0
        x_total_w = remaining_for_flex

    widths = [0] * ncols
    for i in explicit_indices:
        widths[i] = int(round(col_ratios[i] * total_w))
    if auto_indices and auto_weight_sum > 0:
        for i in auto_indices:
            widths[i] = max(240, int(round(auto_w * weights[i] / auto_weight_sum)))
    elif auto_indices:
        per = auto_w // len(auto_indices)
        for i in auto_indices:
            widths[i] = max(240, per)
    if x_count > 0:
        per_x = x_total_w // x_count
        for i in x_indices:
            widths[i] = max(240, per_x)

    # 修正舍入误差
    diff = total_w - sum(widths)
    if diff != 0 and widths:
        idx = max(range(ncols), key=lambda i: widths[i])
        widths[idx] = max(240, widths[idx] + diff)

    return widths

def set_table_full_width_and_columns(
    ns: dict[str, str], tbl: ET.Element, text_w: int,
    col_ratios: list[float] | None = None,
) -> None:
    w_tblPr = qn(ns, "w", "tblPr")
    w_tblW = qn(ns, "w", "tblW")
    w_tblLayout = qn(ns, "w", "tblLayout")
    w_tblGrid = qn(ns, "w", "tblGrid")
    w_gridCol = qn(ns, "w", "gridCol")
    w_tr = qn(ns, "w", "tr")
    w_tc = qn(ns, "w", "tc")
    w_tcPr = qn(ns, "w", "tcPr")
    w_tcW = qn(ns, "w", "tcW")
    w_gridSpan = qn(ns, "w", "gridSpan")
    w_type = qn(ns, "w", "type")
    w_val = qn(ns, "w", "val")
    w_w = qn(ns, "w", "w")

    ncols = table_col_count(ns, tbl)
    if ncols <= 0:
        return

    # 优先使用 LaTeX 源码中的显式列宽比例
    if col_ratios is not None and len(col_ratios) == ncols:
        widths = apply_latex_col_ratios(ns, tbl, ncols, col_ratios, text_w)
    else:
        weights = table_col_weights(ns, tbl, ncols)
        widths = normalize_widths_to_total(weights, text_w)
    if not widths:
        return

    pr = ensure_tbl_pr(ns, tbl)
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

def fit_figure_images_to_cells(ns: dict[str, str], body: ET.Element) -> int:
    """缩放 FigureTable 单元格中超宽的 inline 图片，使其适配列宽。

    pandoc 将 LaTeX minipage 并排图转为 FigureTable（两列表格），但图片宽度
    按全局 textwidth 计算，导致 cx 超出列宽约 4%，Word 会裁剪右边缘。
    此函数读取每列的 gridCol 宽度（twip），将超宽图片等比缩放至列宽内。

    Returns the number of images scaled.
    """
    TWIP_TO_EMU = 635  # 914400 / 1440

    w_tbl = qn(ns, "w", "tbl")
    w_tblPr = qn(ns, "w", "tblPr")
    w_tblStyle = qn(ns, "w", "tblStyle")
    w_val = qn(ns, "w", "val")
    w_tblGrid = qn(ns, "w", "tblGrid")
    w_gridCol = qn(ns, "w", "gridCol")
    w_w = qn(ns, "w", "w")
    w_tr = qn(ns, "w", "tr")
    w_tc = qn(ns, "w", "tc")
    w_drawing = qn(ns, "w", "drawing")

    # wp (wordprocessingDrawing) namespace — look it up if present, else use
    # the well-known URI so the function still works even when the ns dict
    # was collected from a document that hasn't declared the prefix yet.
    wp_uri = ns.get("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing")
    wp_inline = f"{{{wp_uri}}}inline"
    wp_extent = f"{{{wp_uri}}}extent"

    # drawingml namespace for a:ext inside pic:spPr/a:xfrm
    a_uri = ns.get("a", "http://schemas.openxmlformats.org/drawingml/2006/main")
    a_ext_tag = f"{{{a_uri}}}ext"

    scaled = 0

    for tbl in body.findall(f".//{w_tbl}"):
        # 只处理 FigureTable
        tbl_pr = tbl.find(w_tblPr)
        if tbl_pr is None:
            continue
        style_el = tbl_pr.find(w_tblStyle)
        if style_el is None:
            continue
        if (style_el.get(w_val) or "").strip() != "FigureTable":
            continue

        # 获取 gridCol 宽度列表
        grid = tbl.find(w_tblGrid)
        if grid is None:
            continue
        grid_cols = grid.findall(w_gridCol)
        col_widths_twip: list[int] = []
        for gc in grid_cols:
            w_attr = gc.get(w_w)
            if w_attr:
                col_widths_twip.append(int(w_attr))

        if not col_widths_twip:
            continue

        # 遍历行和单元格
        for tr in tbl.findall(w_tr):
            cells = tr.findall(w_tc)
            for col_idx, tc in enumerate(cells):
                if col_idx >= len(col_widths_twip):
                    break
                col_w_emu = col_widths_twip[col_idx] * TWIP_TO_EMU

                # 查找单元格中的所有 inline drawing
                for drawing in tc.iter(w_drawing):
                    inline = drawing.find(wp_inline)
                    if inline is None:
                        continue
                    extent = inline.find(wp_extent)
                    if extent is None:
                        continue
                    cx = int(extent.get("cx") or "0")
                    cy = int(extent.get("cy") or "0")

                    if cx > col_w_emu and cx > 0:
                        ratio = col_w_emu / cx
                        new_cx = int(col_w_emu)
                        new_cy = int(cy * ratio)
                        extent.set("cx", str(new_cx))
                        extent.set("cy", str(new_cy))

                        # 同时更新 a:ext（pic:spPr/a:xfrm/a:ext）
                        for a_ext in inline.iter(a_ext_tag):
                            a_cx = a_ext.get("cx")
                            if a_cx is not None and int(a_cx) == cx:
                                a_ext.set("cx", str(new_cx))
                                a_ext.set("cy", str(new_cy))

                        scaled += 1

    if scaled:
        print(f"  [figures] Scaled {scaled} image(s) in FigureTable cells")

    return scaled

def inject_figure_table_style(styles_xml: bytes) -> bytes:
    """Inject a FigureTable table style with zero cell margins.

    Pandoc generates ``w:tblStyle="FigureTable"`` for two-column figure
    wrapper tables, but this style is not defined in the reference template.
    Without the definition Word/LibreOffice falls back to Normal Table which
    has 108-twip left/right cell margins, causing images to be clipped by ~9%.
    """
    if not styles_xml:
        return styles_xml

    sroot = ET.fromstring(styles_xml)

    q_style = f"{{{W_URI}}}style"
    q_styleId = f"{{{W_URI}}}styleId"

    # Check if FigureTable style already exists
    for s in sroot.findall(q_style):
        if s.get(q_styleId) == "FigureTable":
            return styles_xml  # already present, nothing to do

    # Build the style element:
    # <w:style w:type="table" w:customStyle="1" w:styleId="FigureTable">
    #   <w:name w:val="FigureTable"/>
    #   <w:tblPr>
    #     <w:tblCellMar>
    #       <w:top    w:type="dxa" w:w="0"/>
    #       <w:left   w:type="dxa" w:w="0"/>
    #       <w:bottom w:type="dxa" w:w="0"/>
    #       <w:right  w:type="dxa" w:w="0"/>
    #     </w:tblCellMar>
    #   </w:tblPr>
    # </w:style>
    def _q(local: str) -> str:
        return f"{{{W_URI}}}{local}"

    style_el = ET.SubElement(sroot, _q("style"))
    style_el.set(_q("type"), "table")
    style_el.set(_q("customStyle"), "1")
    style_el.set(_q("styleId"), "FigureTable")

    name_el = ET.SubElement(style_el, _q("name"))
    name_el.set(_q("val"), "FigureTable")

    tblPr = ET.SubElement(style_el, _q("tblPr"))
    tblCellMar = ET.SubElement(tblPr, _q("tblCellMar"))

    for side in ("top", "left", "bottom", "right"):
        margin_el = ET.SubElement(tblCellMar, _q(side))
        margin_el.set(_q("type"), "dxa")
        margin_el.set(_q("w"), "0")

    print("  [styles] Injected FigureTable style (zero cell margins)")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)

def build_tbl_label_map(
    ns: dict[str, str], body: ET.Element
) -> dict[int, list[str]]:
    """扫描 body 子元素，构建 {tbl在body中的index: [tab:xxx labels]} 反向映射。

    Pandoc 把 \\label{tab:xxx} 转换为 body 级别的 bookmarkStart，
    位于对应 <w:tbl> 前方约 4 个元素。本函数向后搜索最近的数据表进行关联。
    """
    w_tbl = qn(ns, "w", "tbl")
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_name = qn(ns, "w", "name")

    children = list(body)
    result: dict[int, list[str]] = {}
    WINDOW = 8  # 向后搜索窗口

    for i, el in enumerate(children):
        # 收集当前元素中的 tab: 书签
        labels: list[str] = []
        for bm in el.iter(w_bookmarkStart):
            name = (bm.get(w_name) or bm.get("name") or "").strip()
            if name.startswith("tab:") or name.startswith("tbl:"):
                labels.append(name)
        if not labels:
            continue
        # 向后搜索最近的 <w:tbl>
        for j in range(i + 1, min(i + WINDOW + 1, len(children))):
            if children[j].tag == w_tbl:
                if is_data_table(ns, children[j]):
                    result.setdefault(j, []).extend(labels)
                break

    return result

def is_figure_table_block(ns: dict[str, str], block: ET.Element) -> bool:
    if block.tag != qn(ns, "w", "tbl"):
        return False
    pr = block.find(qn(ns, "w", "tblPr"))
    if pr is None:
        return False
    style = pr.find(qn(ns, "w", "tblStyle"))
    if style is None:
        return False
    return (style.get(qn(ns, "w", "val")) or "").strip() == "FigureTable"

def table_width_dxa(ns: dict[str, str], tbl: ET.Element) -> int | None:
    w_tblW = qn(ns, "w", "tblW")
    w_type = qn(ns, "w", "type")
    w_w = qn(ns, "w", "w")
    w_tblGrid = qn(ns, "w", "tblGrid")
    w_gridCol = qn(ns, "w", "gridCol")
    pr = tbl.find(qn(ns, "w", "tblPr"))
    if pr is None:
        pr = ensure_tbl_pr(ns, tbl)
    width = pr.find(w_tblW)
    if width is not None and (width.get(w_type) or "") == "dxa":
        try:
            val = int(width.get(w_w) or "0")
        except ValueError:
            val = 0
        if val > 0:
            return val
    grid = tbl.find(w_tblGrid)
    if grid is not None:
        vals: list[int] = []
        for col in grid.findall(w_gridCol):
            try:
                w = int(col.get(w_w) or "0")
            except ValueError:
                w = 0
            if w > 0:
                vals.append(w)
        if vals:
            return sum(vals)
    return None

def set_row_cant_split(ns: dict[str, str], tr: ET.Element) -> None:
    w_trPr = qn(ns, "w", "trPr")
    w_cantSplit = qn(ns, "w", "cantSplit")
    trPr = tr.find(w_trPr)
    if trPr is None:
        trPr = ET.SubElement(tr, w_trPr)
    if trPr.find(w_cantSplit) is None:
        ET.SubElement(trPr, w_cantSplit)


def _is_empty_para(ns: dict[str, str], p: ET.Element) -> bool:
    """判断段落是否为空段落（无文字、非分节符、非标题）。"""
    w_sectPr = qn(ns, "w", "sectPr")
    w_pStyle = qn(ns, "w", "pStyle")
    w_pPr = qn(ns, "w", "pPr")

    # 含 w:sectPr 的分节符段落不视为空段落
    if p.find(f".//{w_sectPr}") is not None:
        return False

    # 含 pStyle 且 style 以 "Heading" 开头的不视为空段落
    pPr = p.find(w_pPr)
    if pPr is not None:
        pStyle = pPr.find(w_pStyle)
        if pStyle is not None:
            style_val = pStyle.get(qn(ns, "w", "val")) or ""
            if style_val.startswith("Heading") or style_val == "1" or style_val == "2" or style_val == "3":
                return False

    # 无文字内容
    return "".join(p.itertext()).strip() == ""


def remove_empty_para_before_table_captions(ns: dict[str, str], body: ET.Element) -> int:
    """删除紧邻表格标题前的空段落。

    扫描所有 w:tbl 元素，找到其前面的标题段落链（匹配 ^表\\d+-\\d+ 或 ^Table \\d+-\\d+），
    如果标题链最顶部的段落前面紧邻一个空段落，则删除该空段落。

    返回删除的空段落数量。
    """
    w_tbl = qn(ns, "w", "tbl")
    w_p = qn(ns, "w", "p")
    w_bookmarkStart = qn(ns, "w", "bookmarkStart")
    w_bookmarkEnd = qn(ns, "w", "bookmarkEnd")
    _SKIP_TAGS = {w_bookmarkStart, w_bookmarkEnd}

    _TABLE_CAPTION_RE = re.compile(r"^(表\d+-\d+|Table\s+\d+-\d+)", re.IGNORECASE)

    children = list(body)
    to_remove: list[ET.Element] = []

    for i, el in enumerate(children):
        if el.tag != w_tbl:
            continue

        # 向上寻找紧邻此 tbl 的标题段落链（可能有中文+英文两行）
        # 跳过 bookmarkStart/End，它们可能出现在 caption 和 tbl 之间
        caption_top = i  # 标题链中最顶部的 w:p 的 index
        j = i - 1
        while j >= 0:
            prev = children[j]
            if prev.tag in _SKIP_TAGS:
                j -= 1
                continue
            if prev.tag != w_p:
                break
            txt = "".join(prev.itertext()).strip()
            if not txt:
                # 空段落不属于标题链，停止向上搜索
                break
            if _TABLE_CAPTION_RE.match(txt):
                caption_top = j
                j -= 1
            else:
                break

        # caption_top 是标题链中最顶部的 index；
        # 如果 caption_top < i，说明找到了标题段落
        if caption_top >= i:
            continue

        # 检查 caption_top 前面是否紧邻空段落（跳过 bookmark 节点）
        prev_idx = caption_top - 1
        while prev_idx >= 0 and children[prev_idx].tag in _SKIP_TAGS:
            prev_idx -= 1
        if prev_idx < 0:
            continue
        prev_el = children[prev_idx]
        if prev_el.tag == w_p and _is_empty_para(ns, prev_el):
            if prev_el not in to_remove:
                to_remove.append(prev_el)

    removed = 0
    for el in to_remove:
        try:
            body.remove(el)
            removed += 1
        except ValueError:
            pass

    if removed:
        print(f"  [table] Removed {removed} empty paragraph(s) before table caption(s)")
    return removed


__all__ = [
    "fix_figure_captions",
    "inject_captions_from_meta",
    "wrap_figure_with_captions",
    "build_figure_caption_wrapper",
    "make_caption_para",
    "make_caption_run",
    "make_equation_number_run",
    "main_body_context",
    "iter_anchor_names_in_element",
    "find_next_anchor_target_block",
    "collect_anchor_block_positions",
    "dedupe_body_level_anchor_bookmarks",
    "clean_table_title",
    "is_table_caption_para",
    "find_caption_idx_near_table",
    "is_caption_paragraph_near_block",
    "remove_adjacent_caption_paragraphs",
    "strip_latex_escapes_for_docx",
    "normalize_caption_title",
    "set_tbl_caption_value",
    "apply_three_line_tables",
    "first_table_style_id",
    "ensure_tbl_pr",
    "set_border_el",
    "is_data_table",
    "visual_text_len",
    "table_col_count",
    "table_col_weights",
    "normalize_widths_to_total",
    "apply_latex_col_ratios",
    "set_table_full_width_and_columns",
    "fit_figure_images_to_cells",
    "inject_figure_table_style",
    "build_tbl_label_map",
    "is_figure_table_block",
    "table_width_dxa",
    "set_row_cant_split",
    "remove_empty_para_before_table_captions",
    "set_p_style",
    "set_paragraph_text",
]
