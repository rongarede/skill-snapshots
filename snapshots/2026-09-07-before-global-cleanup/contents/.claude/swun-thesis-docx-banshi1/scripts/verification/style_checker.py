"""Style checker facade extracted from report_generator."""

from __future__ import annotations

from verification.report_generator import (
    _check_heading5_and_following_body_indent,
    _collect_main_body_hyperlink_style_runs,
    _collect_unnumbered_heading5_in_main_body,
)

check_heading5_and_following_body_indent = _check_heading5_and_following_body_indent
collect_main_body_hyperlink_style_runs = _collect_main_body_hyperlink_style_runs
collect_unnumbered_heading5_in_main_body = _collect_unnumbered_heading5_in_main_body

__all__ = [
    "check_heading5_and_following_body_indent",
    "collect_main_body_hyperlink_style_runs",
    "collect_unnumbered_heading5_in_main_body",
]
