"""Reference checker facade extracted from report_generator."""

from __future__ import annotations

from verification.report_generator import (
    _check_reference_external_hyperlinks,
    _collect_dotted_fig_table_hyperlinks,
    _collect_main_body_anchor_hyperlinks,
)

check_reference_external_hyperlinks = _check_reference_external_hyperlinks
collect_dotted_fig_table_hyperlinks = _collect_dotted_fig_table_hyperlinks
collect_main_body_anchor_hyperlinks = _collect_main_body_anchor_hyperlinks

__all__ = [
    "check_reference_external_hyperlinks",
    "collect_dotted_fig_table_hyperlinks",
    "collect_main_body_anchor_hyperlinks",
]
