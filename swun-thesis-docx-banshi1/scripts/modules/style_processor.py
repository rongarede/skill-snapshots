"""Style processing facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    _ensure_indent_for_body_paragraphs,
    _normalize_unknown_pstyles,
    _set_para_center,
    _set_para_keep_lines,
    _set_para_keep_next,
    _set_para_tabs_for_equation,
)

ensure_indent_for_body_paragraphs = _ensure_indent_for_body_paragraphs
normalize_unknown_pstyles = _normalize_unknown_pstyles
set_para_center = _set_para_center
set_para_keep_lines = _set_para_keep_lines
set_para_keep_next = _set_para_keep_next
set_para_tabs_for_equation = _set_para_tabs_for_equation

__all__ = [
    "ensure_indent_for_body_paragraphs",
    "normalize_unknown_pstyles",
    "set_para_center",
    "set_para_keep_lines",
    "set_para_keep_next",
    "set_para_tabs_for_equation",
]
