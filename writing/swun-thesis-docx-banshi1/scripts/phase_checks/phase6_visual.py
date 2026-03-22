#!/usr/bin/env python3
"""Phase 6: 视觉审查。

生成 DOCX → PDF，并将生成的 PDF 与 LaTeX PDF 进行版式门禁对比。
当前硬门禁聚焦两个已知高风险回归：
1. 章标题不能退化成正文样式（必须保持居中，且字号不能明显变小）
2. 关键项目列表的正文起始位置不能明显漂移
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pdfplumber


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
CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
LIST_MARKERS = ("Consistency", "Validity", "Integrity")
LINE_Y_TOLERANCE = 3.0
CHAPTER_CENTER_TOLERANCE = 40.0
CHAPTER_HEIGHT_RATIO_MIN = 0.85
LIST_X_TOLERANCE = 24.0
CHAPTER_MIN_TOP = 65.0


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str | None:
    """用 soffice/libreoffice 将 DOCX 转为 PDF。"""
    office_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not office_bin:
        return None
    try:
        result = subprocess.run(
            [
                office_bin,
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


def _merge_line_text(words: list[dict]) -> str:
    parts: list[str] = []
    for word in words:
        text = (word.get("text") or "").strip()
        if not text:
            continue
        if parts and re.match(r"[A-Za-z0-9]",
    parts[-1][-1:]) and re.match(r"[A-Za-z0-9]",
     text[:1]):
            parts.append(" ")
        parts.append(text)
    return "".join(parts)


def _extract_lines(pdf_path: str) -> list[dict]:
    pages: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(
    x_tolerance=1,
    y_tolerance=2,
     keep_blank_chars=False) or []
            words = sorted(
    words, key=lambda w: (
        round(
            float(
                w["top"]), 2), float(
                    w["x0"])))
            lines: list[dict] = []
            current: list[dict] = []
            current_top: float | None = None

            def flush() -> None:
                nonlocal current, current_top
                if not current:
                    return
                line_words = sorted(current, key=lambda w: float(w["x0"]))
                x0 = min(float(w["x0"]) for w in line_words)
                x1 = max(float(w["x1"]) for w in line_words)
                top = min(float(w["top"]) for w in line_words)
                bottom = max(float(w["bottom"]) for w in line_words)
                avg_height = sum(float(w["height"])
                                 for w in line_words) / len(line_words)
                lines.append(
                    {
                        "text": _merge_line_text(line_words),
                        "x0": x0,
                        "x1": x1,
                        "top": top,
                        "bottom": bottom,
                        "height": avg_height,
                    }
                )
                current = []
                current_top = None

            for word in words:
                top = float(word["top"])
                if current_top is None or abs(
    top - current_top) <= LINE_Y_TOLERANCE:
                    current.append(word)
                    if current_top is None:
                        current_top = top
                    else:
                        current_top = min(current_top, top)
                else:
                    flush()
                    current.append(word)
                    current_top = top
            flush()
            pages.append({"page_num": page_num, "width": float(
                page.width), "lines": lines, "words": words})
    return pages


def _find_chapter_lines(pages: list[dict]) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for page in pages:
        for line in page["lines"]:
            text = line["text"]
            if line["top"] < CHAPTER_MIN_TOP:
                continue
            if re.search(r"\.{2,}\s*\d+\s*$", text):
                continue
            match = CHAPTER_RE.search(line["text"])
            if not match:
                continue
            chapter_no = int(match.group(1))
            candidate = {
                "page_num": page["page_num"],
                "page_width": page["width"],
                **line,
            }
            best = result.get(chapter_no)
            if best is None or candidate["page_num"] < best["page_num"]:
                result[chapter_no] = candidate
    return result


def _find_list_lines(pages: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for page in pages:
        for word in page["words"]:
            text = (word.get("text") or "").strip()
            for marker in LIST_MARKERS:
                if text.startswith(marker):
                    result.setdefault(
                        marker,
                        {
                            "page_num": page["page_num"],
                            "page_width": page["width"],
                            "text": text,
                            "x0": float(word["x0"]),
                            "x1": float(word["x1"]),
                            "top": float(word["top"]),
                            "bottom": float(word["bottom"]),
                            "height": float(word["height"]),
                        },
                    )
    return result


def _compare_pdfs(docx_pdf: str, latex_pdf: str |
                  None) -> tuple[list[str], dict]:
    if not latex_pdf or not os.path.exists(latex_pdf):
        return ["缺少 LaTeX PDF 基线，无法执行 Phase 6 视觉门禁"], {}

    latex_pages = _extract_lines(latex_pdf)
    docx_pages = _extract_lines(docx_pdf)

    latex_chapters = _find_chapter_lines(latex_pages)
    docx_chapters = _find_chapter_lines(docx_pages)
    latex_lists = _find_list_lines(latex_pages)
    docx_lists = _find_list_lines(docx_pages)

    errors: list[str] = []
    metrics: dict[str, dict] = {
        "chapters": {},
        "lists": {},
    }

    shared_chapters = sorted(set(latex_chapters) & set(docx_chapters))
    if not shared_chapters:
        errors.append("未在 DOCX PDF 与 LaTeX PDF 中找到可比对的章标题")
    for chapter_no in shared_chapters:
        latex_line = latex_chapters[chapter_no]
        docx_line = docx_chapters[chapter_no]
        latex_center_offset = abs(
            ((latex_line["x0"] + latex_line["x1"]) / 2.0) - (latex_line["page_width"] / 2.0))
        docx_center_offset = abs(
            ((docx_line["x0"] + docx_line["x1"]) / 2.0) - (docx_line["page_width"] / 2.0))
        height_ratio = float(docx_line["height"]) / \
                             max(float(latex_line["height"]), 1.0)
        metrics["chapters"][str(chapter_no)] = {
            "latex_page": latex_line["page_num"],
            "docx_page": docx_line["page_num"],
            "latex_center_offset": round(latex_center_offset, 2),
            "docx_center_offset": round(docx_center_offset, 2),
            "latex_height": round(float(latex_line["height"]), 2),
            "docx_height": round(float(docx_line["height"]), 2),
            "height_ratio": round(height_ratio, 3),
        }
        if docx_center_offset > CHAPTER_CENTER_TOLERANCE:
            errors.append(
    f"第{chapter_no}章标题未居中: LaTeX偏移={
        latex_center_offset:.1f}pt, DOCX偏移={
            docx_center_offset:.1f}pt" )
        if height_ratio < CHAPTER_HEIGHT_RATIO_MIN:
            errors.append(
    f"第{chapter_no}章标题高度偏小: LaTeX={
        latex_line['height']:.2f}, DOCX={
            docx_line['height']:.2f}" )

    # Only markers present in at least one PDF are relevant for regression detection.
    any_markers = [
    marker for marker in LIST_MARKERS if marker in latex_lists or marker in docx_lists]
    shared_markers = [
    marker for marker in LIST_MARKERS if marker in latex_lists and marker in docx_lists]
    # Report an error only when a marker appears in one PDF but is absent from the other
    # (indicates a real regression).  When no marker exists in either document, there is
    # nothing to compare — skip silently rather than flagging a spurious error.
    for marker in any_markers:
        if marker not in latex_lists:
            errors.append(f"列表项 {marker} 在 LaTeX PDF 中未找到（可能丢失）")
        elif marker not in docx_lists:
            errors.append(f"列表项 {marker} 在 DOCX PDF 中未找到（可能丢失）")
    for marker in shared_markers:
        latex_line = latex_lists[marker]
        docx_line = docx_lists[marker]
        x_delta = abs(float(docx_line["x0"]) - float(latex_line["x0"]))
        metrics["lists"][marker] = {
            "latex_page": latex_line["page_num"],
            "docx_page": docx_line["page_num"],
            "latex_x0": round(float(latex_line["x0"]), 2),
            "docx_x0": round(float(docx_line["x0"]), 2),
            "delta": round(x_delta, 2),
        }
        if x_delta > LIST_X_TOLERANCE:
            errors.append(
    f"列表项 {marker} 缩进漂移过大: LaTeX x0={
        latex_line['x0']:.1f}, DOCX x0={
            docx_line['x0']:.1f}" )

    return errors, metrics


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

    errors, metrics = _compare_pdfs(docx_pdf, latex_pdf_path)
    return {
        "docx_pdf": docx_pdf,
        "latex_pdf": latex_pdf_path,
        "review_pages": REVIEW_PAGES,
        "errors": errors,
        "metrics": metrics,
        "status": "pass" if not errors else "fail",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
    "usage: phase6_visual.py /path/to/main_版式1.docx [/path/to/main.pdf]",
     file=sys.stderr)
        sys.exit(2)
    docx = sys.argv[1]
    latex_pdf = sys.argv[2] if len(sys.argv) > 2 else None
    print(json.dumps(run(docx, latex_pdf), indent=2, ensure_ascii=False))
