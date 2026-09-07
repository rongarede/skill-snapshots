#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin CLI wrapper for refactored extra DOCX verification.

Compatibility note:
- Re-exports legacy symbols for scripts that imported helpers
  from `verify_extra` directly.
"""

from __future__ import annotations

import verification.report_generator as _core

for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

_core_main = _core.main


def main() -> int:
    """委托给核心模块执行额外的 DOCX 验证检查并返回退出码。"""
    return _core_main()


if __name__ == "__main__":
    raise SystemExit(main())
