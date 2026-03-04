#!/usr/bin/env python3
"""Phase 6: 视觉审查。

生成 DOCX → PDF → 截图，与 LaTeX PDF 对比。
返回需要审查的页面清单和截图路径。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REVIEW_PAGES = [
    {"name": "封面", "page": 1, "check": "封面布局、校名、论文标题位置"},
    {"name": "目录", "page": "toc", "check": "页码对齐、层级缩进"},
    {"name": "中文摘要", "page": "abstract_cn", "check": "标题、正文缩进、关键词位置"},
    {"name": "英文摘要", "page": "abstract_en", "check": "标题、正文缩进、Keywords 位置"},
    {"name": "第2章首页", "page": "ch2_start", "check": "章标题编号、首段缩进"},
    {"name": "第3章首页", "page": "ch3_start", "check": "章标题编号、首段缩进"},
    {"name": "第4章首页", "page": "ch4_start", "check": "章标题编号、首段缩进"},
    {"name": "图表页示例", "page": "figure_sample", "check": "图片位置、标题排版"},
    {"name": "参考文献首页", "page": "refs_start", "check": "悬挂缩进、编号格式"},
]


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str | None:
    """用 libreoffice 将 DOCX 转为 PDF。"""
    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                output_dir,
                docx_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            return None
        pdf_name = Path(docx_path).stem + ".pdf"
        pdf_path = os.path.join(output_dir, pdf_name)
        if os.path.exists(pdf_path):
            return pdf_path
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def run(docx_path: str, latex_pdf_path: str | None = None) -> dict:
    """运行 Phase 6 准备工作。"""
    thesis_dir = str(Path(docx_path).parent)
    docx_pdf = convert_docx_to_pdf(docx_path, thesis_dir)

    if latex_pdf_path is None:
        candidate = os.path.join(thesis_dir, "main.pdf")
        if os.path.exists(candidate):
            latex_pdf_path = candidate

    if docx_pdf is None:
        return {
            "docx_pdf": None,
            "latex_pdf": latex_pdf_path,
            "review_pages": REVIEW_PAGES,
            "status": "conversion_failed",
        }

    return {
        "docx_pdf": docx_pdf,
        "latex_pdf": latex_pdf_path,
        "review_pages": REVIEW_PAGES,
        "status": "ready_for_review",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: phase6_visual.py /path/to/main_版式1.docx [/path/to/main.pdf]", file=sys.stderr)
        sys.exit(2)
    docx = sys.argv[1]
    latex_pdf = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(run(docx, latex_pdf), indent=2, ensure_ascii=False))
