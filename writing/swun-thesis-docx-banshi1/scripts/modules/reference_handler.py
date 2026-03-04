"""Reference handling facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    _ensure_hanging_indent_for_bibliography,
    _fix_ref_dot_to_hyphen,
    _strip_anchor_hyperlinks_in_main_body,
)

ensure_hanging_indent_for_bibliography = _ensure_hanging_indent_for_bibliography
fix_ref_dot_to_hyphen = _fix_ref_dot_to_hyphen
strip_anchor_hyperlinks_in_main_body = _strip_anchor_hyperlinks_in_main_body

__all__ = [
    "ensure_hanging_indent_for_bibliography",
    "fix_ref_dot_to_hyphen",
    "strip_anchor_hyperlinks_in_main_body",
]
