#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
封面 / 摘要 / 目录 / 分节模块。

从 docx_builder.py 提取的公共 API：
- prepend_template_cover_pages      封面页插入
- insert_abstract_chapters_and_sections  摘要章节与分节符
- insert_abstract_keywords          关键词行插入
- insert_toc_before_first_chapter   目录字段插入
- add_page_breaks_before_h1         各章节前分页
- ensure_update_fields_in_settings  settings.xml 自动更新 TOC
- split_keywords                    关键词切分辅助
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import zipfile

try:
    from utils.ooxml import (
        qn,
        p_text,
        p_style,
        ensure_ppr,
        set_sect_pgnum,
        set_sect_break_next_page,
        make_section_break_paragraph,
        make_unnumbered_heading1,
        remove_page_break_before,
        make_page_break_p,
        p_has_sectPr,
        make_empty_para,
        make_run_text,
        clear_paragraph_runs_and_text,
        set_para_keep_lines,
        set_para_keep_next,
        collect_ns,
        register_ns,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.utils.ooxml import (
        qn,
        p_text,
        p_style,
        ensure_ppr,
        set_sect_pgnum,
        set_sect_break_next_page,
        make_section_break_paragraph,
        make_unnumbered_heading1,
        remove_page_break_before,
        make_page_break_p,
        p_has_sectPr,
        make_empty_para,
        make_run_text,
        clear_paragraph_runs_and_text,
        set_para_keep_lines,
        set_para_keep_next,
        collect_ns,
        register_ns,
    )


# ====================  关键词切分  ====================

def split_keywords(raw: str, max_groups: int = 4, lang: str = "cn") -> str:
    """
    将关键词字符串切分为 3-4 组（默认最多 4 组），不丢弃信息。

    超出 max_groups 时，尾部条目合并为一组。
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

    def split_en_by_top_level_commas(text: str) -> list[str]:
        parts: list[str] = []
        buf: list[str] = []
        depth = 0
        for ch in text:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            if ch in {",", "，"} and depth == 0:
                part = "".join(buf).strip(" ;；,，")
                if part:
                    parts.append(part)
                buf = []
                continue
            buf.append(ch)
        tail = "".join(buf).strip(" ;；,，")
        if tail:
            parts.append(tail)
        return parts

    # 中文：按常见分隔符切分；英文：优先用分号，无分号才用逗号（避免切破括号内内容）
    if lang == "en":
        text = raw.strip()
        if ";" in text or "；" in text:
            parts = [
    p.strip(" ;；,，") for p in re.split(
        r"[;；]\s*",
         text) if p.strip(" ;；,，")]
        else:
            parts = split_en_by_top_level_commas(text)
    else:
        parts = [p.strip() for p in re.split(r"[;；,，]\s*", raw) if p.strip()]
    if len(parts) > max_groups:
        head = parts[: max_groups - 1]
        tail = parts[max_groups - 1:]
        merged = merge_tail_en(tail) if lang == "en" else merge_tail_cn(tail)
        parts = [p for p in head + [merged] if p]
    return "；".join(parts)


# ====================  封面  ====================

def prepend_template_cover_pages(
    ns: dict[str, str],
    body: ET.Element,
    template_docx: Path,
    *,
    marker_text: str = "研究生学位论文排版格式（版式1）",
    end_before_text: str = "学位论文版权使用授权书",
) -> None:
    """
    从官方模板 docx 中将封面页（前两页）原样插入到正文开头。

    幂等性：若前 80 个元素中已出现 marker_text，则跳过。
    截止策略：找到"日期：…年…月…日"行或 end_before_text 行为止。
    """
    w_p = qn(ns, "w", "p")

    # 幂等检查：marker 已在文档开头，说明封面已插入
    children = list(body)
    early = []
    for el in children[:80]:
        if el.tag != w_p:
            continue
        early.append(p_text(ns, el))
    if marker_text in "".join(early):
        return

    if not template_docx.exists():
        return

    with zipfile.ZipFile(template_docx, "r") as zt:
        t_doc_xml = zt.read("word/document.xml")
    t_ns = collect_ns(t_doc_xml)
    if "w" not in t_ns:
        return
    register_ns(t_ns)

    t_root = ET.fromstring(t_doc_xml)
    t_body = t_root.find(qn(t_ns, "w", "body"))
    if t_body is None:
        return

    t_children = list(t_body)
    cutoff = None
    # 优先按"日期：  年  月  日"行截断（SWUN 模板第三页起始行）
    date_line_re = re.compile(r"^日期：[\s\u3000]*年[\s\u3000]*月[\s\u3000]*日$")
    for i, el in enumerate(t_children):
        if el.tag != qn(t_ns, "w", "p"):
            continue
        txt = p_text(t_ns, el).strip()
        if date_line_re.match(txt):
            cutoff = i
            break
        if end_before_text in txt:
            cutoff = i
            break
    if cutoff is None or cutoff <= 0:
        return

    # 将模板封面元素插入到正文开头
    insert_at = 0
    for el in t_children[:cutoff]:
        body.insert(insert_at, copy.deepcopy(el))
        insert_at += 1

    # 在论文正文第一段添加 pageBreakBefore，避免 LibreOffice 产生多余空白页
    w_pageBreakBefore = qn(ns, "w", "pageBreakBefore")
    children = list(body)
    for i in range(insert_at, len(children)):
        el = children[i]
        if el.tag != w_p:
            continue
        if not p_text(ns, el).strip():
            continue
        pPr = ensure_ppr(ns, el)
        if pPr.find(w_pageBreakBefore) is None:
            ET.SubElement(pPr, w_pageBreakBefore)
        break


def strip_template_body_leak_after_front_matter(
    ns: dict[str, str],
    body: ET.Element,
) -> int:
    """
    清理参考模板正文泄漏：
    - 删除“摘要”之后误混入的封面/声明段落（常见为样式 12）
    - 同时清理明显的声明关键词段落（原创性声明/作者签名等）

    返回删除段落数。
    """
    w_p = qn(ns, "w", "p")
    children = list(body)

    cn_h_idx: int | None = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if p_style(ns, el) == "1" and p_text(ns, el).strip() == "摘要":
            cn_h_idx = i
            break
    if cn_h_idx is None:
        return 0

    marker_re = re.compile(
        r"(专业学位硕士学位论文|原创性声明|学位论文版权使用授权书|作者签名|题\s*目|作\s*者|论文定稿日期)"
    )
    to_remove: list[ET.Element] = []

    for i in range(cn_h_idx + 1, len(children)):
        el = children[i]
        if el.tag != w_p:
            continue
        txt = p_text(ns, el).strip()
        st = p_style(ns, el)
        # 核心规则：摘要之后不应再出现模板封面样式 12
        if st == "12":
            to_remove.append(el)
            continue
        if txt and marker_re.search(txt):
            to_remove.append(el)

    for el in to_remove:
        if el in body:
            body.remove(el)
    return len(to_remove)


# ====================  摘要章节与分节符  ====================

def insert_abstract_chapters_and_sections(
    ns: dict[str, str], body: ET.Element, sectPr_proto: ET.Element
) -> None:
    """
    要求：
    - 中英文摘要各作为独立的一级章节（Heading 1，无编号）。
    - 目录页脚使用罗马数字起始页；正文页脚使用阿拉伯数字。

    实现：
    - 在中文摘要前插入分节符，开始第 2 节。
    - 将"摘要"和"Abstract"作为无编号 Heading 1 插入。
    - 在英文摘要后插入分节符，结束第 2 节，pgNumType=lowerRoman start=1。
    - 最终节（正文）使用 decimal start=1。
    """
    w_p = qn(ns, "w", "p")

    cn_anchors = (
        "在车联网（V2X）环境中",
        "车联网（V2X）环境下",
        "车联网(V2X)环境下",
        "车联网（V2X）",
        # 以下锚点覆盖摘要改写后不以"车联网(V2X)环境"开头的情况
        "近年来，区块链共识协议",
        "面向车联网环境的拜占庭容错共识",
        "拜占庭容错共识已受到广泛关注",
    )
    en_anchors = (
        "In the Vehicular-to-Everything",
        "In Vehicle-to-Everything",
        "In the Vehicle-to-Everything",
        "Vehicle-to-Everything (V2X)",
    )
    front_h1 = {"摘要", "Abstract", "目录"}

    def find_heading_idx(title: str, start: int = 0) -> int | None:
        children = list(body)
        for i in range(start, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_style(ns, el) == "1" and p_text(ns, el).strip() == title:
                return i
        return None

    def find_first_main_h1(start: int = 0) -> int | None:
        children = list(body)
        for i in range(start, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_style(ns, el) != "1":
                continue
            txt = p_text(ns, el).strip()
            if txt and txt not in front_h1:
                return i
        return None

    def first_nonempty_para(start: int, end: int | None = None) -> int | None:
        children = list(body)
        lim = len(children) if end is None else min(end, len(children))
        for i in range(start, lim):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_text(ns, el).strip():
                return i
        return None

    def find_anchor_para(
        anchors: tuple[str, ...], start: int = 0, end: int | None = None
    ) -> int | None:
        children = list(body)
        lim = len(children) if end is None else min(end, len(children))
        anchors_l = tuple(a.lower() for a in anchors)
        for i in range(start, lim):
            el = children[i]
            if el.tag != w_p:
                continue
            txt = p_text(ns, el)
            if not txt:
                continue
            txt_l = txt.lower()
            if any(a in txt_l for a in anchors_l):
                return i
        return None

    def fallback_cn_para(start: int, end: int) -> int | None:
        # 模板封面页（专业学位硕士学位论文封面 + 原创性声明）使用的段落样式集合
        # 这些样式不属于摘要正文，必须跳过，否则回退逻辑会错误定位到封面文字
        _cover_styles = {"12"}
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_style(ns, el) == "1":
                continue
            if p_style(ns, el) in _cover_styles:
                continue
            txt = p_text(ns, el).strip()
            if len(txt) >= 8 and re.search(r"[\u4e00-\u9fff]", txt):
                return i
        return None

    def fallback_en_para(start: int, end: int) -> int | None:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_style(ns, el) == "1":
                continue
            txt = p_text(ns, el).strip()
            if not txt:
                continue
            letters = len(re.findall(r"[A-Za-z]", txt))
            if letters >= 20 and not re.search(r"[\u4e00-\u9fff]", txt):
                return i
        return None

    children = list(body)
    scan_end = find_first_main_h1(0)
    if scan_end is None:
        scan_end = len(children)

    # 定位中文摘要段落
    cn_idx = find_anchor_para(cn_anchors, 0, scan_end)
    if cn_idx is None:
        cn_h = find_heading_idx("摘要", 0)
        if cn_h is not None:
            cn_idx = first_nonempty_para(cn_h + 1, scan_end)
    if cn_idx is None:
        # 回退：最后一个封面分节符后的第一段中文段落
        scan_start = 0
        for i in range(0, scan_end):
            el = children[i]
            if el.tag == w_p and p_has_sectPr(ns, el):
                scan_start = i + 1
        cn_idx = fallback_cn_para(scan_start, scan_end)
    if cn_idx is None:
        return

    # 若中文摘要段落前已有"摘要"标题，则将插入点提前到该标题处
    if cn_idx > 0:
        j = cn_idx - 1
        while j >= 0:
            prev = children[j]
            if prev.tag != w_p:
                j -= 1
                continue
            prev_txt = p_text(ns, prev).strip()
            if not prev_txt:
                j -= 1
                continue
            if p_style(ns, prev) == "1" and prev_txt == "摘要":
                cn_idx = j
            break

    children = list(body)
    remove_page_break_before(ns, children[cn_idx])

    # 定位英文摘要段落（在中文摘要之后查找）
    en_idx = find_anchor_para(en_anchors, cn_idx, scan_end)
    if en_idx is None:
        en_h = find_heading_idx("Abstract", cn_idx)
        if en_h is not None:
            en_idx = first_nonempty_para(en_h + 1, scan_end)
    if en_idx is None:
        en_idx = fallback_en_para(cn_idx + 1, scan_end)
    if en_idx is None:
        return
    children = list(body)
    remove_page_break_before(ns, children[en_idx])

    # 在中文摘要前插入分节符（结束封面节）
    sect1 = copy.deepcopy(sectPr_proto)
    set_sect_break_next_page(ns, sect1)
    set_sect_pgnum(ns, sect1, fmt="decimal", start=None)
    sb_before = make_section_break_paragraph(ns, sect1)

    body.insert(cn_idx, sb_before)
    children = list(body)
    has_cn_h_after = False
    j = cn_idx + 1
    while j < len(children):
        el = children[j]
        if el.tag != w_p:
            j += 1
            continue
        txt = p_text(ns, el).strip()
        if not txt:
            j += 1
            continue
        if p_style(ns, el) == "1" and txt == "摘要":
            has_cn_h_after = True
        break
    if not has_cn_h_after:
        body.insert(cn_idx + 1, make_unnumbered_heading1(ns, "摘要"))

    # 重新计算索引（插入后偏移已变）
    en_h2 = find_heading_idx("Abstract", cn_idx + 1)
    if en_h2 is None:
        en_idx2 = find_anchor_para(en_anchors, cn_idx + 1, scan_end)
        if en_idx2 is None:
            en_idx2 = fallback_en_para(cn_idx + 1, scan_end)
        if en_idx2 is None:
            return
        body.insert(en_idx2, make_unnumbered_heading1(ns, "Abstract"))
        en_h2 = en_idx2

    # 在英文摘要标题前插入分节符（结束中文摘要节 → lowerRoman 继续计数）
    # 使用分节符替代 pageBreakBefore，这样 CN 摘要和 EN 摘要各有独立 section，
    # 以便 header_handler 为两者分配不同的页眉。
    sect_cn_end = copy.deepcopy(sectPr_proto)
    set_sect_break_next_page(ns, sect_cn_end)
    set_sect_pgnum(ns, sect_cn_end, fmt="lowerRoman", start=None)
    sb_cn_end = make_section_break_paragraph(ns, sect_cn_end)
    body.insert(en_h2, sb_cn_end)

    # 移除英文摘要标题上残留的 pageBreakBefore（已由分节符替代）
    en_h2_el = list(body)[en_h2 + 1]  # +1：刚插入了分节符，索引偏移
    w_pageBreakBefore = qn(ns, "w", "pageBreakBefore")
    pPr_en = ensure_ppr(ns, en_h2_el)
    pbf = pPr_en.find(w_pageBreakBefore)
    if pbf is not None:
        pPr_en.remove(pbf)

    # 找到英文摘要标题后第一个正文段落（重新定位，因为插入了分节符）
    en_h2_new = en_h2 + 1  # 分节符占了 en_h2 位置，Abstract heading 后移 1
    main_h1_after_en = find_first_main_h1(en_h2_new + 1)
    en_p_idx = first_nonempty_para(en_h2_new + 1, main_h1_after_en)
    if en_p_idx is None:
        return

    # 在第一章标题前插入节尾分节符，结束英文摘要节（lowerRoman，继续计数）
    break_idx = main_h1_after_en if main_h1_after_en is not None else (
        en_p_idx + 1)

    sect2 = copy.deepcopy(sectPr_proto)
    set_sect_break_next_page(ns, sect2)
    set_sect_pgnum(ns, sect2, fmt="lowerRoman", start=None)
    sb_after = make_section_break_paragraph(ns, sect2)
    body.insert(break_idx, sb_after)


# ====================  关键词  ====================

def insert_abstract_keywords(
    ns: dict[str, str],
    body: ET.Element,
    cn_keywords: str | None,
    en_keywords: str | None,
) -> None:
    """
    在中英文摘要末尾各插入关键词行：
    - 空一行后插入关键词段落
    - 默认最多 4 组关键词
    """
    w_p = qn(ns, "w", "p")

    def _find_heading_idx(title: str) -> int | None:
        for i, el in enumerate(list(body)):
            if el.tag != w_p:
                continue
            if p_style(ns, el) == "1" and p_text(ns, el).strip() == title:
                return i
        return None

    def _already_has_kw(start: int, end: int, marker: str) -> bool:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if marker in p_text(ns, el):
                return True
        return False

    def _insert_kw_block(after_idx: int, line: str, *, keep_with_prev: bool = False) -> None:
        # 空行 + 关键词段落
        p = make_empty_para(ns, "a")
        clear_paragraph_runs_and_text(ns, p)
        p.append(make_run_text(ns, line))
        set_para_keep_lines(ns, p)
        blank = make_empty_para(ns, "a")
        if keep_with_prev:
            set_para_keep_next(ns, blank)
        body.insert(after_idx + 1, blank)
        body.insert(after_idx + 2, p)

    children = list(body)
    cn_h = _find_heading_idx("摘要")
    en_h = _find_heading_idx("Abstract")
    if cn_h is None or en_h is None or cn_h >= en_h:
        return

    # 中文关键词：插入在"Abstract"标题之前，中文摘要最后一段之后
    if cn_keywords:
        if not _already_has_kw(cn_h, en_h, "关键词"):
            cn_kw = split_keywords(cn_keywords, max_groups=4, lang="cn")
            last = None
            children = list(body)
            for i in range(en_h - 1, cn_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                _insert_kw_block(last, f"关键词：{cn_kw}")

    # 英文关键词：插入在英文摘要节尾分节符之前，或下一个 Heading 1 之前
    if en_keywords:
        # 可能已有插入偏移，重新定位
        children = list(body)
        en_h = _find_heading_idx("Abstract")
        if en_h is None:
            return
        end = len(children)
        for i in range(en_h + 1, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if p_has_sectPr(ns, el):
                end = i
                break
            if p_style(ns, el) == "1":
                end = i
                break

        if not _already_has_kw(en_h, end, "Keywords"):
            en_kw = split_keywords(en_keywords, max_groups=4, lang="en")
            last = None
            children = list(body)
            for i in range(end - 1, en_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                _insert_kw_block(
                    last,
                    f"Keywords: {en_kw.replace('；', '; ')}",
                    keep_with_prev=True,
                )
                # 让英文摘要最后一段尽量与关键词同行，避免“关键词尾部独占新页”。
                children2 = list(body)
                if 0 <= last < len(children2):
                    prev_p = children2[last]
                    if prev_p.tag == w_p:
                        set_para_keep_next(ns, prev_p)


# ====================  settings.xml 自动更新 TOC  ====================

def ensure_update_fields_in_settings(
    ns: dict[str, str], settings_xml: bytes) -> bytes:
    """在 settings.xml 中添加 updateFields 以支持打开时自动更新 TOC。"""
    settings_root = ET.fromstring(settings_xml)
    w_updateFields = qn(ns, "w", "updateFields")
    w_val = qn(ns, "w", "val")

    # 已存在则直接返回
    if settings_root.find(w_updateFields) is not None:
        return settings_xml

    # 在 w:compat 后插入，否则追加到末尾
    w_compat = qn(ns, "w", "compat")
    compat = settings_root.find(w_compat)

    update_el = ET.Element(w_updateFields)
    update_el.set(w_val, "true")

    if compat is not None:
        idx = list(settings_root).index(compat)
        settings_root.insert(idx + 1, update_el)
    else:
        settings_root.append(update_el)

    return ET.tostring(settings_root, encoding="utf-8", xml_declaration=True)


# ====================  目录  ====================

def insert_toc_before_first_chapter(
    ns: dict[str, str], body: ET.Element, sectPr_proto: ET.Element | None = None
) -> None:
    """在第一章（或"摘要"标题）前插入目录字段段落。"""
    w_p = qn(ns, "w", "p")
    w_pPr = qn(ns, "w", "pPr")
    w_pStyle = qn(ns, "w", "pStyle")
    w_jc = qn(ns, "w", "jc")
    w_val = qn(ns, "w", "val")
    w_numPr = qn(ns, "w", "numPr")
    w_numId = qn(ns, "w", "numId")
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")
    w_fldChar = qn(ns, "w", "fldChar")
    w_fldCharType = qn(ns, "w", "fldCharType")
    w_instrText = qn(ns, "w", "instrText")

    children = list(body)
    first_h1_idx = None
    unnumbered = {"目录", "摘要", "Abstract"}
    # 优先将目录插入到"摘要"标题之前，保证目录在罗马数字节内（目录在前，摘要在后）
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if p_style(ns, el) == "1":
            txt = p_text(ns, el).strip()
            if txt == "摘要":
                first_h1_idx = i
                break
            if txt in unnumbered:
                continue
            first_h1_idx = i
            break
    if first_h1_idx is None:
        return

    # 目录标题段落：使用 Heading 1 样式，但逐段抑制编号（numId=0）
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

    # 目录字段段落（Word field code）
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

    # 目录节尾分节符：目录节使用罗马数字起始页，摘要节继续罗马计数
    if sectPr_proto is not None:
        sect_toc = copy.deepcopy(sectPr_proto)
        set_sect_break_next_page(ns, sect_toc)
        set_sect_pgnum(ns, sect_toc, fmt="lowerRoman", start=1)
        sb = make_section_break_paragraph(ns, sect_toc)
        body.insert(first_h1_idx, toc_title_p)
        body.insert(first_h1_idx + 1, toc_field_p)
        body.insert(first_h1_idx + 2, sb)
    else:
        pb = make_page_break_p(ns)
        body.insert(first_h1_idx, toc_title_p)
        body.insert(first_h1_idx + 1, toc_field_p)
        body.insert(first_h1_idx + 2, pb)


# ====================  章节前分页  ====================

def add_page_breaks_before_h1(ns: dict[str, str], body: ET.Element) -> None:
    """为每个一级标题（Heading 1）添加 pageBreakBefore 属性，确保每章另起新页。

    直接在标题段落上设置属性，而非插入独立分页段落，避免
    LibreOffice 在前页未满时产生空白页。
    """
    w_p = qn(ns, "w", "p")
    w_pPr = qn(ns, "w", "pPr")
    w_pageBreakBefore = qn(ns, "w", "pageBreakBefore")

    children = list(body)
    front_h1 = {"目录", "摘要", "Abstract"}
    for idx, el in enumerate(children):
        if el.tag != w_p or p_style(ns, el) != "1":
            continue
        title = p_text(ns, el).strip()
        if title in front_h1:
            continue
        # 若紧邻前一段就是 section-break（nextPage），则不再叠加 pageBreakBefore，
        # 否则易产生“空白页只有页码”的问题。
        prev_is_sect_break = False
        j = idx - 1
        while j >= 0:
            prev = children[j]
            if prev.tag != w_p:
                j -= 1
                continue
            if p_text(ns, prev).strip():
                prev_is_sect_break = p_has_sectPr(ns, prev)
                break
            if p_has_sectPr(ns, prev):
                prev_is_sect_break = True
                break
            j -= 1
        if prev_is_sect_break:
            continue
        pPr = el.find(w_pPr)
        if pPr is None:
            pPr = ET.SubElement(el, w_pPr)
            el.insert(0, pPr)
        if pPr.find(w_pageBreakBefore) is None:
            ET.SubElement(pPr, w_pageBreakBefore)


# ====================  公共 __all__  ====================

__all__ = [
    "split_keywords",
    "prepend_template_cover_pages",
    "strip_template_body_leak_after_front_matter",
    "insert_abstract_chapters_and_sections",
    "insert_abstract_keywords",
    "ensure_update_fields_in_settings",
    "insert_toc_before_first_chapter",
    "add_page_breaks_before_h1",
]
