#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
页眉替换模块：按 section 写入论文题目页眉。

论文 section 布局（由 insert_abstract_chapters_and_sections 建立，含 CN/EN 分节后）：
  Section 0  封面/原创性声明   → 无页眉
  Section 1  目录             → 中文题目
  Section 2  中文摘要         → 中文题目
  Section 3  英文摘要         → 英文题目
  Section 4  正文 + 参考文献 + 致谢 → 中文题目

公共 API：
    add_thesis_headers(file_data, doc_xml, cn_title, en_title) -> None
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
except ModuleNotFoundError:  # pragma: no cover
    from scripts.utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
    )


# ---------------------------------------------------------------------------
# 论文页眉配置
# ---------------------------------------------------------------------------

CN_TITLE = "基于DAG-BFT和HotStuff的车联网共识算法改进及其应用"
EN_TITLE = (
    "Improvement and Application of Vehicular Network "
    "Consensus Algorithms Based on DAG-BFT and HotStuff"
)

# 页眉 XML 命名空间（最小集，兼容 Word/WPS）
_HDR_NAMESPACES = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)

_CONTENT_TYPE_HDR = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
)
_REL_TYPE_HDR = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
)


def _make_header_xml(
    text: str,
    font_size: int = 24,
    char_spacing: int | None = None,
) -> bytes:
    """生成带文本的页眉 XML（居中，宋体/Times New Roman，小四号 12pt）。

    页眉段落格式：
    - 居中对齐
    - 段落底部细实线边框（标准论文页眉分隔线）
    - 字体：中文宋体 / 西文 Times New Roman
    - 字号：默认小四号 = 12pt = w:sz 24（half-points）
    """
    # XML 特殊字符转义
    safe_text = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
    spacing_xml = (
        f'<w:spacing w:val="{char_spacing}"/>' if char_spacing is not None else ""
    )
    xml_str = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:hdr {_HDR_NAMESPACES}>'
        '<w:p>'
        '<w:pPr>'
        '<w:jc w:val="center"/>'
        '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
        '<w:pBdr>'
        '<w:bottom w:val="single" w:sz="4" w:space="1" w:color="auto"/>'
        '</w:pBdr>'
        '</w:pPr>'
        '<w:r>'
        '<w:rPr>'
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"'
        ' w:eastAsia="宋体" w:cs="Times New Roman"/>'
        f'<w:sz w:val="{font_size}"/>'
        f'<w:szCs w:val="{font_size}"/>'
        f'{spacing_xml}'
        '</w:rPr>'
        f'<w:t>{safe_text}</w:t>'
        '</w:r>'
        '</w:p>'
        '</w:hdr>'
    )
    return xml_str.encode("utf-8")


def _make_empty_header_xml() -> bytes:
    """生成空页眉 XML（封面和目录用）。"""
    xml_str = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:hdr {_HDR_NAMESPACES}>'
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr></w:p>'
        '</w:hdr>'
    )
    return xml_str.encode("utf-8")


def _find_max_rid(rels_bytes: bytes) -> int:
    """从 rels XML 中找到最大的 rIdN 数字，用于分配新的 rId。"""
    max_n = 0
    for m in re.finditer(r'\bId="rId(\d+)"', rels_bytes.decode("utf-8", errors="ignore")):
        n = int(m.group(1))
        if n > max_n:
            max_n = n
    return max_n


def _find_max_header_index(file_data: dict[str, bytes]) -> int:
    """找到 file_data 中最大的 header{N}.xml 编号。"""
    max_n = 0
    for name in file_data:
        m = re.match(r"word/header(\d+)\.xml$", name)
        if m:
            n = int(m.group(1))
            if n > max_n:
                max_n = n
    return max_n


def add_thesis_headers(
    file_data: dict[str, bytes],
    doc_xml: bytes,
    cn_title: str = CN_TITLE,
    en_title: str = EN_TITLE,
) -> None:
    """为论文各 section 写入页眉，就地修改 file_data。

    Section 布局（按插入顺序，0-based）：
      0  封面               → 空页眉
      1  目录               → 空页眉
      2  中文摘要           → cn_title
      3  英文摘要           → en_title  (需 insert_abstract_chapters_and_sections_v2 分节)
      4  正文 + 后记        → cn_title
      （若未分 CN/EN 节，section 2 = 摘要全部内容 → cn_title）

    实现策略：
    1. 解析 document.xml 中所有 sectPr 的 headerReference
    2. 按 section 索引决定页眉内容（空 / CN / EN）
    3. 直接覆写 file_data 中对应的 header*.xml 内容
    4. 若存在共享冲突（多 section 共用同一 header 文件），拆分为独立文件
    5. 若 sectPr 缺少 headerReference，新建 header 文件并注册到 rels/Content_Types
    """
    # --- 解析 document.xml ---
    dns = _collect_ns(doc_xml)
    _register_ns(dns)
    droot = ET.fromstring(doc_xml)

    w_sectPr_tag = _qn(dns, "w", "sectPr")
    w_hdrRef_tag = _qn(dns, "w", "headerReference")
    w_type_attr = _qn(dns, "w", "type")
    r_id_attr = _qn(dns, "r", "id") if "r" in dns else (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )

    all_sectPr = droot.findall(f".//{w_sectPr_tag}")
    n_sects = len(all_sectPr)

    # --- 解析 rels 映射 rId → header 文件名 ---
    rels_bytes = file_data.get("word/_rels/document.xml.rels", b"")
    rid_to_hdr: dict[str, str] = {}   # rId → "header1.xml"
    if rels_bytes:
        rns = _collect_ns(rels_bytes)
        _register_ns(rns)
        rroot = ET.fromstring(rels_bytes)
        for rel in rroot:
            target = rel.get("Target", "")
            rid = rel.get("Id", "")
            typ = rel.get("Type", "")
            if re.match(r"header\d+\.xml$", target) and "header" in typ:
                rid_to_hdr[rid] = target

    # --- 决定每个 section 所需的页眉内容 ---
    # 0 → 空；1,2 → CN；3 → EN（若有独立 EN 节）；4+ → CN
    def _sect_header_text(idx: int) -> str | None:
        """None 表示空页眉。"""
        if idx == 0:
            return None
        if idx == 3 and n_sects >= 5:
            # 有 CN+EN 分节（5 个 section：cover/toc/cn/en/body）
            return en_title
        return cn_title

    # --- 收集每个 section 的 default headerReference rId ---
    sect_default_rid: list[str | None] = []
    for sp in all_sectPr:
        default_rid = None
        for hr in sp.findall(w_hdrRef_tag):
            if hr.get(w_type_attr) == "default":
                default_rid = hr.get(r_id_attr)
                break
        sect_default_rid.append(default_rid)

    # --- 确定 header 文件需要的内容（按 fname → 最终文本） ---
    # 如果多 section 共用同一 header 文件但需要不同内容，需要拆分。
    fname_to_text: dict[str, str | None] = {}   # "header1.xml" → text | None
    split_needed: list[tuple[int, str | None]] = []  # (sect_idx, desired_text)

    for i, rid in enumerate(sect_default_rid):
        desired = _sect_header_text(i)
        if rid and rid in rid_to_hdr:
            fname = rid_to_hdr[rid]
            if fname not in fname_to_text:
                fname_to_text[fname] = desired
            elif fname_to_text[fname] != desired:
                # 冲突：同一文件被两个需要不同内容的 section 引用
                split_needed.append((i, desired))
        else:
            # sectPr 没有 default headerReference，稍后新建
            split_needed.append((i, desired))

    def _header_char_spacing(text: str | None) -> int | None:
        if text == en_title:
            # Keep the required small-four size while slightly condensing the
            # long English title so it stays on one line.
            return -6
        return None

    # --- 处理冲突/缺失：新建 header 文件并更新 sectPr ---
    if split_needed:
        max_rid_n = _find_max_rid(rels_bytes)
        max_hdr_n = _find_max_header_index(file_data)

        # 重新解析 rels 为可写 Element
        rels_root = ET.fromstring(rels_bytes) if rels_bytes else ET.Element(
            "Relationships",
            {"xmlns": "http://schemas.openxmlformats.org/package/2006/relationships"},
        )
        rels_ns_uri = (
            "http://schemas.openxmlformats.org/package/2006/relationships"
        )

        # 解析 Content_Types.xml 为可写 Element
        ct_bytes = file_data.get("[Content_Types].xml", b"")
        ct_root = ET.fromstring(ct_bytes) if ct_bytes else None
        ct_ns_uri = "http://schemas.openxmlformats.org/package/2006/content-types"

        modified_doc = False

        for sect_idx, desired_text in split_needed:
            max_rid_n += 1
            max_hdr_n += 1
            new_rid = f"rId{max_rid_n}"
            new_fname = f"header{max_hdr_n}.xml"
            new_fpath = f"word/{new_fname}"

            # 写 header XML 到 file_data
            if desired_text is None:
                file_data[new_fpath] = _make_empty_header_xml()
            else:
                file_data[new_fpath] = _make_header_xml(
                    desired_text,
                    24,
                    _header_char_spacing(desired_text),
                )

            # 更新 fname_to_text
            fname_to_text[new_fname] = desired_text

            # 在 rels 中注册新 relationship
            new_rel = ET.SubElement(rels_root, f"{{{rels_ns_uri}}}Relationship")
            new_rel.set("Id", new_rid)
            new_rel.set("Type", _REL_TYPE_HDR)
            new_rel.set("Target", new_fname)

            # 更新 rid_to_hdr 映射
            rid_to_hdr[new_rid] = new_fname

            # 在 Content_Types.xml 中注册
            if ct_root is not None:
                # 检查是否已有该 Part
                already = False
                for ov in ct_root.iter(f"{{{ct_ns_uri}}}Override"):
                    if ov.get("PartName") == f"/word/{new_fname}":
                        already = True
                        break
                if not already:
                    ov_el = ET.SubElement(ct_root, f"{{{ct_ns_uri}}}Override")
                    ov_el.set("PartName", f"/word/{new_fname}")
                    ov_el.set("ContentType", _CONTENT_TYPE_HDR)

            # 在对应 sectPr 中添加/替换 default headerReference
            sp = all_sectPr[sect_idx]
            # 移除已有 default headerReference
            for hr in list(sp.findall(w_hdrRef_tag)):
                if hr.get(w_type_attr) == "default":
                    sp.remove(hr)
            new_hr = ET.SubElement(sp, w_hdrRef_tag)
            new_hr.set(w_type_attr, "default")
            new_hr.set(r_id_attr, new_rid)

            # 更新 sect_default_rid
            sect_default_rid[sect_idx] = new_rid
            modified_doc = True

        # 序列化修改后的 rels 和 Content_Types 回 file_data
        file_data["word/_rels/document.xml.rels"] = ET.tostring(
            rels_root, encoding="utf-8", xml_declaration=True
        )
        if ct_root is not None:
            file_data["[Content_Types].xml"] = ET.tostring(
                ct_root, encoding="utf-8", xml_declaration=True
            )
        if modified_doc:
            file_data["word/document.xml"] = ET.tostring(
                droot, encoding="utf-8", xml_declaration=True
            )

    # --- 覆写已映射的 header 文件 ---
    for fname, text in fname_to_text.items():
        fpath = f"word/{fname}"
        if text is None:
            file_data[fpath] = _make_empty_header_xml()
        else:
            file_data[fpath] = _make_header_xml(
                text,
                24,
                _header_char_spacing(text),
            )

    # --- 确保 first 和 even 类型的 headerReference 也有对应文件（空页眉） ---
    # Word 若找不到 first/even 引用的文件会报错，确保所有 referenced header 文件存在
    all_hdr_fnames: set[str] = set()
    for sp in all_sectPr:
        for hr in sp.findall(w_hdrRef_tag):
            rid = hr.get(r_id_attr)
            if rid and rid in rid_to_hdr:
                all_hdr_fnames.add(f"word/{rid_to_hdr[rid]}")
    for fpath in all_hdr_fnames:
        if fpath not in file_data:
            file_data[fpath] = _make_empty_header_xml()

    # 统计并打印
    non_empty = sum(1 for t in fname_to_text.values() if t is not None)
    print(
        f"  [header] {n_sects} sections → "
        f"{non_empty} header(s) with text, "
        f"{len(fname_to_text) - non_empty} empty"
    )
