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

pushd "$THESIS_DIR" >/dev/null

echo "[1/3] Building DOCX..."
python3 "$SCRIPT_DIR/build_docx_banshi1.py" "$THESIS_DIR"

echo "[2/4] Running ref normalization regression samples..."
python3 "$SCRIPT_DIR/ref_hyphen_regression.py"

echo "[3/4] Running general DOCX checks..."
python3 /Users/bit/.codex/skills/swun-thesis-docx-banshi1/scripts/verify_extra.py \
  "$THESIS_DIR/main_版式1.docx"

echo "[4/4] Running table layout/caption checks..."
python3 - "$THESIS_DIR/main_版式1.docx" <<'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import io
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

        below = first_non_empty_para(children, i, 1, ns)
        if below is None:
            fail(f"data table #{table_count} has no caption paragraph below")
        _idx_below, p_below = below
        if p_style(ns, p_below) != "TableCaption":
            fail(f"data table #{table_count} caption below is not TableCaption style")
        cap_txt = p_text(ns, p_below)
        m = cap_re.match(cap_txt)
        if not m:
            fail(f"data table #{table_count} caption format invalid: {cap_txt}")
        cap_nums.append((int(m.group(1)), int(m.group(2))))

        above = first_non_empty_para(children, i, -1, ns)
        if above is not None:
            _idx_above, p_above = above
            if p_style(ns, p_above) == "TableCaption":
                fail(f"data table #{table_count} still has caption above table")

    if table_count == 0:
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
