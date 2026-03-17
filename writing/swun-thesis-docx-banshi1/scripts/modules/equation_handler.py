#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公式编号模块：为 DOCX 中的行间公式添加章节编号，并确保公式段落居中对齐。

从 docx_builder.py 提取，作为独立可测试模块。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import (
        qn as _qn,
        p_text as _p_text,
        p_style as _p_style,
        ensure_ppr as _ensure_ppr,
        set_para_tabs_for_equation as _set_para_tabs_for_equation,
        make_run_tab as _make_run_tab,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import (
        qn as _qn,
        p_text as _p_text,
        p_style as _p_style,
        ensure_ppr as _ensure_ppr,
        set_para_tabs_for_equation as _set_para_tabs_for_equation,
        make_run_tab as _make_run_tab,
    )


def _sect_text_width_dxa(ns: dict[str, str], root: ET.Element) -> int | None:
    """从节属性中计算可写文字区域宽度（dxa 单位）。"""
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


def make_equation_number_run(ns: dict[str, str], text: str) -> ET.Element:
    """创建公式编号的 run，字体强制设为 Times New Roman。

    公式编号如 (3-13) 需使用 Times New Roman 字体以符合排版规范。
    """
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_t = _qn(ns, "w", "t")

    r = ET.Element(w_r)
    rPr = ET.SubElement(r, w_rPr)
    fonts = ET.SubElement(rPr, w_rFonts)
    fonts.set(_qn(ns, "w", "ascii"), "Times New Roman")
    fonts.set(_qn(ns, "w", "hAnsi"), "Times New Roman")
    t = ET.SubElement(r, w_t)
    t.text = text
    return r


def number_display_equations(
    ns: dict[str, str],
    root: ET.Element,
    body: ET.Element,
    display_math_flags: list[bool] | None,
) -> None:
    """为包含 m:oMathPara 的段落添加章节式公式编号。

    同时确保所有行间公式段落居中对齐，并在前缀 tab 之后附加右对齐的编号。
    """
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
    m_t = f"{{{m_uri}}}t"

    text_w = _sect_text_width_dxa(ns, root)
    if text_w is None or text_w == 0:
        # 回退到 A4 模板预期正文宽度：A4 11907，左边距 1417，右边距 1134 => 9356
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
        # pandoc 有时将 OMML 直接以 <m:oMath> 放在段落中；
        # 仅当段落无可见文字 run 时才视为行间公式。
        if p.find(m_oMath) is not None and not _p_text(ns, p).strip():
            return True
        return False

    math_paras = [p for p in children if is_display_math_para(p)]

    # 若 LaTeX 派生的标志列表与实际公式段落数对齐，则采用；否则全部编号。
    if (
        isinstance(display_math_flags, list)
        and all(isinstance(x, bool) for x in display_math_flags)
        and len(display_math_flags) == len(math_paras)
    ):
        flag_iter: object = iter(display_math_flags)
    else:
        flag_iter = None

    def should_number() -> bool:
        if flag_iter is None:
            return True
        try:
            return next(flag_iter)  # type: ignore[call-overload]
        except StopIteration:
            return True

    def _ensure_display_math_para_centered(p: ET.Element) -> None:
        """确保行间公式段落居中，通过前导 tab 停止点对齐公式，右 tab 停止点对齐编号。"""
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # 插入前导 tab run（幂等）使公式从居中 tab 停止点开始
        children2 = list(p)
        insert_idx = 0
        if children2 and children2[0].tag == _qn(ns, "w", "pPr"):
            insert_idx = 1

        has_leading_tab = False
        for el in children2[insert_idx:]:
            # 检查第一个内容元素是否已经是 tab run
            if el.tag == _qn(ns, "w", "r"):
                if el.find(_qn(ns, "w", "tab")) is not None:
                    has_leading_tab = True
                break
            # 如果数学内容先于 run，仍需插入前导 tab
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

        # 每个行间公式段落消耗一个标志位，保持与 LaTeX 解析的对齐稳定
        num_flag = should_number()
        math_txt = "".join((x.text or "") for x in p.iter(m_t))

        # 始终居中对齐行间公式
        _ensure_display_math_para_centered(p)

        if chapter_no <= 0:
            continue

        # 仅含量词的行间公式保持不编号
        # 兼容性说明：当前验证器要求含 "∀" 的行保持不编号
        compact_math = re.sub(r"\s+", "", math_txt)
        if "∀" in compact_math:
            continue
        if "∃" in compact_math and not any(
            op in compact_math for op in ("=", "≈", "≜", "≤", "≥", "<", ">")
        ):
            continue

        if not num_flag:
            continue

        # 避免对已含编号格式（如 (2-1)）的公式重复编号
        if re.search(r"\(\d+[-\.]\d+\)\s*$", txt):
            continue

        eq_no += 1
        num_txt = f"({chapter_no}-{eq_no})"

        # 行间公式段落不应有首行缩进
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # 追加 tab + 编号（公式编号使用 Times New Roman 字体）
        p.append(_make_run_tab(ns))
        p.append(make_equation_number_run(ns, num_txt))


# 公共别名，供 docx_builder 等模块导入
sect_text_width_dxa = _sect_text_width_dxa


__all__ = [
    "number_display_equations",
    "make_equation_number_run",
    "sect_text_width_dxa",
]
