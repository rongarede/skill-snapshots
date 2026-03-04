"""Equation handling facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    _extract_display_math_number_flags,
    _number_display_equations,
)

extract_display_math_number_flags = _extract_display_math_number_flags
number_display_equations = _number_display_equations

__all__ = [
    "extract_display_math_number_flags",
    "number_display_equations",
]
