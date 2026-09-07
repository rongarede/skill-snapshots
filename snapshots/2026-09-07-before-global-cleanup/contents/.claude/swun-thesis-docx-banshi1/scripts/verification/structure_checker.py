"""Structure checker facade extracted from report_generator."""

from __future__ import annotations

from verification.report_generator import (
    _check_no_forced_break_after_heading,
    _iter_main_body_blocks,
    _iter_paragraphs,
    _iter_tables,
)

check_no_forced_break_after_heading = _check_no_forced_break_after_heading
iter_main_body_blocks = _iter_main_body_blocks
iter_paragraphs = _iter_paragraphs
iter_tables = _iter_tables

__all__ = [
    "check_no_forced_break_after_heading",
    "iter_main_body_blocks",
    "iter_paragraphs",
    "iter_tables",
]
