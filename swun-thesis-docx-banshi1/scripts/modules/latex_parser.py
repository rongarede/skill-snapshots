"""LaTeX parsing facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    CaptionMeta,
    _extract_caption_meta,
    _extract_display_math_number_flags,
    _extract_keywords,
    _parse_latex_table_col_specs,
    _preprocess_latex,
    _split_keywords,
)

preprocess_latex = _preprocess_latex
extract_caption_meta = _extract_caption_meta
parse_latex_table_col_specs = _parse_latex_table_col_specs
extract_display_math_number_flags = _extract_display_math_number_flags
extract_keywords = _extract_keywords
split_keywords = _split_keywords

__all__ = [
    "CaptionMeta",
    "preprocess_latex",
    "extract_caption_meta",
    "parse_latex_table_col_specs",
    "extract_display_math_number_flags",
    "extract_keywords",
    "split_keywords",
]
