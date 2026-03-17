#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DOCX 后处理编排器 — 将 LaTeX 编译产出的中间 DOCX 转换为最终版式1格式。

Pipeline:
1) latexpand main.tex -> .main.flat.tex
2) preprocess LaTeX 源文本（规范化特殊符号、算法块等）
3) pandoc -> 中间 DOCX（带 citeproc + GB/T CSL）
4) OOXML 后处理 -> 最终 DOCX（封面、样式、字体、标题编号、公式、图表等）
"""

from __future__ import annotations

import copy
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# ==================== 模块导入（双路径兼容） ====================

try:
    from utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        get_body_sectPr as _get_body_sectPr,
        set_sect_pgnum as _set_sect_pgnum,
        run_cmd as _run,
    )
except ModuleNotFoundError:
    from scripts.utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        get_body_sectPr as _get_body_sectPr,
        set_sect_pgnum as _set_sect_pgnum,
        run_cmd as _run,
    )

try:
    from modules.caption_profile import (
        CaptionFormatProfile,
        extract_caption_profiles,
    )
except ModuleNotFoundError:
    from scripts.modules.caption_profile import (
        CaptionFormatProfile,
        extract_caption_profiles,
    )

try:
    from modules.template_loader import (
        prepend_template_cover_pages as _prepend_template_cover_pages,
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
        insert_abstract_keywords as _insert_abstract_keywords,
        ensure_update_fields_in_settings as _ensure_update_fields_in_settings,
        insert_toc_before_first_chapter as _insert_toc_before_first_chapter,
        add_page_breaks_before_h1 as _add_page_breaks_before_h1,
    )
except ModuleNotFoundError:
    from scripts.modules.template_loader import (
        prepend_template_cover_pages as _prepend_template_cover_pages,
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
        insert_abstract_keywords as _insert_abstract_keywords,
        ensure_update_fields_in_settings as _ensure_update_fields_in_settings,
        insert_toc_before_first_chapter as _insert_toc_before_first_chapter,
        add_page_breaks_before_h1 as _add_page_breaks_before_h1,
    )

try:
    from modules.style_processor import (
        align_styles_to_reference as _align_styles_to_reference,
        collect_style_ids as _collect_style_ids,
        normalize_unknown_pstyles as _normalize_unknown_pstyles,
        fix_numbering_isLgl as _fix_numbering_isLgl,
        normalize_list_indents as _normalize_list_indents,
        inject_heading_numbering as _inject_heading_numbering,
        bind_heading_styles_to_numbering as _bind_heading_styles_to_numbering,
        number_paragraph_headings_in_main_body as _number_paragraph_headings_in_main_body,
        strip_numbering_from_backmatter_headings as _strip_numbering_from_backmatter_headings,
        ensure_indent_for_body_paragraphs as _ensure_indent_for_body_paragraphs,
        ensure_hanging_indent_for_bibliography as _ensure_hanging_indent_for_bibliography,
        remove_docgrid_lines_type as _remove_docgrid_lines_type,
    )
except ModuleNotFoundError:
    from scripts.modules.style_processor import (
        align_styles_to_reference as _align_styles_to_reference,
        collect_style_ids as _collect_style_ids,
        normalize_unknown_pstyles as _normalize_unknown_pstyles,
        fix_numbering_isLgl as _fix_numbering_isLgl,
        normalize_list_indents as _normalize_list_indents,
        inject_heading_numbering as _inject_heading_numbering,
        bind_heading_styles_to_numbering as _bind_heading_styles_to_numbering,
        number_paragraph_headings_in_main_body as _number_paragraph_headings_in_main_body,
        strip_numbering_from_backmatter_headings as _strip_numbering_from_backmatter_headings,
        ensure_indent_for_body_paragraphs as _ensure_indent_for_body_paragraphs,
        ensure_hanging_indent_for_bibliography as _ensure_hanging_indent_for_bibliography,
        remove_docgrid_lines_type as _remove_docgrid_lines_type,
    )

try:
    from modules.font_handler import (
        split_mixed_script_runs as _split_mixed_script_runs,
        normalize_ascii_run_fonts as _normalize_ascii_run_fonts,
        normalize_bibliography_run_style as _normalize_bibliography_run_style,
    )
except ModuleNotFoundError:
    from scripts.modules.font_handler import (
        split_mixed_script_runs as _split_mixed_script_runs,
        normalize_ascii_run_fonts as _normalize_ascii_run_fonts,
        normalize_bibliography_run_style as _normalize_bibliography_run_style,
    )

try:
    from modules.reference_handler import (
        fix_ref_dot_to_hyphen as _fix_ref_dot_to_hyphen,
        collect_hyperlink_char_style_ids as _collect_hyperlink_char_style_ids,
        strip_anchor_hyperlinks_in_main_body as _strip_anchor_hyperlinks_in_main_body,
        strip_doi_hyperlinks_in_bibliography as _strip_doi_hyperlinks_in_bibliography,
    )
except ModuleNotFoundError:
    from scripts.modules.reference_handler import (
        fix_ref_dot_to_hyphen as _fix_ref_dot_to_hyphen,
        collect_hyperlink_char_style_ids as _collect_hyperlink_char_style_ids,
        strip_anchor_hyperlinks_in_main_body as _strip_anchor_hyperlinks_in_main_body,
        strip_doi_hyperlinks_in_bibliography as _strip_doi_hyperlinks_in_bibliography,
    )

try:
    from modules.figure_table_handler import (
        inject_captions_from_meta as _inject_captions_from_meta,
        apply_three_line_tables as _apply_three_line_tables,
        fit_figure_images_to_cells as _fit_figure_images_to_cells,
        dedupe_body_level_anchor_bookmarks as _dedupe_body_level_anchor_bookmarks,
        first_table_style_id as _first_table_style_id,
        inject_figure_table_style as _inject_figure_table_style,
        remove_empty_para_before_table_captions as _remove_empty_para_before_table_captions,
    )
except ModuleNotFoundError:
    from scripts.modules.figure_table_handler import (
        inject_captions_from_meta as _inject_captions_from_meta,
        apply_three_line_tables as _apply_three_line_tables,
        fit_figure_images_to_cells as _fit_figure_images_to_cells,
        dedupe_body_level_anchor_bookmarks as _dedupe_body_level_anchor_bookmarks,
        first_table_style_id as _first_table_style_id,
        inject_figure_table_style as _inject_figure_table_style,
        remove_empty_para_before_table_captions as _remove_empty_para_before_table_captions,
    )

try:
    from modules.equation_handler import (
        number_display_equations as _number_display_equations,
    )
except ModuleNotFoundError:
    from scripts.modules.equation_handler import (
        number_display_equations as _number_display_equations,
    )

try:
    from modules.algorithm_handler import (
        format_algorithm_blocks as _format_algorithm_blocks,
    )
except ModuleNotFoundError:
    from scripts.modules.algorithm_handler import (
        format_algorithm_blocks as _format_algorithm_blocks,
    )

try:
    from modules.footer_handler import (
        replace_wps_footers as _replace_wps_footers,
        fix_hyperlink_style as _fix_hyperlink_style,
    )
except ModuleNotFoundError:
    from scripts.modules.footer_handler import (
        replace_wps_footers as _replace_wps_footers,
        fix_hyperlink_style as _fix_hyperlink_style,
    )

try:
    from modules.latex_parser import (
        CaptionMeta as CaptionMeta,
        load_caption_profiles as _load_caption_profiles,
        preprocess_latex as _preprocess_latex,
        is_experiment_figure_path as _is_experiment_figure_path,
        extract_caption_meta as _extract_caption_meta,
        parse_latex_table_col_specs as _parse_latex_table_col_specs,
        extract_display_math_number_flags as _extract_display_math_number_flags,
        extract_keywords as _extract_keywords,
    )
except ModuleNotFoundError:
    from scripts.modules.latex_parser import (
        CaptionMeta as CaptionMeta,
        load_caption_profiles as _load_caption_profiles,
        preprocess_latex as _preprocess_latex,
        is_experiment_figure_path as _is_experiment_figure_path,
        extract_caption_meta as _extract_caption_meta,
        parse_latex_table_col_specs as _parse_latex_table_col_specs,
        extract_display_math_number_flags as _extract_display_math_number_flags,
        extract_keywords as _extract_keywords,
    )

try:
    from utils.text_utils import normalize_chinese_spaces as _normalize_chinese_spaces
except ModuleNotFoundError:
    from scripts.utils.text_utils import normalize_chinese_spaces as _normalize_chinese_spaces

# ==================== 全局路径变量 ====================

ROOT = Path("/Users/bit/LaTeX/SWUN_Thesis")

# post_processor.py 位于 scripts/modules/，SCRIPT_DIR 指向 scripts/
SCRIPT_DIR = Path(__file__).resolve().parents[1]

TEMPLATE_DOCX = Path(
    os.environ.get(
        "SWUN_TEMPLATE_DOCX",
        "/Users/bit/LaTeX/SWUN_Thesis/.高春琴_normalized.docx",
    )
).expanduser()
CAPTION_PROFILE_DOCX = Path(
    os.environ.get(
        "SWUN_CAPTION_PROFILE_DOCX",
        "/Users/bit/LaTeX/SWUN_Thesis/网络与信息安全_高春琴.docx",
    )
).expanduser()
MAIN_TEX = ROOT / "main.tex"
CSL = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
BIB = ROOT / "backmatter" / "references.bib"

FLAT_TEX = ROOT / ".main.flat.tex"
INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
OUTPUT_DOCX = ROOT / "main_版式1.docx"

# caption profiles 缓存（_resolve_paths 重置为 None 触发重新加载）
_DEFAULT_CAPTION_PROFILES: dict[str, CaptionFormatProfile] | None = None


# ==================== 核心函数 ====================

def _verify_docx_experiment_images_are_png(
    docx_path: Path,
) -> tuple[int, list[tuple[str, str]]]:
    """验证 DOCX 内实验图引用全部落为 PNG 媒体。"""
    with zipfile.ZipFile(docx_path, "r") as zf:
        doc_xml = zf.read("word/document.xml")
        rel_xml = zf.read("word/_rels/document.xml.rels")

    ns_doc = _collect_ns(doc_xml)
    if "w" not in ns_doc:
        return 0, [("document.xml", "missing w namespace")]
    root = ET.fromstring(doc_xml)

    rel_root = ET.fromstring(rel_xml)
    rel_map: dict[str, str] = {}
    for rel in rel_root:
        # 包关系中 Id/Target 通常是非限定属性
        rid = rel.get("Id")
        target = rel.get("Target", "")
        if rid is None:
            rid = rel.get(next((k for k in rel.attrib if k.endswith("}Id")), ""))
        if not target:
            target = rel.get(
                next((k for k in rel.attrib if k.endswith("}Target")), ""), ""
            )
        if rid:
            rel_map[rid] = target

    q = lambda p, l: f"{{{ns_doc[p]}}}{l}"
    q_r_embed = "{%s}embed" % ns_doc["r"]
    bad: list[tuple[str, str]] = []
    total = 0
    for d in root.findall(f".//{q('w', 'drawing')}"):
        blip = d.find(f".//{q('a', 'blip')}")
        if blip is None:
            continue
        rid = blip.get(q_r_embed)
        if not rid:
            continue
        cNvPr = d.find(f".//{q('pic', 'cNvPr')}")
        desc = cNvPr.get("descr", "").strip() if cNvPr is not None else ""
        if not _is_experiment_figure_path(desc):
            continue
        total += 1
        target = rel_map.get(rid, "")
        if not target.lower().endswith(".png"):
            bad.append((desc, target))
    return total, bad


def _normalize_body_chinese_spaces(doc_ns: dict, body) -> None:
    """遍历正文段落的 <w:t> 元素，规范化中文排版空格。

    处理两种情况：
    1. 单个 <w:t> 内部的空格
    2. 跨 <w:r> 的空格（前一个 run 结尾字符 + 下一个 run 开头空格）
    """
    w_p = _qn(doc_ns, "w", "p")
    w_r = _qn(doc_ns, "w", "r")
    w_t = _qn(doc_ns, "w", "t")
    w_pPr = _qn(doc_ns, "w", "pPr")
    w_pStyle = _qn(doc_ns, "w", "pStyle")
    w_val = _qn(doc_ns, "w", "val")

    # 跳过的样式（标题、目录等）
    skip_styles = {"Heading1", "Heading2", "Heading3", "Heading4", "Heading5",
                   "TOC1", "TOC2", "TOC3", "TOCHeading", "Title", "Subtitle"}

    for para in body.iter(w_p):
        # 检查段落样式，跳过标题和目录
        pPr = para.find(w_pPr)
        if pPr is not None:
            pStyle = pPr.find(w_pStyle)
            if pStyle is not None and pStyle.get(w_val, "") in skip_styles:
                continue

        # 收集段落中所有 <w:t> 元素
        t_elems = list(para.iter(w_t))
        if not t_elems:
            continue

        # 处理单个 <w:t> 内部的空格
        for t_elem in t_elems:
            if t_elem.text:
                new_text = _normalize_chinese_spaces(t_elem.text)
                if new_text != t_elem.text:
                    t_elem.text = new_text

        # 处理跨 run 的空格：前一个 run 结尾 + 下一个 run 开头空格
        for idx in range(1, len(t_elems)):
            prev_t = t_elems[idx - 1]
            curr_t = t_elems[idx]
            if not prev_t.text or not curr_t.text:
                continue
            if not curr_t.text.startswith(" "):
                continue

            prev_last = prev_t.text[-1]
            # 去掉开头空格后的第一个字符
            stripped = curr_t.text.lstrip(" ")
            if not stripped:
                continue
            curr_first = stripped[0]

            # 用 normalize_chinese_spaces 判断这个空格是否应删除
            test = prev_last + " " + curr_first
            normalized = _normalize_chinese_spaces(test)
            if " " not in normalized:
                curr_t.text = stripped
                # 如果去掉了开头空格，需要检查 xml:space="preserve"
                if curr_t.text and not curr_t.text[0].isspace() and not curr_t.text[-1].isspace():
                    if "{http://www.w3.org/XML/1998/namespace}space" in curr_t.attrib:
                        del curr_t.attrib["{http://www.w3.org/XML/1998/namespace}space"]


def _postprocess_docx(
    input_docx: Path,
    output_docx: Path,
    display_math_flags: list[bool] | None,
    cn_keywords: str | None,
    en_keywords: str | None,
    caption_meta: dict[str, CaptionMeta],
    caption_profiles: dict[str, CaptionFormatProfile],
    latex_col_ratios: dict[str, list[float]] | None = None,
) -> None:
    """OOXML 后处理编排：从中间 DOCX 生成最终版式1 DOCX。"""
    with zipfile.ZipFile(input_docx, "r") as zin:
        files = zin.namelist()

        doc_xml = zin.read("word/document.xml")
        doc_ns = _collect_ns(doc_xml)
        if "w" not in doc_ns:
            raise RuntimeError("word/document.xml missing w namespace")
        _register_ns(doc_ns)

        root = ET.fromstring(doc_xml)
        w_body = _qn(doc_ns, "w", "body")
        body = root.find(w_body)
        if body is None:
            raise RuntimeError("word/document.xml missing w:body")

        # 插入封面页（来自模板）
        _prepend_template_cover_pages(doc_ns, body, TEMPLATE_DOCX)

        styles_xml = zin.read("word/styles.xml") if "word/styles.xml" in files else b""
        known_styles = _collect_style_ids(styles_xml) if styles_xml else set()
        table_style_id = _first_table_style_id(styles_xml) if styles_xml else None
        hyperlink_style_ids = (
            _collect_hyperlink_char_style_ids(styles_xml) if styles_xml else set()
        )

        sectPr = _get_body_sectPr(doc_ns, body)
        if sectPr is not None:
            sectPr_proto = copy.deepcopy(sectPr)
        else:
            sectPr_proto = None

        # 插入中英文摘要章节与关键词
        if sectPr_proto is not None:
            _insert_abstract_chapters_and_sections(doc_ns, body, sectPr_proto)

        _insert_abstract_keywords(doc_ns, body, cn_keywords, en_keywords)

        # 目录、分页、标题编号
        _insert_toc_before_first_chapter(doc_ns, body, sectPr_proto)
        _add_page_breaks_before_h1(doc_ns, body)
        _number_paragraph_headings_in_main_body(doc_ns, body)

        # 算法块格式化
        _format_algorithm_blocks(doc_ns, root, body)

        # 正文段落缩进 & 参考文献悬挂缩进
        _ensure_indent_for_body_paragraphs(doc_ns, body)
        _ensure_hanging_indent_for_bibliography(doc_ns, body)

        # 字体处理：中英文分割 -> ASCII 字体规范化 -> 参考文献字体
        _split_mixed_script_runs(doc_ns, body)
        _normalize_ascii_run_fonts(doc_ns, body)
        _normalize_bibliography_run_style(doc_ns, body)

        # 三线表 & 图表标题注入（表格字体必须在 normalize 之后）
        _apply_three_line_tables(
            doc_ns, root, body, table_style_id, latex_col_ratios=latex_col_ratios
        )
        _inject_captions_from_meta(doc_ns, body, caption_meta, caption_profiles)
        # 清理表格标题前的多余空段落
        _remove_empty_para_before_table_captions(doc_ns, body)
        _fit_figure_images_to_cells(doc_ns, body)

        # 书签去重 & 超链接清理
        _dedupe_body_level_anchor_bookmarks(doc_ns, body)
        _fix_ref_dot_to_hyphen(doc_ns, body)
        _strip_anchor_hyperlinks_in_main_body(doc_ns, body, hyperlink_style_ids)
        _strip_doi_hyperlinks_in_bibliography(doc_ns, body)

        # 公式编号
        _number_display_equations(doc_ns, root, body, display_math_flags)

        # 未知段落样式规范化
        if known_styles:
            _normalize_unknown_pstyles(doc_ns, body, known_styles)

        # 后附章节（参考文献/致谢）去除编号
        _strip_numbering_from_backmatter_headings(doc_ns, body)

        # 最终/主节：页码从 1 开始（阿拉伯数字）
        sectPr2 = _get_body_sectPr(doc_ns, body)
        if sectPr2 is not None:
            _set_sect_pgnum(doc_ns, sectPr2, fmt="decimal", start=1)

        # 中文排版空格规范化（移除标点后空格、中英文间空格）
        _normalize_body_chinese_spaces(doc_ns, body)

        # 移除 docGrid type="lines" 防止行间距膨胀
        _remove_docgrid_lines_type(doc_ns, body)

        new_doc_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        # 编号 XML 处理
        numbering_xml = (
            zin.read("word/numbering.xml") if "word/numbering.xml" in files else None
        )
        new_numbering_xml = numbering_xml
        if new_numbering_xml:
            new_numbering_xml = _inject_heading_numbering(new_numbering_xml)
            new_numbering_xml = _fix_numbering_isLgl(doc_ns, new_numbering_xml)
            new_numbering_xml = _normalize_list_indents(new_numbering_xml)

        # 样式 XML 处理：标题编号绑定 + 样式对齐 + Hyperlink 样式修复 + 图表样式注入
        new_styles_xml = styles_xml
        if new_styles_xml:
            new_styles_xml = _bind_heading_styles_to_numbering(new_styles_xml)
            new_styles_xml = _align_styles_to_reference(new_styles_xml)
            new_styles_xml = _fix_hyperlink_style(new_styles_xml)
            new_styles_xml = _inject_figure_table_style(new_styles_xml)

        # 读取所有文件数据供 footer 替换使用
        file_data: dict[str, bytes] = {}
        for name in files:
            file_data[name] = zin.read(name)

        # 替换 WPS 遗留页脚为干净的 PAGE 域页脚
        file_data["word/document.xml"] = new_doc_xml
        _replace_wps_footers(file_data, new_doc_xml)
        # 从 footer 重新分配后获取可能更新的 document.xml
        new_doc_xml = file_data["word/document.xml"]

        # settings.xml：添加 updateFields 支持打开时自动更新目录
        if "word/settings.xml" in file_data:
            new_settings_xml = _ensure_update_fields_in_settings(
                doc_ns, file_data["word/settings.xml"]
            )
        else:
            new_settings_xml = None

        # 写入新 DOCX（其余文件原样复制）
        tmp_out = output_docx.with_suffix(".docx.tmp")
        if tmp_out.exists():
            tmp_out.unlink()
        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in files:
                if name == "word/document.xml":
                    data = new_doc_xml
                elif name == "word/numbering.xml" and new_numbering_xml is not None:
                    data = new_numbering_xml
                elif name == "word/styles.xml" and new_styles_xml is not None:
                    data = new_styles_xml
                elif name == "word/settings.xml" and new_settings_xml is not None:
                    data = new_settings_xml
                else:
                    data = file_data[name]
                zout.writestr(name, data)
        tmp_out.replace(output_docx)


def _resolve_paths(thesis_dir: Path) -> None:
    """将模块级路径变量重新绑定到指定的论文目录。"""
    global ROOT, MAIN_TEX, CSL, BIB, FLAT_TEX, INTERMEDIATE_DOCX, OUTPUT_DOCX  # noqa: PLW0603
    global CAPTION_PROFILE_DOCX, _DEFAULT_CAPTION_PROFILES  # noqa: PLW0603

    ROOT = thesis_dir
    MAIN_TEX = ROOT / "main.tex"

    # 优先使用项目本地 CSL，回退到 skill 内置副本
    default_csl = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
    if default_csl.exists():
        CSL = default_csl
    else:
        CSL = SCRIPT_DIR / "china-national-standard-gb-t-7714-2015-numeric.csl"

    BIB = Path(
        os.environ.get("SWUN_BIB", str(ROOT / "backmatter" / "references.bib"))
    ).expanduser()
    CAPTION_PROFILE_DOCX = Path(
        os.environ.get(
            "SWUN_CAPTION_PROFILE_DOCX",
            str(ROOT / "网络与信息安全_高春琴.docx"),
        )
    ).expanduser()
    _DEFAULT_CAPTION_PROFILES = None

    FLAT_TEX = ROOT / ".main.flat.tex"
    INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
    OUTPUT_DOCX = ROOT / "main_版式1.docx"


def main(argv: list[str] | None = None) -> None:
    """主入口：解析参数、运行完整构建管线。"""
    argv = list(sys.argv[1:] if argv is None else argv)

    # 默认：使用当前工作目录（若包含 main.tex），否则使用硬编码回退路径
    if argv:
        thesis_dir = Path(argv[0]).expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        thesis_dir = (
            cwd if (cwd / "main.tex").exists() else Path("/Users/bit/LaTeX/SWUN_Thesis")
        )

    _resolve_paths(thesis_dir)

    # 允许通过环境变量在绑定 thesis_dir 后覆盖 CSL（保持旧行为）
    csl_override = os.environ.get("SWUN_CSL")
    if csl_override:
        global CSL  # noqa: PLW0603
        CSL = Path(csl_override).expanduser()

    # 验证必要文件存在
    for p in [TEMPLATE_DOCX, CAPTION_PROFILE_DOCX, MAIN_TEX, CSL, BIB]:
        if not p.exists():
            if p == CAPTION_PROFILE_DOCX:
                raise SystemExit(
                    f"missing required caption profile source: {p} "
                    "(override with SWUN_CAPTION_PROFILE_DOCX)"
                )
            raise SystemExit(f"missing required file: {p}")

    # 备份现有输出
    if OUTPUT_DOCX.exists():
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = OUTPUT_DOCX.with_suffix(f".docx.bak_{ts}")
        shutil.copy2(OUTPUT_DOCX, bak)

    # 1) latexpand -> flat tex
    flat = subprocess.run(
        ["latexpand", str(MAIN_TEX)],
        cwd=str(ROOT),
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8", errors="ignore")

    flat = _preprocess_latex(flat)
    FLAT_TEX.write_text(flat, encoding="utf-8")
    caption_meta = _extract_caption_meta(flat)
    caption_profiles = _load_caption_profiles(CAPTION_PROFILE_DOCX)
    display_math_flags = _extract_display_math_number_flags(flat)
    cn_kw, en_kw = _extract_keywords(flat)
    latex_col_ratios = _parse_latex_table_col_specs(flat)

    # 2) pandoc -> 中间 DOCX
    if INTERMEDIATE_DOCX.exists():
        INTERMEDIATE_DOCX.unlink()
    _run(
        [
            "pandoc",
            str(FLAT_TEX),
            "--from=latex",
            "--to=docx",
            f"--reference-doc={TEMPLATE_DOCX}",
            f"--csl={CSL}",
            f"--bibliography={BIB}",
            "--citeproc",
            "--metadata=reference-section-title:参考文献",
            "--resource-path=.:./media:./figures",
            "-o",
            str(INTERMEDIATE_DOCX),
        ],
        cwd=ROOT,
    )

    # 3) OOXML 后处理 -> 最终 DOCX
    _postprocess_docx(
        INTERMEDIATE_DOCX,
        OUTPUT_DOCX,
        display_math_flags,
        cn_kw,
        en_kw,
        caption_meta,
        caption_profiles,
        latex_col_ratios=latex_col_ratios,
    )
    exp_total, exp_bad = _verify_docx_experiment_images_are_png(OUTPUT_DOCX)
    if exp_bad:
        details = "\n".join(f"  - {d} => {t}" for d, t in exp_bad)
        raise RuntimeError(
            "DOCX build blocked: experiment figures must be embedded as PNG in the final document.\n"
            f"{details}"
        )
    print(f"PNG VERIFY: PASS ({exp_total} experiment figures)")

    # 清理临时文件（保留 FLAT_TEX 用于调试，删除中间 DOCX）
    if INTERMEDIATE_DOCX.exists():
        INTERMEDIATE_DOCX.unlink()
    if FLAT_TEX.exists():
        FLAT_TEX.unlink()

    print(f"OK: {OUTPUT_DOCX}")


# 向后兼容：保留 postprocess_docx 公共别名
postprocess_docx = _postprocess_docx

__all__ = [
    "postprocess_docx",
    "_postprocess_docx",
    "_resolve_paths",
    "_verify_docx_experiment_images_are_png",
    "main",
    "ROOT",
    "SCRIPT_DIR",
    "TEMPLATE_DOCX",
    "CAPTION_PROFILE_DOCX",
    "MAIN_TEX",
    "CSL",
    "BIB",
    "FLAT_TEX",
    "INTERMEDIATE_DOCX",
    "OUTPUT_DOCX",
]


if __name__ == "__main__":
    main()
