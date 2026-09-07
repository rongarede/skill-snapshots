#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
算法伪代码渲染模块 — 从 docx_builder.py 提取的算法格式化函数。

提供以下公共 API（无下划线前缀）：
- build_algorithm_table     — 构建算法三线表格
- format_algo_runs          — 格式化算法 run（字体、字号、去粗体）
- set_algo_para_props       — 设置算法段落属性（对齐、行距、缩进）
- format_algorithm_blocks   — 检测并格式化全文算法块（主入口）
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import (
        qn as _qn,
        p_text as _p_text,
        ensure_ppr as _ensure_ppr,
    )
except ModuleNotFoundError:
    from scripts.utils.ooxml import (
        qn as _qn,
        p_text as _p_text,
        ensure_ppr as _ensure_ppr,
    )


# ---------------------------------------------------------------------------
# 私有辅助：计算版心文字宽度（dxa）
# ---------------------------------------------------------------------------

def _sect_text_width_dxa(ns: dict[str, str], root: ET.Element) -> int | None:
    """从 sectPr 计算版心文字区宽度（dxa）。"""
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


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def build_algorithm_table(
    ns: dict[str, str],
    title_p: ET.Element,
    body_paragraphs: list[ET.Element],
    table_width_dxa: int,
) -> ET.Element:
    """构建算法三线表格。

    将算法标题段落和正文段落包裹进一个单列两行的三线表：
    - 第一行：标题段落
    - 第二行：所有正文段落
    """
    w_tbl = _qn(ns, "w", "tbl")
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tblW = _qn(ns, "w", "tblW")
    w_jc = _qn(ns, "w", "jc")
    w_tblLook = _qn(ns, "w", "tblLook")
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcW = _qn(ns, "w", "tcW")
    w_val = _qn(ns, "w", "val")
    w_w = _qn(ns, "w", "w")
    w_type = _qn(ns, "w", "type")
    tw_str = str(table_width_dxa)
    tbl = ET.Element(w_tbl)
    tblPr = ET.SubElement(tbl, w_tblPr)
    style_el = ET.SubElement(tblPr, w_tblStyle)
    style_el.set(w_val, "55")
    tw_el = ET.SubElement(tblPr, w_tblW)
    tw_el.set(w_w, tw_str)
    tw_el.set(w_type, "dxa")
    jc_el = ET.SubElement(tblPr, w_jc)
    jc_el.set(w_val, "center")
    look_el = ET.SubElement(tblPr, w_tblLook)
    look_el.set(w_val, "04A0")
    look_el.set(_qn(ns, "w", "firstRow"), "1")
    look_el.set(_qn(ns, "w", "lastRow"), "0")
    look_el.set(_qn(ns, "w", "firstColumn"), "0")
    look_el.set(_qn(ns, "w", "lastColumn"), "0")
    look_el.set(_qn(ns, "w", "noHBand"), "0")
    look_el.set(_qn(ns, "w", "noVBand"), "1")
    grid = ET.SubElement(tbl, w_tblGrid)
    col = ET.SubElement(grid, w_gridCol)
    col.set(w_w, tw_str)
    tr0 = ET.SubElement(tbl, w_tr)
    tc0 = ET.SubElement(tr0, w_tc)
    tcPr0 = ET.SubElement(tc0, w_tcPr)
    tcW0 = ET.SubElement(tcPr0, w_tcW)
    tcW0.set(w_w, tw_str)
    tcW0.set(w_type, "dxa")
    tc0.append(title_p)
    tr1 = ET.SubElement(tbl, w_tr)
    tc1 = ET.SubElement(tr1, w_tc)
    tcPr1 = ET.SubElement(tc1, w_tcPr)
    tcW1 = ET.SubElement(tcPr1, w_tcW)
    tcW1.set(w_w, tw_str)
    tcW1.set(w_type, "dxa")
    for bp in body_paragraphs:
        tc1.append(bp)
    return tbl


def format_algo_runs(ns: dict[str, str], p: ET.Element) -> None:
    """格式化段落内所有 run：Times New Roman 10.5pt，去粗体。"""
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_b = _qn(ns, "w", "b")
    w_bCs = _qn(ns, "w", "bCs")
    w_val = _qn(ns, "w", "val")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    for r in p.findall(f".//{w_r}"):
        rPr = r.find(w_rPr)
        if rPr is None:
            rPr = ET.Element(w_rPr)
            r.insert(0, rPr)
        rFonts = rPr.find(w_rFonts)
        if rFonts is None:
            rFonts = ET.SubElement(rPr, w_rFonts)
        rFonts.set(w_ascii, "Times New Roman")
        rFonts.set(w_hAnsi, "Times New Roman")
        sz_el = rPr.find(w_sz)
        if sz_el is None:
            sz_el = ET.SubElement(rPr, w_sz)
        sz_el.set(w_val, "21")
        szCs_el = rPr.find(w_szCs)
        if szCs_el is None:
            szCs_el = ET.SubElement(rPr, w_szCs)
        szCs_el.set(w_val, "21")
        for b_tag in (w_b, w_bCs):
            b_el = rPr.find(b_tag)
            if b_el is not None:
                rPr.remove(b_el)


def set_algo_para_props(ns: dict[str, str], p: ET.Element) -> None:
    """设置算法段落属性：左对齐、单倍行距、无首行缩进、无段落边框。"""
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_spacing = _qn(ns, "w", "spacing")
    w_ind = _qn(ns, "w", "ind")
    w_pBdr = _qn(ns, "w", "pBdr")
    pPr = _ensure_ppr(ns, p)
    jc = pPr.find(w_jc)
    if jc is None:
        jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "left")
    sp = pPr.find(w_spacing)
    if sp is None:
        sp = ET.SubElement(pPr, w_spacing)
    sp.set(_qn(ns, "w", "line"), "240")
    sp.set(_qn(ns, "w", "lineRule"), "auto")
    sp.set(_qn(ns, "w", "before"), "0")
    sp.set(_qn(ns, "w", "after"), "0")
    ind = pPr.find(w_ind)
    if ind is not None:
        pPr.remove(ind)
    ind = ET.SubElement(pPr, w_ind)
    ind.set(_qn(ns, "w", "firstLine"), "0")
    ind.set(_qn(ns, "w", "firstLineChars"), "0")
    pBdr = pPr.find(w_pBdr)
    if pBdr is not None:
        pPr.remove(pBdr)


def format_algorithm_blocks(
    ns: dict[str, str], root: ET.Element, body: ET.Element) -> None:
    """检测算法块并应用学术排版格式。

    算法块结构：
      1. 标题段落：文字以"算法 N ..."开头（"算法 N"加粗）
      2. VML 水平线段落（顶部分隔线）
      3. 正文段落：输入/输出行 + 带行号的算法行
         每行以 ⌊N⌋ 缩进标记开头，N 为缩进级别
      4. VML 水平线段落（底部分隔线）

    本函数执行：
      - 用段落顶部/底部边框替换 VML 水平线
      - 在标题段落上方添加顶部边框
      - 剥离 ⌊N⌋ 标记并应用正确的左缩进
      - 去除算法段落的首行缩进
      - 设置紧凑行距（单倍，段后为 0）
      - 应用 小五（9pt）字号于算法正文
    """
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    _qn(ns, "w", "pPr")
    w_rPr = _qn(ns, "w", "rPr")
    _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    _qn(ns, "w", "ind")
    _qn(ns, "w", "left")
    _qn(ns, "w", "firstLine")
    _qn(ns, "w", "firstLineChars")
    _qn(ns, "w", "spacing")
    _qn(ns, "w", "line")
    _qn(ns, "w", "lineRule")
    _qn(ns, "w", "before")
    _qn(ns, "w", "after")
    _qn(ns, "w", "pBdr")
    _qn(ns, "w", "top")
    _qn(ns, "w", "bottom")
    _qn(ns, "w", "sz")
    _qn(ns, "w", "space")
    _qn(ns, "w", "color")
    _qn(ns, "w", "sz")
    _qn(ns, "w", "szCs")
    _qn(ns, "w", "jc")
    w_pict = _qn(ns, "w", "pict")
    w_b = _qn(ns, "w", "b")
    _qn(ns, "w", "bCs")
    text_w = _sect_text_width_dxa(ns, root) or 8277

    # 缩进标记正则：⌊N⌋，N 为数字
    indent_marker_re = re.compile(r"\u230A(\d+)\u230B")

    children = list(body)
    total = len(children)

    def _is_vml_hrule(el: ET.Element) -> bool:
        """检查段落是否仅包含一个 VML 水平线。"""
        if el.tag != w_p:
            return False
        pict = el.find(f".//{w_pict}")
        if pict is None:
            return False
        # VML hrule: <v:rect ... o:hr="t" />
        for child in pict:
            hr_attr = child.get("{urn:schemas-microsoft-com:office:office}hr")
            if hr_attr == "t":
                return True
        return False

    def _strip_indent_markers(p: ET.Element) -> int:
        """从文本 run 中找到并移除 ⌊N⌋ 缩进标记，返回缩进级别。"""
        indent_level = 0
        for t in p.findall(f".//{w_t}"):
            if t.text and indent_marker_re.search(t.text):
                m = indent_marker_re.search(t.text)
                indent_level = int(m.group(1))
                t.text = indent_marker_re.sub("", t.text)
        return indent_level

    def _has_bold_alg_prefix(p: ET.Element) -> bool:
        """检查段落是否以加粗的"算法"文字开头（区分标题与正文中提及算法的情况）。"""
        for r in p.findall(f".//{w_r}"):
            rPr = r.find(w_rPr)
            if rPr is None:
                continue
            b_el = rPr.find(w_b)
            if b_el is None:
                continue
            b_val = b_el.get(w_val)
            if b_val is not None and b_val not in ("true", "1", ""):
                continue
            t_el = r.find(w_t)
            if t_el is not None and t_el.text and "算法" in t_el.text:
                return True
        return False

    INDENT_SPACES = 4
    # 行号匹配：以 "数字:" 开头（可能后面有空格），用于区分有行号的行
    lineno_re = re.compile(r"^(\d+:)\s*")

    alg_title_re = re.compile(r"^算法\s*\d+")
    alg_count = 0
    i = 0
    while i < total:
        el = children[i]
        if el.tag != w_p:
            i += 1
            continue

        text = _p_text(ns, el).strip()
        if not alg_title_re.match(text):
            i += 1
            continue

        # 确认是算法标题（加粗"算法"），而非正文中提及算法
        if not _has_bold_alg_prefix(el):
            i += 1
            continue

        title_idx = i

        # 下一段应为 VML 水平线（顶部分隔线）
        top_rule_idx = i + 1
        if top_rule_idx >= total or not _is_vml_hrule(children[top_rule_idx]):
            i += 1
            continue

        bottom_rule_idx = None
        j = top_rule_idx + 1
        while j < total:
            if _is_vml_hrule(children[j]):
                bottom_rule_idx = j
                break
            j += 1

        if bottom_rule_idx is None:
            i += 1
            continue

        alg_count += 1
        title_p = children[title_idx]
        body_ps = [children[k]
            for k in range(top_rule_idx + 1, bottom_rule_idx)]

        # 格式化标题段落
        format_algo_runs(ns, title_p)
        set_algo_para_props(ns, title_p)

        # 格式化正文段落
        for bp in body_ps:
            if bp.tag != w_p:
                continue
            indent_level = _strip_indent_markers(bp)
            if indent_level > 0:
                indent_str = " " * (indent_level * INDENT_SPACES)
                # 行号始终左对齐：缩进空格应插入到行号之后，而不是行号之前。
                # 遍历所有 <w:t>，找到第一个有内容的文本元素：
                #   - 若文本以 "数字: " 开头（行号行），把缩进插在行号之后
                #   - 否则（输入/输出行等无行号行），把缩进插在文本开头
                for t_el in bp.findall(f".//{w_t}"):
                    if not t_el.text:
                        continue
                    lm = lineno_re.match(t_el.text)
                    if lm:
                        # 行号行：在行号之后插入缩进，保持行号左对齐
                        after_lineno = t_el.text[lm.end():]
                        t_el.text = lm.group(1) + " " + \
                                             indent_str + after_lineno
                    else:
                        # 无行号行（输入/输出）：在开头插入缩进
                        t_el.text = indent_str + t_el.text
                    break
            format_algo_runs(ns, bp)
            set_algo_para_props(ns, bp)

        # 从 body 中移除原有元素
        for idx in sorted(range(title_idx, bottom_rule_idx + 1), reverse=True):
            body.remove(children[idx])

        # 构建三线表并插入
        tbl = build_algorithm_table(ns, title_p, body_ps, text_w)
        body.insert(title_idx, tbl)

        # 刷新 children 列表
        children = list(body)
        total = len(children)
        i = title_idx + 1

    if alg_count:
        print(
    f"  [algorithms] Wrapped {alg_count} algorithm block(s) in three-line tables")
