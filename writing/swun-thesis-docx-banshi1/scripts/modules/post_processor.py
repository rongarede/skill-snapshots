"""Post-processing facade module extracted from docx_builder."""

from __future__ import annotations

from modules.docx_builder import _postprocess_docx

postprocess_docx = _postprocess_docx

__all__ = ["postprocess_docx"]
