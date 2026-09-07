#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin CLI wrapper for the refactored DOCX build pipeline.

Compatibility note:
- Re-exports legacy symbols for regression scripts importing
  private helpers from `build_docx_banshi1`.
"""

from __future__ import annotations

import modules.docx_builder as _core

# Re-export all implementation symbols, including private helpers used by
# local regression scripts.
for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

_core_main = _core.main


def main(argv: list[str] | None = None) -> None:
    """委托给核心模块的 main 函数，构建版式1 DOCX 文件。"""
    _core_main(argv)


if __name__ == "__main__":
    main()
