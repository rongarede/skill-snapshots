#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OOXML 原语工具集 — 从 docx_builder.py 中提取的低层 OOXML 操作函数。

本模块提供无副作用的纯 OOXML 原语，供上层模块复用。
所有函数均为公共 API（无下划线前缀）。
"""

from __future__ import annotations

import copy
import io
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


# ---------------------------------------------------------------------------
# XML namespace tools
# ---------------------------------------------------------------------------

def collect_ns(xml_bytes: bytes) -> dict[str, str]:
    """收集 XML 文档中所有命名空间前缀到 URI 的映射。"""
    ns: dict[str, str] = {}
    for event, item in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = item
        ns[prefix or ""] = uri
    return ns


def register_ns(ns: dict[str, str]) -> None:
    """将命名空间前缀注册到 ElementTree，使序列化时保留原前缀。"""
    for prefix, uri in ns.items():
        if prefix:  # ElementTree doesn't support registering default namespace cleanly.
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                # Skip invalid prefixes; Word namespaces should be fine.
                pass


def qn(ns: dict[str, str], prefix: str, local: str) -> str:
    """构造 Clark 格式的限定名 {uri}local。"""
    uri = ns[prefix]
    return f"{{{uri}}}{local}"


# ---------------------------------------------------------------------------
# Paragraph read / judge helpers
# ---------------------------------------------------------------------------

def p_text(ns: dict[str, str], p: ET.Element) -> str:
    """提取段落中所有 w:t 文本节点的拼接字符串。"""
    w_t = qn(ns, "w", "t")
    parts = []
    for t in p.iter(w_t):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def ensure_ppr(ns: dict[str, str], p: ET.Element) -> ET.Element:
    """确保段落存在 w:pPr 子元素，不存在则创建并插入到首位。"""
    w_pPr = qn(ns, "w", "pPr")
    pPr = p.find(w_pPr)
    if pPr is None:
        pPr = ET.Element(w_pPr)
        p.insert(0, pPr)
    return pPr


def p_style(ns: dict[str, str], p: ET.Element) -> str | None:
    """返回段落的样式 ID（w:pStyle/@w:val），无样式则返回 None。"""
    w_pPr = qn(ns, "w", "pPr")
    w_pStyle = qn(ns, "w", "pStyle")
    w_val = qn(ns, "w", "val")
    pPr = p.find(w_pPr)
    if pPr is None:
        return None
    pStyle = pPr.find(w_pStyle)
    if pStyle is None:
        return None
    return pStyle.get(w_val)


def p_has_page_break(ns: dict[str, str], p: ET.Element) -> bool:
    """判断段落是否包含手动分页符（w:br @w:type=page）。"""
    w_br = qn(ns, "w", "br")
    w_type = qn(ns, "w", "type")
    for br in p.iter(w_br):
        if br.get(w_type) == "page":
            return True
    return False


def p_has_sectPr(ns: dict[str, str], p: ET.Element) -> bool:
    """判断段落 pPr 中是否包含 w:sectPr（节属性）。"""
    w_sectPr = qn(ns, "w", "sectPr")
    pPr = p.find(qn(ns, "w", "pPr"))
    return pPr is not None and pPr.find(w_sectPr) is not None


# ---------------------------------------------------------------------------
# Page break / section construction
# ---------------------------------------------------------------------------

def make_page_break_p(ns: dict[str, str]) -> ET.Element:
    """创建仅含手动分页符的段落元素。"""
    w_p = qn(ns, "w", "p")
    w_r = qn(ns, "w", "r")
    w_br = qn(ns, "w", "br")
    w_type = qn(ns, "w", "type")
    p = ET.Element(w_p)
    r = ET.SubElement(p, w_r)
    br = ET.SubElement(r, w_br)
    br.set(w_type, "page")
    return p


def get_body_sectPr(ns: dict[str, str], body: ET.Element) -> ET.Element | None:
    """获取文档体的节属性元素（w:sectPr）。

    优先返回作为 w:body 直接子元素的 sectPr；
    退而在最后一个段落的 pPr 中查找。
    """
    # Usually a direct child of <w:body>.
    w_sectPr = qn(ns, "w", "sectPr")
    for el in list(body):
        if el.tag == w_sectPr:
            return el
    # Fallback: sectPr in the last paragraph pPr.
    w_p = qn(ns, "w", "p")
    for el in reversed(list(body)):
        if el.tag != w_p:
            continue
        pPr = el.find(qn(ns, "w", "pPr"))
        if pPr is None:
            continue
        sectPr = pPr.find(w_sectPr)
        if sectPr is not None:
            return sectPr
    return None


def set_sect_pgnum(
    ns: dict[str, str], sectPr: ET.Element, fmt: str, start: int | None
) -> None:
    """设置节的页码格式和起始页码（w:pgNumType）。"""
    w_pgNumType = qn(ns, "w", "pgNumType")
    w_fmt = qn(ns, "w", "fmt")
    w_start = qn(ns, "w", "start")
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


def set_sect_break_next_page(ns: dict[str, str], sectPr: ET.Element) -> None:
    """将节的分隔类型设为 nextPage（下一页换节）。"""
    w_type = qn(ns, "w", "type")
    w_val = qn(ns, "w", "val")
    t = sectPr.find(w_type)
    if t is None:
        t = ET.Element(w_type)
        sectPr.insert(0, t)
    t.set(w_val, "nextPage")


def make_section_break_paragraph(ns: dict[str, str], sectPr: ET.Element) -> ET.Element:
    """创建含节属性的分节段落（pPr/sectPr 形式）。"""
    w_p = qn(ns, "w", "p")
    w_pPr = qn(ns, "w", "pPr")
    w_sectPr = qn(ns, "w", "sectPr")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    # sectPr must be a child of pPr for a section break paragraph.
    sp = copy.deepcopy(sectPr)
    sp.tag = w_sectPr
    pPr.append(sp)
    return p


def make_unnumbered_heading1(ns: dict[str, str], title: str) -> ET.Element:
    """创建无编号的一级标题段落（居中、禁止自动编号）。"""
    w_p = qn(ns, "w", "p")
    w_pPr = qn(ns, "w", "pPr")
    w_pStyle = qn(ns, "w", "pStyle")
    w_jc = qn(ns, "w", "jc")
    w_val = qn(ns, "w", "val")
    w_numPr = qn(ns, "w", "numPr")
    w_numId = qn(ns, "w", "numId")
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")

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


def remove_page_break_before(ns: dict[str, str], p: ET.Element) -> None:
    """移除段落 pPr 中的 w:pageBreakBefore 属性。"""
    w_pageBreakBefore = qn(ns, "w", "pageBreakBefore")
    pPr = p.find(qn(ns, "w", "pPr"))
    if pPr is None:
        return
    pbb = pPr.find(w_pageBreakBefore)
    if pbb is not None:
        pPr.remove(pbb)


# ---------------------------------------------------------------------------
# Paragraph property setters
# ---------------------------------------------------------------------------

def p_has_drawing(ns: dict[str, str], p: ET.Element) -> bool:
    """判断段落是否包含内嵌图片（w:drawing 或 w:pict）。"""
    w_drawing = qn(ns, "w", "drawing")
    w_pict = qn(ns, "w", "pict")
    return p.find(f".//{w_drawing}") is not None or p.find(f".//{w_pict}") is not None


def set_para_center(ns: dict[str, str], p: ET.Element) -> None:
    """将段落对齐方式设为居中（w:jc=center）。"""
    w_jc = qn(ns, "w", "jc")
    w_val = qn(ns, "w", "val")
    pPr = ensure_ppr(ns, p)
    jc = pPr.find(w_jc)
    if jc is None:
        jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")


def set_para_keep_next(ns: dict[str, str], p: ET.Element) -> None:
    """为段落添加 w:keepNext（与下段同页）属性。"""
    w_keepNext = qn(ns, "w", "keepNext")
    pPr = ensure_ppr(ns, p)
    if pPr.find(w_keepNext) is None:
        ET.SubElement(pPr, w_keepNext)


def set_para_keep_lines(ns: dict[str, str], p: ET.Element) -> None:
    """为段落添加 w:keepLines（段落内所有行同页）属性。"""
    w_keepLines = qn(ns, "w", "keepLines")
    pPr = ensure_ppr(ns, p)
    if pPr.find(w_keepLines) is None:
        ET.SubElement(pPr, w_keepLines)


def set_para_tabs_for_equation(ns: dict[str, str], p: ET.Element, text_w: int) -> None:
    """设置公式编号用的居中+右对齐制表位。"""
    w_tabs = qn(ns, "w", "tabs")
    w_tab = qn(ns, "w", "tab")
    w_val = qn(ns, "w", "val")
    w_pos = qn(ns, "w", "pos")

    mid = max(0, text_w // 2)
    right = max(0, text_w)

    pPr = ensure_ppr(ns, p)
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


def make_run_tab(ns: dict[str, str]) -> ET.Element:
    """创建仅含制表符的 run 元素（w:r/w:tab）。"""
    w_r = qn(ns, "w", "r")
    w_tab = qn(ns, "w", "tab")
    r = ET.Element(w_r)
    ET.SubElement(r, w_tab)
    return r


def make_run_text(ns: dict[str, str], text: str) -> ET.Element:
    """创建含指定文本的 run 元素（w:r/w:t）。"""
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")
    r = ET.Element(w_r)
    t = ET.SubElement(r, w_t)
    t.text = text
    return r


def set_para_single_line_spacing(ns: dict[str, str], p: ET.Element) -> None:
    """将段落行距设为单倍行距（240 twips，lineRule=auto）。"""
    w_spacing = qn(ns, "w", "spacing")
    pPr = ensure_ppr(ns, p)
    sp = pPr.find(w_spacing)
    if sp is None:
        sp = ET.SubElement(pPr, w_spacing)
    sp.set(qn(ns, "w", "line"), "240")
    sp.set(qn(ns, "w", "lineRule"), "auto")


def clear_para_first_indent(ns: dict[str, str], p: ET.Element) -> None:
    """清除段落首行缩进（覆盖 Normal 样式的缩进设置）。"""
    w_ind = qn(ns, "w", "ind")
    pPr = ensure_ppr(ns, p)
    ind = pPr.find(w_ind)
    if ind is None:
        ind = ET.SubElement(pPr, w_ind)
    ind.set(qn(ns, "w", "firstLine"), "0")
    ind.set(qn(ns, "w", "firstLineChars"), "0")
    # Also remove hanging indent if present
    for attr in ("hanging", "hangingChars"):
        key = qn(ns, "w", attr)
        if key in ind.attrib:
            del ind.attrib[key]


def clear_paragraph_runs_and_text(ns: dict[str, str], p: ET.Element) -> None:
    """移除段落中所有 w:r 子元素（保留数学公式、图片等）。"""
    w_r = qn(ns, "w", "r")
    for r in list(p.findall(w_r)):
        p.remove(r)


# ---------------------------------------------------------------------------
# Other paragraph tools
# ---------------------------------------------------------------------------

def make_empty_para(ns: dict[str, str], style: str = "a") -> ET.Element:
    """创建指定样式的空段落元素。"""
    w_p = qn(ns, "w", "p")
    w_pPr = qn(ns, "w", "pPr")
    w_pStyle = qn(ns, "w", "pStyle")
    w_val = qn(ns, "w", "val")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)
    return p


def set_p_style(ns: dict[str, str], p: ET.Element, style: str) -> None:
    """设置段落样式 ID（w:pStyle/@w:val）。"""
    w_pStyle = qn(ns, "w", "pStyle")
    w_val = qn(ns, "w", "val")
    pPr = ensure_ppr(ns, p)
    ps = pPr.find(w_pStyle)
    if ps is None:
        ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)


def set_paragraph_text(ns: dict[str, str], p: ET.Element, txt: str) -> None:
    """清空段落现有 run 并写入新文本。"""
    clear_paragraph_runs_and_text(ns, p)
    p.append(make_run_text(ns, txt))


def block_has_drawing(ns: dict[str, str], el: ET.Element) -> bool:
    """判断任意 OOXML 块元素（段落或表格单元格等）是否包含图片。"""
    w_drawing = qn(ns, "w", "drawing")
    w_pict = qn(ns, "w", "pict")
    return el.find(f".//{w_drawing}") is not None or el.find(f".//{w_pict}") is not None


def is_centered_paragraph(ns: dict[str, str], p: ET.Element) -> bool:
    """判断段落是否设置了居中对齐（w:jc=center）。"""
    w_jc = qn(ns, "w", "jc")
    w_val = qn(ns, "w", "val")
    pPr = p.find(qn(ns, "w", "pPr"))
    if pPr is None:
        return False
    jc = pPr.find(w_jc)
    return jc is not None and (jc.get(w_val) or "") == "center"


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------

def run_cmd(cmd: list[str], cwd: Path) -> None:
    """运行外部命令，失败时抛出异常（subprocess.run 的简单封装）。"""
    subprocess.run(cmd, cwd=str(cwd), check=True)
