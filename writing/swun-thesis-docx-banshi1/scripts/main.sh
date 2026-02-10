#!/usr/bin/env bash
# swun-thesis-docx-banshi1: build SWUN thesis DOCX (Format 1) from LaTeX

set -euo pipefail

THESIS_DIR="${1:-/Users/bit/LaTeX/SWUN_Thesis}"

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

if [[ ! -f "$THESIS_DIR/build_docx_banshi1.py" ]]; then
  echo "error: missing: $THESIS_DIR/build_docx_banshi1.py" >&2
  exit 1
fi

if [[ ! -f "$THESIS_DIR/main.tex" ]]; then
  echo "error: missing: $THESIS_DIR/main.tex" >&2
  exit 1
fi

pushd "$THESIS_DIR" >/dev/null

python3 build_docx_banshi1.py

if [[ -f verify_docx.py ]]; then
  python3 verify_docx.py || true
fi

python3 /Users/bit/.codex/skills/swun-thesis-docx-banshi1/scripts/verify_extra.py \
  "$THESIS_DIR/main_版式1.docx"

popd >/dev/null

echo "OK: $THESIS_DIR/main_版式1.docx"

