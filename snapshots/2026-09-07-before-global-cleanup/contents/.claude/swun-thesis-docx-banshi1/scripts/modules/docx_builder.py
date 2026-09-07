#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build SWUN thesis DOCX (Format 1) from LaTeX using the official reference template.

Pipeline (per AGENTS.md):
1) latexpand main.tex -> .main.flat.tex
2) preprocess: replace '\\<' -> '<', drop/normalize a few LaTeX constructs pandoc drops
3) pandoc -> intermediate docx (with citeproc + GB/T CSL)
4) OOXML postprocess:
   - insert Word TOC field before the first Heading 1 chapter
   - add page breaks before each Heading 1 (except when already preceded by a page break)
   - add first-line indent for body paragraphs (BodyText/FirstParagraph/Compact)
   - add hanging indent for bibliography entries ([n]...) inside the references section
   - fix mixed Chinese/Arabic section numbers by adding w:isLgl for ilvl>=1 (abstractNumId=0)
"""

from __future__ import annotations


try:
    pass
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    pass

try:
    pass
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    pass
except ModuleNotFoundError:
    pass

try:
    from modules.latex_parser import (  # noqa: F401
        CaptionMeta as CaptionMeta,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.modules.latex_parser import (  # noqa: F401
        CaptionMeta as CaptionMeta,
    )

try:
    pass
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    pass

# ==================== 全局路径变量（从 post_processor 导入，保持兼容） ====================
# 函数和全局变量已搬至 modules/post_processor.py（DOCX 后处理编排器）
# docx_builder 保留 import alias 供外部调用者（build_docx_banshi1.py 等）使用

try:
    from modules.post_processor import (
        main,
    )
except ModuleNotFoundError:
    from scripts.modules.post_processor import (
        main,
    )

# ==================== 回归测试兼容：re-export 私有帮助函数 ====================
# abstract_section_regression.py 通过 build_docx_banshi1 as builder 调用这些符号

try:
    from utils.ooxml import (
        get_body_sectPr as _get_body_sectPr,
    )
except ModuleNotFoundError:
    from scripts.utils.ooxml import (
        get_body_sectPr as _get_body_sectPr,
    )

try:
    from modules.template_loader import (
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
    )
except ModuleNotFoundError:
    from scripts.modules.template_loader import (
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
    )


if __name__ == "__main__":
    main()
