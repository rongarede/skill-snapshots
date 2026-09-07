#!/usr/bin/env bash
# gate-loop: 6-Phase DOCX 检测循环
set -euo pipefail

THESIS_DIR="${1:-/Users/bit/LaTeX/SWUN_Thesis}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "  DOCX Gate-Loop 6-Phase Detection"
echo "=========================================="

python3 "$SCRIPT_DIR/gate_loop_runner.py" "$THESIS_DIR" "${@:2}"
