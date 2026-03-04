#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extra validations for the produced SWUN DOCX.
This avoids relying on styleId string-matching in styles.xml, which can vary across templates.
"""

from __future__ import annotations

import re
import sys
import zipfile
import xml.etree.ElementTree as ET


def _iter_paragraphs(doc_xml: str) -> list[str]:
    # Good enough for checks (Word XML is regular; paragraphs aren't nested).
    return re.findall(r"(<w:p[\s\S]*?</w:p>)", doc_xml)

def _iter_tables(doc_xml: str) -> list[str]:
    # Tables aren't nested in our use-case; regex is sufficient for lightweight validation.
    return re.findall(r"(<w:tbl[\s\S]*?</w:tbl>)", doc_xml)

def _p_text(p_xml: str) -> str:
    # Join all text runs within a paragraph. This avoids false negatives when punctuation
    # is split across <w:t> nodes.
    parts = re.findall(r"<w:t[^>]*>([\s\S]*?)</w:t>", p_xml)
    return "".join(parts)


def _check_no_forced_break_after_heading(
    paras: list[str], texts: list[str], heading_text: str
) -> str | None:
    """
    Ensure no forced page break sneaks in between heading and its first content paragraph.
    This catches the regression where abstract heading is followed by an empty page.
    """
    idx = None
    for i, t in enumerate(texts):
        if t.strip() == heading_text:
            idx = i
            break
    if idx is None:
        return None

    # Look ahead to the first non-empty paragraph.
    j = idx + 1
    while j < len(paras):
        p_xml = paras[j]
        t = texts[j].strip()
        # A hard page-break paragraph or section break right after heading is suspicious.
        if 'w:type="page"' in p_xml:
            return f"found explicit page break paragraph right after heading '{heading_text}'"
        if "<w:pageBreakBefore" in p_xml:
            return f"found pageBreakBefore on paragraph right after heading '{heading_text}'"
        if t:
            break
        j += 1

    if j >= len(paras):
        return None

    first_content_p = paras[j]
    if "<w:pageBreakBefore" in first_content_p:
        return f"first content paragraph under '{heading_text}' has pageBreakBefore (can create an empty page)"
    return None


def _collect_dotted_fig_table_hyperlinks(doc_xml: str) -> list[tuple[str, str]]:
    """Collect fig/tab/tbl hyperlinks whose visible text still uses dot numbering."""
    out: list[tuple[str, str]] = []
    dotted_re = re.compile(r"(?<!\d)\d+\.\d+(?!\d)")
    # Hyperlink content can include runs; extract text from <w:t> nodes.
    for m in re.finditer(
        r'<w:hyperlink[^>]*w:anchor="([^"]+)"[^>]*>([\s\S]*?)</w:hyperlink>',
        doc_xml,
    ):
        anchor, inner = m.group(1), m.group(2)
        if not anchor.startswith(("fig:", "tab:", "tbl:")):
            continue
        txt = "".join(re.findall(r"<w:t[^>]*>([\s\S]*?)</w:t>", inner)).strip()
        if txt and dotted_re.search(txt):
            out.append((anchor, txt))
    return out


def _iter_main_body_blocks(root: ET.Element, ns: dict[str, str]) -> list[ET.Element]:
    """Return paragraph/table blocks within thesis main body (正文)."""
    body = root.find("w:body", ns)
    if body is None:
        return []

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}
    blocks: list[ET.Element] = []
    in_main_body = False

    for el in list(body):
        if el.tag == f"{{{ns['w']}}}p":
            p_style = el.find("w:pPr/w:pStyle", ns)
            style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
            p_txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()
            if style_val == "1":
                if p_txt in stop_h1:
                    in_main_body = False
                elif p_txt and p_txt not in excluded_h1:
                    in_main_body = True
        if not in_main_body:
            continue
        if el.tag in {f"{{{ns['w']}}}p", f"{{{ns['w']}}}tbl"}:
            blocks.append(el)

    return blocks


def _collect_main_body_anchor_hyperlinks(doc_xml: str) -> list[tuple[str, str]]:
    """Collect remaining internal anchor hyperlinks in thesis main body."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(doc_xml)
    out: list[tuple[str, str]] = []
    for el in _iter_main_body_blocks(root, ns):
        for hl in el.findall(".//w:hyperlink", ns):
            anchor = hl.get(f"{{{ns['w']}}}anchor", "") or ""
            if not anchor:
                continue
            txt = "".join((t.text or "") for t in hl.findall(".//w:t", ns)).strip()
            out.append((anchor, txt or "<EMPTY>"))

    return out


def _run_has_hyperlink_style(r: ET.Element, ns: dict[str, str]) -> bool:
    rpr = r.find("w:rPr", ns)
    if rpr is None:
        return False

    rstyle = rpr.find("w:rStyle", ns)
    if rstyle is not None and "hyperlink" in (rstyle.get(f"{{{ns['w']}}}val") or "").lower():
        return True

    color = rpr.find("w:color", ns)
    if color is not None:
        theme = (color.get(f"{{{ns['w']}}}themeColor") or "").lower()
        val = (color.get(f"{{{ns['w']}}}val") or "").lower()
        if theme == "hyperlink" or val in {"0563c1", "0000ff"}:
            return True

    u = rpr.find("w:u", ns)
    if u is not None:
        uval = (u.get(f"{{{ns['w']}}}val") or "").lower()
        if uval in {"", "single"}:
            return True

    return False


def _collect_main_body_hyperlink_style_runs(doc_xml: str) -> list[str]:
    """Collect runs in main body that still look like hyperlink style."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(doc_xml)
    out: list[str] = []

    for block in _iter_main_body_blocks(root, ns):
        for r in block.findall(".//w:r", ns):
            if not _run_has_hyperlink_style(r, ns):
                continue
            t = "".join((x.text or "") for x in r.findall(".//w:t", ns)).strip() or "<EMPTY>"
            out.append(t)
            if len(out) >= 20:
                return out

    return out


def _collect_unnumbered_heading5_in_main_body(doc_xml: str) -> list[str]:
    """Collect Heading5 lines in main body that do not start with '(n) '."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(doc_xml)
    body = root.find("w:body", ns)
    if body is None:
        return []

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}
    heading5_styles = {"Heading5", "5"}
    pref_re = re.compile(r"^\(\d+\)\s+")

    in_main_body = False
    out: list[str] = []

    for el in list(body):
        if el.tag != f"{{{ns['w']}}}p":
            continue
        p_style = el.find("w:pPr/w:pStyle", ns)
        style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
        p_txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()

        if style_val == "1":
            if p_txt in stop_h1:
                in_main_body = False
            elif p_txt and p_txt not in excluded_h1:
                in_main_body = True

        if not in_main_body or style_val not in heading5_styles:
            continue
        if not p_txt:
            continue
        if not pref_re.match(p_txt):
            out.append(p_txt)

    return out


def _iter_reference_blocks(root: ET.Element, ns: dict[str, str]) -> list[ET.Element]:
    """Return paragraph/table blocks inside the references section."""
    body = root.find("w:body", ns)
    if body is None:
        return []

    blocks: list[ET.Element] = []
    in_refs = False
    stop_h1 = {"致谢", "攻读硕士学位期间所取得的相关科研成果", "攻读硕士学位期间发表的学术成果"}

    for el in list(body):
        if el.tag == f"{{{ns['w']}}}p":
            p_style = el.find("w:pPr/w:pStyle", ns)
            style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
            p_txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()
            if style_val == "1":
                if p_txt == "参考文献":
                    in_refs = True
                    continue
                if in_refs and p_txt in stop_h1:
                    in_refs = False
        if not in_refs:
            continue
        if el.tag in {f"{{{ns['w']}}}p", f"{{{ns['w']}}}tbl"}:
            blocks.append(el)

    return blocks


def _check_reference_external_hyperlinks(doc_xml: str) -> str | None:
    """
    Guardrail: if references contain DOI/URL text, they should retain external
    hyperlinks (w:hyperlink with r:id).
    """
    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }
    root = ET.fromstring(doc_xml)
    ref_blocks = _iter_reference_blocks(root, ns)
    if not ref_blocks:
        return None

    ref_text = "".join(
        "".join((t.text or "") for t in block.findall(".//w:t", ns)) for block in ref_blocks
    )
    has_doi_or_url = bool(re.search(r"(10\.\d{4,9}/\S+|https?://\S+)", ref_text, flags=re.IGNORECASE))
    if not has_doi_or_url:
        return None

    rid_links = 0
    for block in ref_blocks:
        for hl in block.findall(".//w:hyperlink", ns):
            if hl.get(f"{{{ns['r']}}}id"):
                rid_links += 1
    if rid_links == 0:
        return "references contain DOI/URL text but no external hyperlinks (w:hyperlink r:id)"
    return None


def _paragraph_has_first_line_indent(p: ET.Element, ns: dict[str, str]) -> bool:
    w = ns["w"]
    ppr = p.find("w:pPr", ns)
    if ppr is None:
        return False
    ind = ppr.find("w:ind", ns)
    if ind is None:
        return False
    first_line_chars = ind.get(f"{{{w}}}firstLineChars")
    first_line = ind.get(f"{{{w}}}firstLine")
    return (first_line_chars not in (None, "", "0")) or (first_line not in (None, "", "0"))


def _check_heading5_and_following_body_indent(doc_xml: str) -> list[str]:
    """
    Regression guard for LaTeX \\paragraph -> DOCX Heading5 mapping:
    1) Heading5 line itself MUST have first-line indent (matching PDF layout).
    2) First non-empty content paragraph right after Heading5 keeps first-line indent.
    """
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    errors: list[str] = []

    try:
        root = ET.fromstring(doc_xml)
    except ET.ParseError as exc:
        return [f"failed to parse document.xml when checking Heading5/body indent: {exc}"]

    body = root.find("w:body", ns)
    if body is None:
        return ["missing w:body when checking Heading5/body indent"]

    children = list(body)
    heading_styles = {"1", "2", "3", "4", "5", "Heading1", "Heading2", "Heading3", "Heading4", "Heading5"}

    for i, el in enumerate(children):
        if el.tag != f"{{{ns['w']}}}p":
            continue
        p_style = el.find("w:pPr/w:pStyle", ns)
        style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
        if style_val != "Heading5":
            continue

        heading_text = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip() or "<EMPTY>"
        if not _paragraph_has_first_line_indent(el, ns):
            errors.append(f"Heading5 paragraph '{heading_text}' must have first-line indent")

        j = i + 1
        next_p: ET.Element | None = None
        while j < len(children):
            cand = children[j]
            j += 1
            if cand.tag != f"{{{ns['w']}}}p":
                continue
            cand_text = "".join((t.text or "") for t in cand.findall(".//w:t", ns)).strip()
            if not cand_text:
                continue
            next_p = cand
            break

        if next_p is None:
            continue

        next_style_el = next_p.find("w:pPr/w:pStyle", ns)
        next_style = next_style_el.get(f"{{{ns['w']}}}val") if next_style_el is not None else None
        next_text = "".join((t.text or "") for t in next_p.findall(".//w:t", ns)).strip() or "<EMPTY>"
        if next_style in heading_styles:
            errors.append(f"Heading5 paragraph '{heading_text}' is not followed by a body paragraph")
            continue
        if not _paragraph_has_first_line_indent(next_p, ns):
            errors.append(
                f"first content paragraph after Heading5 '{heading_text}' missing first-line indent: '{next_text}'"
            )

    return errors


def _block_has_drawing(el: ET.Element, ns: dict[str, str]) -> bool:
    return el.find(".//w:drawing", ns) is not None or el.find(".//w:pict", ns) is not None


def _iter_anchor_names(el: ET.Element, ns: dict[str, str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    w_name = f"{{{ns['w']}}}name"
    for bm in el.findall(".//w:bookmarkStart", ns):
        name = (bm.get(w_name) or bm.get("name") or "").strip()
        if not name or name in seen:
            continue
        if not name.startswith(("fig:", "tab:", "tbl:")):
            continue
        seen.add(name)
        out.append(name)
    return out


def _main_body_children_with_chapter(
    root: ET.Element, ns: dict[str, str]
) -> tuple[list[ET.Element], int, int, dict[int, int]]:
    body = root.find("w:body", ns)
    if body is None:
        return [], 0, 0, {}

    children = list(body)
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}
    in_main_body = False
    chapter_no = 0
    chapter_by_idx: dict[int, int] = {}
    start = 0
    end = len(children)
    started = False

    for i, el in enumerate(children):
        if el.tag == f"{{{ns['w']}}}p":
            p_style = el.find("w:pPr/w:pStyle", ns)
            style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
            p_txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()
            if style_val == "1":
                if p_txt in stop_h1:
                    if in_main_body and end == len(children):
                        end = i
                    in_main_body = False
                elif p_txt and p_txt not in excluded_h1:
                    if not started:
                        start = i
                        started = True
                    in_main_body = True
                    chapter_no += 1
        if in_main_body:
            chapter_by_idx[i] = chapter_no

    if not started:
        return children, 0, 0, {}
    return children, start, end, chapter_by_idx


def _next_anchor_target_idx(
    children: list[ET.Element], start: int, end: int, ns: dict[str, str], kind: str
) -> int | None:
    w_p = f"{{{ns['w']}}}p"
    w_tbl = f"{{{ns['w']}}}tbl"
    fallback: int | None = None
    for i in range(start, end):
        el = children[i]
        if el.tag == w_tbl:
            has_draw = _block_has_drawing(el, ns)
            if kind == "figure":
                return i
            if kind == "table" and not has_draw:
                return i
            if fallback is None:
                fallback = i
            continue
        if el.tag == w_p and kind == "figure" and _block_has_drawing(el, ns):
            return i
    return fallback


def _collect_anchor_positions(
    root: ET.Element, ns: dict[str, str]
) -> tuple[list[tuple[str, str, int]], dict[int, int], list[str]]:
    children, start, end, chapter_by_idx = _main_body_children_with_chapter(root, ns)
    if end <= start:
        return [], chapter_by_idx, []

    w_p = f"{{{ns['w']}}}p"
    w_tbl = f"{{{ns['w']}}}tbl"
    w_bookmark_start = f"{{{ns['w']}}}bookmarkStart"
    w_name = f"{{{ns['w']}}}name"
    best: dict[str, tuple[int, int]] = {}
    errors: list[str] = []

    def kind_of(label: str) -> str:
        return "figure" if label.startswith("fig:") else "table"

    def score(kind: str, block: ET.Element, inline: bool) -> int:
        s = 2 if inline else 1
        has_draw = _block_has_drawing(block, ns)
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
        for label in _iter_anchor_names(el, ns):
            k = kind_of(label)
            if k == "table" and el.tag != w_tbl:
                continue
            if k == "figure" and not _block_has_drawing(el, ns) and el.tag != w_tbl:
                continue
            cand = (score(k, el, True), i)
            prev = best.get(label)
            if prev is None or cand[0] > prev[0]:
                best[label] = cand

    for i in range(start, end):
        el = children[i]
        if el.tag != w_bookmark_start:
            continue
        name = (el.get(w_name) or el.get("name") or "").strip()
        if not name.startswith(("fig:", "tab:", "tbl:")):
            continue
        k = kind_of(name)
        j = _next_anchor_target_idx(children, i + 1, end, ns, k)
        if j is None:
            errors.append(f"anchor '{name}' has no following block in main body")
            continue
        block = children[j]
        cand = (score(k, block, False), j)
        prev = best.get(name)
        if prev is None or cand[0] > prev[0]:
            best[name] = cand

    placements = [(kind_of(label), label, idx) for label, (_sc, idx) in best.items()]
    placements.sort(key=lambda x: (x[2], x[1]))
    return placements, chapter_by_idx, errors


def _neighbor_nonempty_paras(
    children: list[ET.Element], block_idx: int, ns: dict[str, str], *, before: bool, limit: int = 2
) -> list[str]:
    out: list[str] = []
    w_p = f"{{{ns['w']}}}p"
    w_bookmark_start = f"{{{ns['w']}}}bookmarkStart"
    w_bookmark_end = f"{{{ns['w']}}}bookmarkEnd"
    if before:
        rng = range(block_idx - 1, -1, -1)
    else:
        rng = range(block_idx + 1, len(children))

    for i in rng:
        el = children[i]
        if el.tag in {w_bookmark_start, w_bookmark_end}:
            continue
        if el.tag != w_p:
            break
        txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()
        if not txt:
            continue
        out.append(txt)
        if len(out) >= limit:
            break
    return out


def _parse_caption_index(kind: str, lang: str, text: str) -> tuple[int, int] | None:
    if kind == "figure" and lang == "cn":
        m = re.match(r"^图\s*(\d+)-(\d+)\b", text)
    elif kind == "figure":
        m = re.match(r"^Figure\s+(\d+)-(\d+)\b", text, flags=re.IGNORECASE)
    elif kind == "table" and lang == "cn":
        m = re.match(r"^表\s*(\d+)-(\d+)\b", text)
    else:
        m = re.match(r"^Table\s+(\d+)-(\d+)\b", text, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _check_anchor_caption_rules(doc_xml: str) -> list[str]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        root = ET.fromstring(doc_xml)
    except ET.ParseError as exc:
        return [f"failed to parse document.xml for anchor-caption checks: {exc}"]

    children, _start, _end, _chapter_by_idx = _main_body_children_with_chapter(root, ns)
    placements, chapter_by_idx, errors = _collect_anchor_positions(root, ns)
    if not placements:
        return errors

    counters: dict[tuple[int, str], int] = {}

    for kind, label, block_idx in placements:
        chapter_no = chapter_by_idx.get(block_idx)
        if chapter_no is None:
            continue
        key = (chapter_no, kind)
        seq = counters.get(key, 0) + 1
        counters[key] = seq

        before = _neighbor_nonempty_paras(children, block_idx, ns, before=True, limit=2)
        after = _neighbor_nonempty_paras(children, block_idx, ns, before=False, limit=2)

        if kind == "figure":
            cn = _parse_caption_index(kind, "cn", after[0]) if after else None
            if cn is None:
                misplaced = any(_parse_caption_index(kind, "cn", t) is not None for t in before)
                if misplaced:
                    errors.append(f"anchor '{label}' figure caption is above the block (expected below)")
                else:
                    errors.append(f"anchor '{label}' missing figure caption below block")
                continue
            if cn != (chapter_no, seq):
                errors.append(
                    f"anchor '{label}' figure caption numbering mismatch: got 图{cn[0]}-{cn[1]}, expected 图{chapter_no}-{seq}"
                )
            if len(after) < 2:
                errors.append(f"anchor '{label}' missing figure English caption line below block")
            else:
                en = _parse_caption_index(kind, "en", after[1])
                if en is None:
                    errors.append(f"anchor '{label}' figure English caption line format invalid: {after[1]!r}")
                elif en != (chapter_no, seq):
                    errors.append(
                        f"anchor '{label}' figure English caption numbering mismatch: got Figure {en[0]}-{en[1]}, expected Figure {chapter_no}-{seq}"
                    )
        else:
            cn = None
            if before:
                cn = _parse_caption_index(kind, "cn", before[0])
            if cn is None and len(before) >= 2:
                cn = _parse_caption_index(kind, "cn", before[1])
            if cn is None:
                misplaced = any(_parse_caption_index(kind, "cn", t) is not None for t in after)
                if misplaced:
                    errors.append(f"anchor '{label}' table caption is below the block (expected above)")
                else:
                    errors.append(f"anchor '{label}' missing table caption above block")
                continue
            if cn != (chapter_no, seq):
                errors.append(
                    f"anchor '{label}' table caption numbering mismatch: got 表{cn[0]}-{cn[1]}, expected 表{chapter_no}-{seq}"
                )
            en = _parse_caption_index(kind, "en", before[0]) if before else None
            if en is None and len(before) >= 2:
                en = _parse_caption_index(kind, "en", before[1])
            if en is None:
                sample = before[0] if before else "<MISSING>"
                errors.append(f"anchor '{label}' missing table English caption line above block (nearest='{sample}')")
            elif en != (chapter_no, seq):
                errors.append(
                    f"anchor '{label}' table English caption numbering mismatch: got Table {en[0]}-{en[1]}, expected Table {chapter_no}-{seq}"
                )

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_extra.py /path/to/main_版式1.docx", file=sys.stderr)
        return 2

    docx_path = sys.argv[1]
    with zipfile.ZipFile(docx_path, "r") as zf:
        doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        num = zf.read("word/numbering.xml").decode("utf-8", errors="ignore")

    errors: list[str] = []

    if " TOC " not in doc:
        errors.append("missing Word TOC field (instrText contains ' TOC ')")

    if "目录" not in doc:
        errors.append("missing TOC title text '目录'")

    # Ensure page breaks exist (chapters start on new page).
    if 'w:type="page"' not in doc:
        errors.append("missing page breaks (w:br w:type=page)")

    # Numbering fix for mixed Chinese/Arabic at lower levels.
    if "w:abstractNumId=\"0\"" in num and "w:isLgl" not in num:
        errors.append("missing w:isLgl in numbering.xml (abstractNumId=0)")

    # Sectioned page numbering: expect Roman + Arabic page formats.
    if 'w:fmt="lowerRoman"' not in doc:
        errors.append('missing Roman page numbering (w:pgNumType w:fmt="lowerRoman") for abstracts section')
    if 'w:fmt="decimal"' not in doc or 'w:start="1"' not in doc:
        errors.append('missing Arabic page numbering restart (w:pgNumType w:fmt="decimal" w:start="1") for main body')

    paras = _iter_paragraphs(doc)
    texts = [_p_text(p) for p in paras]

    for h in ("摘要", "Abstract"):
        err = _check_no_forced_break_after_heading(paras, texts, h)
        if err is not None:
            errors.append(err)

    # Figure/table refs must use caption numbering style with hyphen (e.g., 3-16).
    dotted_refs = _collect_dotted_fig_table_hyperlinks(doc)
    if dotted_refs:
        sample = ", ".join([f"{a}='{t}'" for a, t in dotted_refs[:3]])
        errors.append(
            "found dotted figure/table hyperlink refs (must use hyphen numbering): "
            + sample
        )

    # In main body, internal cross-reference hyperlinks (w:anchor) must be unwrapped.
    body_anchor_hyperlinks = _collect_main_body_anchor_hyperlinks(doc)
    if body_anchor_hyperlinks:
        sample = ", ".join(f"{a}={t!r}" for a, t in body_anchor_hyperlinks[:3])
        errors.append("found internal anchor hyperlinks in main body (must be plain text refs): " + sample)

    # Also clear hyperlink-like visual style leakage (blue/underline) in main body.
    style_leaks = _collect_main_body_hyperlink_style_runs(doc)
    if style_leaks:
        sample = ", ".join(repr(t) for t in style_leaks[:3])
        errors.append("found hyperlink-like style runs in main body: " + sample)

    # Anchor-to-caption hard checks: presence, position (fig below / table above), chapter-local numbering.
    errors.extend(_check_anchor_caption_rules(doc))

    # References DOI/URL external links should be preserved.
    ref_link_err = _check_reference_external_hyperlinks(doc)
    if ref_link_err:
        errors.append(ref_link_err)

    # Heading5 lines in main body must have explicit '(n) ' prefix.
    unnumbered_h5 = _collect_unnumbered_heading5_in_main_body(doc)
    if unnumbered_h5:
        sample = ", ".join(repr(t) for t in unnumbered_h5[:3])
        errors.append("found unnumbered Heading5 in main body (expected '(n) ' prefix): " + sample)

    # \paragraph mapping guard: Heading5 line has no indent; following body paragraph keeps indent.
    errors.extend(_check_heading5_and_following_body_indent(doc))

    # Abstract keywords: required with a blank line before.
    if not any("关键词：" in t for t in texts):
        errors.append("missing Chinese abstract keywords line (expected '关键词：...')")
    if not any("Keywords:" in t for t in texts):
        errors.append("missing English abstract keywords line (expected 'Keywords: ...')")

    # Best-effort: ensure there is an empty paragraph right before each keywords line.
    for marker in ["关键词：", "Keywords:"]:
        for i, t in enumerate(texts):
            if marker not in t:
                continue
            if i == 0:
                errors.append(f"keywords line '{marker}' is the first paragraph; expected a blank line before it")
                continue
            prev_t = texts[i - 1].strip()
            if prev_t:
                errors.append(f"missing blank line before keywords line '{marker}' (previous paragraph contains text)")
            break

    # Best-effort: ensure 3-4 groups (<= 3 separators) for both CN and EN.
    # We only check locally around the marker to avoid over-parsing OOXML.
    def _check_groups(marker: str, sep: str, max_sep: int = 3) -> None:
        for t in texts:
            if marker not in t:
                continue
            tail = t.split(marker, 1)[1]
            if tail.count(sep) > max_sep:
                errors.append(f"too many keyword separators near '{marker}' (expected 3-4 groups)")
            return

    _check_groups("关键词：", "；", 3)
    _check_groups("Keywords:", ";", 3)

    # Bibliography hanging indent: should be present for entries.
    if "参考文献" in doc and "hangingChars" not in doc:
        errors.append("missing hanging indent for bibliography entries (w:hangingChars)")

    # Citations should appear as [n] and often superscript.
    if "vertAlign" not in doc and not re.search(r"\[[0-9]{1,3}\]", doc):
        errors.append("no obvious citation markers found (expected [n] possibly superscript)")

    # Figure captions: expect "图{章}-{序号} ..."
    cap_re = re.compile(r"图\d+-\d+\s+")
    cap_paras = []
    for p in _iter_paragraphs(doc):
        if cap_re.search(p):
            cap_paras.append(p)

    if not cap_paras:
        errors.append("no numbered figure captions found (expected '图{章}-{序号} ...')")
    else:
        # Captions should be centered.
        not_centered = [p for p in cap_paras if 'w:jc w:val="center"' not in p]
        if not_centered:
            errors.append("some figure captions are not centered (missing w:jc center)")

    # Equation numbering: expect some display-math paras to end with '(章-序号)'.
    eq_re = re.compile(r"\(\d+-\d+\)")
    math_paras = [p for p in _iter_paragraphs(doc) if "<m:oMathPara" in p]
    numbered_math_paras = [p for p in math_paras if eq_re.search(p)]
    if math_paras and not numbered_math_paras:
        errors.append("no equation numbers found on display-math paragraphs (expected '(章-序号)')")

    # Ensure we don't accidentally number the universal-quantifier display line.
    for p in math_paras:
        if "<m:t>∀</m:t>" in p and eq_re.search(p):
            errors.append("found an equation number on a quantifier-only display math paragraph (should be unnumbered)")
            break

    # KeepTogether hints for figures (best-effort).
    if "<w:keepNext" not in doc:
        errors.append("missing keepNext in document.xml (expected for figure paragraphs)")

    # Three-line tables: apply only to data tables (those with w:tblCaption).
    tables = _iter_tables(doc)
    data_tables = [t for t in tables if "<w:tblCaption" in t]
    for t in data_tables:
        m = re.search(r"(<w:tblBorders[\s\S]*?</w:tblBorders>)", t)
        if not m:
            errors.append("data table missing w:tblBorders (expected three-line table borders)")
            break
        b = m.group(1)
        need = [
            'w:top w:val="single"',
            'w:bottom w:val="single"',
            'w:left w:val="nil"',
            'w:right w:val="nil"',
            'w:insideH w:val="nil"',
            'w:insideV w:val="nil"',
        ]
        missing = [x for x in need if x not in b]
        if missing:
            errors.append("data table borders are not three-line (missing: " + ", ".join(missing) + ")")
            break
        if '<w:tcBorders><w:bottom w:val="single"' not in t:
            errors.append("data table missing header separator line (expected cell bottom border on header row)")
            break

    if errors:
        print("EXTRA VERIFY: FAIL")
        for e in errors:
            print(f"- {e}")
        return 1

    print("EXTRA VERIFY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
