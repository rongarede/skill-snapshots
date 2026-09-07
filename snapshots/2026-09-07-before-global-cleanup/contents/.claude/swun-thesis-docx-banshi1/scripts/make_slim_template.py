#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从完整参考论文 docx 生成瘦身格式模板。

保留：
  - styles/numbering/settings/fontTable/theme/headers/footers 等全部非正文部件
  - document.xml 正文中的封面页区域（含截断标记"日期：年月日"行）
  - 每类各一个代表性题注段落（图x-x / 表x-x，供 caption profile 提取）
  - 文档末尾 sectPr

删除：
  - 其余全部正文内容
  - 未被保留部件引用的 word/media/* 与 word/embeddings/*
  - [Content_Types].xml 中指向已删部件的 Override 条目

用法：
  python3 make_slim_template.py --input ref.docx --output slim.docx
"""

from __future__ import annotations

import argparse
import io
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W_NS}

DATE_LINE_RE = re.compile(r"^日期：[\s　]*年[\s　]*月[\s　]*日$")
END_BEFORE_TEXT = "学位论文版权使用授权书"

CAPTION_PATTERNS = {
    "figure": re.compile(r"^图\s*\d+[\-\.．]\d+\b"),
    "table": re.compile(r"^表\s*\d+[\-\.．]\d+\b"),
}


def _register_namespaces(xml_bytes: bytes) -> None:
    for _event, (prefix, uri) in ET.iterparse(
            io.BytesIO(xml_bytes), events=["start-ns"]):
        ET.register_namespace(prefix or "", uri)


def _p_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.findall(".//w:t", NS)).strip()


def _serialize(tree: ET.ElementTree) -> bytes:
    buf = io.BytesIO()
    tree.write(buf, xml_declaration=True, encoding="UTF-8")
    return buf.getvalue()


def build_slim_document(doc_xml: bytes) -> bytes:
    """裁剪 document.xml：封面区 + 题注样本 + 末尾 sectPr。"""
    _register_namespaces(doc_xml)
    tree = ET.ElementTree(ET.fromstring(doc_xml))
    body = tree.getroot().find("w:body", NS)
    if body is None:
        raise RuntimeError("document.xml missing w:body")

    children = list(body)
    w_p = f"{{{W_NS}}}p"

    cutoff = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        txt = _p_text(el)
        if DATE_LINE_RE.match(txt) or END_BEFORE_TEXT in txt:
            cutoff = i
            break
    if cutoff is None or cutoff <= 0:
        raise RuntimeError("cover cutoff marker not found in reference docx")

    # pandoc 取文档中第一个 sectPr 作为页面几何来源（页尺寸/页边距/
    # 页眉页脚引用），必须保留首个含内嵌 sectPr 的段落
    w_sectPr = f"{{{W_NS}}}sectPr"
    first_sect = None
    for i, el in enumerate(children[:-1]):
        if el.find(f".//{w_sectPr}") is not None:
            first_sect = i
            break
    if first_sect is None:
        raise RuntimeError("no inline sectPr found in reference docx body")

    # 封面区含截断标记行本身（构建时 prepend_template_cover_pages 依赖它定位）
    keep: list[ET.Element] = children[: max(cutoff, first_sect) + 1]

    for kind, pattern in CAPTION_PATTERNS.items():
        sample = None
        for el in children[cutoff + 1:]:
            if el.tag == w_p and pattern.match(_p_text(el)):
                sample = el
                break
        if sample is None:
            raise RuntimeError(f"no {kind} caption paragraph found")
        keep.append(sample)

    last = children[-1]
    if not last.tag.endswith("}sectPr"):
        raise RuntimeError("document.xml body does not end with sectPr")
    keep.append(last)

    for el in list(body):
        body.remove(el)
    for el in keep:
        body.append(el)

    return _serialize(tree)


def referenced_rel_ids(doc_xml: bytes) -> set[str]:
    """收集 document.xml 中所有 relationship 命名空间的属性值（rId）。"""
    root = ET.fromstring(doc_xml)
    ids: set[str] = set()
    for el in root.iter():
        for key, value in el.attrib.items():
            if key.startswith(f"{{{R_NS}}}"):
                ids.add(value)
    return ids


def prune_document_rels(
        rels_xml: bytes, used_ids: set[str]) -> tuple[bytes, set[str]]:
    """删除未引用的 media/embeddings 关系，返回 (新 rels, 删除的目标部件)。"""
    _register_namespaces(rels_xml)
    tree = ET.ElementTree(ET.fromstring(rels_xml))
    root = tree.getroot()
    dropped: set[str] = set()
    for rel in list(root):
        target = rel.get("Target", "")
        norm = posixpath.normpath(posixpath.join("word", target))
        if not (norm.startswith("word/media/")
                or norm.startswith("word/embeddings/")):
            continue
        if rel.get("Id") in used_ids:
            continue
        root.remove(rel)
        dropped.add(norm)
    return _serialize(tree), dropped


def rels_targets(rels_xml: bytes, base_dir: str) -> set[str]:
    """列出一个 .rels 文件引用的全部内部部件路径（相对包根）。"""
    root = ET.fromstring(rels_xml)
    targets: set[str] = set()
    for rel in root:
        if rel.get("TargetMode") == "External":
            continue
        target = rel.get("Target", "")
        targets.add(posixpath.normpath(posixpath.join(base_dir, target)))
    return targets


def prune_content_types(ct_xml: bytes, kept_parts: set[str]) -> bytes:
    """删除指向不存在部件的 Override 条目。"""
    _register_namespaces(ct_xml)
    tree = ET.ElementTree(ET.fromstring(ct_xml))
    root = tree.getroot()
    for el in list(root):
        if el.tag != f"{{{CT_NS}}}Override":
            continue
        part = el.get("PartName", "").lstrip("/")
        if part not in kept_parts:
            root.remove(el)
    return _serialize(tree)


def make_slim_template(input_docx: Path, output_docx: Path) -> None:
    with zipfile.ZipFile(input_docx, "r") as zin:
        names = zin.namelist()
        slim_doc = build_slim_document(zin.read("word/document.xml"))
        used_ids = referenced_rel_ids(slim_doc)

        new_rels, _ = prune_document_rels(
            zin.read("word/_rels/document.xml.rels"), used_ids)

        # 仍被引用的 media/embeddings：document.xml 的 rels + 其他部件的 rels
        needed: set[str] = rels_targets(new_rels, "word")
        for name in names:
            if (name.startswith("word/_rels/") and name.endswith(".rels")
                    and name != "word/_rels/document.xml.rels"):
                needed |= rels_targets(zin.read(name), "word")

        kept_parts: set[str] = set()
        entries: list[tuple[str, bytes]] = []
        for name in names:
            if name.startswith(("word/media/", "word/embeddings/")) \
                    and name not in needed:
                continue
            if name == "word/document.xml":
                data = slim_doc
            elif name == "word/_rels/document.xml.rels":
                data = new_rels
            else:
                data = zin.read(name)
            kept_parts.add(name)
            entries.append((name, data))

        ct_xml = prune_content_types(
            zin.read("[Content_Types].xml"), kept_parts)
        entries = [(n, ct_xml if n == "[Content_Types].xml" else d)
                   for n, d in entries]

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
            output_docx, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries:
            zout.writestr(name, data)

    size_mb = output_docx.stat().st_size / 1024 / 1024
    print(f"slim template written: {output_docx} ({size_mb:.2f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    make_slim_template(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
