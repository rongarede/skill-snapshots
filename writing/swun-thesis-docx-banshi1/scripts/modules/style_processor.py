#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
样式对齐、编号、缩进处理模块。

从 docx_builder.py 提取，提供公共 API（无下划线前缀）。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        p_text as _p_text,
        p_style as _p_style,
        ensure_ppr as _ensure_ppr,
        clear_para_first_indent as _clear_para_first_indent,
        set_paragraph_text as _set_paragraph_text,
        p_has_sectPr as _p_has_sectPr,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        p_text as _p_text,
        p_style as _p_style,
        ensure_ppr as _ensure_ppr,
        clear_para_first_indent as _clear_para_first_indent,
        set_paragraph_text as _set_paragraph_text,
        p_has_sectPr as _p_has_sectPr,
    )

# ---------------------------------------------------------------------------
# 标题多级编号常量
# ---------------------------------------------------------------------------
_HEADING_ABSTRACT_NUM_XML = '''\
<w:abstractNum w:abstractNumId="88880" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:multiLevelType w:val="multilevel"/>
  <w:lvl w:ilvl="0">
    <w:start w:val="1"/>
    <w:numFmt w:val="chineseCounting"/>
    <w:lvlText w:val="第%1章"/>
    <w:lvlJc w:val="left"/>
    <w:isLgl/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="1">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="2">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2.%3"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="3">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2.%3.%4"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
</w:abstractNum>'''

_HEADING_NUM_ID = "8888"
_HEADING_ABSTRACT_NUM_ID = "88880"


# ---------------------------------------------------------------------------
# 缩进
# ---------------------------------------------------------------------------

def ensure_indent_for_body_paragraphs(ns: dict[str, str], body: ET.Element) -> None:
    """为正文段落添加首行缩进，为二三级标题设置左对齐（清除编号缩进）。"""
    w_p = _qn(ns, "w", "p")
    w_ind = _qn(ns, "w", "ind")
    w_firstLineChars = _qn(ns, "w", "firstLineChars")
    w_left = _qn(ns, "w", "left")
    w_hanging = _qn(ns, "w", "hanging")
    w_hangingChars = _qn(ns, "w", "hangingChars")

    # Pandoc + template mapping may emit Normal as styleId "a".
    # Heading5 (\paragraph) is demoted to Normal ("a") before this runs.
    body_styles = {"BodyText", "FirstParagraph", "Compact", "a"}
    # Heading2/3 (二级/三级子标题) must be flush-left; override numbering indent.
    flush_left_styles = {"Heading2", "2", "Heading3", "3"}

    w_firstLine = _qn(ns, "w", "firstLine")
    m_uri = ns.get("m")
    m_oMathPara = f"{{{m_uri}}}oMathPara" if m_uri else None
    m_oMath = f"{{{m_uri}}}oMath" if m_uri else None

    def is_display_math_para(p: ET.Element) -> bool:
        if p.tag != w_p or not m_uri:
            return False
        if p.find(m_oMathPara) is not None:
            return True
        # Pandoc may emit display math as a bare oMath paragraph with no prose text.
        return p.find(m_oMath) is not None and not _p_text(ns, p).strip()

    prev_sig: ET.Element | None = None

    for child in list(body):
        if child.tag != w_p:
            continue
        style = _p_style(ns, child)
        if style in body_styles:
            pPr = _ensure_ppr(ns, child)
            ind = pPr.find(w_ind)
            # Skip paragraphs already formatted by _format_algorithm_blocks
            # (they have explicit firstLine="0")
            if ind is not None and ind.get(w_firstLine) == "0":
                prev_sig = child
                continue
            if prev_sig is not None and is_display_math_para(prev_sig):
                _clear_para_first_indent(ns, child)
                prev_sig = child
                continue
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            # Keep other indentation attributes intact; only enforce first-line indent.
            ind.set(w_firstLineChars, "200")
        elif style in flush_left_styles:
            pPr = _ensure_ppr(ns, child)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            # Override numbering indent: flush left, no hanging.
            ind.set(w_left, "0")
            for attr in (w_hanging, w_hangingChars):
                if attr in ind.attrib:
                    del ind.attrib[attr]

        prev_sig = child


def ensure_hanging_indent_for_bibliography(ns: dict[str, str], body: ET.Element) -> None:
    """为参考文献条目添加悬挂缩进（GB/T 数字序号格式）。"""
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


# ---------------------------------------------------------------------------
# 样式对齐
# ---------------------------------------------------------------------------

def align_styles_to_reference(styles_xml: bytes) -> bytes:
    """将 styles.xml 中的关键样式对齐至 SWUN 参考论文规范。"""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    if "w" not in sns:
        return styles_xml
    _register_ns(sns)
    sroot = ET.fromstring(styles_xml)

    w_style = _qn(sns, "w", "style")
    w_styleId = _qn(sns, "w", "styleId")
    w_pPr = _qn(sns, "w", "pPr")
    w_rPr = _qn(sns, "w", "rPr")
    w_ind = _qn(sns, "w", "ind")
    w_jc = _qn(sns, "w", "jc")
    w_spacing = _qn(sns, "w", "spacing")
    w_widowControl = _qn(sns, "w", "widowControl")
    w_outlineLvl = _qn(sns, "w", "outlineLvl")
    w_b = _qn(sns, "w", "b")
    w_kern = _qn(sns, "w", "kern")
    w_sz = _qn(sns, "w", "sz")
    w_szCs = _qn(sns, "w", "szCs")
    w_val = _qn(sns, "w", "val")
    w_name = _qn(sns, "w", "name")

    def _ensure(parent: ET.Element, tag: str) -> ET.Element:
        el = parent.find(tag)
        if el is None:
            el = ET.SubElement(parent, tag)
        return el

    def _style_key(st: ET.Element) -> tuple[str, str]:
        sid = (st.get(w_styleId, "") or "").strip()
        name_el = st.find(w_name)
        name = ""
        if name_el is not None:
            name = (name_el.get(w_val, "") or "").strip()
        sid_norm = sid.replace(" ", "").lower()
        name_norm = name.replace(" ", "").lower()
        return sid_norm, name_norm

    updated: list[str] = []
    for st in sroot.findall(w_style):
        sid = st.get(w_styleId, "")
        sid_norm, name_norm = _style_key(st)

        # 1) Normal style (template styleId='a', style name='Normal').
        # Some previous builds incorrectly assumed styleId='1', which is actually
        # Heading 1 in this template family and corrupts chapter titles.
        if sid_norm == "a" or name_norm == "normal":
            pPr = _ensure(st, w_pPr)
            ind = _ensure(pPr, w_ind)
            ind.set(_qn(sns, "w", "firstLine"), "480")
            ind.set(_qn(sns, "w", "firstLineChars"), "200")

            jc = _ensure(pPr, w_jc)
            jc.set(w_val, "both")

            spacing = _ensure(pPr, w_spacing)
            spacing.set(_qn(sns, "w", "line"), "360")
            spacing.set(_qn(sns, "w", "lineRule"), "auto")
            for attr in ("before", "beforeLines", "beforeAutospacing", "after", "afterLines", "afterAutospacing"):
                q_attr = _qn(sns, "w", attr)
                if q_attr in spacing.attrib:
                    del spacing.attrib[q_attr]

            widow = _ensure(pPr, w_widowControl)
            widow.set(w_val, "0")

            rPr = _ensure(st, w_rPr)
            for b in list(rPr.findall(w_b)):
                rPr.remove(b)

            kern = _ensure(rPr, w_kern)
            kern.set(w_val, "2")

            sz = _ensure(rPr, w_sz)
            sz.set(w_val, "24")
            szCs = _ensure(rPr, w_szCs)
            szCs.set(w_val, "24")

            updated.append(f"Normal(styleId={sid or 'unknown'})")

        # 2) Heading 3 style (styleId='Heading3', style name='heading 3').
        elif sid_norm in {"heading3", "3"} or name_norm == "heading3":
            pPr = _ensure(st, w_pPr)
            ind = _ensure(pPr, w_ind)
            ind.set(_qn(sns, "w", "firstLine"), "482")
            fl_chars = _qn(sns, "w", "firstLineChars")
            if fl_chars in ind.attrib:
                del ind.attrib[fl_chars]

            outline = _ensure(pPr, w_outlineLvl)
            outline.set(w_val, "2")

            spacing = _ensure(pPr, w_spacing)
            spacing.set(_qn(sns, "w", "before"), "260")
            spacing.set(_qn(sns, "w", "after"), "260")
            spacing.set(_qn(sns, "w", "line"), "415")

            rPr = st.find(w_rPr)
            if rPr is not None:
                for node in list(rPr.findall(w_sz)):
                    rPr.remove(node)
                for node in list(rPr.findall(w_szCs)):
                    rPr.remove(node)

            updated.append(f"Heading3(styleId={sid or 'unknown'})")

    if updated:
        print(f"  [styles] Aligned reference styles: {', '.join(updated)}")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)


def collect_style_ids(styles_xml: bytes) -> set[str]:
    """收集 styles.xml 中所有已定义的 styleId。"""
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


def normalize_unknown_pstyles(
    ns: dict[str, str], body: ET.Element, known_styles: set[str]
) -> None:
    """将引用了不存在样式的段落映射回 Normal ('a')。"""
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
        "TableCaption",
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


# ---------------------------------------------------------------------------
# 编号
# ---------------------------------------------------------------------------

def fix_numbering_isLgl(ns: dict[str, str], numbering_xml: bytes) -> bytes:
    """为 ilvl >= 1 的编号级别添加 isLgl，修复中阿文章节号混排问题。"""
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

    # Find multi-level abstractNum (heading numbering); prefer id=0 for
    # backwards-compatibility with 版式1 template, fall back to any with ≥2 levels.
    targets: list[ET.Element] = []
    fallbacks: list[ET.Element] = []
    for absn in root.findall(w_abstractNum):
        levels = absn.findall(w_lvl)
        if absn.get(w_abstractNumId) == "0" and len(levels) >= 2:
            targets.append(absn)
        elif len(levels) >= 2:
            fallbacks.append(absn)
    if not targets:
        targets = fallbacks
    if not targets:
        return numbering_xml

    changed = False
    for target in targets:
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


def normalize_list_indents(numbering_xml: bytes) -> bytes:
    """将 pandoc 生成的列表缩进调整至与 LaTeX PDF 对齐。"""
    if not numbering_xml:
        return numbering_xml

    ns = _collect_ns(numbering_xml)
    if "w" not in ns:
        return numbering_xml
    _register_ns(ns)
    w_uri = ns["w"]
    w_abstractNum = f"{{{w_uri}}}abstractNum"
    w_abstractNumId = f"{{{w_uri}}}abstractNumId"
    w_lvl = f"{{{w_uri}}}lvl"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_numFmt = f"{{{w_uri}}}numFmt"
    w_pPr = f"{{{w_uri}}}pPr"
    w_ind = f"{{{w_uri}}}ind"
    w_val = f"{{{w_uri}}}val"
    w_left = f"{{{w_uri}}}left"
    w_hanging = f"{{{w_uri}}}hanging"
    w_firstLine = f"{{{w_uri}}}firstLine"
    w_firstLineChars = f"{{{w_uri}}}firstLineChars"
    w_hangingChars = f"{{{w_uri}}}hangingChars"

    root = ET.fromstring(numbering_xml)
    list_numfmts = {"bullet", "decimal", "lowerLetter", "lowerRoman"}
    # Calibrated against the current SWUN DOCX->PDF output so level-0 list
    # body text lands on the same x coordinate as the LaTeX PDF.
    left_shift = 362
    min_left = 358
    target_hanging = "360"
    changed = 0

    for absn in root.findall(w_abstractNum):
        abs_id = absn.get(w_abstractNumId, "")
        if abs_id in {"0", _HEADING_ABSTRACT_NUM_ID}:
            continue

        lvls = absn.findall(w_lvl)
        if not lvls:
            continue

        sample_fmt = None
        for lvl in lvls:
            numfmt = lvl.find(w_numFmt)
            if numfmt is not None:
                sample_fmt = numfmt.get(w_val, "")
                if sample_fmt:
                    break
        if sample_fmt not in list_numfmts:
            continue

        for lvl in lvls:
            ilvl_raw = lvl.get(w_ilvl, "0")
            try:
                ilvl = int(ilvl_raw)
            except ValueError:
                ilvl = 0

            pPr = lvl.find(w_pPr)
            if pPr is None:
                pPr = ET.SubElement(lvl, w_pPr)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)

            old_left = ind.get(w_left)
            try:
                base_left = int(old_left) if old_left is not None else 720 * (ilvl + 1)
            except ValueError:
                base_left = 720 * (ilvl + 1)

            ind.set(w_left, str(max(min_left, base_left - left_shift)))
            ind.set(w_hanging, target_hanging)
            for attr in (w_firstLine, w_firstLineChars, w_hangingChars):
                if attr in ind.attrib:
                    del ind.attrib[attr]
            changed += 1

    if changed:
        print(f"  [numbering] Normalized {changed} list level indent(s)")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def inject_heading_numbering(numbering_xml: bytes) -> bytes:
    """向 numbering.xml 注入多级章节编号定义（第X章 / X.Y / X.Y.Z）。"""
    ns2 = _collect_ns(numbering_xml)
    if "w" not in ns2:
        return numbering_xml
    _register_ns(ns2)
    w_uri = ns2["w"]

    root = ET.fromstring(numbering_xml)

    # Check if our abstractNum already exists
    for absn in root.findall(f"{{{w_uri}}}abstractNum"):
        if absn.get(f"{{{w_uri}}}abstractNumId") == _HEADING_ABSTRACT_NUM_ID:
            return numbering_xml  # Already injected

    # Parse abstractNum element
    absn_el = ET.fromstring(_HEADING_ABSTRACT_NUM_XML)

    # Word requires: all abstractNum BEFORE all num.
    # Find the index of the first w:num element and insert abstractNum before it.
    w_num_tag = f"{{{w_uri}}}num"
    insert_idx = len(root)  # default: end
    for i, child in enumerate(root):
        if child.tag == w_num_tag:
            insert_idx = i
            break
    root.insert(insert_idx, absn_el)

    # Append num entry at the end (after all other num elements)
    num_el = ET.SubElement(root, f"{{{w_uri}}}num")
    num_el.set(f"{{{w_uri}}}numId", _HEADING_NUM_ID)
    absn_ref = ET.SubElement(num_el, f"{{{w_uri}}}abstractNumId")
    absn_ref.set(f"{{{w_uri}}}val", _HEADING_ABSTRACT_NUM_ID)

    print(f"  [numbering] Injected heading abstractNum={_HEADING_ABSTRACT_NUM_ID} num={_HEADING_NUM_ID}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def bind_heading_styles_to_numbering(styles_xml: bytes) -> bytes:
    """为 Heading1/2/3 样式定义添加 numPr，绑定章节编号。"""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    if "w" not in sns:
        return styles_xml
    _register_ns(sns)
    w_uri = sns["w"]

    sroot = ET.fromstring(styles_xml)

    # Map: styleId -> (numId, ilvl)
    heading_bindings = {
        "1": ("0",),       # heading 1 -> ilvl=0
        "Heading2": ("1",),  # heading 2 -> ilvl=1
        "Heading3": ("2",),  # heading 3 -> ilvl=2
    }

    w_style = f"{{{w_uri}}}style"
    w_styleId = f"{{{w_uri}}}styleId"
    w_pPr = f"{{{w_uri}}}pPr"
    w_numPr = f"{{{w_uri}}}numPr"
    w_numId = f"{{{w_uri}}}numId"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_val = f"{{{w_uri}}}val"

    count = 0
    for s in sroot.findall(w_style):
        sid = s.get(w_styleId, "")
        if sid not in heading_bindings:
            continue

        ilvl_val = heading_bindings[sid][0]

        pPr = s.find(w_pPr)
        if pPr is None:
            pPr = ET.SubElement(s, w_pPr)

        # Remove existing numPr if any
        old_numPr = pPr.find(w_numPr)
        if old_numPr is not None:
            pPr.remove(old_numPr)

        # Add numPr
        numPr = ET.SubElement(pPr, w_numPr)
        ilvl_el = ET.SubElement(numPr, w_ilvl)
        ilvl_el.set(w_val, ilvl_val)
        numId_el = ET.SubElement(numPr, w_numId)
        numId_el.set(w_val, _HEADING_NUM_ID)

        count += 1

    if count:
        print(f"  [styles] Bound {count} heading style(s) to numId={_HEADING_NUM_ID}")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)


def number_paragraph_headings_in_main_body(ns: dict[str, str], body: ET.Element) -> int:
    """为正文中的 Heading5 标题写入显式 (n) 前缀，并降级为正文样式。"""
    w_p = _qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    prefix_re = re.compile(r"^\s*[（(]\d+[)）]\s*")

    in_main_body = False
    seq = 0
    touched = 0

    for el in list(body):
        if el.tag != w_p:
            continue

        style = _p_style(ns, el)
        txt = _p_text(ns, el).strip()

        if style == "1":
            if txt in stop_h1:
                in_main_body = False
                seq = 0
            elif txt and txt not in excluded_h1:
                in_main_body = True
                seq = 0
            continue

        if not in_main_body:
            continue

        if style in {"Heading2", "2", "Heading3", "3"}:
            seq = 0
            continue

        if style not in {"Heading5", "5"}:
            continue
        if not txt:
            continue

        base = prefix_re.sub("", txt).strip()
        if not base:
            continue
        seq += 1
        _set_paragraph_text(ns, el, f"({seq}) {base}")
        # Demote from Heading5 to Normal body text style so the paragraph
        # renders with the same formatting as surrounding body paragraphs.
        pPr = el.find(_qn(ns, "w", "pPr"))
        if pPr is not None:
            ps = pPr.find(_qn(ns, "w", "pStyle"))
            if ps is not None:
                ps.set(_qn(ns, "w", "val"), "a")
        touched += 1

    return touched


# ---------------------------------------------------------------------------
# 后处理
# ---------------------------------------------------------------------------

def strip_numbering_from_backmatter_headings(
    ns: dict[str, str], body: ET.Element
) -> None:
    """为后置章节（致谢、参考文献等）的 Heading1 添加 numId=0，抑制章节编号。"""
    excluded_titles: set[str] = {
        "致谢",
        "参考文献",
        "攻读硕士学位期间所取得的相关科研成果",
    }

    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    w_numPr = _qn(ns, "w", "numPr")
    w_numId = _qn(ns, "w", "numId")

    fixed: list[str] = []
    for p in body.iter(w_p):
        pPr = p.find(w_pPr)
        if pPr is None:
            continue
        ps = pPr.find(w_pStyle)
        if ps is None:
            continue
        if ps.get(w_val) != "1":  # Heading 1 styleId is "1"
            continue

        text = _p_text(ns, p).strip()
        if text not in excluded_titles:
            continue

        # Ensure numPr exists with numId=0 to override style-level numbering
        numPr = pPr.find(w_numPr)
        if numPr is None:
            numPr = ET.SubElement(pPr, w_numPr)
        numId = numPr.find(w_numId)
        if numId is None:
            numId = ET.SubElement(numPr, w_numId)
        if numId.get(w_val) != "0":
            numId.set(w_val, "0")
            fixed.append(text)

    if fixed:
        for title in fixed:
            print(f"  [backmatter] Disabled numbering for: {title!r}")
    else:
        print("  [backmatter] Backmatter headings already have numbering disabled")


def remove_docgrid_lines_type(ns: dict[str, str], body: ET.Element) -> None:
    """删除所有 sectPr 中 docGrid 的 type='lines'，防止行间距膨胀。"""
    w_sectPr = _qn(ns, "w", "sectPr")
    w_docGrid = _qn(ns, "w", "docGrid")
    w_type = _qn(ns, "w", "type")
    count = 0
    for sp in body.iter(w_sectPr):
        grid = sp.find(w_docGrid)
        if grid is not None and w_type in grid.attrib:
            del grid.attrib[w_type]
            count += 1
    if count:
        print(f"  [docGrid] Removed type='lines' from {count} section(s)")


# ---------------------------------------------------------------------------
# 别名（保留下划线前缀以兼容现有调用方）
# ---------------------------------------------------------------------------
_ensure_indent_for_body_paragraphs = ensure_indent_for_body_paragraphs
_ensure_hanging_indent_for_bibliography = ensure_hanging_indent_for_bibliography
_align_styles_to_reference = align_styles_to_reference
_collect_style_ids = collect_style_ids
_normalize_unknown_pstyles = normalize_unknown_pstyles
_fix_numbering_isLgl = fix_numbering_isLgl
_normalize_list_indents = normalize_list_indents
_inject_heading_numbering = inject_heading_numbering
_bind_heading_styles_to_numbering = bind_heading_styles_to_numbering
_number_paragraph_headings_in_main_body = number_paragraph_headings_in_main_body
_strip_numbering_from_backmatter_headings = strip_numbering_from_backmatter_headings
_remove_docgrid_lines_type = remove_docgrid_lines_type


__all__ = [
    # 公共 API
    "ensure_indent_for_body_paragraphs",
    "ensure_hanging_indent_for_bibliography",
    "align_styles_to_reference",
    "collect_style_ids",
    "normalize_unknown_pstyles",
    "fix_numbering_isLgl",
    "normalize_list_indents",
    "inject_heading_numbering",
    "bind_heading_styles_to_numbering",
    "number_paragraph_headings_in_main_body",
    "strip_numbering_from_backmatter_headings",
    "remove_docgrid_lines_type",
    # 常量（供外部模块引用）
    "_HEADING_NUM_ID",
    "_HEADING_ABSTRACT_NUM_ID",
]
