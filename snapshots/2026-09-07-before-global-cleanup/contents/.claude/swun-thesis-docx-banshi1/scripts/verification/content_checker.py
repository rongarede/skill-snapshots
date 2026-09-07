"""Content checker facade extracted from report_generator."""

from __future__ import annotations

from verification.report_generator import _check_anchor_caption_rules

check_anchor_caption_rules = _check_anchor_caption_rules

__all__ = ["check_anchor_caption_rules"]
