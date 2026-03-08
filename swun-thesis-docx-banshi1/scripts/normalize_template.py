#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize a DOCX template's style IDs to match the expected ID scheme.

Two-phase rename avoids collisions:
  Phase 1: old_id -> __tmp_{old_id}  (for all mapped IDs)
  Phase 2: __tmp_{old_id} -> target_id
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _replace_style_ids(xml_bytes: bytes, mapping: dict[str, str]) -> bytes:
    """Replace style ID references in an OOXML part using two-phase rename."""
    if not mapping:
        return xml_bytes

    # Register all namespace prefixes before parsing to preserve them on write
    for _event, (prefix, uri) in ET.iterparse(io.BytesIO(xml_bytes), events=["start-ns"]):
        ET.register_namespace(prefix or "", uri)

    tree = ET.ElementTree(ET.fromstring(xml_bytes))
    root = tree.getroot()

    w_styleId = f"{{{W_NS}}}styleId"
    w_val = f"{{{W_NS}}}val"

    ref_tags = {
        f"{{{W_NS}}}pStyle",
        f"{{{W_NS}}}rStyle",
        f"{{{W_NS}}}tblStyle",
        f"{{{W_NS}}}basedOn",
        f"{{{W_NS}}}link",
        f"{{{W_NS}}}next",
    }

    # Phase 1: old -> __tmp_{old}
    tmp_map = {old: f"__tmp_{old}" for old in mapping}
    _apply_rename(root, tmp_map, w_styleId, w_val, ref_tags)

    # Phase 2: __tmp_{old} -> target
    final_map = {f"__tmp_{old}": target for old, target in mapping.items()}
    _apply_rename(root, final_map, w_styleId, w_val, ref_tags)

    buf = io.BytesIO()
    tree.write(buf, xml_declaration=True, encoding="UTF-8")
    return buf.getvalue()


def _apply_rename(
    root: ET.Element,
    rename: dict[str, str],
    w_styleId: str,
    w_val: str,
    ref_tags: set[str],
) -> None:
    """Apply a single rename pass across all elements."""
    for elem in root.iter():
        sid = elem.get(w_styleId)
        if sid is not None and sid in rename:
            elem.set(w_styleId, rename[sid])

        if elem.tag in ref_tags:
            val = elem.get(w_val)
            if val is not None and val in rename:
                elem.set(w_val, rename[val])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize DOCX template style IDs via two-phase rename"
    )
    parser.add_argument("--input", required=True, help="Source DOCX template")
    parser.add_argument("--output", required=True, help="Output normalized DOCX")
    parser.add_argument(
        "--mapping", required=True, help="JSON file: {old_id: target_id}"
    )
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    mapping_path = Path(args.mapping)

    if not src.exists():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 1
    if not mapping_path.exists():
        print(f"ERROR: mapping not found: {mapping_path}", file=sys.stderr)
        return 1

    with open(mapping_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    mapping: dict[str, str] = {k: v for k, v in raw.items() if not k.startswith("_")}

    style_parts = {"word/styles.xml", "word/numbering.xml", "word/document.xml"}

    buf = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in style_parts:
                data = _replace_style_ids(data, mapping)
            zout.writestr(item, data)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(buf.getvalue())

    # Verification
    with zipfile.ZipFile(dst, "r") as zf:
        styles_xml = zf.read("word/styles.xml")
    root = ET.fromstring(styles_xml)
    w_styleId = f"{{{W_NS}}}styleId"
    found_ids = {elem.get(w_styleId) for elem in root.iter() if elem.get(w_styleId)}
    missing = set(mapping.values()) - found_ids
    if missing:
        print(f"WARNING: target IDs not found in output: {missing}", file=sys.stderr)

    print(f"OK: normalized {len(mapping)} style IDs -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
