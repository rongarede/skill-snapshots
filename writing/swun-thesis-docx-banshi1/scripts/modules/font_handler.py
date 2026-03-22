#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字体处理工具模块 — 从 docx_builder.py 提取的字体规范化函数。

提供以下公共 API（无下划线前缀）：
- contains_cjk           — 判断字符串是否含 CJK 字符
- is_ascii_token_char    — 判断字符是否属于 ASCII token 字符
- split_mixed_script_runs — 拆分中英混排 run
- normalize_ascii_run_fonts — 英数 run 强制使用 Times New Roman
- normalize_bibliography_run_style — 参考文献 run 字体与字号规范化
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import qn as _qn, p_text as _p_text, p_style as _p_style
except ModuleNotFoundError:
    from scripts.utils.ooxml import qn as _qn, p_text as _p_text, p_style as _p_style


# ---------------------------------------------------------------------------
# CJK / ASCII 字符分类
# ---------------------------------------------------------------------------

def contains_cjk(text: str) -> bool:
    """判断字符串是否包含 CJK（中日韩）字符。"""
    return any(
        "\u4e00" <= ch <= "\u9fff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\u3040" <= ch <= "\u30ff"
        or "\uac00" <= ch <= "\ud7af"
        for ch in text
    )


def is_ascii_token_char(ch: str) -> bool:
    """判断单个字符是否属于 ASCII token 字符（字母、数字及常用标点）。"""
    return ord(ch) < 128 and (ch.isalnum() or ch in " ./,:;%+-_/()[]")


# ---------------------------------------------------------------------------
# Run 拆分与字体规范化
# ---------------------------------------------------------------------------

def split_mixed_script_runs(ns: dict[str, str], body: ET.Element) -> None:
    """拆分中英混排的 run，使 Latin token 可以单独设置拉丁字体。"""
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_t = _qn(ns, "w", "t")

    split_count = 0

    for p in body.findall(f".//{w_p}"):
        children = list(p)
        i = 0
        while i < len(children):
            r = children[i]
            if r.tag != w_r:
                i += 1
                continue

            parts = list(r)
            if any(part.tag not in {w_rPr, w_t} for part in parts):
                i += 1
                continue
            t_nodes = [part for part in parts if part.tag == w_t]
            if len(t_nodes) != 1:
                i += 1
                continue

            text = t_nodes[0].text or ""
            if not text or not contains_cjk(
                text) or not re.search(r"[A-Za-z0-9]", text):
                i += 1
                continue

            segments: list[tuple[str, str]] = []
            buf = []
            kind: str | None = None
            for ch in text:
                next_kind = "ascii" if is_ascii_token_char(ch) else "cjk"
                if kind is None or next_kind == kind:
                    buf.append(ch)
                    kind = next_kind
                    continue
                segments.append((kind, "".join(buf)))
                buf = [ch]
                kind = next_kind
            if buf:
                segments.append((kind or "cjk", "".join(buf)))

            if len(segments) <= 1:
                i += 1
                continue

            insert_at = i
            for _, seg in segments:
                if not seg:
                    continue
                new_r = copy.deepcopy(r)
                for child in list(new_r):
                    if child.tag == w_t:
                        new_r.remove(child)
                new_t = ET.SubElement(new_r, w_t)
                new_t.text = seg
                if seg[0] == " " or seg[-1] == " ":
                    new_t.set(
    "{http://www.w3.org/XML/1998/namespace}space",
     "preserve")
                p.insert(insert_at, new_r)
                insert_at += 1
            p.remove(r)
            split_count += 1
            children = list(p)
            i = insert_at

    if split_count:
        print(f"  [fonts] Split {split_count} mixed-script run(s)")


def normalize_ascii_run_fonts(ns: dict[str, str], body: ET.Element) -> None:
    """将含英文字母或阿拉伯数字的 run 字体强制设为 Times New Roman。"""
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    w_eastAsia = _qn(ns, "w", "eastAsia")
    w_hint = _qn(ns, "w", "hint")
    w_cs = _qn(ns, "w", "cs")
    changed = 0
    ascii_re = re.compile(r"[0-9A-Za-z]")

    for r in body.findall(f".//{w_r}"):
        texts = [t.text or "" for t in r.findall(f".//{w_t}")]
        if not texts:
            continue
        joined = "".join(texts)
        if not ascii_re.search(joined):
            continue

        rPr = r.find(w_rPr)
        if rPr is None:
            rPr = ET.Element(w_rPr)
            r.insert(0, rPr)

        rFonts = rPr.find(w_rFonts)
        if rFonts is None:
            rFonts = ET.SubElement(rPr, w_rFonts)

        if rFonts.get(w_ascii) != "Times New Roman":
            rFonts.set(w_ascii, "Times New Roman")
            changed += 1
        if rFonts.get(w_hAnsi) != "Times New Roman":
            rFonts.set(w_hAnsi, "Times New Roman")
        if not contains_cjk(joined):
            for attr in (w_eastAsia, w_hint, w_cs):
                if attr in rFonts.attrib:
                    del rFonts.attrib[attr]

    if changed:
        print(
    f"  [fonts] Normalized {changed} ASCII/numeric run(s) to Times New Roman")


def normalize_bibliography_run_style(
    ns: dict[str, str], body: ET.Element) -> None:
    """将参考文献区域各条目的 run 字体设为 Times New Roman，字号设为五号（21）。"""
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_val = _qn(ns, "w", "val")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    w_cs = _qn(ns, "w", "cs")

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

    bib_entry_re = re.compile(r"^(\[[0-9]{1,4}\]|［[0-9]{1,4}］)")
    changed = 0
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
        if not bib_entry_re.match(txt):
            i += 1
            continue

        for r in el.findall(f".//{w_r}"):
            rPr = r.find(w_rPr)
            if rPr is None:
                rPr = ET.Element(w_rPr)
                r.insert(0, rPr)

            rFonts = rPr.find(w_rFonts)
            if rFonts is None:
                rFonts = ET.SubElement(rPr, w_rFonts)
            rFonts.set(w_ascii, "Times New Roman")
            rFonts.set(w_hAnsi, "Times New Roman")
            if rFonts.get(w_cs) is None:
                rFonts.set(w_cs, "Times New Roman")

            sz = rPr.find(w_sz)
            if sz is None:
                sz = ET.SubElement(rPr, w_sz)
            sz.set(w_val, "21")

            szCs = rPr.find(w_szCs)
            if szCs is None:
                szCs = ET.SubElement(rPr, w_szCs)
            szCs.set(w_val, "21")
            changed += 1
        i += 1

    if changed:
        print(f"  [fonts] Normalized {changed} bibliography run(s) to 五号")
