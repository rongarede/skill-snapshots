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

import datetime as _dt
import copy
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from modules.caption_profile import (
    CaptionFormatProfile,
    build_caption_paragraph,
    extract_caption_profiles,
)

try:
    from utils.text_utils import normalize_chinese_double_quotes
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.text_utils import normalize_chinese_double_quotes

try:
    from utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        p_text as _p_text,
        ensure_ppr as _ensure_ppr,
        p_style as _p_style,
        p_has_page_break as _p_has_page_break,
        p_has_sectPr as _p_has_sectPr,
        make_page_break_p as _make_page_break_p,
        get_body_sectPr as _get_body_sectPr,
        set_sect_pgnum as _set_sect_pgnum,
        set_sect_break_next_page as _set_sect_break_next_page,
        make_section_break_paragraph as _make_section_break_paragraph,
        make_unnumbered_heading1 as _make_unnumbered_heading1,
        remove_page_break_before as _remove_page_break_before,
        p_has_drawing as _p_has_drawing,
        set_para_center as _set_para_center,
        set_para_keep_next as _set_para_keep_next,
        set_para_keep_lines as _set_para_keep_lines,
        set_para_tabs_for_equation as _set_para_tabs_for_equation,
        make_run_tab as _make_run_tab,
        make_run_text as _make_run_text,
        set_para_single_line_spacing as _set_para_single_line_spacing,
        clear_para_first_indent as _clear_para_first_indent,
        clear_paragraph_runs_and_text as _clear_paragraph_runs_and_text,
        make_empty_para as _make_empty_para,
        set_p_style as _set_p_style,
        set_paragraph_text as _set_paragraph_text,
        block_has_drawing as _block_has_drawing,
        is_centered_paragraph as _is_centered_paragraph,
        run_cmd as _run,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import (
        collect_ns as _collect_ns,
        register_ns as _register_ns,
        qn as _qn,
        p_text as _p_text,
        ensure_ppr as _ensure_ppr,
        p_style as _p_style,
        p_has_page_break as _p_has_page_break,
        p_has_sectPr as _p_has_sectPr,
        make_page_break_p as _make_page_break_p,
        get_body_sectPr as _get_body_sectPr,
        set_sect_pgnum as _set_sect_pgnum,
        set_sect_break_next_page as _set_sect_break_next_page,
        make_section_break_paragraph as _make_section_break_paragraph,
        make_unnumbered_heading1 as _make_unnumbered_heading1,
        remove_page_break_before as _remove_page_break_before,
        p_has_drawing as _p_has_drawing,
        set_para_center as _set_para_center,
        set_para_keep_next as _set_para_keep_next,
        set_para_keep_lines as _set_para_keep_lines,
        set_para_tabs_for_equation as _set_para_tabs_for_equation,
        make_run_tab as _make_run_tab,
        make_run_text as _make_run_text,
        set_para_single_line_spacing as _set_para_single_line_spacing,
        clear_para_first_indent as _clear_para_first_indent,
        clear_paragraph_runs_and_text as _clear_paragraph_runs_and_text,
        make_empty_para as _make_empty_para,
        set_p_style as _set_p_style,
        set_paragraph_text as _set_paragraph_text,
        block_has_drawing as _block_has_drawing,
        is_centered_paragraph as _is_centered_paragraph,
        run_cmd as _run,
    )

try:
    from modules.font_handler import (
        contains_cjk as _contains_cjk,
        is_ascii_token_char as _is_ascii_token_char,
        split_mixed_script_runs as _split_mixed_script_runs,
        normalize_ascii_run_fonts as _normalize_ascii_run_fonts,
        normalize_bibliography_run_style as _normalize_bibliography_run_style,
    )
except ModuleNotFoundError:
    from scripts.modules.font_handler import (
        contains_cjk as _contains_cjk,
        is_ascii_token_char as _is_ascii_token_char,
        split_mixed_script_runs as _split_mixed_script_runs,
        normalize_ascii_run_fonts as _normalize_ascii_run_fonts,
        normalize_bibliography_run_style as _normalize_bibliography_run_style,
    )

try:
    from modules.algorithm_handler import (
        build_algorithm_table as _build_algorithm_table,
        format_algo_runs as _format_algo_runs,
        set_algo_para_props as _set_algo_para_props,
        format_algorithm_blocks as _format_algorithm_blocks,
    )
except ModuleNotFoundError:
    from scripts.modules.algorithm_handler import (
        build_algorithm_table as _build_algorithm_table,
        format_algo_runs as _format_algo_runs,
        set_algo_para_props as _set_algo_para_props,
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
    from modules.equation_handler import (
        number_display_equations as _number_display_equations,
        make_equation_number_run as _make_equation_number_run,
        sect_text_width_dxa as _sect_text_width_dxa,
    )
except ModuleNotFoundError:
    from scripts.modules.equation_handler import (
        number_display_equations as _number_display_equations,
        make_equation_number_run as _make_equation_number_run,
        sect_text_width_dxa as _sect_text_width_dxa,
    )

try:
    from modules.template_loader import (
        split_keywords as _split_keywords,
        prepend_template_cover_pages as _prepend_template_cover_pages,
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
        insert_abstract_keywords as _insert_abstract_keywords,
        ensure_update_fields_in_settings as _ensure_update_fields_in_settings,
        insert_toc_before_first_chapter as _insert_toc_before_first_chapter,
        add_page_breaks_before_h1 as _add_page_breaks_before_h1,
    )
except ModuleNotFoundError:
    from scripts.modules.template_loader import (
        split_keywords as _split_keywords,
        prepend_template_cover_pages as _prepend_template_cover_pages,
        insert_abstract_chapters_and_sections as _insert_abstract_chapters_and_sections,
        insert_abstract_keywords as _insert_abstract_keywords,
        ensure_update_fields_in_settings as _ensure_update_fields_in_settings,
        insert_toc_before_first_chapter as _insert_toc_before_first_chapter,
        add_page_breaks_before_h1 as _add_page_breaks_before_h1,
    )

try:
    from modules.figure_table_handler import (
        fix_figure_captions as _fix_figure_captions,
        inject_captions_from_meta as _inject_captions_from_meta,
        wrap_figure_with_captions as _wrap_figure_with_captions,
        build_figure_caption_wrapper as _build_figure_caption_wrapper,
        make_caption_para as _make_caption_para,
        make_caption_run as _make_caption_run,
        main_body_context as _main_body_context,
        iter_anchor_names_in_element as _iter_anchor_names_in_element,
        find_next_anchor_target_block as _find_next_anchor_target_block,
        collect_anchor_block_positions as _collect_anchor_block_positions,
        dedupe_body_level_anchor_bookmarks as _dedupe_body_level_anchor_bookmarks,
        clean_table_title as _clean_table_title,
        is_table_caption_para as _is_table_caption_para,
        find_caption_idx_near_table as _find_caption_idx_near_table,
        is_caption_paragraph_near_block as _is_caption_paragraph_near_block,
        remove_adjacent_caption_paragraphs as _remove_adjacent_caption_paragraphs,
        strip_latex_escapes_for_docx as _strip_latex_escapes_for_docx,
        normalize_caption_title as _normalize_caption_title,
        set_tbl_caption_value as _set_tbl_caption_value,
        apply_three_line_tables as _apply_three_line_tables,
        first_table_style_id as _first_table_style_id,
        ensure_tbl_pr as _ensure_tbl_pr,
        set_border_el as _set_border_el,
        is_data_table as _is_data_table,
        visual_text_len as _visual_text_len,
        table_col_count as _table_col_count,
        table_col_weights as _table_col_weights,
        normalize_widths_to_total as _normalize_widths_to_total,
        apply_latex_col_ratios as _apply_latex_col_ratios,
        set_table_full_width_and_columns as _set_table_full_width_and_columns,
        fit_figure_images_to_cells as _fit_figure_images_to_cells,
        inject_figure_table_style as _inject_figure_table_style,
        build_tbl_label_map as _build_tbl_label_map,
        is_figure_table_block as _is_figure_table_block,
        table_width_dxa as _table_width_dxa,
        set_row_cant_split as _set_row_cant_split,
    )
except ModuleNotFoundError:
    from scripts.modules.figure_table_handler import (
        fix_figure_captions as _fix_figure_captions,
        inject_captions_from_meta as _inject_captions_from_meta,
        wrap_figure_with_captions as _wrap_figure_with_captions,
        build_figure_caption_wrapper as _build_figure_caption_wrapper,
        make_caption_para as _make_caption_para,
        make_caption_run as _make_caption_run,
        main_body_context as _main_body_context,
        iter_anchor_names_in_element as _iter_anchor_names_in_element,
        find_next_anchor_target_block as _find_next_anchor_target_block,
        collect_anchor_block_positions as _collect_anchor_block_positions,
        dedupe_body_level_anchor_bookmarks as _dedupe_body_level_anchor_bookmarks,
        clean_table_title as _clean_table_title,
        is_table_caption_para as _is_table_caption_para,
        find_caption_idx_near_table as _find_caption_idx_near_table,
        is_caption_paragraph_near_block as _is_caption_paragraph_near_block,
        remove_adjacent_caption_paragraphs as _remove_adjacent_caption_paragraphs,
        strip_latex_escapes_for_docx as _strip_latex_escapes_for_docx,
        normalize_caption_title as _normalize_caption_title,
        set_tbl_caption_value as _set_tbl_caption_value,
        apply_three_line_tables as _apply_three_line_tables,
        first_table_style_id as _first_table_style_id,
        ensure_tbl_pr as _ensure_tbl_pr,
        set_border_el as _set_border_el,
        is_data_table as _is_data_table,
        visual_text_len as _visual_text_len,
        table_col_count as _table_col_count,
        table_col_weights as _table_col_weights,
        normalize_widths_to_total as _normalize_widths_to_total,
        apply_latex_col_ratios as _apply_latex_col_ratios,
        set_table_full_width_and_columns as _set_table_full_width_and_columns,
        fit_figure_images_to_cells as _fit_figure_images_to_cells,
        inject_figure_table_style as _inject_figure_table_style,
        build_tbl_label_map as _build_tbl_label_map,
        is_figure_table_block as _is_figure_table_block,
        table_width_dxa as _table_width_dxa,
        set_row_cant_split as _set_row_cant_split,
    )

try:
    from modules.reference_handler import (
        fix_ref_dot_to_hyphen as _fix_ref_dot_to_hyphen,
        collect_hyperlink_char_style_ids as _collect_hyperlink_char_style_ids,
        strip_hyperlink_run_style as _strip_hyperlink_run_style,
        unwrap_selected_hyperlinks_in_node as _unwrap_selected_hyperlinks_in_node,
        is_fig_table_ref_number_token as _is_fig_table_ref_number_token,
        collect_fig_table_ref_run_indexes as _collect_fig_table_ref_run_indexes,
        strip_fig_table_ref_link_style_in_node as _strip_fig_table_ref_link_style_in_node,
        strip_anchor_hyperlinks_in_main_body as _strip_anchor_hyperlinks_in_main_body,
        strip_doi_hyperlinks_in_bibliography as _strip_doi_hyperlinks_in_bibliography,
    )
except ModuleNotFoundError:
    from scripts.modules.reference_handler import (
        fix_ref_dot_to_hyphen as _fix_ref_dot_to_hyphen,
        collect_hyperlink_char_style_ids as _collect_hyperlink_char_style_ids,
        strip_hyperlink_run_style as _strip_hyperlink_run_style,
        unwrap_selected_hyperlinks_in_node as _unwrap_selected_hyperlinks_in_node,
        is_fig_table_ref_number_token as _is_fig_table_ref_number_token,
        collect_fig_table_ref_run_indexes as _collect_fig_table_ref_run_indexes,
        strip_fig_table_ref_link_style_in_node as _strip_fig_table_ref_link_style_in_node,
        strip_anchor_hyperlinks_in_main_body as _strip_anchor_hyperlinks_in_main_body,
        strip_doi_hyperlinks_in_bibliography as _strip_doi_hyperlinks_in_bibliography,
    )

try:
    from modules.latex_parser import (
        CaptionMeta as CaptionMeta,
        load_caption_profiles as _load_caption_profiles,
        default_caption_profiles as _default_caption_profiles,
        infer_caption_kind as _infer_caption_kind,
        parse_aux_labels as _parse_aux_labels,
        resolve_latex_refs as _resolve_latex_refs,
        convert_algorithms_to_plain_text as _convert_algorithms_to_plain_text,
        expand_custom_column_types as _expand_custom_column_types,
        preprocess_latex as _preprocess_latex,
        is_experiment_figure_path as _is_experiment_figure_path,
        find_unresolved_pdf_experiment_refs as _find_unresolved_pdf_experiment_refs,
        expand_if_file_exists as _expand_if_file_exists,
        prefer_png_for_docx_images as _prefer_png_for_docx_images,
        strip_latex_comments as _strip_latex_comments,
        skip_ws as _skip_ws,
        read_balanced as _read_balanced,
        extract_command_args as _extract_command_args,
        extract_caption_meta as _extract_caption_meta,
        parse_latex_table_col_specs as _parse_latex_table_col_specs,
        parse_width_to_ratio as _parse_width_to_ratio,
        flatten_subfigures as _flatten_subfigures,
        extract_display_math_number_flags as _extract_display_math_number_flags,
        extract_keywords as _extract_keywords,
        split_keywords as _split_keywords,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.modules.latex_parser import (
        CaptionMeta as CaptionMeta,
        load_caption_profiles as _load_caption_profiles,
        default_caption_profiles as _default_caption_profiles,
        infer_caption_kind as _infer_caption_kind,
        parse_aux_labels as _parse_aux_labels,
        resolve_latex_refs as _resolve_latex_refs,
        convert_algorithms_to_plain_text as _convert_algorithms_to_plain_text,
        expand_custom_column_types as _expand_custom_column_types,
        preprocess_latex as _preprocess_latex,
        is_experiment_figure_path as _is_experiment_figure_path,
        find_unresolved_pdf_experiment_refs as _find_unresolved_pdf_experiment_refs,
        expand_if_file_exists as _expand_if_file_exists,
        prefer_png_for_docx_images as _prefer_png_for_docx_images,
        strip_latex_comments as _strip_latex_comments,
        skip_ws as _skip_ws,
        read_balanced as _read_balanced,
        extract_command_args as _extract_command_args,
        extract_caption_meta as _extract_caption_meta,
        parse_latex_table_col_specs as _parse_latex_table_col_specs,
        parse_width_to_ratio as _parse_width_to_ratio,
        flatten_subfigures as _flatten_subfigures,
        extract_display_math_number_flags as _extract_display_math_number_flags,
        extract_keywords as _extract_keywords,
        split_keywords as _split_keywords,
    )

try:
    from modules.style_processor import (
        ensure_indent_for_body_paragraphs as _ensure_indent_for_body_paragraphs,
        ensure_hanging_indent_for_bibliography as _ensure_hanging_indent_for_bibliography,
        align_styles_to_reference as _align_styles_to_reference,
        collect_style_ids as _collect_style_ids,
        normalize_unknown_pstyles as _normalize_unknown_pstyles,
        fix_numbering_isLgl as _fix_numbering_isLgl,
        normalize_list_indents as _normalize_list_indents,
        inject_heading_numbering as _inject_heading_numbering,
        bind_heading_styles_to_numbering as _bind_heading_styles_to_numbering,
        number_paragraph_headings_in_main_body as _number_paragraph_headings_in_main_body,
        strip_numbering_from_backmatter_headings as _strip_numbering_from_backmatter_headings,
        remove_docgrid_lines_type as _remove_docgrid_lines_type,
        _HEADING_NUM_ID,
        _HEADING_ABSTRACT_NUM_ID,
    )
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.modules.style_processor import (
        ensure_indent_for_body_paragraphs as _ensure_indent_for_body_paragraphs,
        ensure_hanging_indent_for_bibliography as _ensure_hanging_indent_for_bibliography,
        align_styles_to_reference as _align_styles_to_reference,
        collect_style_ids as _collect_style_ids,
        normalize_unknown_pstyles as _normalize_unknown_pstyles,
        fix_numbering_isLgl as _fix_numbering_isLgl,
        normalize_list_indents as _normalize_list_indents,
        inject_heading_numbering as _inject_heading_numbering,
        bind_heading_styles_to_numbering as _bind_heading_styles_to_numbering,
        number_paragraph_headings_in_main_body as _number_paragraph_headings_in_main_body,
        strip_numbering_from_backmatter_headings as _strip_numbering_from_backmatter_headings,
        remove_docgrid_lines_type as _remove_docgrid_lines_type,
        _HEADING_NUM_ID,
        _HEADING_ABSTRACT_NUM_ID,
    )

# ==================== 全局路径变量（从 post_processor 导入，保持兼容） ====================
# 函数和全局变量已搬至 modules/post_processor.py（DOCX 后处理编排器）
# docx_builder 保留 import alias 供外部调用者（build_docx_banshi1.py 等）使用

try:
    from modules.post_processor import (
        ROOT,
        SCRIPT_DIR,
        TEMPLATE_DOCX,
        CAPTION_PROFILE_DOCX,
        MAIN_TEX,
        CSL,
        BIB,
        FLAT_TEX,
        INTERMEDIATE_DOCX,
        OUTPUT_DOCX,
        _verify_docx_experiment_images_are_png,
        _postprocess_docx,
        _resolve_paths,
        main,
    )
except ModuleNotFoundError:
    from scripts.modules.post_processor import (
        ROOT,
        SCRIPT_DIR,
        TEMPLATE_DOCX,
        CAPTION_PROFILE_DOCX,
        MAIN_TEX,
        CSL,
        BIB,
        FLAT_TEX,
        INTERMEDIATE_DOCX,
        OUTPUT_DOCX,
        _verify_docx_experiment_images_are_png,
        _postprocess_docx,
        _resolve_paths,
        main,
    )


if __name__ == "__main__":
    main()
