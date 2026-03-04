"""Verification modules for swun-thesis-docx-banshi1."""

from .content_checker import check_anchor_caption_rules
from .reference_checker import (
    check_reference_external_hyperlinks,
    collect_dotted_fig_table_hyperlinks,
    collect_main_body_anchor_hyperlinks,
)
from .report_generator import main
from .structure_checker import (
    check_no_forced_break_after_heading,
    iter_main_body_blocks,
    iter_paragraphs,
    iter_tables,
)
from .style_checker import (
    check_heading5_and_following_body_indent,
    collect_main_body_hyperlink_style_runs,
    collect_unnumbered_heading5_in_main_body,
)

__all__ = [
    "main",
    "check_anchor_caption_rules",
    "check_reference_external_hyperlinks",
    "collect_dotted_fig_table_hyperlinks",
    "collect_main_body_anchor_hyperlinks",
    "check_no_forced_break_after_heading",
    "iter_main_body_blocks",
    "iter_paragraphs",
    "iter_tables",
    "check_heading5_and_following_body_indent",
    "collect_main_body_hyperlink_style_runs",
    "collect_unnumbered_heading5_in_main_body",
]
