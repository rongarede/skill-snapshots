"""Template loading facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import (
    _insert_abstract_chapters_and_sections,
    _prepend_template_cover_pages,
)

insert_abstract_chapters_and_sections = _insert_abstract_chapters_and_sections
prepend_template_cover_pages = _prepend_template_cover_pages

__all__ = [
    "insert_abstract_chapters_and_sections",
    "prepend_template_cover_pages",
]
