"""Figure/table handling facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    _apply_three_line_tables,
    _fix_figure_captions,
    _inject_captions_from_meta,
)

apply_three_line_tables = _apply_three_line_tables
fix_figure_captions = _fix_figure_captions
inject_captions_from_meta = _inject_captions_from_meta

__all__ = [
    "apply_three_line_tables",
    "fix_figure_captions",
    "inject_captions_from_meta",
]
