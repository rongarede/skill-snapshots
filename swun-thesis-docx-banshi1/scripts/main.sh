#!/usr/bin/env bash
# swun-thesis-docx-banshi1: build SWUN thesis DOCX (Format 1) from LaTeX

set -euo pipefail

THESIS_DIR="${1:-/Users/bit/LaTeX/SWUN_Thesis}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: missing dependency: $1" >&2
    exit 1
  }
}

need pandoc
need latexpand
need python3

if [[ ! -d "$THESIS_DIR" ]]; then
  echo "error: thesis dir not found: $THESIS_DIR" >&2
  exit 1
fi

if [[ ! -f "$THESIS_DIR/main.tex" ]]; then
  echo "error: missing: $THESIS_DIR/main.tex" >&2
  exit 1
fi

# --- Normalize reference template ---
REFERENCE_DOCX="${SWUN_REFERENCE_DOCX:-$THESIS_DIR/网络与信息安全_高春琴.docx}"
NORMALIZED_DOCX="$THESIS_DIR/.高春琴_normalized.docx"
MAPPING_JSON="$SCRIPT_DIR/style_id_mapping.json"

if [[ -f "$REFERENCE_DOCX" ]] && [[ -f "$MAPPING_JSON" ]]; then
  echo "[1/6] Normalizing reference template style IDs..."
  python3 "$SCRIPT_DIR/normalize_template.py" \
    --input "$REFERENCE_DOCX" \
    --mapping "$MAPPING_JSON" \
    --output "$NORMALIZED_DOCX"
  export SWUN_TEMPLATE_DOCX="$NORMALIZED_DOCX"
else
  echo "[1/6] SKIP: reference template or mapping not found, using default template"
fi

pushd "$THESIS_DIR" >/dev/null

echo "[2/6] Building DOCX..."
python3 "$SCRIPT_DIR/build_docx_banshi1.py" "$THESIS_DIR"

echo "[3/6] Running ref normalization regression samples..."
python3 "$SCRIPT_DIR/ref_hyphen_regression.py"

echo "[4/6] Running abstract section regression samples..."
python3 "$SCRIPT_DIR/abstract_section_regression.py"

echo "[5/6] Running general DOCX checks..."
python3 "$SCRIPT_DIR/verify_extra.py" \
  "$THESIS_DIR/main_版式1.docx"

echo "[6/6] Running table layout/caption checks..."
python3 - "$THESIS_DIR/main_版式1.docx" <<'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET


def fail(msg: str) -> None:
    print(f"TABLE VERIFY: FAIL - {msg}", file=sys.stderr)
    raise SystemExit(1)


def p_text(ns: dict[str, str], p: ET.Element) -> str:
    w_t = f"{{{ns['w']}}}t"
    return "".join((t.text or "") for t in p.iter(w_t)).strip()


def p_style(ns: dict[str, str], p: ET.Element) -> str | None:
    w_pPr = f"{{{ns['w']}}}pPr"
    w_pStyle = f"{{{ns['w']}}}pStyle"
    w_val = f"{{{ns['w']}}}val"
    pPr = p.find(w_pPr)
    if pPr is None:
        return None
    ps = pPr.find(w_pStyle)
    if ps is None:
        return None
    return ps.get(w_val)


def is_data_table(ns: dict[str, str], tbl: ET.Element) -> bool:
    w_tblPr = f"{{{ns['w']}}}tblPr"
    w_tblStyle = f"{{{ns['w']}}}tblStyle"
    w_tblCaption = f"{{{ns['w']}}}tblCaption"
    w_val = f"{{{ns['w']}}}val"

    pr = tbl.find(w_tblPr)
    if pr is None:
        return False
    st = pr.find(w_tblStyle)
    st_val = st.get(w_val) if st is not None else None
    if st_val == "FigureTable":
        return False
    return pr.find(w_tblCaption) is not None or st_val == "Table"


def first_non_empty_para(children: list[ET.Element], start: int, step: int, ns: dict[str, str]) -> tuple[int, ET.Element] | None:
    w_p = f"{{{ns['w']}}}p"
    if step < 0:
        rng = range(start - 1, -1, -1)
    else:
        rng = range(start + 1, len(children))
    for i in rng:
        el = children[i]
        if el.tag != w_p:
            continue
        if p_text(ns, el):
            return i, el
    return None


def main() -> int:
    if len(sys.argv) != 2:
        fail("usage: <script> /path/to/main_版式1.docx")
    docx_path = sys.argv[1]

    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml")

    ns: dict[str, str] = {}
    for _event, item in ET.iterparse(io.BytesIO(doc_xml), events=("start-ns",)):
        prefix, uri = item
        ns[prefix or ""] = uri
    if "w" not in ns:
        fail("missing w namespace in document.xml")

    q = lambda local: f"{{{ns['w']}}}{local}"
    root = ET.fromstring(doc_xml)
    body = root.find(q("body"))
    if body is None:
        fail("missing w:body")
    children = list(body)

    sect = root.find(f".//{q('sectPr')}")
    if sect is None:
        fail("missing section properties")
    pg_sz = sect.find(q("pgSz"))
    pg_mar = sect.find(q("pgMar"))
    if pg_sz is None or pg_mar is None:
        fail("missing page size/margins")
    w_w = q("w")
    w_left = q("left")
    w_right = q("right")
    try:
        text_w = int(pg_sz.get(w_w) or "0") - int(pg_mar.get(w_left) or "0") - int(pg_mar.get(w_right) or "0")
    except ValueError:
        fail("invalid page/margin numeric values")
    if text_w <= 0:
        fail("computed non-positive text width")

    w_tbl = q("tbl")
    w_tblPr = q("tblPr")
    w_tblW = q("tblW")
    w_tblLayout = q("tblLayout")
    w_tblGrid = q("tblGrid")
    w_gridCol = q("gridCol")
    w_type = q("type")
    w_val = q("val")

    cap_re = re.compile(r"^表(\d+)-(\d+)\s+.+")
    cap_nums: list[tuple[int, int]] = []
    table_count = 0

    for i, el in enumerate(children):
        if el.tag != w_tbl:
            continue
        if not is_data_table(ns, el):
            continue
        table_count += 1

        pr = el.find(w_tblPr)
        if pr is None:
            fail(f"data table #{table_count} missing tblPr")

        tbl_w = pr.find(w_tblW)
        if tbl_w is None or tbl_w.get(w_type) != "dxa":
            fail(f"data table #{table_count} missing tblW dxa")
        try:
            tbl_w_val = int(tbl_w.get(w_w) or "0")
        except ValueError:
            fail(f"data table #{table_count} has invalid tblW value")
        if tbl_w_val != text_w:
            fail(f"data table #{table_count} width {tbl_w_val} != text width {text_w}")

        layout = pr.find(w_tblLayout)
        if layout is None or layout.get(w_type) != "fixed":
            fail(f"data table #{table_count} missing fixed table layout")

        grid = el.find(w_tblGrid)
        if grid is None:
            fail(f"data table #{table_count} missing tblGrid")
        cols = grid.findall(w_gridCol)
        if not cols:
            fail(f"data table #{table_count} has empty tblGrid")
        try:
            grid_sum = sum(int(c.get(w_w) or "0") for c in cols)
        except ValueError:
            fail(f"data table #{table_count} has invalid gridCol width")
        if grid_sum != tbl_w_val:
            fail(f"data table #{table_count} grid width sum {grid_sum} != tblW {tbl_w_val}")

        above = first_non_empty_para(children, i, -1, ns)
        if above is None:
            fail(f"data table #{table_count} has no caption paragraph above")
        idx_above_1, p_above_1 = above
        cap_txt_1 = p_text(ns, p_above_1)
        cap_style_1 = p_style(ns, p_above_1)
        m = cap_re.match(cap_txt_1)
        if m is None:
            # bilingual caption: nearest line may be English, Chinese line is one paragraph above.
            above2 = first_non_empty_para(children, idx_above_1, -1, ns)
            if above2 is None:
                fail(f"data table #{table_count} caption above format invalid: {cap_txt_1}")
            _idx_above_2, p_above_2 = above2
            cap_txt_2 = p_text(ns, p_above_2)
            # Accept legacy TableCaption, current Normal/"a", or no explicit pStyle
            _valid_cap_styles = {"TableCaption", "a", None, ""}
            if cap_style_1 not in _valid_cap_styles or p_style(ns, p_above_2) not in _valid_cap_styles:
                fail(f"data table #{table_count} caption above style invalid: {cap_style_1}")
            m = cap_re.match(cap_txt_2)
            if not m:
                fail(f"data table #{table_count} caption format invalid: {cap_txt_2}")
        else:
            _valid_cap_styles = {"TableCaption", "a", None, ""}
            if cap_style_1 not in _valid_cap_styles:
                fail(f"data table #{table_count} caption above style invalid: {cap_style_1}")

        cap_nums.append((int(m.group(1)), int(m.group(2))))

        below = first_non_empty_para(children, i, 1, ns)
        if below is not None:
            _idx_below, p_below = below
            _below_style = p_style(ns, p_below)
            _below_txt = p_text(ns, p_below).strip()
            # Detect table caption below table by style or text pattern
            _is_tbl_cap_below = (_below_style == "TableCaption" or
                                 bool(re.match(r"^(表[\s\xa0]*\d+[\-\.．]\d+|Table\s+\d+[\-\.．]\d+)", _below_txt, re.IGNORECASE)))
            if _is_tbl_cap_below:
                fail(f"data table #{table_count} still has caption below table")

    allow_empty_tables = os.environ.get("SWUN_TABLE_VERIFY_ALLOW_EMPTY", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
    if table_count == 0:
        if allow_empty_tables:
            print("TABLE VERIFY: SKIP (no data tables found)")
            return 0
        fail("no data tables found")

    prev_ch = None
    prev_no = 0
    for ch, no in cap_nums:
        if prev_ch is None:
            prev_ch, prev_no = ch, no
            continue
        if ch == prev_ch:
            if no != prev_no + 1:
                fail(f"caption numbering not continuous in chapter {ch}: got {no} after {prev_no}")
        elif ch > prev_ch:
            if no != 1:
                fail(f"caption numbering must restart at 1 for new chapter {ch}, got {no}")
        else:
            fail(f"caption chapter index decreased from {prev_ch} to {ch}")
        prev_ch, prev_no = ch, no

    print(f"TABLE VERIFY: PASS ({table_count} data tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

popd >/dev/null

echo "OK: $THESIS_DIR/main_版式1.docx"
