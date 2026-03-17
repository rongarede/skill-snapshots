#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
页脚替换模块：替换 WPS 页脚、修复超链接样式。

公共 API：
    replace_wps_footers(file_data, doc_xml) -> None
    fix_hyperlink_style(styles_xml)         -> bytes
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
    )


# ---------------------------------------------------------------------------
# 页脚 XML 模板
# ---------------------------------------------------------------------------

_FOOTER_PAGE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>'
)

_FOOTER_EMPTY_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr></w:p></w:ftr>'
)


# ---------------------------------------------------------------------------
# 公共函数
# ---------------------------------------------------------------------------

def replace_wps_footers(
    file_data: dict[str, bytes],
    doc_xml: bytes,
) -> None:
    """Replace footer*.xml with clean PAGE field footers based on actual sectPr references.

    封面 section (0) 和目录 section (1) 的 default footer 写空（不显示页码），
    摘要 section (lowerRoman) 和正文 section (decimal) 的 default footer 写 PAGE 字段。
    pgNumType（lowerRoman / decimal）已在 sectPr 中设定，控制显示格式。

    若空 footer section 和 PAGE footer section 共享同一 default footer rId，则自动拆分：
    把空 footer section 的 default footerReference 指向一个空闲 footer 文件。
    """
    footer_files: list[str] = []
    for name in list(file_data):
        if re.match(r"word/footer\d+\.xml$", name):
            footer_files.append(name)
    if not footer_files:
        return

    # --- 解析 document.xml 获取 sectPr → footerReference 映射 ---
    dns = _collect_ns(doc_xml)
    _register_ns(dns)
    droot = ET.fromstring(doc_xml)
    w_sectPr_tag = _qn(dns, "w", "sectPr")
    w_footerRef_tag = _qn(dns, "w", "footerReference")
    w_type_attr = _qn(dns, "w", "type")
    w_pgNumType_tag = _qn(dns, "w", "pgNumType")
    w_fmt_attr = _qn(dns, "w", "fmt")
    r_id_attr = _qn(dns, "r", "id") if "r" in dns else (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )

    all_sectPr = droot.findall(f".//{w_sectPr_tag}")

    # 解析 rels 映射 rId → footer 文件名
    rels_bytes = file_data.get("word/_rels/document.xml.rels", b"")
    rid_to_footer: dict[str, str] = {}  # rId6 -> footer1.xml
    if rels_bytes:
        rns = _collect_ns(rels_bytes)
        _register_ns(rns)
        rroot = ET.fromstring(rels_bytes)
        for rel in rroot:
            target = rel.get("Target", "")
            rid = rel.get("Id", "")
            if re.match(r"footer\d+\.xml$", target):
                rid_to_footer[rid] = target

    # 收集每个 section 的 default footer rId 和 pgNumType fmt
    sect_info: list[dict[str, str | None]] = []
    for sp in all_sectPr:
        default_rid = None
        for fr in sp.findall(w_footerRef_tag):
            if fr.get(w_type_attr) == "default":
                default_rid = fr.get(r_id_attr)
                break
        pgnum = sp.find(w_pgNumType_tag)
        fmt = pgnum.get(w_fmt_attr) if pgnum is not None else None
        sect_info.append({"default_rid": default_rid, "fmt": fmt})

    # 确定哪些 footer 文件需要 PAGE 字段，哪些需要空
    # 规则：section 0（封面）和 section 1（目录）的 default footer → 空（不显示页码）
    #        其余 section（摘要=lowerRoman、正文=decimal）的 default footer → PAGE 字段
    page_footer_files: set[str] = set()  # 需要 PAGE 字段的 footer 文件
    empty_footer_files: set[str] = set()  # 需要空的 footer 文件
    empty_sect_indices: list[int] = []  # 需要空 footer 的 section 索引

    for i, info in enumerate(sect_info):
        rid = info["default_rid"]
        if rid and rid in rid_to_footer:
            fname = f"word/{rid_to_footer[rid]}"
            if i <= 1:  # 封面 (0) + 目录 (1) 不显示页码
                empty_footer_files.add(fname)
                empty_sect_indices.append(i)
            else:
                page_footer_files.add(fname)

    # 处理冲突：同一 footer 文件既需要空又需要 PAGE
    conflict = page_footer_files & empty_footer_files
    if conflict and len(sect_info) > 0:
        # 需要拆分：把需要空 footer 的 section 指向一个空闲 footer 文件
        used_footers = {f"word/{rid_to_footer[info['default_rid']]}"
                        for info in sect_info
                        if info["default_rid"] and info["default_rid"] in rid_to_footer}
        free_footer = None
        for ff in sorted(footer_files):
            if ff not in used_footers:
                free_footer = ff
                break

        if free_footer is not None:
            free_base = free_footer.replace("word/", "")
            free_rid = None
            for rid, target in rid_to_footer.items():
                if target == free_base:
                    free_rid = rid
                    break

            if free_rid is not None:
                # 把所有需要空 footer 的 section 的 default footerReference 指向空闲 footer
                for sect_idx in empty_sect_indices:
                    sp = all_sectPr[sect_idx]
                    for fr in sp.findall(w_footerRef_tag):
                        if fr.get(w_type_attr) == "default":
                            fr.set(r_id_attr, free_rid)
                            break
                # 更新映射
                for cf in conflict:
                    empty_footer_files.discard(cf)
                empty_footer_files.add(free_footer)
                page_footer_files.discard(free_footer)

                # 序列化修改后的 document.xml 回 file_data
                file_data["word/document.xml"] = ET.tostring(
                    droot, encoding="utf-8", xml_declaration=True
                )
                print(f"  [footer] Sections {empty_sect_indices} default footer reassigned to {free_base} ({free_rid})")

    # 写入 footer 文件内容
    replaced = 0
    for fname in footer_files:
        if fname in page_footer_files:
            file_data[fname] = _FOOTER_PAGE_XML.encode("utf-8")
        else:
            # 所有非 PAGE 的 footer 文件都写空（包括 first/even 类型、封面 default、未使用的）
            file_data[fname] = _FOOTER_EMPTY_XML.encode("utf-8")
        replaced += 1

    print(f"  [footer] Replaced {replaced} footer file(s) with clean XML")


def fix_hyperlink_style(styles_xml: bytes) -> bytes:
    """Modify Hyperlink char style: color=000000 (black), underline=none, remove textFill."""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    _register_ns(sns)
    sroot = ET.fromstring(styles_xml)

    w_style = _qn(sns, "w", "style")
    w_name = _qn(sns, "w", "name")
    w_val = _qn(sns, "w", "val")
    w_rPr = _qn(sns, "w", "rPr")
    w_color = _qn(sns, "w", "color")
    w_u = _qn(sns, "w", "u")
    w_themeColor = _qn(sns, "w", "themeColor")

    # w14:textFill (Word 2010+ gradient fill)
    w14_uri = sns.get("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
    w14_textFill = f"{{{w14_uri}}}textFill"

    count = 0
    for s in sroot.iter(w_style):
        name_el = s.find(w_name)
        if name_el is None:
            continue
        name_val = (name_el.get(w_val) or "").lower()
        if "hyperlink" not in name_val:
            continue

        rPr = s.find(w_rPr)
        if rPr is None:
            continue

        # 设为黑色（不显示为蓝色链接）
        color = rPr.find(w_color)
        if color is not None:
            color.set(w_val, "000000")
            if w_themeColor in color.attrib:
                del color.attrib[w_themeColor]
        else:
            c = ET.SubElement(rPr, w_color)
            c.set(w_val, "000000")

        # 移除下划线
        u = rPr.find(w_u)
        if u is not None:
            u.set(w_val, "none")
        else:
            u = ET.SubElement(rPr, w_u)
            u.set(w_val, "none")

        # 移除 w14:textFill
        tf = rPr.find(w14_textFill)
        if tf is not None:
            rPr.remove(tf)

        count += 1

    if count:
        print(f"  [styles] Changed {count} Hyperlink style(s) to black + no underline")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)
