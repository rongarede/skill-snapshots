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
from dataclasses import dataclass
from pathlib import Path


ROOT = Path("/Users/bit/LaTeX/SWUN_Thesis")

# docx_builder.py now lives under scripts/modules/; keep SCRIPT_DIR at scripts/
SCRIPT_DIR = Path(__file__).resolve().parents[1]

TEMPLATE_DOCX = Path(
    os.environ.get(
        "SWUN_TEMPLATE_DOCX",
        "/Users/bit/LaTeX/SWUN_Thesis/.高春琴_normalized.docx",
    )
).expanduser()
MAIN_TEX = ROOT / "main.tex"
CSL = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
BIB = ROOT / "backmatter" / "references.bib"

FLAT_TEX = ROOT / ".main.flat.tex"
INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
OUTPUT_DOCX = ROOT / "main_版式1.docx"
@dataclass
class CaptionMeta:
    kind: str  # "figure" | "table"
    label: str
    cn_title: str
    en_title: str | None
    source: str  # "bilingualcaption" | "caption"


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


# ---------------------------------------------------------------------------
# Cross-reference resolution: parse main.aux and replace \ref/\eqref with
# resolved numbers so pandoc doesn't emit raw [label] text.
# ---------------------------------------------------------------------------

def _parse_aux_labels(aux_path: Path) -> dict[str, str]:
    """Parse main.aux and return {label: number} for alg:/eq:/tab:/fig:/sec: labels."""
    if not aux_path.exists():
        return {}
    text = aux_path.read_text(encoding="utf-8", errors="ignore")
    labels: dict[str, str] = {}
    for m in re.finditer(
        r"\\newlabel\{((?:alg|eq|tab|fig|sec):[^}]+)\}\{\{([^}]+)\}", text
    ):
        labels[m.group(1)] = m.group(2)
    return labels


def _resolve_latex_refs(s: str, labels: dict[str, str]) -> str:
    """Replace \\ref{alg/eq/tab/fig/sec:...} and \\eqref{eq:...} with resolved text.

    - \\eqref{eq:X} where aux gives "4.2" → (4-2)
    - \\ref{eq:X}   where aux gives "4.2" → (4-2)
    - \\ref{alg:X}  where aux gives "2"   → 2
    - \\ref{tab:X}  where aux gives "3-4" → 3-4
    - \\ref{fig:X}  where aux gives "3-1" → 3-1
    - \\ref{sec:X}  where aux gives "2.2.4" → 2.2.4
    Tilde before \\ref/\\eqref is consumed to avoid double spacing.
    """
    if not labels:
        return s

    def _eq_num(raw: str) -> str:
        """Convert '4.2' → '4-2' for DOCX hyphen convention."""
        return raw.replace(".", "-")

    def _repl_eqref(m: re.Match) -> str:
        label = m.group(1)
        num = labels.get(label)
        if num is None:
            return m.group(0)  # leave unresolved
        return f"({_eq_num(num)})"

    def _repl_ref(m: re.Match) -> str:
        label = m.group(1)
        num = labels.get(label)
        if num is None:
            return m.group(0)  # leave unresolved
        if label.startswith("eq:"):
            return f"({_eq_num(num)})"
        # tab:/fig: numbers already use hyphens (e.g. "3-4") from the cls
        # sec: numbers use dots (e.g. "2.2.4") — keep as-is
        # alg: returns plain number
        return num

    # \\eqref{eq:X} — with optional preceding tilde
    s = re.sub(r"~?\\eqref\{(eq:[^}]+)\}", _repl_eqref, s)
    # \\ref{alg/eq/tab/fig/sec:X} — with optional preceding tilde
    s = re.sub(
        r"~?\\ref\{((?:alg|eq|tab|fig|sec):[^}]+)\}", _repl_ref, s
    )
    return s


def _convert_algorithms_to_plain_text(s: str) -> str:
    """Convert \\begin{algorithm}...\\end{algorithm} to pandoc-friendly plain text.

    Pandoc doesn't understand the algorithmic environment; it flattens the
    content into a single unformatted paragraph.  This function rewrites each
    algorithm block into structured paragraphs pandoc can render properly in
    DOCX.
    """
    alg_re = re.compile(
        r"\\begin\{algorithm\}[^\n]*\n(.*?)\\end\{algorithm\}",
        re.DOTALL,
    )
    alg_counter = 0

    def _parse_algorithmic_body(body: str) -> list[tuple[int, int, str]]:
        """Return list of (line_number, indent_level, text)."""
        lines: list[tuple[int, int, str]] = []
        indent = 0
        num = 0

        # Strip \COMMENT{...} → ▷ ...
        def _strip_comment(t: str) -> str:
            return re.sub(r"\\COMMENT\{([^}]*)\}", r"  ▷ \1", t)

        for raw in body.strip().splitlines():
            raw = raw.strip()
            if not raw:
                continue

            # \REQUIRE / \ENSURE — not numbered
            m = re.match(r"\\REQUIRE\s+(.*)", raw)
            if m:
                lines.append((0, 0, "\\textbf{输入：}" + _strip_comment(m.group(1).strip())))
                continue
            m = re.match(r"\\ENSURE\s+(.*)", raw)
            if m:
                lines.append((0, 0, "\\textbf{输出：}" + _strip_comment(m.group(1).strip())))
                continue

            # \ENDIF / \ENDFOR / \ENDWHILE — decrease indent, numbered
            if re.match(r"\\ENDIF\b", raw):
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{end if}"))
                continue
            if re.match(r"\\ENDFOR\b", raw):
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{end for}"))
                continue
            if re.match(r"\\ENDWHILE\b", raw):
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{end while}"))
                continue

            # \ELSIF{cond} — decrease then increase
            m = re.match(r"\\ELSIF\{(.*)\}", raw)
            if m:
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{else if} " + m.group(1).strip() + " \\textbf{then}"))
                indent += 1
                continue

            # \ELSE — decrease then increase
            if re.match(r"\\ELSE\b", raw):
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{else}"))
                indent += 1
                continue

            # \IF{cond} — numbered, then increase indent
            m = re.match(r"\\IF\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{if} " + m.group(1).strip() + " \\textbf{then}"))
                indent += 1
                continue

            # \FOR{cond}
            m = re.match(r"\\FOR\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{for} " + m.group(1).strip() + " \\textbf{do}"))
                indent += 1
                continue

            # \WHILE{cond}
            m = re.match(r"\\WHILE\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{while} " + m.group(1).strip() + " \\textbf{do}"))
                indent += 1
                continue

            # \RETURN text
            m = re.match(r"\\RETURN\s+(.*)", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{return} " + _strip_comment(m.group(1).strip())))
                continue

            # \STATE text
            m = re.match(r"\\STATE\s+(.*)", raw)
            if m:
                num += 1
                lines.append((num, indent, _strip_comment(m.group(1).strip())))
                continue

        return lines

    def _repl_algorithm(m: re.Match) -> str:
        nonlocal alg_counter
        alg_counter += 1
        block = m.group(1)

        # Extract caption
        cap_m = re.search(r"\\caption\{([^}]*)\}", block)
        caption = cap_m.group(1) if cap_m else f"算法 {alg_counter}"

        # Extract label
        lab_m = re.search(r"\\label\{([^}]*)\}", block)
        label_str = f"\\label{{{lab_m.group(1)}}}" if lab_m else ""

        # Extract algorithmic body
        alg_m = re.search(
            r"\\begin\{algorithmic\}[^\n]*\n(.*?)\\end\{algorithmic\}",
            block, re.DOTALL
        )
        if not alg_m:
            return m.group(0)  # Can't parse, leave as-is

        parsed = _parse_algorithmic_body(alg_m.group(1))

        # Build output: title + rule + numbered lines + rule
        # Use Unicode markers ⌊N⌋ to encode indent level for OOXML post-processing.
        # Title is left-aligned (matching PDF algorithmic package rendering).
        out = []
        out.append("")
        # Algorithm title — the marker ⟦ALGTITLE⟧ is stripped in OOXML postprocess
        out.append(f"\\textbf{{算法 {alg_counter}}} {caption}{label_str}")
        out.append("")
        out.append("\\noindent\\rule{\\textwidth}{0.4pt}")
        out.append("")

        for num, indent, text in parsed:
            # Encode indent level as ⌊N⌋ prefix — survives pandoc as plain text
            indent_marker = f"\u230AN\u230B".replace("N", str(indent))
            if num == 0:
                # Input/Output lines — no number
                out.append(f"\\noindent {indent_marker}{text}")
                out.append("")
            else:
                out.append(f"\\noindent {indent_marker}\\textrm{{{num}:}} {text}")
                out.append("")

        out.append("")
        out.append("\\noindent\\rule{\\textwidth}{0.4pt}")
        out.append("")

        return "\n".join(out)

    return alg_re.sub(_repl_algorithm, s)


def _expand_custom_column_types(s: str) -> str:
    """Replace custom column type Y with X in tabularx column specifications.

    The SWUN thesis defines ``\\newcolumntype{Y}{>{\\centering\\arraybackslash}X}``
    which is a centered variant of the standard ``X`` column.  Pandoc's LaTeX reader
    does not evaluate ``\\newcolumntype`` so tables using ``Y`` are not parsed as
    tables at all—they appear as raw text with ``&`` separators.

    This function rewrites every ``\\begin{tabularx}{width}{colspec}`` occurrence
    by replacing ``Y`` characters in the colspec with ``X`` so pandoc can recognise
    them.  The ``\\newcolumntype{Y}`` definition line (if present) is also stripped
    to avoid pandoc warnings.
    """
    # Strip the \newcolumntype{Y}{...} definition itself
    s = re.sub(r"\\newcolumntype\{Y\}\{[^}]*\}", "", s)

    # Replace Y with X inside tabularx column spec arguments.
    # Pattern: \begin{tabularx}{<width>}{<colspec>}
    # We need to find the second {...} group after \begin{tabularx} and replace
    # Y with X only inside that group.
    def _repl_tabularx(m: re.Match) -> str:
        prefix = m.group(1)  # \begin{tabularx}{width}{
        colspec = m.group(2)  # column spec chars
        suffix = m.group(3)  # }
        return prefix + colspec.replace("Y", "X") + suffix

    s = re.sub(
        r"(\\begin\{tabularx\}\{[^}]*\}\{)([^}]*)(})",
        _repl_tabularx,
        s,
    )

    return s


def _preprocess_latex(s: str) -> str:
    # Pandoc LaTeX reader doesn't recognize \\< escape sequence.
    s = s.replace("\\<", "<")

    # Let citeproc generate the references section; avoid a literal \printbibliography in output.
    s = re.sub(
        r"\\printbibliography\s*(\[[^\]]*\])?",
        "",
        s,
        flags=re.MULTILINE,
    )

    # Pandoc may drop titlepage env; make it a normal block so cover content survives.
    s = s.replace("\\begin{titlepage}", "")
    s = s.replace("\\end{titlepage}", "")

    # ulem's \ul can get dropped; keep visible placeholders.
    # Common in declaration pages: \ul{　　　　　}
    s = re.sub(r"\\ul\\{[^}]*\\}", "__________", s)

    # --- Pandoc 3.8 bug workaround: equation ending with a bare letter before
    # \label causes the TeX math parser to reject \label.  Wrap the trailing
    # bare-letter token of \bmod / \mod in braces so the line no longer ends
    # with a single letter.  \bmod{m} is typographically identical to \bmod m
    # in LaTeX, so the transformation is safe.
    s = re.sub(
        r"(\\[bp]?mod)\s+([A-Za-z])\s*\n",
        r"\1{\2}\n",
        s,
    )

    # --- Resolve \ref{alg/eq/tab/fig/sec:...} and \eqref{eq:...} cross-references ---
    aux_path = ROOT / "main.aux"
    labels = _parse_aux_labels(aux_path)
    if labels:
        s = _resolve_latex_refs(s, labels)

    # --- Convert algorithm environments to pandoc-friendly plain text ---
    s = _convert_algorithms_to_plain_text(s)

    # --- Expand custom \newcolumntype{Y} to X in tabularx column specs ---
    # Y is defined as >{\centering\arraybackslash}X in main.tex.
    # Pandoc does not understand custom column types; replace Y with X so
    # tabularx tables are parsed correctly as Word tables.
    s = _expand_custom_column_types(s)

    # --- Expand \IfFileExists{path}{true}{false} so pandoc can see \includegraphics ---
    s = _expand_if_file_exists(s)

    # --- Flatten subfigures so pandoc counts only main figure captions ---
    s = _flatten_subfigures(s)
    s = _prefer_png_for_docx_images(s)
    unresolved = _find_unresolved_pdf_experiment_refs(s)
    if unresolved:
        lines = "\n".join(f"  - {p}" for p in unresolved)
        raise RuntimeError(
            "DOCX build blocked: experiment figures must use PNG, "
            "but some includegraphics still point to PDF and no PNG fallback was found:\n"
            f"{lines}"
        )

    return s


def _is_experiment_figure_path(path: str) -> bool:
    p = path.strip()
    return (
        p.startswith("experiments/ch3_v2/results/figures/")
        or p.startswith("figures/ch4/")
        or "/fig_3_" in p
        or "/fig_4_" in p
    )


def _find_unresolved_pdf_experiment_refs(s: str) -> list[str]:
    pat = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
    unresolved: list[str] = []
    for m in pat.finditer(s):
        p = m.group(1).strip()
        if _is_experiment_figure_path(p) and p.lower().endswith(".pdf"):
            unresolved.append(p)
    # keep stable order and de-dup
    seen = set()
    out = []
    for p in unresolved:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _expand_if_file_exists(s: str) -> str:
    """展开 \\IfFileExists{path}{true-branch}{false-branch}，使 pandoc 能识别其中的图片。

    Pandoc 不理解 LaTeX 的 \\IfFileExists 命令，会忽略整个结构导致图片丢失。
    此函数在 DOCX 预处理阶段将其展开：
    - 若对应的 PNG/PDF 文件在 ROOT 下存在，则替换为 true-branch 内容
    - 否则替换为 false-branch 内容（占位文本）
    """

    def _read_brace_group(text: str, start: int) -> tuple[str, int] | None:
        """读取从 start 开始的 {…} 括号组，返回 (内容, 结束位置后一位)。"""
        if start >= len(text) or text[start] != "{":
            return None
        depth = 0
        i = start
        while i < len(text):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start + 1 : i], i + 1
            i += 1
        return None  # 未找到匹配括号

    result = []
    i = 0
    pattern = r"\\IfFileExists\s*"
    compiled = re.compile(pattern)

    while i < len(s):
        m = compiled.search(s, i)
        if m is None:
            result.append(s[i:])
            break

        # 追加命令前的内容
        result.append(s[i : m.start()])

        pos = m.end()
        # 读取第一个参数：文件路径
        r1 = _read_brace_group(s, pos)
        if r1 is None:
            result.append(s[m.start()])
            i = m.start() + 1
            continue
        file_path_arg, pos = r1

        # 读取第二个参数：true-branch
        r2 = _read_brace_group(s, pos)
        if r2 is None:
            result.append(s[m.start()])
            i = m.start() + 1
            continue
        true_branch, pos = r2

        # 跳过可选空白
        while pos < len(s) and s[pos] in (" ", "\t", "\n", "%"):
            if s[pos] == "%":
                # 跳过行注释
                while pos < len(s) and s[pos] != "\n":
                    pos += 1
            else:
                pos += 1

        # 读取第三个参数：false-branch（可选）
        r3 = _read_brace_group(s, pos)
        if r3 is not None:
            false_branch, pos = r3
        else:
            false_branch = ""

        # 判断文件是否存在（优先检查 PNG，其次原路径）
        fp = file_path_arg.strip()
        png_fp = str(Path(fp).with_suffix(".png"))
        if (ROOT / png_fp).exists() or (ROOT / fp).exists():
            result.append(true_branch)
        else:
            result.append(false_branch)

        i = pos

    return "".join(result)


def _prefer_png_for_docx_images(s: str) -> str:
    """在 DOCX 构建阶段优先将 includegraphics 的 PDF 路径替换为 PNG。"""

    def _pick_png_path(raw_path: str) -> str | None:
        p = Path(raw_path.strip())
        if p.suffix.lower() != ".pdf":
            return None

        candidates = [p.with_suffix(".png")]
        # chapter4 当前正文引用 figures/ch4/*.pdf，实验图实际由 ch4_v2 生成。
        if p.as_posix().startswith("figures/ch4/"):
            candidates.append(Path("experiments/ch4_v2/results/figures") / p.with_suffix(".png").name)

        for cand in candidates:
            if (ROOT / cand).exists():
                return cand.as_posix()
        return None

    def _repl(m: re.Match) -> str:
        prefix, path_str, suffix = m.group(1), m.group(2), m.group(3)
        new_path = _pick_png_path(path_str)
        if not new_path:
            return m.group(0)
        return f"{prefix}{new_path}{suffix}"

    return re.sub(
        r"(\\includegraphics(?:\[[^\]]*\])?\{)([^}]+)(\})",
        _repl,
        s,
    )


def _strip_latex_comments(s: str) -> str:
    out: list[str] = []
    for line in s.splitlines():
        i = 0
        cut = None
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                cut = i
                break
            i += 1
        out.append(line[:cut] if cut is not None else line)
    return "\n".join(out)


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _read_balanced(s: str, i: int, open_ch: str, close_ch: str) -> tuple[str, int] | None:
    if i >= len(s) or s[i] != open_ch:
        return None
    depth = 0
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return None


def _extract_command_args(text: str, cmd: str, nargs: int) -> list[str] | None:
    pat = re.compile(rf"\\{re.escape(cmd)}(?![A-Za-z])")
    for m in pat.finditer(text):
        i = m.end()
        # Skip optional args like [..]
        while True:
            i = _skip_ws(text, i)
            if i < len(text) and text[i] == "[":
                got = _read_balanced(text, i, "[", "]")
                if got is None:
                    break
                _, i = got
                continue
            break

        args: list[str] = []
        ok = True
        for _ in range(nargs):
            i = _skip_ws(text, i)
            got = _read_balanced(text, i, "{", "}")
            if got is None:
                ok = False
                break
            val, i = got
            args.append(re.sub(r"\s+", " ", val).strip())
        if ok:
            return args
    return None


def _extract_caption_meta(flat_tex: str) -> dict[str, CaptionMeta]:
    """Extract figure/table caption metadata keyed by label from flattened LaTeX."""
    s = _strip_latex_comments(flat_tex)
    begin_re = re.compile(r"\\begin\{(figure|table)\*?\}")
    out: dict[str, CaptionMeta] = {}
    errs: list[str] = []
    pos = 0

    while True:
        m = begin_re.search(s, pos)
        if m is None:
            break
        env = m.group(1)
        start = m.start()
        line_no = s.count("\n", 0, start) + 1
        end_re = re.compile(rf"\\end\{{{env}\*?\}}")
        m_end = end_re.search(s, m.end())
        if m_end is None:
            errs.append(f"{env} block at line {line_no}: missing \\end{{{env}}}")
            pos = m.end()
            continue
        block = s[m.start() : m_end.end()]

        label_args = _extract_command_args(block, "label", 1)
        label = label_args[0].strip() if label_args else ""
        bi = _extract_command_args(block, "bilingualcaption", 2)
        cap = _extract_command_args(block, "caption", 1) if bi is None else None

        if not label:
            errs.append(f"{env} block at line {line_no}: missing \\label{{...}}")
        if bi is None and cap is None:
            errs.append(
                f"{env} block at line {line_no}: missing \\bilingualcaption{{...}}{{...}} or \\caption{{...}}"
            )
        if bi is not None and not (bi[1] or "").strip():
            errs.append(
                f"{env} block at line {line_no}: bilingualcaption English title is empty for label '{label or '<MISSING_LABEL>'}'"
            )

        if label and (bi is not None or cap is not None):
            kind = "figure" if env == "figure" else "table"
            if bi is not None:
                meta = CaptionMeta(
                    kind=kind,
                    label=label,
                    cn_title=bi[0],
                    en_title=bi[1].strip(),
                    source="bilingualcaption",
                )
            else:
                meta = CaptionMeta(
                    kind=kind,
                    label=label,
                    cn_title=(cap[0] if cap else "").strip(),
                    en_title=None,
                    source="caption",
                )
            if label in out:
                errs.append(f"duplicate label in figure/table environments: {label}")
            else:
                out[label] = meta

        pos = m_end.end()

    if errs:
        msg = "\n".join(f"  - {e}" for e in errs)
        raise RuntimeError("DOCX build blocked: failed to extract figure/table captions from LaTeX:\n" + msg)
    return out


def _parse_latex_table_col_specs(latex_src: str) -> dict[str, list[float]]:
    """从 flattened LaTeX 源码解析每个带 label 的表格的列宽比例。

    返回 ``{label: [ratio, ...]}``，仅包含有显式宽度（``p{...}`` 或 ``X``）的表格。
    纯 ``l/c/r`` 表格不出现在结果中。

    特殊值约定：
    - ``float > 0``：显式比例（来自 ``p{0.22\\linewidth}`` 等）
    - ``-1.0``：tabularX 的 ``X`` 列（等分剩余宽度）
    - ``0.0``：混合表中的自动列（``l/c/r``），使用文本推算
    """
    LINEWIDTH_CM = 15.0  # 假设 \linewidth ≈ 15cm

    src = _strip_latex_comments(latex_src)
    result: dict[str, list[float]] = {}

    # 匹配 \begin{table}...\end{table} 环境（含 table*）
    table_env_re = re.compile(
        r"\\begin\{table\*?\}.*?\\end\{table\*?\}", re.DOTALL
    )

    # 匹配 \begin{tabular}{colspec} 或 \begin{tabularx}{\textwidth}{colspec}
    # 注意：colspec 含嵌套花括号（如 p{0.22\linewidth}），不能用简单正则
    tabular_begin_re = re.compile(r"\\begin\{tabular\}")
    tabularx_begin_re = re.compile(r"\\begin\{tabularx\}")

    label_re = re.compile(r"\\label\{(tab:[^}]+)\}")

    def _parse_colspec(spec: str, is_tabularx: bool) -> list[float] | None:
        """解析列规格字符串，返回比例列表或 None（纯自动列）。"""
        cols: list[float] = []
        i = 0
        while i < len(spec):
            ch = spec[i]
            if ch in "lcr":
                cols.append(0.0)  # 自动列
                i += 1
            elif ch in "XY" and is_tabularx:
                cols.append(-1.0)  # X 列（Y 是 X 的居中变体）
                i += 1
            elif ch == "p" and i + 1 < len(spec) and spec[i + 1] == "{":
                # p{宽度定义}
                got = _read_balanced(spec, i + 1, "{", "}")
                if got is None:
                    i += 1
                    continue
                width_str, i = got
                ratio = _parse_width_to_ratio(width_str, LINEWIDTH_CM)
                cols.append(ratio if ratio is not None else 0.0)
            elif ch in "|@!>< {}":
                i += 1  # 跳过分隔符和修饰符
            else:
                i += 1
        if not cols:
            return None
        # 纯自动列（全部 l/c/r）→ 不覆盖
        if all(c == 0.0 for c in cols):
            return None
        return cols

    for m in table_env_re.finditer(src):
        block = m.group(0)
        label_m = label_re.search(block)
        if label_m is None:
            continue
        label = label_m.group(1)

        # 优先匹配 tabularx，再匹配 tabular；用 _read_balanced 处理嵌套花括号
        colspec_str: str | None = None
        is_tabularx = False
        tx_m = tabularx_begin_re.search(block)
        t_m = tabular_begin_re.search(block)
        if tx_m is not None:
            is_tabularx = True
            pos = tx_m.end()
            # 跳过第一个 {width} 参数
            got = _read_balanced(block, pos, "{", "}")
            if got is None:
                continue
            _, pos = got
            # 读取第二个 {colspec} 参数
            got = _read_balanced(block, pos, "{", "}")
            if got is None:
                continue
            colspec_str, _ = got
        elif t_m is not None:
            pos = t_m.end()
            got = _read_balanced(block, pos, "{", "}")
            if got is None:
                continue
            colspec_str, _ = got
        else:
            continue

        if colspec_str is None:
            continue
        cols = _parse_colspec(colspec_str, is_tabularx=is_tabularx)

        if cols is not None:
            result[label] = cols

    return result


def _parse_width_to_ratio(width_str: str, linewidth_cm: float) -> float | None:
    """将 LaTeX 宽度定义转换为 \\linewidth 比例。"""
    s = width_str.strip()
    # 0.22\linewidth 或 0.22\textwidth
    m = re.match(r"([\d.]+)\s*\\(?:linewidth|textwidth)", s)
    if m:
        return float(m.group(1))
    # 3cm
    m = re.match(r"([\d.]+)\s*cm", s)
    if m:
        return float(m.group(1)) / linewidth_cm
    # 30mm
    m = re.match(r"([\d.]+)\s*mm", s)
    if m:
        return float(m.group(1)) / 10.0 / linewidth_cm
    # 2in
    m = re.match(r"([\d.]+)\s*in", s)
    if m:
        return float(m.group(1)) * 2.54 / linewidth_cm
    return None


def _verify_docx_experiment_images_are_png(docx_path: Path) -> tuple[int, list[tuple[str, str]]]:
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
        # In package relationships, Id/Target are typically unqualified attributes.
        rid = rel.get("Id")
        target = rel.get("Target", "")
        if rid is None:
            # Fallback for parsers that preserve qualified attribute names.
            rid = rel.get(next((k for k in rel.attrib if k.endswith("}Id")), ""))
        if not target:
            target = rel.get(next((k for k in rel.attrib if k.endswith("}Target")), ""), "")
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


def _flatten_subfigures(s: str) -> str:
    """Replace subfigure \\ref with parent figure \\ref and strip subfigure captions/labels.

    Pandoc counts every \\caption inside subfigure as a separate figure, inflating
    the figure counter.  This function:
    1. Builds a mapping: subfigure_label -> parent_figure_label
    2. Replaces \\ref{subfig_label} with \\ref{parent_label} everywhere
    3. Strips \\caption and \\label inside subfigure environments
    4. Removes \\begin{subfigure}/\\end{subfigure} wrappers (keeps \\includegraphics)
    5. Deduplicates adjacent identical refs (e.g. "图~\\ref{X}和图~\\ref{X}" -> "图~\\ref{X}")
    """
    # Step 1: extract subfigure labels and their parent figure labels
    subfig_to_parent: dict[str, str] = {}

    # Find each figure environment and its subfigures
    fig_re = re.compile(
        r"\\begin\{figure\}.*?\\end\{figure\}", re.DOTALL
    )
    subfig_label_re = re.compile(
        r"\\begin\{subfigure\}.*?\\label\{([^}]+)\}.*?\\end\{subfigure\}", re.DOTALL
    )
    # Parent label: \label{...} that is NOT inside a subfigure block
    # We find it by looking for \label after the last \end{subfigure} but before \end{figure}
    parent_label_re = re.compile(r"\\label\{([^}]+)\}")

    for fig_m in fig_re.finditer(s):
        fig_block = fig_m.group(0)
        # Collect subfigure labels
        sub_labels = [m.group(1) for m in subfig_label_re.finditer(fig_block)]
        if not sub_labels:
            continue  # no subfigures in this figure

        # Find parent label: the \label that is outside any subfigure
        # Remove all subfigure blocks to find the parent label
        stripped = re.sub(
            r"\\begin\{subfigure\}.*?\\end\{subfigure\}", "", fig_block, flags=re.DOTALL
        )
        parent_m = parent_label_re.search(stripped)
        if not parent_m:
            continue
        parent_label = parent_m.group(1)

        for sl in sub_labels:
            subfig_to_parent[sl] = parent_label

    if not subfig_to_parent:
        return s

    # Step 2: replace \ref{subfig_label} with \ref{parent_label}
    for sub_lbl, par_lbl in subfig_to_parent.items():
        s = s.replace(f"\\ref{{{sub_lbl}}}", f"\\ref{{{par_lbl}}}")

    # Step 3: strip \caption and \label inside subfigure environments
    def _strip_subfig_internals(m: re.Match) -> str:
        block = m.group(0)
        # Remove \caption{...} lines
        block = re.sub(r"\\caption\{[^}]*\}\s*", "", block)
        # Remove \label{...} lines
        block = re.sub(r"\\label\{[^}]*\}\s*", "", block)
        return block

    s = re.sub(
        r"\\begin\{subfigure\}.*?\\end\{subfigure\}",
        _strip_subfig_internals,
        s,
        flags=re.DOTALL,
    )

    # Step 4: remove \begin{subfigure}[...]{...} and \end{subfigure} wrappers
    s = re.sub(r"\\begin\{subfigure\}(\[[^\]]*\])?\{[^}]*\}", "", s)
    s = re.sub(r"\\end\{subfigure\}", "", s)

    # Step 5: deduplicate adjacent identical figure refs
    # "图~\ref{X}和图~\ref{X}" or "图 \ref{X} 与图 \ref{X}" -> single ref
    s = re.sub(
        r"(图[~\s]*)\\ref\{([^}]+)\}\s*[与和及]\s*图[~\s]*\\ref\{\2\}",
        r"\1\\ref{\2}",
        s,
    )

    return s


def _extract_display_math_number_flags(latex: str) -> list[bool]:
    """
    Return a sequence aligned with pandoc's display-math paragraphs order.

    - Numbered: equation/align/gather/multline environments without '*'
    - Unnumbered: starred variants and \\[ ... \\] blocks
    """
    blocks: list[tuple[int, bool]] = []

    env_re = re.compile(
        r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}[\s\S]*?\\end\{\1\}"
    )
    for m in env_re.finditer(latex):
        env = m.group(1)
        blocks.append((m.start(), not env.endswith("*")))

    # Match display-math \[ ... \] but not line breaks \\[0.5em] in tabular, etc.
    br_re = re.compile(r"(?<!\\)\\\[[\s\S]*?\\\]")
    for m in br_re.finditer(latex):
        blocks.append((m.start(), False))

    blocks.sort(key=lambda x: x[0])
    return [b for _, b in blocks]


def _extract_keywords(latex: str) -> tuple[str | None, str | None]:
    def last_group(pattern: str) -> str | None:
        ms = list(re.finditer(pattern, latex, flags=re.DOTALL))
        if not ms:
            return None
        val = ms[-1].group(1)
        val = re.sub(r"\s+", " ", val).strip()
        return val or None

    cn = last_group(r"\\cnkeywords\{([^}]*)\}")
    en = last_group(r"\\enkeywords\{([^}]*)\}")
    return cn, en


def _split_keywords(raw: str, max_groups: int = 4, lang: str = "cn") -> str:
    """
    Split keywords into 3-4 groups (default max 4) without dropping information.

    If there are more than `max_groups` items, merge items from the last group onward.
    """

    def merge_tail_cn(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]}与{items[1]}"
        return "、".join(items)

    def merge_tail_en(items: list[str]) -> str:
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])} and {items[-1]}"

    def split_en_by_top_level_commas(text: str) -> list[str]:
        parts: list[str] = []
        buf: list[str] = []
        depth = 0
        for ch in text:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            if ch in {",", "，"} and depth == 0:
                part = "".join(buf).strip(" ;；,，")
                if part:
                    parts.append(part)
                buf = []
                continue
            buf.append(ch)
        tail = "".join(buf).strip(" ;；,，")
        if tail:
            parts.append(tail)
        return parts

    # Chinese: split on common delimiters.
    # English: prefer semicolon as the primary delimiter. Only fall back to commas
    # when no semicolon exists, and avoid splitting commas inside paired punctuation.
    if lang == "en":
        text = raw.strip()
        if ";" in text or "；" in text:
            parts = [p.strip(" ;；,，") for p in re.split(r"[;；]\s*", text) if p.strip(" ;；,，")]
        else:
            parts = split_en_by_top_level_commas(text)
    else:
        parts = [p.strip() for p in re.split(r"[;；,，]\s*", raw) if p.strip()]
    if len(parts) > max_groups:
        head = parts[: max_groups - 1]
        tail = parts[max_groups - 1 :]
        merged = merge_tail_en(tail) if lang == "en" else merge_tail_cn(tail)
        parts = [p for p in head + [merged] if p]
    return "；".join(parts)


def _collect_ns(xml_bytes: bytes) -> dict[str, str]:
    ns: dict[str, str] = {}
    for event, item in ET.iterparse(io.BytesIO(xml_bytes), events=("start-ns",)):
        prefix, uri = item
        ns[prefix or ""] = uri
    return ns


def _register_ns(ns: dict[str, str]) -> None:
    for prefix, uri in ns.items():
        if prefix:  # ElementTree doesn't support registering default namespace cleanly.
            try:
                ET.register_namespace(prefix, uri)
            except ValueError:
                # Skip invalid prefixes; Word namespaces should be fine.
                pass


def _qn(ns: dict[str, str], prefix: str, local: str) -> str:
    uri = ns[prefix]
    return f"{{{uri}}}{local}"


def _p_text(ns: dict[str, str], p: ET.Element) -> str:
    w_t = _qn(ns, "w", "t")
    parts = []
    for t in p.iter(w_t):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _ensure_ppr(ns: dict[str, str], p: ET.Element) -> ET.Element:
    w_pPr = _qn(ns, "w", "pPr")
    pPr = p.find(w_pPr)
    if pPr is None:
        pPr = ET.Element(w_pPr)
        p.insert(0, pPr)
    return pPr


def _p_style(ns: dict[str, str], p: ET.Element) -> str | None:
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    pPr = p.find(w_pPr)
    if pPr is None:
        return None
    pStyle = pPr.find(w_pStyle)
    if pStyle is None:
        return None
    return pStyle.get(w_val)


def _p_has_page_break(ns: dict[str, str], p: ET.Element) -> bool:
    w_br = _qn(ns, "w", "br")
    w_type = _qn(ns, "w", "type")
    for br in p.iter(w_br):
        if br.get(w_type) == "page":
            return True
    return False


def _p_has_sectPr(ns: dict[str, str], p: ET.Element) -> bool:
    w_sectPr = _qn(ns, "w", "sectPr")
    pPr = p.find(_qn(ns, "w", "pPr"))
    return pPr is not None and pPr.find(w_sectPr) is not None


def _make_page_break_p(ns: dict[str, str]) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_br = _qn(ns, "w", "br")
    w_type = _qn(ns, "w", "type")
    p = ET.Element(w_p)
    r = ET.SubElement(p, w_r)
    br = ET.SubElement(r, w_br)
    br.set(w_type, "page")
    return p


def _get_body_sectPr(ns: dict[str, str], body: ET.Element) -> ET.Element | None:
    # Usually a direct child of <w:body>.
    w_sectPr = _qn(ns, "w", "sectPr")
    for el in list(body):
        if el.tag == w_sectPr:
            return el
    # Fallback: sectPr in the last paragraph pPr.
    w_p = _qn(ns, "w", "p")
    for el in reversed(list(body)):
        if el.tag != w_p:
            continue
        pPr = el.find(_qn(ns, "w", "pPr"))
        if pPr is None:
            continue
        sectPr = pPr.find(w_sectPr)
        if sectPr is not None:
            return sectPr
    return None


def _set_sect_pgnum(
    ns: dict[str, str], sectPr: ET.Element, fmt: str, start: int | None
) -> None:
    w_pgNumType = _qn(ns, "w", "pgNumType")
    w_fmt = _qn(ns, "w", "fmt")
    w_start = _qn(ns, "w", "start")
    # Remove existing pgNumType(s)
    for el in list(sectPr.findall(w_pgNumType)):
        sectPr.remove(el)
    pg = ET.Element(w_pgNumType)
    pg.set(w_fmt, fmt)
    if start is not None:
        pg.set(w_start, str(start))
    # Put near top for readability (after header/footer refs if present).
    insert_at = 0
    for i, child in enumerate(list(sectPr)):
        if child.tag.endswith("headerReference") or child.tag.endswith("footerReference"):
            insert_at = i + 1
    sectPr.insert(insert_at, pg)


def _set_sect_break_next_page(ns: dict[str, str], sectPr: ET.Element) -> None:
    w_type = _qn(ns, "w", "type")
    w_val = _qn(ns, "w", "val")
    t = sectPr.find(w_type)
    if t is None:
        t = ET.Element(w_type)
        sectPr.insert(0, t)
    t.set(w_val, "nextPage")


def _make_section_break_paragraph(ns: dict[str, str], sectPr: ET.Element) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_sectPr = _qn(ns, "w", "sectPr")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    # sectPr must be a child of pPr for a section break paragraph.
    sp = copy.deepcopy(sectPr)
    sp.tag = w_sectPr
    pPr.append(sp)
    return p


def _make_unnumbered_heading1(ns: dict[str, str], title: str) -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_numPr = _qn(ns, "w", "numPr")
    w_numId = _qn(ns, "w", "numId")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")

    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, "1")
    jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")
    numPr = ET.SubElement(pPr, w_numPr)
    numId = ET.SubElement(numPr, w_numId)
    numId.set(w_val, "0")
    r = ET.SubElement(p, w_r)
    t = ET.SubElement(r, w_t)
    t.text = title
    return p


def _remove_page_break_before(ns: dict[str, str], p: ET.Element) -> None:
    w_pageBreakBefore = _qn(ns, "w", "pageBreakBefore")
    pPr = p.find(_qn(ns, "w", "pPr"))
    if pPr is None:
        return
    pbb = pPr.find(w_pageBreakBefore)
    if pbb is not None:
        pPr.remove(pbb)


def _prepend_template_cover_pages(
    ns: dict[str, str],
    body: ET.Element,
    template_docx: Path,
    *,
    marker_text: str = "研究生学位论文排版格式（版式1）",
    end_before_text: str = "学位论文版权使用授权书",
) -> None:
    """
    Prepend the first two pages from the official template docx *verbatim*.

    Heuristic:
    - Extract elements from template body start until the first paragraph whose text
      contains `end_before_text` (this begins page 3 in the provided template).
    - Skip if we already see `marker_text` very early in the document.
    """
    w_p = _qn(ns, "w", "p")

    # Idempotency: if marker appears in first ~40 paragraphs, assume cover already prepended.
    children = list(body)
    early = []
    for el in children[:80]:
        if el.tag != w_p:
            continue
        early.append(_p_text(ns, el))
    if marker_text in "".join(early):
        return

    if not template_docx.exists():
        return

    with zipfile.ZipFile(template_docx, "r") as zt:
        t_doc_xml = zt.read("word/document.xml")
    t_ns = _collect_ns(t_doc_xml)
    if "w" not in t_ns:
        return
    _register_ns(t_ns)

    t_root = ET.fromstring(t_doc_xml)
    t_body = t_root.find(_qn(t_ns, "w", "body"))
    if t_body is None:
        return

    t_children = list(t_body)
    cutoff = None
    # Prefer cutting at the start of template page-3, which begins with a standalone date line
    # ("日期：  年  月  日") in the provided SWUN template. This yields exactly the first two pages.
    # Be tolerant of fullwidth spaces used by Word.
    date_line_re = re.compile(r"^日期：[\s\u3000]*年[\s\u3000]*月[\s\u3000]*日$")
    for i, el in enumerate(t_children):
        if el.tag != _qn(t_ns, "w", "p"):
            continue
        txt = _p_text(t_ns, el).strip()
        if date_line_re.match(txt):
            cutoff = i
            break
        if end_before_text in txt:
            cutoff = i
            break
    if cutoff is None or cutoff <= 0:
        return

    # Insert in original order at the start of output body.
    insert_at = 0
    for el in t_children[:cutoff]:
        body.insert(insert_at, copy.deepcopy(el))
        insert_at += 1

    # Ensure a hard boundary after template cover pages without creating a blank page in LO:
    # Apply pageBreakBefore to the first paragraph of the thesis content (not the template pages).
    w_pageBreakBefore = _qn(ns, "w", "pageBreakBefore")
    children = list(body)
    for i in range(insert_at, len(children)):
        el = children[i]
        if el.tag != w_p:
            continue
        # Prefer the first paragraph with visible content.
        if not _p_text(ns, el).strip():
            continue
        pPr = _ensure_ppr(ns, el)
        if pPr.find(w_pageBreakBefore) is None:
            ET.SubElement(pPr, w_pageBreakBefore)
        break


def _insert_abstract_chapters_and_sections(
    ns: dict[str, str], body: ET.Element, sectPr_proto: ET.Element
) -> None:
    """
    Requirement:
    - Chinese/English abstracts are separate major chapters (Heading 1, unnumbered).
    - Abstract pages use Roman numerals in footer; the rest uses Arabic.

    Implementation:
    - Insert a section break before the Chinese abstract to start section 2.
    - Insert "摘要" and "Abstract" as unnumbered Heading 1.
    - Insert a section break after English abstract that ends section 2, setting pgNumType=lowerRoman start=1.
    - Ensure the final section (rest of the doc) uses decimal start=1.
    """
    w_p = _qn(ns, "w", "p")

    cn_anchors = (
        "在车联网（V2X）环境中",
        "车联网（V2X）环境下",
        "车联网(V2X)环境下",
        "车联网（V2X）",
    )
    en_anchors = (
        "In the Vehicular-to-Everything",
        "In Vehicle-to-Everything",
        "In the Vehicle-to-Everything",
        "Vehicle-to-Everything (V2X)",
    )
    front_h1 = {"摘要", "Abstract", "目录"}

    def _find_heading_idx(title: str, start: int = 0) -> int | None:
        children = list(body)
        for i in range(start, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_style(ns, el) == "1" and _p_text(ns, el).strip() == title:
                return i
        return None

    def _find_first_main_h1(start: int = 0) -> int | None:
        children = list(body)
        for i in range(start, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_style(ns, el) != "1":
                continue
            txt = _p_text(ns, el).strip()
            if txt and txt not in front_h1:
                return i
        return None

    def _first_nonempty_para(start: int, end: int | None = None) -> int | None:
        children = list(body)
        lim = len(children) if end is None else min(end, len(children))
        for i in range(start, lim):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_text(ns, el).strip():
                return i
        return None

    def _find_anchor_para(
        anchors: tuple[str, ...], start: int = 0, end: int | None = None
    ) -> int | None:
        children = list(body)
        lim = len(children) if end is None else min(end, len(children))
        anchors_l = tuple(a.lower() for a in anchors)
        for i in range(start, lim):
            el = children[i]
            if el.tag != w_p:
                continue
            txt = _p_text(ns, el)
            if not txt:
                continue
            txt_l = txt.lower()
            if any(a in txt_l for a in anchors_l):
                return i
        return None

    def _fallback_cn_para(start: int, end: int) -> int | None:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_style(ns, el) == "1":
                continue
            txt = _p_text(ns, el).strip()
            if len(txt) >= 8 and re.search(r"[\u4e00-\u9fff]", txt):
                return i
        return None

    def _fallback_en_para(start: int, end: int) -> int | None:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_style(ns, el) == "1":
                continue
            txt = _p_text(ns, el).strip()
            if not txt:
                continue
            letters = len(re.findall(r"[A-Za-z]", txt))
            if letters >= 20 and not re.search(r"[\u4e00-\u9fff]", txt):
                return i
        return None

    children = list(body)
    scan_end = _find_first_main_h1(0)
    if scan_end is None:
        scan_end = len(children)

    # Find Chinese abstract paragraph.
    cn_idx = _find_anchor_para(cn_anchors, 0, scan_end)
    if cn_idx is None:
        cn_h = _find_heading_idx("摘要", 0)
        if cn_h is not None:
            cn_idx = _first_nonempty_para(cn_h + 1, scan_end)
    if cn_idx is None:
        # Fallback: first non-empty Chinese paragraph after the last cover section break.
        scan_start = 0
        for i in range(0, scan_end):
            el = children[i]
            if el.tag == w_p and _p_has_sectPr(ns, el):
                scan_start = i + 1
        cn_idx = _fallback_cn_para(scan_start, scan_end)
    if cn_idx is None:
        return

    # If the source already has a CN abstract heading before the first CN paragraph
    # (possibly separated by empty paragraphs), place section break before that heading.
    if cn_idx > 0:
        j = cn_idx - 1
        while j >= 0:
            prev = children[j]
            if prev.tag != w_p:
                j -= 1
                continue
            prev_txt = _p_text(ns, prev).strip()
            if not prev_txt:
                j -= 1
                continue
            if _p_style(ns, prev) == "1" and prev_txt == "摘要":
                cn_idx = j
            break

    children = list(body)
    _remove_page_break_before(ns, children[cn_idx])

    # Find English abstract paragraph (search after CN).
    en_idx = _find_anchor_para(en_anchors, cn_idx, scan_end)
    if en_idx is None:
        en_h = _find_heading_idx("Abstract", cn_idx)
        if en_h is not None:
            en_idx = _first_nonempty_para(en_h + 1, scan_end)
    if en_idx is None:
        en_idx = _fallback_en_para(cn_idx + 1, scan_end)
    if en_idx is None:
        return
    children = list(body)
    _remove_page_break_before(ns, children[en_idx])

    # Section break before Chinese abstract (ends previous section).
    sect1 = copy.deepcopy(sectPr_proto)
    _set_sect_break_next_page(ns, sect1)
    # Keep default as decimal; no explicit start so it won't force restarts.
    _set_sect_pgnum(ns, sect1, fmt="decimal", start=None)
    sb_before = _make_section_break_paragraph(ns, sect1)

    # Insert section break. Keep or add CN abstract heading inside the Roman-numbered section.
    body.insert(cn_idx, sb_before)
    children = list(body)
    has_cn_h_after = False
    j = cn_idx + 1
    while j < len(children):
        el = children[j]
        if el.tag != w_p:
            j += 1
            continue
        txt = _p_text(ns, el).strip()
        if not txt:
            j += 1
            continue
        if _p_style(ns, el) == "1" and txt == "摘要":
            has_cn_h_after = True
        break
    if not has_cn_h_after:
        body.insert(cn_idx + 1, _make_unnumbered_heading1(ns, "摘要"))

    # Recompute indices after insertions.
    en_h2 = _find_heading_idx("Abstract", cn_idx + 1)
    if en_h2 is None:
        en_idx2 = _find_anchor_para(en_anchors, cn_idx + 1, scan_end)
        if en_idx2 is None:
            en_idx2 = _fallback_en_para(cn_idx + 1, scan_end)
        if en_idx2 is None:
            return
        body.insert(en_idx2, _make_unnumbered_heading1(ns, "Abstract"))
        en_h2 = en_idx2

    # Find the first English abstract paragraph after heading.
    main_h1_after_en = _find_first_main_h1(en_h2 + 1)
    en_p_idx = _first_nonempty_para(en_h2 + 1, main_h1_after_en)
    if en_p_idx is None:
        return

    # End Roman-numbered abstract section right before the first main chapter heading.
    # This keeps all EN abstract paragraphs (and keywords/TOC inserted later) inside front matter.
    break_idx = main_h1_after_en if main_h1_after_en is not None else (en_p_idx + 1)

    sect2 = copy.deepcopy(sectPr_proto)
    _set_sect_break_next_page(ns, sect2)
    _set_sect_pgnum(ns, sect2, fmt="lowerRoman", start=1)
    sb_after = _make_section_break_paragraph(ns, sect2)
    body.insert(break_idx, sb_after)


def _sect_text_width_dxa(ns: dict[str, str], root: ET.Element) -> int | None:
    """Compute writable text width in dxa from section properties if available."""
    w_sectPr = _qn(ns, "w", "sectPr")
    w_pgSz = _qn(ns, "w", "pgSz")
    w_pgMar = _qn(ns, "w", "pgMar")
    w_w = _qn(ns, "w", "w")
    w_left = _qn(ns, "w", "left")
    w_right = _qn(ns, "w", "right")

    sectPr = root.find(f".//{w_sectPr}")
    if sectPr is None:
        return None
    pgSz = sectPr.find(w_pgSz)
    pgMar = sectPr.find(w_pgMar)
    if pgSz is None or pgMar is None:
        return None
    try:
        page_w = int(pgSz.get(w_w) or "0")
        mar_l = int(pgMar.get(w_left) or "0")
        mar_r = int(pgMar.get(w_right) or "0")
    except ValueError:
        return None
    if page_w <= 0:
        return None
    return max(0, page_w - mar_l - mar_r)


def _p_has_drawing(ns: dict[str, str], p: ET.Element) -> bool:
    w_drawing = _qn(ns, "w", "drawing")
    w_pict = _qn(ns, "w", "pict")
    return p.find(f".//{w_drawing}") is not None or p.find(f".//{w_pict}") is not None


def _set_para_center(ns: dict[str, str], p: ET.Element) -> None:
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    pPr = _ensure_ppr(ns, p)
    jc = pPr.find(w_jc)
    if jc is None:
        jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")


def _set_para_keep_next(ns: dict[str, str], p: ET.Element) -> None:
    w_keepNext = _qn(ns, "w", "keepNext")
    pPr = _ensure_ppr(ns, p)
    if pPr.find(w_keepNext) is None:
        ET.SubElement(pPr, w_keepNext)


def _set_para_keep_lines(ns: dict[str, str], p: ET.Element) -> None:
    w_keepLines = _qn(ns, "w", "keepLines")
    pPr = _ensure_ppr(ns, p)
    if pPr.find(w_keepLines) is None:
        ET.SubElement(pPr, w_keepLines)


def _set_para_tabs_for_equation(ns: dict[str, str], p: ET.Element, text_w: int) -> None:
    """Set center + right tab stops for equation numbering."""
    w_tabs = _qn(ns, "w", "tabs")
    w_tab = _qn(ns, "w", "tab")
    w_val = _qn(ns, "w", "val")
    w_pos = _qn(ns, "w", "pos")

    mid = max(0, text_w // 2)
    right = max(0, text_w)

    pPr = _ensure_ppr(ns, p)
    tabs = pPr.find(w_tabs)
    if tabs is None:
        tabs = ET.SubElement(pPr, w_tabs)

    # Avoid duplicating tabs if script is rerun.
    existing = {(t.get(w_val), t.get(w_pos)) for t in tabs.findall(w_tab)}
    if ("center", str(mid)) not in existing:
        t = ET.SubElement(tabs, w_tab)
        t.set(w_val, "center")
        t.set(w_pos, str(mid))
    if ("right", str(right)) not in existing:
        t = ET.SubElement(tabs, w_tab)
        t.set(w_val, "right")
        t.set(w_pos, str(right))


def _make_run_tab(ns: dict[str, str]) -> ET.Element:
    w_r = _qn(ns, "w", "r")
    w_tab = _qn(ns, "w", "tab")
    r = ET.Element(w_r)
    ET.SubElement(r, w_tab)
    return r


def _make_run_text(ns: dict[str, str], text: str) -> ET.Element:
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    r = ET.Element(w_r)
    t = ET.SubElement(r, w_t)
    t.text = text
    return r


def _make_equation_number_run(ns: dict[str, str], text: str) -> ET.Element:
    """创建公式编号的 run，字体强制设为 Times New Roman。

    公式编号如 (3-13) 需使用 Times New Roman 字体以符合排版规范。
    """
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_t = _qn(ns, "w", "t")

    r = ET.Element(w_r)
    rPr = ET.SubElement(r, w_rPr)
    fonts = ET.SubElement(rPr, w_rFonts)
    fonts.set(_qn(ns, "w", "ascii"), "Times New Roman")
    fonts.set(_qn(ns, "w", "hAnsi"), "Times New Roman")
    t = ET.SubElement(r, w_t)
    t.text = text
    return r


def _make_caption_run(ns: dict[str, str], text: str) -> ET.Element:
    """Create a bold, 10.5pt, Times New Roman run for figure/table captions.

    Matches the reference thesis caption run properties:
      <w:rPr>
        <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>
        <w:b/><w:sz w:val="21"/><w:szCs w:val="21"/>
      </w:rPr>
    """
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_b = _qn(ns, "w", "b")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_t = _qn(ns, "w", "t")
    w_val = _qn(ns, "w", "val")

    r = ET.Element(w_r)
    rPr = ET.SubElement(r, w_rPr)
    fonts = ET.SubElement(rPr, w_rFonts)
    fonts.set(_qn(ns, "w", "ascii"), "Times New Roman")
    fonts.set(_qn(ns, "w", "hAnsi"), "Times New Roman")
    ET.SubElement(rPr, w_b)
    sz = ET.SubElement(rPr, w_sz)
    sz.set(w_val, "21")
    szCs = ET.SubElement(rPr, w_szCs)
    szCs.set(w_val, "21")
    t = ET.SubElement(r, w_t)
    t.text = text
    if text and (text[0] == " " or text[-1] == " "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _set_para_single_line_spacing(ns: dict[str, str], p: ET.Element) -> None:
    """Set paragraph line spacing to single (240 twips, lineRule=auto)."""
    w_spacing = _qn(ns, "w", "spacing")
    pPr = _ensure_ppr(ns, p)
    sp = pPr.find(w_spacing)
    if sp is None:
        sp = ET.SubElement(pPr, w_spacing)
    sp.set(_qn(ns, "w", "line"), "240")
    sp.set(_qn(ns, "w", "lineRule"), "auto")


def _clear_para_first_indent(ns: dict[str, str], p: ET.Element) -> None:
    """Remove first-line indent from paragraph (override Normal style indent)."""
    w_ind = _qn(ns, "w", "ind")
    pPr = _ensure_ppr(ns, p)
    ind = pPr.find(w_ind)
    if ind is None:
        ind = ET.SubElement(pPr, w_ind)
    ind.set(_qn(ns, "w", "firstLine"), "0")
    ind.set(_qn(ns, "w", "firstLineChars"), "0")
    # Also remove hanging indent if present
    for attr in ("hanging", "hangingChars"):
        key = _qn(ns, "w", attr)
        if key in ind.attrib:
            del ind.attrib[key]


def _clear_paragraph_runs_and_text(ns: dict[str, str], p: ET.Element) -> None:
    """Remove existing w:r children (keeps math, drawings, etc)."""
    w_r = _qn(ns, "w", "r")
    for r in list(p.findall(w_r)):
        p.remove(r)


def _fix_ref_dot_to_hyphen(ns: dict[str, str], body: ET.Element) -> None:
    """Replace dot-format figure/table refs (图3.1, 表4.2) with hyphen format (图3-1, 表4-2).

    Handles two cases:
    1. Reference within a single <w:t>: "如图3.1所示" or "图 3.7 与图 3.8"
    2. Split across runs: <w:t>图 </w:t> + <w:t>3.1</w:t>
    """
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_hyperlink = _qn(ns, "w", "hyperlink")
    w_anchor = _qn(ns, "w", "anchor")

    # Pattern for refs inside a single text node
    inline_re = re.compile(r"((?:图|表)\s*)(\d+)\.(\d+)")
    compact_re = re.compile(r"((?:图|表))[\s\u00a0]+(\d+-\d+)")
    # Pattern for a standalone number at the start of a text node
    num_re = re.compile(r"^(\s*)(\d+)[\.\-．](\d+)")

    for p in body.iter(w_p):
        # Pass 1: fix refs contained in a single <w:t>
        for t in p.iter(w_t):
            if not t.text:
                continue
            new_text = inline_re.sub(r"\1\2-\3", t.text)
            new_text = compact_re.sub(r"\1\2", new_text)
            t.text = new_text

        # Pass 2: fix split refs (图/表 at end of one run, number in a later run)
        # Pandoc often splits as: [..."图"] [" "] ["3.7"] [" "]
        runs = list(p.findall(f".//{w_r}"))
        for i in range(len(runs) - 1):
            cur_texts = list(runs[i].iter(w_t))
            if not cur_texts:
                continue
            tail = (cur_texts[-1].text or "").rstrip()
            if not tail.endswith(("图", "表")):
                continue
            # Look ahead, skipping whitespace-only runs
            for j in range(i + 1, min(i + 4, len(runs))):
                nxt_texts = list(runs[j].iter(w_t))
                if not nxt_texts:
                    continue
                nxt_val = nxt_texts[0].text or ""
                if nxt_val.strip() == "":
                    continue  # skip whitespace-only run
                if num_re.match(nxt_val):
                    nxt_texts[0].text = num_re.sub(r"\1\2-\3", nxt_val, count=1)
                    # Collapse whitespace runs between "图/表" and the numeric ref.
                    for k in range(i + 1, j):
                        for tk in runs[k].iter(w_t):
                            tk.text = ""
                break  # stop at first non-whitespace run

        # Pass 3: normalize standalone hyperlink ref text for fig/tab/tbl anchors (3.16 -> 3-16).
        for hl in p.iter(w_hyperlink):
            anchor = hl.get(w_anchor, "")
            if not anchor.startswith(("fig:", "tab:", "tbl:")):
                continue
            t_nodes = list(hl.iter(w_t))
            if not t_nodes:
                continue
            raw = "".join((t.text or "") for t in t_nodes)
            norm = re.sub(r"(?<!\d)(\d+)\.(\d+)(?!\d)", r"\1-\2", raw)
            if norm == raw:
                continue
            t_nodes[0].text = norm
            for t in t_nodes[1:]:
                t.text = ""


def _collect_hyperlink_char_style_ids(styles_xml: bytes) -> set[str]:
    """Return style IDs whose name contains 'hyperlink' (case-insensitive)."""
    if not styles_xml:
        return set()
    sns = _collect_ns(styles_xml)
    sroot = ET.fromstring(styles_xml)
    w_style = _qn(sns, "w", "style")
    w_name = _qn(sns, "w", "name")
    w_val = _qn(sns, "w", "val")
    w_type = _qn(sns, "w", "type")
    ids: set[str] = set()
    for s in sroot.iter(w_style):
        if s.get(w_type) != "character":
            continue
        name_el = s.find(w_name)
        if name_el is None:
            continue
        name_val = (name_el.get(w_val) or "").lower()
        if "hyperlink" in name_val:
            sid = s.get(_qn(sns, "w", "styleId"), "")
            if sid:
                ids.add(sid)
    return ids


def _strip_hyperlink_run_style(
    ns: dict[str, str],
    node: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> None:
    """Remove hyperlink-like run formatting so unwrapped refs render as normal text."""
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rStyle = _qn(ns, "w", "rStyle")
    w_color = _qn(ns, "w", "color")
    w_u = _qn(ns, "w", "u")
    w_val = _qn(ns, "w", "val")
    w_themeColor = _qn(ns, "w", "themeColor")
    hl_ids = hyperlink_style_ids or set()

    for r in node.iter(w_r):
        rPr = r.find(w_rPr)
        if rPr is None:
            continue

        for rs in list(rPr.findall(w_rStyle)):
            sval = (rs.get(w_val) or "")
            if "hyperlink" in sval.lower() or sval in hl_ids:
                rPr.remove(rs)

        for c in list(rPr.findall(w_color)):
            theme = (c.get(w_themeColor) or "").lower()
            cval = (c.get(w_val) or "").lower()
            if theme == "hyperlink" or cval in {"0563c1", "0000ff"}:
                rPr.remove(c)

        for u in list(rPr.findall(w_u)):
            uval = (u.get(w_val) or "").lower()
            if uval in {"", "single"}:
                rPr.remove(u)

        if len(rPr) == 0:
            r.remove(rPr)


def _unwrap_selected_hyperlinks_in_node(
    ns: dict[str, str],
    node: ET.Element,
    anchor_prefixes: tuple[str, ...] | None = None,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Replace selected anchor hyperlinks with child runs, preserving visible text order."""
    w_hyperlink = _qn(ns, "w", "hyperlink")
    w_anchor = _qn(ns, "w", "anchor")
    removed = 0

    for parent in node.iter():
        children = list(parent)
        if not children:
            continue

        changed = False
        new_children: list[ET.Element] = []
        for child in children:
            if child.tag != w_hyperlink:
                new_children.append(child)
                continue

            anchor = child.get(w_anchor, "")
            if not anchor:
                new_children.append(child)
                continue
            if anchor_prefixes and not anchor.startswith(anchor_prefixes):
                new_children.append(child)
                continue

            changed = True
            removed += 1
            for sub in list(child):
                _strip_hyperlink_run_style(ns, sub, hyperlink_style_ids)
                new_children.append(sub)

        if changed:
            parent[:] = new_children

    return removed


def _is_fig_table_ref_number_token(text: str) -> bool:
    return bool(re.match(r"^\d+-\d+[）)\]】,，.。:：;；]*$", text.strip()))


def _collect_fig_table_ref_run_indexes(ns: dict[str, str], node: ET.Element) -> set[int]:
    """Collect run indexes that belong to figure/table refs like 图2-1 / 表 3-2."""
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")

    runs = list(node.iter(w_r))
    run_texts = ["".join((t.text or "") for t in r.iter(w_t)) for r in runs]
    target: set[int] = set()

    # Case 1: same-run refs, e.g. "图2-1" / "表 3-2".
    same_run_re = re.compile(r"[图表]\s*\d+-\d+")
    for i, txt in enumerate(run_texts):
        if same_run_re.search(txt):
            target.add(i)

    # Case 2: split runs, e.g. "图" + whitespace + "2-1".
    for i, txt in enumerate(run_texts):
        marker = txt.strip()
        if marker not in {"图", "表"}:
            continue
        j = i + 1
        while j < len(run_texts):
            nxt = run_texts[j]
            if nxt.strip() == "":
                j += 1
                continue
            if _is_fig_table_ref_number_token(nxt):
                target.update({i, j})
                for k in range(i + 1, j):
                    if run_texts[k].strip() == "":
                        target.add(k)
            break

    return target


def _strip_fig_table_ref_link_style_in_node(
    ns: dict[str, str],
    node: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Strip hyperlink-like style only on fig/table reference runs."""
    w_r = _qn(ns, "w", "r")
    runs = list(node.iter(w_r))
    targets = _collect_fig_table_ref_run_indexes(ns, node)
    touched = 0
    for i, r in enumerate(runs):
        if i not in targets:
            continue
        _strip_hyperlink_run_style(ns, r, hyperlink_style_ids)
        touched += 1
    return touched


def _strip_anchor_hyperlinks_in_main_body(
    ns: dict[str, str],
    body: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Remove internal anchor hyperlinks from thesis main-body section (正文)."""
    w_p = _qn(ns, "w", "p")
    w_tbl = _qn(ns, "w", "tbl")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    in_main_body = False
    removed = 0

    for el in list(body):
        if el.tag == w_p:
            style = _p_style(ns, el)
            txt = _p_text(ns, el).strip()
            if style == "1":
                if txt in stop_h1:
                    in_main_body = False
                elif txt and txt not in excluded_h1:
                    in_main_body = True

        if not in_main_body:
            continue
        if el.tag not in {w_p, w_tbl}:
            continue
        # Remove internal cross-reference links (w:anchor) in main body.
        # Hyperlink-like run style is stripped only on unwrapped runs in
        # _unwrap_selected_hyperlinks_in_node to avoid over-cleaning normal text style.
        removed += _unwrap_selected_hyperlinks_in_node(ns, el, hyperlink_style_ids=hyperlink_style_ids)
        # Also strip orphan hyperlink rStyle on non-hyperlink runs (pandoc sometimes
        # applies the Hyperlink character style directly without wrapping in w:hyperlink).
        _strip_hyperlink_run_style(ns, el, hyperlink_style_ids)

    return removed


def _number_paragraph_headings_in_main_body(ns: dict[str, str], body: ET.Element) -> int:
    """Write explicit (n) prefixes on Heading5 titles, reset per Heading3, fallback reset per Heading2."""
    w_p = _qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    prefix_re = re.compile(r"^\s*[（(]\d+[)）]\s*")

    in_main_body = False
    seq = 0
    touched = 0

    for el in list(body):
        if el.tag != w_p:
            continue

        style = _p_style(ns, el)
        txt = _p_text(ns, el).strip()

        if style == "1":
            if txt in stop_h1:
                in_main_body = False
                seq = 0
            elif txt and txt not in excluded_h1:
                in_main_body = True
                seq = 0
            continue

        if not in_main_body:
            continue

        if style in {"Heading2", "2", "Heading3", "3"}:
            seq = 0
            continue

        if style not in {"Heading5", "5"}:
            continue
        if not txt:
            continue

        base = prefix_re.sub("", txt).strip()
        if not base:
            continue
        seq += 1
        _set_paragraph_text(ns, el, f"({seq}) {base}")
        # Demote from Heading5 to Normal body text style so the paragraph
        # renders with the same formatting as surrounding body paragraphs.
        pPr = el.find(_qn(ns, "w", "pPr"))
        if pPr is not None:
            ps = pPr.find(_qn(ns, "w", "pStyle"))
            if ps is not None:
                ps.set(_qn(ns, "w", "val"), "a")
        touched += 1

    return touched


def _fix_figure_captions(ns: dict[str, str], body: ET.Element) -> None:
    """Prefix figure captions with chapter-based numbering and center-align."""
    w_p = _qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}

    chapter_no = 0
    fig_no = 0

    children = list(body)
    to_remove: list[ET.Element] = []

    for el in children:
        if el.tag != w_p:
            continue
        style = _p_style(ns, el)
        txt = _p_text(ns, el).strip()

        if style == "1":
            title = txt
            if title and title not in excluded_h1:
                chapter_no += 1
                fig_no = 0
            continue

        if style == "CaptionedFigure" or _p_has_drawing(ns, el):
            _set_para_center(ns, el)
            # Keep caption together with the figure.
            _set_para_keep_next(ns, el)
            _set_para_keep_lines(ns, el)
            continue

        # Fallback for caption-like paragraphs that already carry figure numbering
        # but are not mapped to the expected ImageCaption style by pandoc/template mapping.
        m_prefixed = re.match(r"^图[\s\u00a0]*(\d+)[\-\.．](\d+)\s*(.*)$", txt)
        if m_prefixed:
            chap = m_prefixed.group(1)
            seq = m_prefixed.group(2)
            title = (m_prefixed.group(3) or "").strip()
            new_txt = f"图{chap}-{seq}" + (f" {title}" if title else "")
            _set_para_center(ns, el)
            _set_para_keep_lines(ns, el)
            for hl in list(el.findall(_qn(ns, "w", "hyperlink"))):
                el.remove(hl)
            _clear_paragraph_runs_and_text(ns, el)
            el.append(_make_run_text(ns, new_txt))
            continue

        if style != "ImageCaption":
            continue

        if not txt:
            # Pandoc sometimes generates empty caption paragraphs; remove them.
            to_remove.append(el)
            continue

        # If already numbered like "图2-1 ..." then keep.
        if re.match(r"^图\\s*\\d+[-\\.]\\d+\\s*", txt):
            _set_para_center(ns, el)
            continue

        if chapter_no <= 0:
            # Before first real chapter: skip numbering.
            _set_para_center(ns, el)
            continue

        fig_no += 1
        new_txt = f"图{chapter_no}-{fig_no} {txt}"

        _set_para_center(ns, el)
        _set_para_keep_lines(ns, el)
        _clear_paragraph_runs_and_text(ns, el)
        el.append(_make_run_text(ns, new_txt))

    for el in to_remove:
        try:
            body.remove(el)
        except ValueError:
            pass


def _first_table_style_id(styles_xml: bytes) -> str | None:
    ns = _collect_ns(styles_xml)
    if "w" not in ns:
        return None
    w_uri = ns["w"]
    q_style = f"{{{w_uri}}}style"
    q_type = f"{{{w_uri}}}type"
    q_styleId = f"{{{w_uri}}}styleId"
    root = ET.fromstring(styles_xml)
    for st in root.findall(q_style):
        if st.get(q_type) != "table":
            continue
        sid = st.get(q_styleId)
        if sid:
            return sid
    return None


def _ensure_tbl_pr(ns: dict[str, str], tbl: ET.Element) -> ET.Element:
    w_tblPr = _qn(ns, "w", "tblPr")
    pr = tbl.find(w_tblPr)
    if pr is None:
        pr = ET.Element(w_tblPr)
        tbl.insert(0, pr)
    return pr


def _set_border_el(ns: dict[str, str], parent: ET.Element, edge: str, val: str, sz: str) -> None:
    w_val = _qn(ns, "w", "val")
    w_sz = _qn(ns, "w", "sz")
    w_space = _qn(ns, "w", "space")
    w_color = _qn(ns, "w", "color")
    el = parent.find(_qn(ns, "w", edge))
    if el is None:
        el = ET.SubElement(parent, _qn(ns, "w", edge))
    el.attrib.clear()
    el.set(w_val, val)
    if val != "nil":
        el.set(w_sz, sz)
        el.set(w_space, "0")
        el.set(w_color, "auto")


def _is_data_table(ns: dict[str, str], tbl: ET.Element) -> bool:
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tblCaption = _qn(ns, "w", "tblCaption")
    w_val = _qn(ns, "w", "val")

    pr = tbl.find(w_tblPr)
    if pr is None:
        return False
    st = pr.find(w_tblStyle)
    st_val = st.get(w_val) if st is not None else None
    has_caption = pr.find(w_tblCaption) is not None
    # Pandoc uses FigureTable for figure layout tables; never treat them as data tables.
    if st_val == "FigureTable":
        return False
    return has_caption or st_val == "Table"


def _visual_text_len(s: str) -> int:
    n = 0
    for ch in s:
        if ch.isspace():
            continue
        n += 1 if ord(ch) < 128 else 2
    return n


def _table_col_count(ns: dict[str, str], tbl: ET.Element) -> int:
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_val = _qn(ns, "w", "val")

    grid = tbl.find(w_tblGrid)
    if grid is not None:
        cols = len(grid.findall(w_gridCol))
        if cols > 0:
            return cols

    max_cols = 0
    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is not None:
                gs = tcPr.find(w_gridSpan)
                if gs is not None:
                    try:
                        span = max(1, int(gs.get(w_val) or "1"))
                    except ValueError:
                        span = 1
            col += span
        max_cols = max(max_cols, col)
    return max_cols


def _table_col_weights(ns: dict[str, str], tbl: ET.Element, ncols: int) -> list[int]:
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_val = _qn(ns, "w", "val")
    w_t = _qn(ns, "w", "t")

    if ncols <= 0:
        return []

    weights = [1] * ncols
    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is not None:
                gs = tcPr.find(w_gridSpan)
                if gs is not None:
                    try:
                        span = max(1, int(gs.get(w_val) or "1"))
                    except ValueError:
                        span = 1
            txt = "".join((t.text or "") for t in tc.iter(w_t)).strip()
            score = max(1, _visual_text_len(txt))
            per_col = max(1, int(round(score / max(1, span))))
            for k in range(span):
                idx = col + k
                if idx >= ncols:
                    break
                weights[idx] = max(weights[idx], per_col)
            col += span
    return weights


def _normalize_widths_to_total(weights: list[int], total_w: int) -> list[int]:
    n = len(weights)
    if n == 0:
        return []
    if total_w <= 0:
        return [0] * n

    min_col = max(240, min(720, total_w // n))
    s = sum(max(1, w) for w in weights)
    widths = [max(min_col, int(round(total_w * max(1, w) / s))) for w in weights]

    diff = total_w - sum(widths)
    if diff > 0:
        order = sorted(range(n), key=lambda i: weights[i], reverse=True)
        if not order:
            order = list(range(n))
        k = 0
        while diff > 0:
            idx = order[k % len(order)]
            widths[idx] += 1
            diff -= 1
            k += 1
    elif diff < 0:
        order = sorted(range(n), key=lambda i: widths[i], reverse=True)
        k = 0
        guard = 0
        while diff < 0 and guard < n * max(total_w, 1):
            idx = order[k % len(order)]
            if widths[idx] > min_col:
                widths[idx] -= 1
                diff += 1
            k += 1
            guard += 1
        # Last resort: force exact total on the widest column.
        if diff != 0 and widths:
            widest = max(range(n), key=lambda i: widths[i])
            widths[widest] = max(min_col, widths[widest] + diff)

    return widths


def _apply_latex_col_ratios(
    ns: dict[str, str], tbl: ET.Element, ncols: int,
    col_ratios: list[float], total_w: int,
) -> list[int]:
    """根据 LaTeX 列宽比例计算 DOCX 列宽（dxa 单位）。

    col_ratios 约定：
    - >0：显式比例（p{0.22\\linewidth}）
    - -1.0：tabularX X 列（等分剩余宽度）
    - 0.0：混合表中的自动列（l/c/r），用文本推算
    """
    has_auto = any(r == 0.0 for r in col_ratios)
    has_x = any(r < 0 for r in col_ratios)

    if not has_auto and not has_x:
        # 纯显式比例 → 归一化后直接分配
        total_r = sum(col_ratios)
        if total_r <= 0:
            return _normalize_widths_to_total(
                _table_col_weights(ns, tbl, ncols), total_w
            )
        raw = [int(round(r / total_r * total_w)) for r in col_ratios]
        # 修正舍入误差
        diff = total_w - sum(raw)
        if diff != 0 and raw:
            idx = max(range(len(raw)), key=lambda i: col_ratios[i])
            raw[idx] += diff
        return raw

    # 混合模式：自动列用文本推算，X 列等分剩余
    weights = _table_col_weights(ns, tbl, ncols)

    # 显式列占用的宽度
    explicit_indices = [i for i, r in enumerate(col_ratios) if r > 0]
    auto_indices = [i for i, r in enumerate(col_ratios) if r == 0.0]
    x_indices = [i for i, r in enumerate(col_ratios) if r < 0]

    explicit_ratio_sum = sum(col_ratios[i] for i in explicit_indices)
    explicit_w = int(round(explicit_ratio_sum * total_w)) if explicit_indices else 0

    # 自动列：按文本权重在剩余空间中分配一个合理份额
    remaining_for_flex = total_w - explicit_w
    auto_weight_sum = sum(weights[i] for i in auto_indices) if auto_indices else 0
    x_count = len(x_indices)

    if auto_indices and x_count > 0:
        # 自动列和 X 列共享剩余空间
        # 自动列按文本权重占比，但不超过剩余空间的 40%
        total_flex_weight = auto_weight_sum + sum(weights[i] for i in x_indices)
        auto_share = auto_weight_sum / max(1, total_flex_weight)
        auto_share = min(auto_share, 0.4)
        auto_w = int(round(remaining_for_flex * auto_share))
        x_total_w = remaining_for_flex - auto_w
    elif auto_indices:
        auto_w = remaining_for_flex
        x_total_w = 0
    else:
        auto_w = 0
        x_total_w = remaining_for_flex

    widths = [0] * ncols
    for i in explicit_indices:
        widths[i] = int(round(col_ratios[i] * total_w))
    if auto_indices and auto_weight_sum > 0:
        for i in auto_indices:
            widths[i] = max(240, int(round(auto_w * weights[i] / auto_weight_sum)))
    elif auto_indices:
        per = auto_w // len(auto_indices)
        for i in auto_indices:
            widths[i] = max(240, per)
    if x_count > 0:
        per_x = x_total_w // x_count
        for i in x_indices:
            widths[i] = max(240, per_x)

    # 修正舍入误差
    diff = total_w - sum(widths)
    if diff != 0 and widths:
        idx = max(range(ncols), key=lambda i: widths[i])
        widths[idx] = max(240, widths[idx] + diff)

    return widths


def _set_table_full_width_and_columns(
    ns: dict[str, str], tbl: ET.Element, text_w: int,
    col_ratios: list[float] | None = None,
) -> None:
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblW = _qn(ns, "w", "tblW")
    w_tblLayout = _qn(ns, "w", "tblLayout")
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcW = _qn(ns, "w", "tcW")
    w_gridSpan = _qn(ns, "w", "gridSpan")
    w_type = _qn(ns, "w", "type")
    w_val = _qn(ns, "w", "val")
    w_w = _qn(ns, "w", "w")

    ncols = _table_col_count(ns, tbl)
    if ncols <= 0:
        return

    # 优先使用 LaTeX 源码中的显式列宽比例
    if col_ratios is not None and len(col_ratios) == ncols:
        widths = _apply_latex_col_ratios(ns, tbl, ncols, col_ratios, text_w)
    else:
        weights = _table_col_weights(ns, tbl, ncols)
        widths = _normalize_widths_to_total(weights, text_w)
    if not widths:
        return

    pr = _ensure_tbl_pr(ns, tbl)
    tblW = pr.find(w_tblW)
    if tblW is None:
        tblW = ET.SubElement(pr, w_tblW)
    tblW.set(w_type, "dxa")
    tblW.set(w_w, str(text_w))

    layout = pr.find(w_tblLayout)
    if layout is None:
        layout = ET.SubElement(pr, w_tblLayout)
    layout.set(w_type, "fixed")

    tblGrid = tbl.find(w_tblGrid)
    if tblGrid is None:
        tblGrid = ET.Element(w_tblGrid)
        insert_at = 0
        for i, child in enumerate(list(tbl)):
            if child.tag == w_tblPr:
                insert_at = i + 1
                break
        tbl.insert(insert_at, tblGrid)
    for gc in list(tblGrid.findall(w_gridCol)):
        tblGrid.remove(gc)
    for wv in widths:
        gc = ET.SubElement(tblGrid, w_gridCol)
        gc.set(w_w, str(wv))

    for tr in tbl.findall(w_tr):
        col = 0
        for tc in tr.findall(w_tc):
            span = 1
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                tcPr = ET.SubElement(tc, w_tcPr)
            gs = tcPr.find(w_gridSpan)
            if gs is not None:
                try:
                    span = max(1, int(gs.get(w_val) or "1"))
                except ValueError:
                    span = 1
            cell_w = 0
            for k in range(span):
                idx = col + k
                if idx < len(widths):
                    cell_w += widths[idx]
            if cell_w <= 0 and col < len(widths):
                cell_w = widths[col]

            tcW = tcPr.find(w_tcW)
            if tcW is None:
                tcW = ET.SubElement(tcPr, w_tcW)
            tcW.set(w_type, "dxa")
            tcW.set(w_w, str(max(1, cell_w)))
            col += span


def _set_p_style(ns: dict[str, str], p: ET.Element, style: str) -> None:
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    pPr = _ensure_ppr(ns, p)
    ps = pPr.find(w_pStyle)
    if ps is None:
        ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)


def _set_paragraph_text(ns: dict[str, str], p: ET.Element, txt: str) -> None:
    _clear_paragraph_runs_and_text(ns, p)
    p.append(_make_run_text(ns, txt))


def _clean_table_title(txt: str) -> str:
    s = (txt or "").strip()
    s = re.sub(r"^表[\s\xa0]*\d+(?:[\-\.．]\d+)?[\s\xa0:：、.]*", "", s)
    return s.strip()


def _is_table_caption_para(ns: dict[str, str], p: ET.Element) -> bool:
    style = _p_style(ns, p)
    txt = _p_text(ns, p).strip()
    if style == "TableCaption":
        return True
    return bool(re.match(r"^(表[\s\xa0]*\d+(?:[\-\.．]\d+)?|Table\s+\d+[\-\.－]\d+)", txt, re.IGNORECASE))


def _find_caption_idx_near_table(
    ns: dict[str, str], children: list[ET.Element], tbl_idx: int, direction: int
) -> int | None:
    w_p = _qn(ns, "w", "p")
    step = -1 if direction < 0 else 1
    rng = range(tbl_idx + step, -1, -1) if step < 0 else range(tbl_idx + 1, len(children))
    checked = 0
    for j in rng:
        el = children[j]
        if el.tag != w_p:
            continue
        txt = _p_text(ns, el).strip()
        if not txt:
            continue
        checked += 1
        if _is_table_caption_para(ns, el):
            return j
        # Stop at first non-caption paragraph near the table.
        if checked >= 1:
            break
    return None


def _block_has_drawing(ns: dict[str, str], el: ET.Element) -> bool:
    w_drawing = _qn(ns, "w", "drawing")
    w_pict = _qn(ns, "w", "pict")
    return el.find(f".//{w_drawing}") is not None or el.find(f".//{w_pict}") is not None


def _iter_anchor_names_in_element(ns: dict[str, str], el: ET.Element) -> list[str]:
    w_bookmarkStart = _qn(ns, "w", "bookmarkStart")
    w_name = _qn(ns, "w", "name")
    out: list[str] = []
    seen: set[str] = set()
    for bm in el.iter(w_bookmarkStart):
        name = (bm.get(w_name) or bm.get("name") or "").strip()
        if not name or name in seen:
            continue
        if not name.startswith(("fig:", "tab:", "tbl:")):
            continue
        seen.add(name)
        out.append(name)
    return out


def _main_body_context(
    ns: dict[str, str], body: ET.Element
) -> tuple[list[ET.Element], int, int, dict[int, int]]:
    """Return body children, main-body [start,end), and block-index -> chapter number."""
    w_p = _qn(ns, "w", "p")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    children = list(body)
    in_main_body = False
    chapter_no = 0
    chapter_by_index: dict[int, int] = {}
    start = 0
    end = len(children)
    started = False

    for i, el in enumerate(children):
        if el.tag == w_p and _p_style(ns, el) == "1":
            txt = _p_text(ns, el).strip()
            if txt in stop_h1:
                if in_main_body and end == len(children):
                    end = i
                in_main_body = False
            elif txt and txt not in excluded_h1:
                if not started:
                    start = i
                    started = True
                in_main_body = True
                chapter_no += 1

        if in_main_body:
            chapter_by_index[i] = chapter_no

    if not started:
        start = 0
        end = 0
    return children, start, end, chapter_by_index


def _find_next_anchor_target_block(
    ns: dict[str, str], children: list[ET.Element], start_idx: int, end_idx: int, kind: str
) -> int | None:
    w_p = _qn(ns, "w", "p")
    w_tbl = _qn(ns, "w", "tbl")
    fallback: int | None = None
    for j in range(start_idx, end_idx):
        el = children[j]
        if el.tag == w_tbl:
            has_draw = _block_has_drawing(ns, el)
            if kind == "figure":
                return j
            if kind == "table" and not has_draw:
                return j
            if fallback is None:
                fallback = j
            continue
        if el.tag == w_p and kind == "figure" and _block_has_drawing(ns, el):
            return j
    return fallback


def _collect_anchor_block_positions(
    ns: dict[str, str], body: ET.Element
) -> tuple[list[tuple[str, str, int]], dict[int, int]]:
    """Collect (kind, label, block_idx) for main-body fig/tab/tbl anchors."""
    w_bookmarkStart = _qn(ns, "w", "bookmarkStart")
    w_name = _qn(ns, "w", "name")
    w_p = _qn(ns, "w", "p")
    w_tbl = _qn(ns, "w", "tbl")

    children, start, end, chapter_by_index = _main_body_context(ns, body)
    if end <= start:
        return [], chapter_by_index

    best: dict[str, tuple[int, int]] = {}

    def kind_of(label: str) -> str:
        return "figure" if label.startswith("fig:") else "table"

    def score(kind: str, block: ET.Element, from_inline: bool) -> int:
        s = 2 if from_inline else 1
        has_draw = _block_has_drawing(ns, block)
        if kind == "figure":
            if has_draw:
                s += 4
            if block.tag == w_tbl:
                s += 1
        else:
            if block.tag == w_tbl:
                s += 4
            if has_draw:
                s -= 2
        return s

    for i in range(start, end):
        el = children[i]
        if el.tag not in {w_p, w_tbl}:
            continue
        for label in _iter_anchor_names_in_element(ns, el):
            k = kind_of(label)
            if k == "table" and el.tag != w_tbl:
                continue
            if k == "figure" and not _block_has_drawing(ns, el) and el.tag != w_tbl:
                continue
            cand = (score(k, el, True), i)
            prev = best.get(label)
            if prev is None or cand[0] > prev[0]:
                best[label] = cand

    for i in range(start, end):
        el = children[i]
        if el.tag != w_bookmarkStart:
            continue
        label = (el.get(w_name) or el.get("name") or "").strip()
        if not label.startswith(("fig:", "tab:", "tbl:")):
            continue
        k = kind_of(label)
        j = _find_next_anchor_target_block(ns, children, i + 1, end, k)
        if j is None:
            continue
        block = children[j]
        cand = (score(k, block, False), j)
        prev = best.get(label)
        if prev is None or cand[0] > prev[0]:
            best[label] = cand

    placements: list[tuple[str, str, int]] = []
    for label, (_score, idx) in best.items():
        placements.append((kind_of(label), label, idx))
    placements.sort(key=lambda x: (x[2], x[1]))
    return placements, chapter_by_index


def _is_centered_paragraph(ns: dict[str, str], p: ET.Element) -> bool:
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    pPr = p.find(_qn(ns, "w", "pPr"))
    if pPr is None:
        return False
    jc = pPr.find(w_jc)
    return jc is not None and (jc.get(w_val) or "") == "center"


def _is_caption_paragraph_near_block(ns: dict[str, str], p: ET.Element, kind: str) -> bool:
    txt = _p_text(ns, p).strip()
    if not txt:
        return False
    style = _p_style(ns, p) or ""
    if kind == "figure":
        if style in {"ImageCaption", "CaptionedFigure"}:
            return True
        if not _is_centered_paragraph(ns, p):
            return False
        return bool(re.match(r"^(图\s*\d+[\-\.．]\d+|Figure\s+\d+[\-\.．]\d+)\b", txt, flags=re.IGNORECASE))
    if style == "TableCaption":
        return True
    if not _is_centered_paragraph(ns, p):
        return False
    return bool(re.match(r"^(表\s*\d+[\-\.．]\d+|Table\s+\d+[\-\.．]\d+)\b", txt, flags=re.IGNORECASE))


def _remove_adjacent_caption_paragraphs(ns: dict[str, str], body: ET.Element, block_idx: int, kind: str) -> None:
    w_p = _qn(ns, "w", "p")
    w_bookmarkStart = _qn(ns, "w", "bookmarkStart")
    w_bookmarkEnd = _qn(ns, "w", "bookmarkEnd")

    children = list(body)
    remove: set[int] = set()

    for step in (-1, 1):
        j = block_idx + step
        while 0 <= j < len(children):
            el = children[j]
            if el.tag in {w_bookmarkStart, w_bookmarkEnd}:
                j += step
                continue
            if el.tag != w_p:
                break
            txt = _p_text(ns, el).strip()
            if not txt:
                if remove:
                    remove.add(j)
                    j += step
                    continue
                break
            if _is_caption_paragraph_near_block(ns, el, kind):
                remove.add(j)
                j += step
                continue
            break

    for idx in sorted(remove, reverse=True):
        try:
            body.remove(children[idx])
        except ValueError:
            pass


def _dedupe_body_level_anchor_bookmarks(ns: dict[str, str], body: ET.Element) -> int:
    """Remove duplicate top-level fig/tab/tbl bookmarks when the same anchor exists inside a block.

    Pandoc may emit two bookmarks for the same LaTeX label:
    1. a body-level ``w:bookmarkStart``/``w:bookmarkEnd`` pair around the figure/table block
    2. an inline bookmark nested inside the actual drawing/table block

    Word is stricter about duplicate bookmark names than LibreOffice, so keep the
    block-local bookmark and remove the top-level duplicate pair.
    """
    w_bookmarkStart = _qn(ns, "w", "bookmarkStart")
    w_bookmarkEnd = _qn(ns, "w", "bookmarkEnd")
    w_name = _qn(ns, "w", "name")
    w_id = _qn(ns, "w", "id")
    prefixes = ("fig:", "tab:", "tbl:")

    children = list(body)
    nested_names: set[str] = set()
    for el in children:
        if el.tag in {w_bookmarkStart, w_bookmarkEnd}:
            continue
        for bm in el.iter(w_bookmarkStart):
            name = (bm.get(w_name) or bm.get("name") or "").strip()
            if name.startswith(prefixes):
                nested_names.add(name)

    remove_ids: set[str] = set()
    remove_nodes: list[ET.Element] = []
    for el in children:
        if el.tag != w_bookmarkStart:
            continue
        name = (el.get(w_name) or el.get("name") or "").strip()
        if not name.startswith(prefixes):
            continue
        if name not in nested_names:
            continue
        bid = el.get(w_id) or el.get("id") or ""
        if not bid:
            continue
        remove_ids.add(bid)
        remove_nodes.append(el)

    if not remove_ids:
        return 0

    for el in children:
        if el.tag != w_bookmarkEnd:
            continue
        bid = el.get(w_id) or el.get("id") or ""
        if bid in remove_ids:
            remove_nodes.append(el)

    removed = 0
    for el in remove_nodes:
        try:
            body.remove(el)
            removed += 1
        except ValueError:
            pass
    return removed


def _strip_latex_escapes_for_docx(s: str) -> str:
    """移除 caption 文本中的 LaTeX 转义符号，使其适合 DOCX 纯文本显示。"""
    # $n=25$ → n=25（去掉数学模式定界符）
    s = re.sub(r"\$([^$]+)\$", r"\1", s)
    # \% → %，\& → &，\_ → _，\# → #
    s = re.sub(r"\\([%&_#])", r"\1", s)
    # \textbf{...} → ...，\textit{...} → ...
    s = re.sub(r"\\text(?:bf|it|rm|tt)\{([^}]*)\}", r"\1", s)
    return s


def _normalize_caption_title(title: str, kind: str, lang: str) -> str:
    s = re.sub(r"\s+", " ", (title or "").strip())
    if not s:
        return s
    # 移除 LaTeX 转义符号
    s = _strip_latex_escapes_for_docx(s)
    if kind == "figure" and lang == "cn":
        s = re.sub(r"^图\s*\d+[\-\.．]\d+\s*", "", s)
    elif kind == "figure" and lang == "en":
        s = re.sub(r"^Figure\s+\d+[\-\.．]\d+\s*", "", s, flags=re.IGNORECASE)
    elif kind == "table" and lang == "cn":
        s = re.sub(r"^表\s*\d+[\-\.．]\d+\s*", "", s)
    else:
        s = re.sub(r"^Table\s+\d+[\-\.．]\d+\s*", "", s, flags=re.IGNORECASE)
    return s.strip()


def _set_tbl_caption_value(ns: dict[str, str], tbl: ET.Element, cn_title: str) -> None:
    w_tblCaption = _qn(ns, "w", "tblCaption")
    w_val = _qn(ns, "w", "val")
    pr = _ensure_tbl_pr(ns, tbl)
    cap = pr.find(w_tblCaption)
    if cap is None:
        cap = ET.SubElement(pr, w_tblCaption)
    cap.set(w_val, cn_title)


def _make_caption_para(ns: dict[str, str], style: str, text: str, keep_next: bool) -> ET.Element:
    """Build a caption paragraph matching the SWUN reference thesis format.

    Properties applied (matching 高春琴.docx baseline):
      - Style: Normal ("a") — ImageCaption/TableCaption don't exist in template
      - Alignment: center
      - Line spacing: single (240 twips, auto)
      - First-line indent: 0 (override Normal's 480 twip indent)
      - Run formatting: bold, Times New Roman, 10.5pt (sz=21)
      - Keep-lines and optionally keep-next for page break control
    """
    # Always use Normal ("a") style — pandoc-generated ImageCaption/TableCaption
    # styles are not present in the official SWUN template and render as unstyled.
    p = _make_empty_para(ns, "a")
    _set_para_center(ns, p)
    _set_para_single_line_spacing(ns, p)
    _clear_para_first_indent(ns, p)
    _set_para_keep_lines(ns, p)
    if keep_next:
        _set_para_keep_next(ns, p)
    # Set paragraph-level rPr (paragraph mark / default run properties)
    # to match the reference thesis format: bold, Times New Roman, 10.5pt
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_b = _qn(ns, "w", "b")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_val = _qn(ns, "w", "val")
    pPr = _ensure_ppr(ns, p)
    prRPr = pPr.find(w_rPr)
    if prRPr is None:
        prRPr = ET.SubElement(pPr, w_rPr)
    # Clear existing and set fresh
    prRPr.clear()
    fonts = ET.SubElement(prRPr, w_rFonts)
    fonts.set(_qn(ns, "w", "ascii"), "Times New Roman")
    fonts.set(_qn(ns, "w", "hAnsi"), "Times New Roman")
    ET.SubElement(prRPr, w_b)
    sz = ET.SubElement(prRPr, w_sz)
    sz.set(w_val, "21")
    szCs = ET.SubElement(prRPr, w_szCs)
    szCs.set(w_val, "21")
    # Use caption-specific run with bold + Times New Roman + 10.5pt
    _clear_paragraph_runs_and_text(ns, p)
    p.append(_make_caption_run(ns, text))
    return p


def _inject_captions_from_meta(
    ns: dict[str, str], body: ET.Element, caption_meta: dict[str, CaptionMeta]
) -> None:
    placements, chapter_by_index = _collect_anchor_block_positions(ns, body)
    if not placements:
        return

    errors: list[str] = []
    numbered: list[tuple[str, str, int, int, int, CaptionMeta]] = []
    counters: dict[tuple[int, str], int] = {}

    for kind, label, block_idx in placements:
        chapter_no = chapter_by_index.get(block_idx)
        if not chapter_no:
            continue
        meta = caption_meta.get(label)
        if meta is None:
            errors.append(f"missing caption metadata for anchor '{label}'")
            continue
        if meta.kind != kind:
            errors.append(
                f"anchor kind mismatch for '{label}': anchor={kind}, latex_meta={meta.kind}"
            )
            continue
        key = (chapter_no, kind)
        seq = counters.get(key, 0) + 1
        counters[key] = seq
        numbered.append((kind, label, block_idx, chapter_no, seq, meta))

    if errors:
        msg = "\n".join(f"  - {e}" for e in errors)
        raise RuntimeError("DOCX build blocked: cannot map figure/table anchors to caption metadata:\n" + msg)

    for kind, label, block_idx, chapter_no, seq, meta in reversed(numbered):
        children = list(body)
        if block_idx < 0 or block_idx >= len(children):
            continue
        block = children[block_idx]
        cn_title = _normalize_caption_title(meta.cn_title, kind, "cn")
        en_title = _normalize_caption_title(meta.en_title or "", kind, "en")
        if meta.source == "bilingualcaption" and not en_title:
            raise RuntimeError(
                "DOCX build blocked: bilingual caption is missing English line after normalization "
                f"(label='{label}')"
            )

        if kind == "figure":
            cn_line = f"图{chapter_no}-{seq}" + (f" {cn_title}" if cn_title else "")
            en_line = (
                f"Figure {chapter_no}-{seq}" + (f" {en_title}" if en_title else "")
                if meta.source == "bilingualcaption"
                else ""
            )
            lines = [cn_line] + ([en_line] if en_line else [])
            style = "a"  # Normal — template has no ImageCaption style
            insert_after = True
        else:
            cn_line = f"表{chapter_no}-{seq}" + (f" {cn_title}" if cn_title else "")
            en_line = (
                f"Table {chapter_no}-{seq}" + (f" {en_title}" if en_title else "")
                if meta.source == "bilingualcaption"
                else ""
            )
            lines = [cn_line] + ([en_line] if en_line else [])
            style = "a"  # Normal — template has no TableCaption style
            insert_after = False
            if block.tag == _qn(ns, "w", "tbl"):
                _set_tbl_caption_value(ns, block, cn_title)

        _remove_adjacent_caption_paragraphs(ns, body, block_idx, kind)
        children = list(body)
        block_idx = children.index(block)

        if insert_after:
            pos = block_idx + 1
            for i, line in enumerate(lines):
                para = _make_caption_para(ns, style, line, keep_next=(i < len(lines) - 1))
                body.insert(pos, para)
                pos += 1
        else:
            for i, line in enumerate(reversed(lines)):
                keep_next = True  # caption above table should stay with following lines/table
                para = _make_caption_para(ns, style, line, keep_next=keep_next)
                body.insert(block_idx, para)


def _build_tbl_label_map(
    ns: dict[str, str], body: ET.Element
) -> dict[int, list[str]]:
    """扫描 body 子元素，构建 {tbl在body中的index: [tab:xxx labels]} 反向映射。

    Pandoc 把 \\label{tab:xxx} 转换为 body 级别的 bookmarkStart，
    位于对应 <w:tbl> 前方约 4 个元素。本函数向后搜索最近的数据表进行关联。
    """
    w_tbl = _qn(ns, "w", "tbl")
    w_bookmarkStart = _qn(ns, "w", "bookmarkStart")
    w_name = _qn(ns, "w", "name")

    children = list(body)
    result: dict[int, list[str]] = {}
    WINDOW = 8  # 向后搜索窗口

    for i, el in enumerate(children):
        # 收集当前元素中的 tab: 书签
        labels: list[str] = []
        for bm in el.iter(w_bookmarkStart):
            name = (bm.get(w_name) or bm.get("name") or "").strip()
            if name.startswith("tab:") or name.startswith("tbl:"):
                labels.append(name)
        if not labels:
            continue
        # 向后搜索最近的 <w:tbl>
        for j in range(i + 1, min(i + WINDOW + 1, len(children))):
            if children[j].tag == w_tbl:
                if _is_data_table(ns, children[j]):
                    result.setdefault(j, []).extend(labels)
                break

    return result


def _apply_three_line_tables(
    ns: dict[str, str], root: ET.Element, body: ET.Element, table_style_id: str | None,
    latex_col_ratios: dict[str, list[float]] | None = None,
) -> None:
    """
    Enforce three-line tables and normalize table layout:
    - table top + bottom border
    - header separator line (bottom border of last header row)
    - no vertical borders and no inner horizontal borders for body rows
    - table width fills full text width; column widths are redistributed by content
      (or by LaTeX source ratios when available)
    """
    w_tbl = _qn(ns, "w", "tbl")
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tr = _qn(ns, "w", "tr")
    w_trPr = _qn(ns, "w", "trPr")
    w_tblHeader = _qn(ns, "w", "tblHeader")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcBorders = _qn(ns, "w", "tcBorders")
    w_tblBorders = _qn(ns, "w", "tblBorders")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_val = _qn(ns, "w", "val")

    # Word border size unit is 1/8 pt. Template examples use w:sz="6" (0.75pt).
    rule_sz = "6"
    table_run_sz = "21"  # 五号 10.5pt in half-points
    text_w = _sect_text_width_dxa(ns, root) or 9356

    # 预构建 tbl body index → [labels] 映射，用于匹配 LaTeX 列宽比例
    tbl_label_map = _build_tbl_label_map(ns, body) if latex_col_ratios else {}

    i = 0
    children = list(body)
    while i < len(children):
        el = children[i]
        if el.tag != w_tbl:
            i += 1
            continue

        tbl = el
        if not _is_data_table(ns, tbl):
            i += 1
            continue

        pr = tbl.find(w_tblPr)
        if pr is None:
            i += 1
            continue

        st = pr.find(w_tblStyle)
        st_val = st.get(w_val) if st is not None else None
        pr = _ensure_tbl_pr(ns, tbl)

        # Make tblStyle valid (pandoc sometimes emits an undefined styleId like "Table").
        if table_style_id and (st_val in (None, "", "Table")):
            if st is None:
                st = ET.SubElement(pr, w_tblStyle)
            st.set(w_val, table_style_id)

        # 通过预构建映射查找表格 label，匹配 LaTeX 列宽比例
        matched_ratios: list[float] | None = None
        if latex_col_ratios and tbl_label_map:
            tbl_idx = children.index(tbl)
            for label in tbl_label_map.get(tbl_idx, []):
                if label in latex_col_ratios:
                    matched_ratios = latex_col_ratios[label]
                    break

        _set_table_full_width_and_columns(ns, tbl, text_w, col_ratios=matched_ratios)

        # Remove any existing cell borders to avoid unwanted gridlines.
        for tc in tbl.iter(w_tc):
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                continue
            tcBorders = tcPr.find(w_tcBorders)
            if tcBorders is not None:
                tcPr.remove(tcBorders)
            # Restrict font-size normalization to text runs inside data-table cells.
            for r in tc.iter(w_r):
                if r.find(w_t) is None:
                    continue
                rPr = r.find(w_rPr)
                if rPr is None:
                    rPr = ET.SubElement(r, w_rPr)
                rFonts = rPr.find(w_rFonts)
                if rFonts is None:
                    rFonts = ET.SubElement(rPr, w_rFonts)
                rFonts.set(w_ascii, "Times New Roman")
                rFonts.set(w_hAnsi, "Times New Roman")
                sz = rPr.find(w_sz)
                if sz is None:
                    sz = ET.SubElement(rPr, w_sz)
                sz.set(w_val, table_run_sz)
                szCs = rPr.find(w_szCs)
                if szCs is None:
                    szCs = ET.SubElement(rPr, w_szCs)
                szCs.set(w_val, table_run_sz)

        # Table-level borders: only top and bottom.
        borders = pr.find(w_tblBorders)
        if borders is not None:
            pr.remove(borders)
        borders = ET.SubElement(pr, w_tblBorders)
        _set_border_el(ns, borders, "top", "single", rule_sz)
        _set_border_el(ns, borders, "bottom", "single", rule_sz)
        _set_border_el(ns, borders, "left", "nil", rule_sz)
        _set_border_el(ns, borders, "right", "nil", rule_sz)
        _set_border_el(ns, borders, "insideH", "nil", rule_sz)
        _set_border_el(ns, borders, "insideV", "nil", rule_sz)

        # Header separator: bottom border of the last header row at the top of table.
        trs = tbl.findall(w_tr)
        if not trs:
            i += 1
            continue

        header_end = None
        for tr_idx, tr in enumerate(trs):
            trPr = tr.find(w_trPr)
            if trPr is not None and trPr.find(w_tblHeader) is not None:
                header_end = tr_idx
                continue
            break
        if header_end is None:
            header_end = 0

        header_tr = trs[header_end]
        for tc in header_tr.findall(w_tc):
            tcPr = tc.find(w_tcPr)
            if tcPr is None:
                tcPr = ET.SubElement(tc, w_tcPr)
            tcBorders = tcPr.find(w_tcBorders)
            if tcBorders is None:
                tcBorders = ET.SubElement(tcPr, w_tcBorders)
            _set_border_el(ns, tcBorders, "bottom", "single", rule_sz)
        children = list(body)
        i = children.index(tbl) + 1


def _make_empty_para(ns: dict[str, str], style: str = "a") -> ET.Element:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    p = ET.Element(w_p)
    pPr = ET.SubElement(p, w_pPr)
    ps = ET.SubElement(pPr, w_pStyle)
    ps.set(w_val, style)
    return p


def _insert_abstract_keywords(
    ns: dict[str, str],
    body: ET.Element,
    cn_keywords: str | None,
    en_keywords: str | None,
) -> None:
    """
    Insert keywords lines for Chinese/English abstracts:
    - leave one blank line before keywords
    - keep 3-4 groups (truncate to 4 by default)
    """
    w_p = _qn(ns, "w", "p")

    def find_heading_idx(title: str) -> int | None:
        for i, el in enumerate(list(body)):
            if el.tag != w_p:
                continue
            if _p_style(ns, el) == "1" and _p_text(ns, el).strip() == title:
                return i
        return None

    def already_has_kw(start: int, end: int, marker: str) -> bool:
        children = list(body)
        for i in range(start, min(end, len(children))):
            el = children[i]
            if el.tag != w_p:
                continue
            if marker in _p_text(ns, el):
                return True
        return False

    def insert_kw_block(after_idx: int, line: str) -> None:
        # Blank line then keywords paragraph.
        body.insert(after_idx + 1, _make_empty_para(ns, "a"))
        p = _make_empty_para(ns, "a")
        _clear_paragraph_runs_and_text(ns, p)
        p.append(_make_run_text(ns, line))
        body.insert(after_idx + 2, p)

    children = list(body)
    cn_h = find_heading_idx("摘要")
    en_h = find_heading_idx("Abstract")
    if cn_h is None or en_h is None or cn_h >= en_h:
        return

    # Chinese keywords: insert just before "Abstract" heading, after last non-empty para in CN block.
    if cn_keywords:
        if not already_has_kw(cn_h, en_h, "关键词"):
            cn_kw = _split_keywords(cn_keywords, max_groups=4, lang="cn")
            last = None
            children = list(body)
            for i in range(en_h - 1, cn_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if _p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                insert_kw_block(last, f"关键词：{cn_kw}")

    # English keywords: insert before the section break paragraph after English abstract if present,
    # else before the next Heading 1.
    if en_keywords:
        # recompute indices after possible insertions
        children = list(body)
        en_h = find_heading_idx("Abstract")
        if en_h is None:
            return
        # locate end bound
        end = len(children)
        for i in range(en_h + 1, len(children)):
            el = children[i]
            if el.tag != w_p:
                continue
            if _p_has_sectPr(ns, el):
                end = i
                break
            if _p_style(ns, el) == "1":
                end = i
                break

        if not already_has_kw(en_h, end, "Keywords"):
            en_kw = _split_keywords(en_keywords, max_groups=4, lang="en")
            last = None
            children = list(body)
            for i in range(end - 1, en_h, -1):
                el = children[i]
                if el.tag != w_p:
                    continue
                if _p_text(ns, el).strip():
                    last = i
                    break
            if last is not None:
                insert_kw_block(last, f"Keywords: {en_kw.replace('；', '; ')}")


def _number_display_equations(
    ns: dict[str, str],
    root: ET.Element,
    body: ET.Element,
    display_math_flags: list[bool] | None,
) -> None:
    """Add chapter-based equation numbers to paragraphs containing m:oMathPara."""
    w_p = _qn(ns, "w", "p")
    m_uri = None
    for k, v in ns.items():
        if k == "m":
            m_uri = v
            break
    if not m_uri:
        return
    m_oMathPara = f"{{{m_uri}}}oMathPara"
    m_oMath = f"{{{m_uri}}}oMath"
    m_t = f"{{{m_uri}}}t"

    text_w = _sect_text_width_dxa(ns, root)
    if text_w is None or text_w == 0:
        # Fallback to A4 template expected content width if section props are missing.
        # A4 11907, margins left 1417 right 1134 => 9356
        text_w = 9356

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    chapter_no = 0
    eq_no = 0

    children = list(body)
    def is_display_math_para(p: ET.Element) -> bool:
        if p.tag != w_p:
            return False
        if p.find(m_oMathPara) is not None:
            return True
        # Some pandoc runs emit OMML as <m:oMath> directly in the paragraph; only treat it
        # as display math if the paragraph has no visible text runs.
        if p.find(m_oMath) is not None and not _p_text(ns, p).strip():
            return True
        return False

    math_paras = [p for p in children if is_display_math_para(p)]

    # Use LaTeX-derived flags if available and aligned; otherwise number all display math.
    if (
        isinstance(display_math_flags, list)
        and all(isinstance(x, bool) for x in display_math_flags)
        and len(display_math_flags) == len(math_paras)
    ):
        flag_iter = iter(display_math_flags)
    else:
        flag_iter = None

    def should_number() -> bool:
        if flag_iter is None:
            return True
        try:
            return next(flag_iter)
        except StopIteration:
            return True

    def _ensure_display_math_para_centered(p: ET.Element) -> None:
        # Display math must be standalone and centered. We implement this via a leading tab
        # to a centered tab stop, keeping the equation number aligned with a right tab stop.
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # Insert a leading tab run (idempotent) so the math starts at the center tab stop.
        children2 = list(p)
        insert_idx = 0
        if children2 and children2[0].tag == _qn(ns, "w", "pPr"):
            insert_idx = 1

        has_leading_tab = False
        for el in children2[insert_idx:]:
            # first content element decides; if it isn't a run tab, we will add one
            if el.tag == _qn(ns, "w", "r"):
                if el.find(_qn(ns, "w", "tab")) is not None:
                    has_leading_tab = True
                break
            # If math comes first, we still want a leading tab.
            break

        if not has_leading_tab:
            p.insert(insert_idx, _make_run_tab(ns))

    for p in children:
        if p.tag != w_p:
            continue
        style = _p_style(ns, p)
        txt = _p_text(ns, p).strip()

        if style == "1":
            if txt and txt not in excluded_h1:
                chapter_no += 1
                eq_no = 0
            continue

        if not is_display_math_para(p):
            continue

        # Consume numbering flag for each display math paragraph to keep alignment stable.
        num_flag = should_number()
        math_txt = "".join((x.text or "") for x in p.iter(m_t))

        # Always center display equations and keep them standalone.
        _ensure_display_math_para_centered(p)

        if chapter_no <= 0:
            continue

        # Keep quantifier-only display lines unnumbered.
        # Compatibility note: current verifier requires any line containing "∀" to stay unnumbered.
        compact_math = re.sub(r"\s+", "", math_txt)
        if "∀" in compact_math:
            continue
        if "∃" in compact_math and not any(
            op in compact_math for op in ("=", "≈", "≜", "≤", "≥", "<", ">")
        ):
            continue

        if not num_flag:
            continue

        # Avoid double-numbering if already contains something like (2-1).
        if re.search(r"\(\d+[-\.]\d+\)\s*$", txt):
            continue

        eq_no += 1
        num_txt = f"({chapter_no}-{eq_no})"

        # Display math paragraphs should not have first-line indents.
        pPr = _ensure_ppr(ns, p)
        ind = pPr.find(_qn(ns, "w", "ind"))
        if ind is not None:
            for attr in ("firstLineChars", "firstLine", "hangingChars", "hanging"):
                ind.attrib.pop(_qn(ns, "w", attr), None)
            if not ind.attrib:
                pPr.remove(ind)

        _set_para_tabs_for_equation(ns, p, text_w)

        # Append tab + number（公式编号使用 Times New Roman 字体）.
        p.append(_make_run_tab(ns))
        p.append(_make_equation_number_run(ns, num_txt))


def _insert_toc_before_first_chapter(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_pPr = _qn(ns, "w", "pPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_numPr = _qn(ns, "w", "numPr")
    w_numId = _qn(ns, "w", "numId")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_fldChar = _qn(ns, "w", "fldChar")
    w_fldCharType = _qn(ns, "w", "fldCharType")
    w_instrText = _qn(ns, "w", "instrText")

    children = list(body)
    first_h1_idx = None
    unnumbered = {"目录", "摘要", "Abstract"}
    # Insert TOC before "摘要" heading so TOC is inside the Roman-numbered
    # front-matter section (目录在前, 摘要在后).  Fall back to first numbered
    # chapter if 摘要 heading is not found.
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if _p_style(ns, el) == "1":
            txt = _p_text(ns, el).strip()
            if txt == "摘要":
                first_h1_idx = i
                break
            if txt in unnumbered:
                continue
            first_h1_idx = i
            break
    if first_h1_idx is None:
        return

    # TOC title paragraph: use Heading 1 style but suppress numbering per-paragraph (numId=0).
    toc_title_p = ET.Element(w_p)
    pPr = ET.SubElement(toc_title_p, w_pPr)
    pStyle = ET.SubElement(pPr, w_pStyle)
    pStyle.set(w_val, "1")
    jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "center")
    numPr = ET.SubElement(pPr, w_numPr)
    numId = ET.SubElement(numPr, w_numId)
    numId.set(w_val, "0")
    r = ET.SubElement(toc_title_p, w_r)
    t = ET.SubElement(r, w_t)
    t.text = "目录"

    # TOC field paragraph (Word field code). Users can right-click -> Update Field.
    toc_field_p = ET.Element(w_p)
    r1 = ET.SubElement(toc_field_p, w_r)
    fld_begin = ET.SubElement(r1, w_fldChar)
    fld_begin.set(w_fldCharType, "begin")

    r2 = ET.SubElement(toc_field_p, w_r)
    instr = ET.SubElement(r2, w_instrText)
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '

    r3 = ET.SubElement(toc_field_p, w_r)
    fld_sep = ET.SubElement(r3, w_fldChar)
    fld_sep.set(w_fldCharType, "separate")

    r4 = ET.SubElement(toc_field_p, w_r)
    t4 = ET.SubElement(r4, w_t)
    t4.text = "（右键此处，选择“更新域”以生成目录）"

    r5 = ET.SubElement(toc_field_p, w_r)
    fld_end = ET.SubElement(r5, w_fldChar)
    fld_end.set(w_fldCharType, "end")

    # Page break after TOC so first chapter starts on a new page.
    pb = _make_page_break_p(ns)

    body.insert(first_h1_idx, toc_title_p)
    body.insert(first_h1_idx + 1, toc_field_p)
    body.insert(first_h1_idx + 2, pb)


def _add_page_breaks_before_h1(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    children = list(body)
    i = 0
    while i < len(children):
        el = children[i]
        if el.tag == w_p and _p_style(ns, el) == "1":
            title = _p_text(ns, el).strip()
            if title == "目录":
                i += 1
                continue
            if i == 0:
                i += 1
                continue
            prev = children[i - 1]
            if prev.tag == w_p and (_p_has_page_break(ns, prev) or _p_has_sectPr(ns, prev)):
                i += 1
                continue
            # Insert a separate page-break paragraph to avoid blank pages at document start.
            pb = _make_page_break_p(ns)
            body.insert(i, pb)
            children.insert(i, pb)
            i += 2
            continue
        i += 1


def _ensure_indent_for_body_paragraphs(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_ind = _qn(ns, "w", "ind")
    w_firstLineChars = _qn(ns, "w", "firstLineChars")
    w_left = _qn(ns, "w", "left")
    w_hanging = _qn(ns, "w", "hanging")
    w_hangingChars = _qn(ns, "w", "hangingChars")

    # Pandoc + template mapping may emit Normal as styleId "a".
    # Heading5 (\paragraph) is demoted to Normal ("a") before this runs.
    body_styles = {"BodyText", "FirstParagraph", "Compact", "a"}
    # Heading2/3 (二级/三级子标题) must be flush-left; override numbering indent.
    flush_left_styles = {"Heading2", "2", "Heading3", "3"}

    w_firstLine = _qn(ns, "w", "firstLine")
    m_uri = ns.get("m")
    m_oMathPara = f"{{{m_uri}}}oMathPara" if m_uri else None
    m_oMath = f"{{{m_uri}}}oMath" if m_uri else None

    def is_display_math_para(p: ET.Element) -> bool:
        if p.tag != w_p or not m_uri:
            return False
        if p.find(m_oMathPara) is not None:
            return True
        # Pandoc may emit display math as a bare oMath paragraph with no prose text.
        return p.find(m_oMath) is not None and not _p_text(ns, p).strip()

    prev_sig: ET.Element | None = None

    for child in list(body):
        if child.tag != w_p:
            continue
        style = _p_style(ns, child)
        if style in body_styles:
            pPr = _ensure_ppr(ns, child)
            ind = pPr.find(w_ind)
            # Skip paragraphs already formatted by _format_algorithm_blocks
            # (they have explicit firstLine="0")
            if ind is not None and ind.get(w_firstLine) == "0":
                prev_sig = child
                continue
            if prev_sig is not None and is_display_math_para(prev_sig):
                _clear_para_first_indent(ns, child)
                prev_sig = child
                continue
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            # Keep other indentation attributes intact; only enforce first-line indent.
            ind.set(w_firstLineChars, "200")
        elif style in flush_left_styles:
            pPr = _ensure_ppr(ns, child)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            # Override numbering indent: flush left, no hanging.
            ind.set(w_left, "0")
            for attr in (w_hanging, w_hangingChars):
                if attr in ind.attrib:
                    del ind.attrib[attr]

        prev_sig = child


def _ensure_hanging_indent_for_bibliography(ns: dict[str, str], body: ET.Element) -> None:
    w_p = _qn(ns, "w", "p")
    w_ind = _qn(ns, "w", "ind")
    w_hangingChars = _qn(ns, "w", "hangingChars")

    children = list(body)
    ref_idx = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if _p_text(ns, el).strip() == "参考文献":
            ref_idx = i
            break
    if ref_idx is None:
        return

    # Typical GB/T numeric entries start with "[1]" (ASCII) or "［1］" (fullwidth).
    bib_entry_re = re.compile(r"^(\[[0-9]{1,4}\]|［[0-9]{1,4}］)")
    i = ref_idx + 1
    while i < len(children):
        el = children[i]
        if el.tag != w_p:
            i += 1
            continue
        style = _p_style(ns, el)
        if style == "1" and _p_text(ns, el).strip() not in {"参考文献"}:
            break
        txt = _p_text(ns, el).strip()
        if bib_entry_re.match(txt):
            pPr = _ensure_ppr(ns, el)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)
            ind.set(w_hangingChars, "200")
        i += 1


def _contains_cjk(text: str) -> bool:
    return any(
        "\u4e00" <= ch <= "\u9fff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\u3040" <= ch <= "\u30ff"
        or "\uac00" <= ch <= "\ud7af"
        for ch in text
    )


def _is_ascii_token_char(ch: str) -> bool:
    return ord(ch) < 128 and (ch.isalnum() or ch in " ./,:;%+-_/()[]")


def _split_mixed_script_runs(ns: dict[str, str], body: ET.Element) -> None:
    """Split mixed CJK/ASCII runs so Latin tokens can use explicit Latin fonts."""
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_t = _qn(ns, "w", "t")

    split_count = 0

    for p in body.findall(f".//{w_p}"):
        children = list(p)
        i = 0
        while i < len(children):
            r = children[i]
            if r.tag != w_r:
                i += 1
                continue

            parts = list(r)
            if any(part.tag not in {w_rPr, w_t} for part in parts):
                i += 1
                continue
            t_nodes = [part for part in parts if part.tag == w_t]
            if len(t_nodes) != 1:
                i += 1
                continue

            text = t_nodes[0].text or ""
            if not text or not _contains_cjk(text) or not re.search(r"[A-Za-z0-9]", text):
                i += 1
                continue

            segments: list[tuple[str, str]] = []
            buf = []
            kind: str | None = None
            for ch in text:
                next_kind = "ascii" if _is_ascii_token_char(ch) else "cjk"
                if kind is None or next_kind == kind:
                    buf.append(ch)
                    kind = next_kind
                    continue
                segments.append((kind, "".join(buf)))
                buf = [ch]
                kind = next_kind
            if buf:
                segments.append((kind or "cjk", "".join(buf)))

            if len(segments) <= 1:
                i += 1
                continue

            insert_at = i
            for _, seg in segments:
                if not seg:
                    continue
                new_r = copy.deepcopy(r)
                for child in list(new_r):
                    if child.tag == w_t:
                        new_r.remove(child)
                new_t = ET.SubElement(new_r, w_t)
                new_t.text = seg
                if seg[0] == " " or seg[-1] == " ":
                    new_t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                p.insert(insert_at, new_r)
                insert_at += 1
            p.remove(r)
            split_count += 1
            children = list(p)
            i = insert_at

    if split_count:
        print(f"  [fonts] Split {split_count} mixed-script run(s)")


def _normalize_ascii_run_fonts(ns: dict[str, str], body: ET.Element) -> None:
    """Force English letters and Arabic numerals to use Times New Roman."""
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    w_eastAsia = _qn(ns, "w", "eastAsia")
    w_hint = _qn(ns, "w", "hint")
    w_cs = _qn(ns, "w", "cs")
    changed = 0
    ascii_re = re.compile(r"[0-9A-Za-z]")

    for r in body.findall(f".//{w_r}"):
        texts = [t.text or "" for t in r.findall(f".//{w_t}")]
        if not texts:
            continue
        joined = "".join(texts)
        if not ascii_re.search(joined):
            continue

        rPr = r.find(w_rPr)
        if rPr is None:
            rPr = ET.Element(w_rPr)
            r.insert(0, rPr)

        rFonts = rPr.find(w_rFonts)
        if rFonts is None:
            rFonts = ET.SubElement(rPr, w_rFonts)

        if rFonts.get(w_ascii) != "Times New Roman":
            rFonts.set(w_ascii, "Times New Roman")
            changed += 1
        if rFonts.get(w_hAnsi) != "Times New Roman":
            rFonts.set(w_hAnsi, "Times New Roman")
        if not _contains_cjk(joined):
            for attr in (w_eastAsia, w_hint, w_cs):
                if attr in rFonts.attrib:
                    del rFonts.attrib[attr]

    if changed:
        print(f"  [fonts] Normalized {changed} ASCII/numeric run(s) to Times New Roman")


def _normalize_bibliography_run_style(ns: dict[str, str], body: ET.Element) -> None:
    """Set bibliography entry runs to 五号 and ensure Latin text uses Times New Roman."""
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_val = _qn(ns, "w", "val")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    w_cs = _qn(ns, "w", "cs")

    children = list(body)
    ref_idx = None
    for i, el in enumerate(children):
        if el.tag != w_p:
            continue
        if _p_text(ns, el).strip() == "参考文献":
            ref_idx = i
            break
    if ref_idx is None:
        return

    bib_entry_re = re.compile(r"^(\[[0-9]{1,4}\]|［[0-9]{1,4}］)")
    changed = 0
    i = ref_idx + 1
    while i < len(children):
        el = children[i]
        if el.tag != w_p:
            i += 1
            continue
        style = _p_style(ns, el)
        if style == "1" and _p_text(ns, el).strip() not in {"参考文献"}:
            break
        txt = _p_text(ns, el).strip()
        if not bib_entry_re.match(txt):
            i += 1
            continue

        for r in el.findall(f".//{w_r}"):
            rPr = r.find(w_rPr)
            if rPr is None:
                rPr = ET.Element(w_rPr)
                r.insert(0, rPr)

            rFonts = rPr.find(w_rFonts)
            if rFonts is None:
                rFonts = ET.SubElement(rPr, w_rFonts)
            rFonts.set(w_ascii, "Times New Roman")
            rFonts.set(w_hAnsi, "Times New Roman")
            if rFonts.get(w_cs) is None:
                rFonts.set(w_cs, "Times New Roman")

            sz = rPr.find(w_sz)
            if sz is None:
                sz = ET.SubElement(rPr, w_sz)
            sz.set(w_val, "21")

            szCs = rPr.find(w_szCs)
            if szCs is None:
                szCs = ET.SubElement(rPr, w_szCs)
            szCs.set(w_val, "21")
            changed += 1
        i += 1

    if changed:
        print(f"  [fonts] Normalized {changed} bibliography run(s) to 五号")


def _fix_numbering_isLgl(ns: dict[str, str], numbering_xml: bytes) -> bytes:
    ns2 = _collect_ns(numbering_xml)
    if "w" not in ns2:
        return numbering_xml
    _register_ns(ns2)
    w_uri = ns2["w"]
    w_abstractNum = f"{{{w_uri}}}abstractNum"
    w_abstractNumId = f"{{{w_uri}}}abstractNumId"
    w_lvl = f"{{{w_uri}}}lvl"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_isLgl = f"{{{w_uri}}}isLgl"
    w_start = f"{{{w_uri}}}start"

    root = ET.fromstring(numbering_xml)

    # Find multi-level abstractNum (heading numbering); prefer id=0 for
    # backwards-compatibility with 版式1 template, fall back to any with ≥2 levels.
    targets: list[ET.Element] = []
    fallbacks: list[ET.Element] = []
    for absn in root.findall(w_abstractNum):
        levels = absn.findall(w_lvl)
        if absn.get(w_abstractNumId) == "0" and len(levels) >= 2:
            targets.append(absn)
        elif len(levels) >= 2:
            fallbacks.append(absn)
    if not targets:
        targets = fallbacks
    if not targets:
        return numbering_xml

    changed = False
    for target in targets:
        for lvl in target.findall(w_lvl):
            ilvl = lvl.get(w_ilvl)
            if ilvl is None:
                continue
            try:
                ilvl_i = int(ilvl)
            except ValueError:
                continue
            if ilvl_i < 1:
                continue
            if lvl.find(w_isLgl) is not None:
                continue
            isLgl = ET.Element(w_isLgl)
            # Insert after <w:start> if present, else as first child.
            start = lvl.find(w_start)
            if start is not None:
                idx = list(lvl).index(start) + 1
                lvl.insert(idx, isLgl)
            else:
                lvl.insert(0, isLgl)
            changed = True

    if not changed:
        return numbering_xml
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _normalize_list_indents(numbering_xml: bytes) -> bytes:
    """Pull pandoc-generated list indents closer to the LaTeX PDF layout."""
    if not numbering_xml:
        return numbering_xml

    ns = _collect_ns(numbering_xml)
    if "w" not in ns:
        return numbering_xml
    _register_ns(ns)
    w_uri = ns["w"]
    w_abstractNum = f"{{{w_uri}}}abstractNum"
    w_abstractNumId = f"{{{w_uri}}}abstractNumId"
    w_lvl = f"{{{w_uri}}}lvl"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_numFmt = f"{{{w_uri}}}numFmt"
    w_pPr = f"{{{w_uri}}}pPr"
    w_ind = f"{{{w_uri}}}ind"
    w_val = f"{{{w_uri}}}val"
    w_left = f"{{{w_uri}}}left"
    w_hanging = f"{{{w_uri}}}hanging"
    w_firstLine = f"{{{w_uri}}}firstLine"
    w_firstLineChars = f"{{{w_uri}}}firstLineChars"
    w_hangingChars = f"{{{w_uri}}}hangingChars"

    root = ET.fromstring(numbering_xml)
    list_numfmts = {"bullet", "decimal", "lowerLetter", "lowerRoman"}
    # Calibrated against the current SWUN DOCX->PDF output so level-0 list
    # body text lands on the same x coordinate as the LaTeX PDF.
    left_shift = 362
    min_left = 358
    target_hanging = "360"
    changed = 0

    for absn in root.findall(w_abstractNum):
        abs_id = absn.get(w_abstractNumId, "")
        if abs_id in {"0", _HEADING_ABSTRACT_NUM_ID}:
            continue

        lvls = absn.findall(w_lvl)
        if not lvls:
            continue

        sample_fmt = None
        for lvl in lvls:
            numfmt = lvl.find(w_numFmt)
            if numfmt is not None:
                sample_fmt = numfmt.get(w_val, "")
                if sample_fmt:
                    break
        if sample_fmt not in list_numfmts:
            continue

        for lvl in lvls:
            ilvl_raw = lvl.get(w_ilvl, "0")
            try:
                ilvl = int(ilvl_raw)
            except ValueError:
                ilvl = 0

            pPr = lvl.find(w_pPr)
            if pPr is None:
                pPr = ET.SubElement(lvl, w_pPr)
            ind = pPr.find(w_ind)
            if ind is None:
                ind = ET.SubElement(pPr, w_ind)

            old_left = ind.get(w_left)
            try:
                base_left = int(old_left) if old_left is not None else 720 * (ilvl + 1)
            except ValueError:
                base_left = 720 * (ilvl + 1)

            ind.set(w_left, str(max(min_left, base_left - left_shift)))
            ind.set(w_hanging, target_hanging)
            for attr in (w_firstLine, w_firstLineChars, w_hangingChars):
                if attr in ind.attrib:
                    del ind.attrib[attr]
            changed += 1

    if changed:
        print(f"  [numbering] Normalized {changed} list level indent(s)")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Bind heading styles to multi-level numbering (第1章 / 1.1 / 1.1.1).
# pandoc strips numPr from heading style definitions during conversion;
# this function restores them using the official template's numbering scheme.
# ---------------------------------------------------------------------------
_HEADING_ABSTRACT_NUM_XML = '''\
<w:abstractNum w:abstractNumId="88880" xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:multiLevelType w:val="multilevel"/>
  <w:lvl w:ilvl="0">
    <w:start w:val="1"/>
    <w:numFmt w:val="chineseCounting"/>
    <w:lvlText w:val="第%1章"/>
    <w:lvlJc w:val="left"/>
    <w:isLgl/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="1">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="2">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2.%3"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
  <w:lvl w:ilvl="3">
    <w:start w:val="1"/>
    <w:numFmt w:val="decimal"/>
    <w:isLgl/>
    <w:lvlText w:val="%1.%2.%3.%4"/>
    <w:lvlJc w:val="left"/>
    <w:suff w:val="space"/>
  </w:lvl>
</w:abstractNum>'''

_HEADING_NUM_ID = "8888"
_HEADING_ABSTRACT_NUM_ID = "88880"


def _inject_heading_numbering(numbering_xml: bytes) -> bytes:
    """Inject multi-level chapter numbering definition into numbering.xml."""
    ns2 = _collect_ns(numbering_xml)
    if "w" not in ns2:
        return numbering_xml
    _register_ns(ns2)
    w_uri = ns2["w"]

    root = ET.fromstring(numbering_xml)

    # Check if our abstractNum already exists
    for absn in root.findall(f"{{{w_uri}}}abstractNum"):
        if absn.get(f"{{{w_uri}}}abstractNumId") == _HEADING_ABSTRACT_NUM_ID:
            return numbering_xml  # Already injected

    # Parse abstractNum element
    absn_el = ET.fromstring(_HEADING_ABSTRACT_NUM_XML)

    # Word requires: all abstractNum BEFORE all num.
    # Find the index of the first w:num element and insert abstractNum before it.
    w_num_tag = f"{{{w_uri}}}num"
    insert_idx = len(root)  # default: end
    for i, child in enumerate(root):
        if child.tag == w_num_tag:
            insert_idx = i
            break
    root.insert(insert_idx, absn_el)

    # Append num entry at the end (after all other num elements)
    num_el = ET.SubElement(root, f"{{{w_uri}}}num")
    num_el.set(f"{{{w_uri}}}numId", _HEADING_NUM_ID)
    absn_ref = ET.SubElement(num_el, f"{{{w_uri}}}abstractNumId")
    absn_ref.set(f"{{{w_uri}}}val", _HEADING_ABSTRACT_NUM_ID)

    print(f"  [numbering] Injected heading abstractNum={_HEADING_ABSTRACT_NUM_ID} num={_HEADING_NUM_ID}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _bind_heading_styles_to_numbering(styles_xml: bytes) -> bytes:
    """Add numPr to heading 1/2/3 style definitions so they pick up chapter numbering."""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    if "w" not in sns:
        return styles_xml
    _register_ns(sns)
    w_uri = sns["w"]

    sroot = ET.fromstring(styles_xml)

    # Map: styleId -> (numId, ilvl)
    heading_bindings = {
        "1": ("0",),       # heading 1 -> ilvl=0
        "Heading2": ("1",),  # heading 2 -> ilvl=1
        "Heading3": ("2",),  # heading 3 -> ilvl=2
    }

    w_style = f"{{{w_uri}}}style"
    w_styleId = f"{{{w_uri}}}styleId"
    w_pPr = f"{{{w_uri}}}pPr"
    w_numPr = f"{{{w_uri}}}numPr"
    w_numId = f"{{{w_uri}}}numId"
    w_ilvl = f"{{{w_uri}}}ilvl"
    w_val = f"{{{w_uri}}}val"

    count = 0
    for s in sroot.findall(w_style):
        sid = s.get(w_styleId, "")
        if sid not in heading_bindings:
            continue

        ilvl_val = heading_bindings[sid][0]

        pPr = s.find(w_pPr)
        if pPr is None:
            pPr = ET.SubElement(s, w_pPr)

        # Remove existing numPr if any
        old_numPr = pPr.find(w_numPr)
        if old_numPr is not None:
            pPr.remove(old_numPr)

        # Add numPr
        numPr = ET.SubElement(pPr, w_numPr)
        ilvl_el = ET.SubElement(numPr, w_ilvl)
        ilvl_el.set(w_val, ilvl_val)
        numId_el = ET.SubElement(numPr, w_numId)
        numId_el.set(w_val, _HEADING_NUM_ID)

        count += 1

    if count:
        print(f"  [styles] Bound {count} heading style(s) to numId={_HEADING_NUM_ID}")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)


def _align_styles_to_reference(styles_xml: bytes) -> bytes:
    """Align key styles in styles.xml to the SWUN reference thesis."""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    if "w" not in sns:
        return styles_xml
    _register_ns(sns)
    sroot = ET.fromstring(styles_xml)

    w_style = _qn(sns, "w", "style")
    w_styleId = _qn(sns, "w", "styleId")
    w_pPr = _qn(sns, "w", "pPr")
    w_rPr = _qn(sns, "w", "rPr")
    w_ind = _qn(sns, "w", "ind")
    w_jc = _qn(sns, "w", "jc")
    w_spacing = _qn(sns, "w", "spacing")
    w_widowControl = _qn(sns, "w", "widowControl")
    w_outlineLvl = _qn(sns, "w", "outlineLvl")
    w_b = _qn(sns, "w", "b")
    w_kern = _qn(sns, "w", "kern")
    w_sz = _qn(sns, "w", "sz")
    w_szCs = _qn(sns, "w", "szCs")
    w_val = _qn(sns, "w", "val")
    w_name = _qn(sns, "w", "name")

    def _ensure(parent: ET.Element, tag: str) -> ET.Element:
        el = parent.find(tag)
        if el is None:
            el = ET.SubElement(parent, tag)
        return el

    def _style_key(st: ET.Element) -> tuple[str, str]:
        sid = (st.get(w_styleId, "") or "").strip()
        name_el = st.find(w_name)
        name = ""
        if name_el is not None:
            name = (name_el.get(w_val, "") or "").strip()
        sid_norm = sid.replace(" ", "").lower()
        name_norm = name.replace(" ", "").lower()
        return sid_norm, name_norm

    updated: list[str] = []
    for st in sroot.findall(w_style):
        sid = st.get(w_styleId, "")
        sid_norm, name_norm = _style_key(st)

        # 1) Normal style (template styleId='a', style name='Normal').
        # Some previous builds incorrectly assumed styleId='1', which is actually
        # Heading 1 in this template family and corrupts chapter titles.
        if sid_norm == "a" or name_norm == "normal":
            pPr = _ensure(st, w_pPr)
            ind = _ensure(pPr, w_ind)
            ind.set(_qn(sns, "w", "firstLine"), "480")
            ind.set(_qn(sns, "w", "firstLineChars"), "200")

            jc = _ensure(pPr, w_jc)
            jc.set(w_val, "both")

            spacing = _ensure(pPr, w_spacing)
            spacing.set(_qn(sns, "w", "line"), "360")
            spacing.set(_qn(sns, "w", "lineRule"), "auto")
            for attr in ("before", "beforeLines", "beforeAutospacing", "after", "afterLines", "afterAutospacing"):
                q_attr = _qn(sns, "w", attr)
                if q_attr in spacing.attrib:
                    del spacing.attrib[q_attr]

            widow = _ensure(pPr, w_widowControl)
            widow.set(w_val, "0")

            rPr = _ensure(st, w_rPr)
            for b in list(rPr.findall(w_b)):
                rPr.remove(b)

            kern = _ensure(rPr, w_kern)
            kern.set(w_val, "2")

            sz = _ensure(rPr, w_sz)
            sz.set(w_val, "24")
            szCs = _ensure(rPr, w_szCs)
            szCs.set(w_val, "24")

            updated.append(f"Normal(styleId={sid or 'unknown'})")

        # 2) Heading 3 style (styleId='Heading3', style name='heading 3').
        elif sid_norm in {"heading3", "3"} or name_norm == "heading3":
            pPr = _ensure(st, w_pPr)
            ind = _ensure(pPr, w_ind)
            ind.set(_qn(sns, "w", "firstLine"), "482")
            fl_chars = _qn(sns, "w", "firstLineChars")
            if fl_chars in ind.attrib:
                del ind.attrib[fl_chars]

            outline = _ensure(pPr, w_outlineLvl)
            outline.set(w_val, "2")

            spacing = _ensure(pPr, w_spacing)
            spacing.set(_qn(sns, "w", "before"), "260")
            spacing.set(_qn(sns, "w", "after"), "260")
            spacing.set(_qn(sns, "w", "line"), "415")

            rPr = st.find(w_rPr)
            if rPr is not None:
                for node in list(rPr.findall(w_sz)):
                    rPr.remove(node)
                for node in list(rPr.findall(w_szCs)):
                    rPr.remove(node)

            updated.append(f"Heading3(styleId={sid or 'unknown'})")

    if updated:
        print(f"  [styles] Aligned reference styles: {', '.join(updated)}")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)


def _collect_style_ids(styles_xml: bytes) -> set[str]:
    ns = _collect_ns(styles_xml)
    if "w" not in ns:
        return set()
    w_uri = ns["w"]
    q_style = f"{{{w_uri}}}style"
    q_styleId = f"{{{w_uri}}}styleId"
    root = ET.fromstring(styles_xml)
    out: set[str] = set()
    for st in root.findall(q_style):
        sid = st.get(q_styleId)
        if sid:
            out.add(sid)
    return out


def _normalize_unknown_pstyles(
    ns: dict[str, str], body: ET.Element, known_styles: set[str]
) -> None:
    """Map paragraphs that reference non-existent styles back to Normal ('a')."""
    w_p = _qn(ns, "w", "p")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")

    # Pandoc may emit these pStyle values even when the reference template doesn't define them.
    # Prefer mapping them to template Normal (styleId 'a') to keep formatting stable.
    candidates = {
        "BodyText",
        "FirstParagraph",
        "Compact",
        "ImageCaption",
        "CaptionedFigure",
        "TableCaption",
        "Bibliography",
        "Caption",
    }

    for p in body.iter(w_p):
        pPr = p.find(_qn(ns, "w", "pPr"))
        if pPr is None:
            continue
        ps = pPr.find(w_pStyle)
        if ps is None:
            continue
        val = ps.get(w_val)
        if not val:
            continue
        if val in known_styles:
            continue
        if val in candidates:
            ps.set(w_val, "a")


# ---------------------------------------------------------------------------
# Round 8 fix: Remove docGrid type="lines" to prevent line-spacing inflation.
# When type="lines" is set and paragraph line spacing (e.g. 360 twips = 1.5x)
# exceeds linePitch (e.g. 312), LibreOffice snaps to the next grid multiple
# (312×2 = 624 twips ≈ 2.6x), causing ~14 lines/page instead of ~30.
# ---------------------------------------------------------------------------
def _remove_docgrid_lines_type(ns: dict[str, str], body: ET.Element) -> None:
    """Remove docGrid type='lines' from all sectPr to disable grid-snap inflation."""
    w_sectPr = _qn(ns, "w", "sectPr")
    w_docGrid = _qn(ns, "w", "docGrid")
    w_type = _qn(ns, "w", "type")
    count = 0
    for sp in body.iter(w_sectPr):
        grid = sp.find(w_docGrid)
        if grid is not None and w_type in grid.attrib:
            del grid.attrib[w_type]
            count += 1
    if count:
        print(f"  [docGrid] Removed type='lines' from {count} section(s)")


# ---------------------------------------------------------------------------
# Round 3b fix: Replace WPS-legacy footer XML with clean PAGE field footers.
# WPS Office embeds complex textbox drawing elements that render as phantom
# "X" characters in LibreOffice.
# ---------------------------------------------------------------------------

# 单一 PAGE 字段 footer —— 实际显示格式由 sectPr 的 pgNumType 控制
_FOOTER_PAGE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/>'
    '<w:sz w:val="18"/></w:rPr><w:fldChar w:fldCharType="end"/></w:r>'
    '</w:p></w:ftr>'
)

_FOOTER_EMPTY_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    '<w:p><w:pPr><w:jc w:val="center"/></w:pPr></w:p></w:ftr>'
)


def _replace_wps_footers(
    file_data: dict[str, bytes],
    doc_xml: bytes,
) -> None:
    """Replace footer*.xml with clean PAGE field footers based on actual sectPr references.

    封面 section 的 default footer 写空（不显示页码），
    前置部分（摘要/目录）和正文 section 的 default footer 写 PAGE 字段。
    pgNumType（lowerRoman / decimal）已在 sectPr 中设定，控制显示格式。

    若封面和正文共享同一 default footer rId，则自动拆分：
    把封面 sectPr 的 default footerReference 指向一个空闲 footer 文件。
    """
    footer_files: list[str] = []
    for name in list(file_data):
        if re.match(r"word/footer\d+\.xml$", name):
            footer_files.append(name)
    if not footer_files:
        return

    # --- 解析 document.xml 获取 sectPr → footerReference 映射 ---
    dns = _collect_ns(doc_xml)
    _register_ns(dns)
    droot = ET.fromstring(doc_xml)
    w_sectPr_tag = _qn(dns, "w", "sectPr")
    w_footerRef_tag = _qn(dns, "w", "footerReference")
    w_type_attr = _qn(dns, "w", "type")
    w_pgNumType_tag = _qn(dns, "w", "pgNumType")
    w_fmt_attr = _qn(dns, "w", "fmt")
    r_id_attr = _qn(dns, "r", "id") if "r" in dns else (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )

    all_sectPr = droot.findall(f".//{w_sectPr_tag}")

    # 解析 rels 映射 rId → footer 文件名
    rels_bytes = file_data.get("word/_rels/document.xml.rels", b"")
    rid_to_footer: dict[str, str] = {}  # rId6 -> footer1.xml
    if rels_bytes:
        rns = _collect_ns(rels_bytes)
        _register_ns(rns)
        rroot = ET.fromstring(rels_bytes)
        for rel in rroot:
            target = rel.get("Target", "")
            rid = rel.get("Id", "")
            if re.match(r"footer\d+\.xml$", target):
                rid_to_footer[rid] = target

    # 收集每个 section 的 default footer rId 和 pgNumType fmt
    sect_info: list[dict[str, str | None]] = []
    for sp in all_sectPr:
        default_rid = None
        for fr in sp.findall(w_footerRef_tag):
            if fr.get(w_type_attr) == "default":
                default_rid = fr.get(r_id_attr)
                break
        pgnum = sp.find(w_pgNumType_tag)
        fmt = pgnum.get(w_fmt_attr) if pgnum is not None else None
        sect_info.append({"default_rid": default_rid, "fmt": fmt})

    # 确定哪些 footer 文件需要 PAGE 字段，哪些需要空
    # 规则：section 0（封面）的 default footer → 空
    #        其余 section 的 default footer → PAGE 字段
    page_footer_files: set[str] = set()  # 需要 PAGE 字段的 footer 文件
    empty_footer_files: set[str] = set()  # 需要空的 footer 文件

    # 找出非封面 section 使用的 default footer
    for i, info in enumerate(sect_info):
        rid = info["default_rid"]
        if rid and rid in rid_to_footer:
            fname = f"word/{rid_to_footer[rid]}"
            if i == 0:
                empty_footer_files.add(fname)
            else:
                page_footer_files.add(fname)

    # 处理冲突：同一 footer 文件既需要空又需要 PAGE
    conflict = page_footer_files & empty_footer_files
    if conflict and len(sect_info) > 0:
        # 封面 section 需要拆分到另一个 footer 文件
        # 找一个没有被任何 section default 引用的空闲 footer 文件
        used_footers = {f"word/{rid_to_footer[info['default_rid']]}"
                        for info in sect_info
                        if info["default_rid"] and info["default_rid"] in rid_to_footer}
        free_footer = None
        for ff in sorted(footer_files):
            if ff not in used_footers:
                free_footer = ff
                break

        if free_footer is not None:
            # 把封面 section 的 default footerReference 指向这个空闲 footer
            # 需要找到空闲 footer 对应的 rId
            free_base = free_footer.replace("word/", "")
            free_rid = None
            for rid, target in rid_to_footer.items():
                if target == free_base:
                    free_rid = rid
                    break

            if free_rid is not None:
                # 修改 document.xml 中封面 section 的 default footer rId
                cover_sp = all_sectPr[0]
                for fr in cover_sp.findall(w_footerRef_tag):
                    if fr.get(w_type_attr) == "default":
                        fr.set(r_id_attr, free_rid)
                        break
                # 更新映射
                empty_footer_files.discard(next(iter(conflict)))
                empty_footer_files.add(free_footer)
                page_footer_files.discard(free_footer)

                # 序列化修改后的 document.xml 回 file_data
                file_data["word/document.xml"] = ET.tostring(
                    droot, encoding="utf-8", xml_declaration=True
                )
                print(f"  [footer] Cover section default footer reassigned to {free_base} ({free_rid})")

    # 写入 footer 文件内容
    replaced = 0
    for fname in footer_files:
        if fname in page_footer_files:
            file_data[fname] = _FOOTER_PAGE_XML.encode("utf-8")
        else:
            # 所有非 PAGE 的 footer 文件都写空（包括 first/even 类型、封面 default、未使用的）
            file_data[fname] = _FOOTER_EMPTY_XML.encode("utf-8")
        replaced += 1

    print(f"  [footer] Replaced {replaced} footer file(s) with clean XML")


# ---------------------------------------------------------------------------
# Round 6 fix: Normalize Hyperlink character style to standard blue + underline.
# ---------------------------------------------------------------------------
def _fix_hyperlink_style(styles_xml: bytes) -> bytes:
    """Modify Hyperlink char style: color=0563C1, underline=single, remove textFill."""
    if not styles_xml:
        return styles_xml
    sns = _collect_ns(styles_xml)
    _register_ns(sns)
    sroot = ET.fromstring(styles_xml)

    w_style = _qn(sns, "w", "style")
    w_name = _qn(sns, "w", "name")
    w_val = _qn(sns, "w", "val")
    w_rPr = _qn(sns, "w", "rPr")
    w_color = _qn(sns, "w", "color")
    w_u = _qn(sns, "w", "u")
    w_themeColor = _qn(sns, "w", "themeColor")

    # w14:textFill (Word 2010+ gradient fill)
    w14_uri = sns.get("w14", "http://schemas.microsoft.com/office/word/2010/wordml")
    w14_textFill = f"{{{w14_uri}}}textFill"

    count = 0
    for s in sroot.iter(w_style):
        name_el = s.find(w_name)
        if name_el is None:
            continue
        name_val = (name_el.get(w_val) or "").lower()
        if "hyperlink" not in name_val:
            continue

        rPr = s.find(w_rPr)
        if rPr is None:
            continue

        # 设为 Word 默认链接蓝色
        color = rPr.find(w_color)
        if color is not None:
            color.set(w_val, "0563C1")
            if w_themeColor in color.attrib:
                del color.attrib[w_themeColor]
        else:
            c = ET.SubElement(rPr, w_color)
            c.set(w_val, "0563C1")

        # 添加单下划线
        u = rPr.find(w_u)
        if u is not None:
            u.set(w_val, "single")
        else:
            u = ET.SubElement(rPr, w_u)
            u.set(w_val, "single")

        # 移除 w14:textFill
        tf = rPr.find(w14_textFill)
        if tf is not None:
            rPr.remove(tf)

        count += 1

    if count:
        print(f"  [styles] Changed {count} Hyperlink style(s) to blue + underline")

    return ET.tostring(sroot, encoding="utf-8", xml_declaration=True)


def _build_algorithm_table(
    ns: dict[str, str],
    title_p: ET.Element,
    body_paragraphs: list[ET.Element],
    table_width_dxa: int,
) -> ET.Element:
    w_tbl = _qn(ns, "w", "tbl")
    w_tblPr = _qn(ns, "w", "tblPr")
    w_tblStyle = _qn(ns, "w", "tblStyle")
    w_tblW = _qn(ns, "w", "tblW")
    w_jc = _qn(ns, "w", "jc")
    w_tblLook = _qn(ns, "w", "tblLook")
    w_tblGrid = _qn(ns, "w", "tblGrid")
    w_gridCol = _qn(ns, "w", "gridCol")
    w_tr = _qn(ns, "w", "tr")
    w_tc = _qn(ns, "w", "tc")
    w_tcPr = _qn(ns, "w", "tcPr")
    w_tcW = _qn(ns, "w", "tcW")
    w_val = _qn(ns, "w", "val")
    w_w = _qn(ns, "w", "w")
    w_type = _qn(ns, "w", "type")
    tw_str = str(table_width_dxa)
    tbl = ET.Element(w_tbl)
    tblPr = ET.SubElement(tbl, w_tblPr)
    style_el = ET.SubElement(tblPr, w_tblStyle)
    style_el.set(w_val, "55")
    tw_el = ET.SubElement(tblPr, w_tblW)
    tw_el.set(w_w, tw_str)
    tw_el.set(w_type, "dxa")
    jc_el = ET.SubElement(tblPr, w_jc)
    jc_el.set(w_val, "center")
    look_el = ET.SubElement(tblPr, w_tblLook)
    look_el.set(w_val, "04A0")
    look_el.set(_qn(ns, "w", "firstRow"), "1")
    look_el.set(_qn(ns, "w", "lastRow"), "0")
    look_el.set(_qn(ns, "w", "firstColumn"), "0")
    look_el.set(_qn(ns, "w", "lastColumn"), "0")
    look_el.set(_qn(ns, "w", "noHBand"), "0")
    look_el.set(_qn(ns, "w", "noVBand"), "1")
    grid = ET.SubElement(tbl, w_tblGrid)
    col = ET.SubElement(grid, w_gridCol)
    col.set(w_w, tw_str)
    tr0 = ET.SubElement(tbl, w_tr)
    tc0 = ET.SubElement(tr0, w_tc)
    tcPr0 = ET.SubElement(tc0, w_tcPr)
    tcW0 = ET.SubElement(tcPr0, w_tcW)
    tcW0.set(w_w, tw_str)
    tcW0.set(w_type, "dxa")
    tc0.append(title_p)
    tr1 = ET.SubElement(tbl, w_tr)
    tc1 = ET.SubElement(tr1, w_tc)
    tcPr1 = ET.SubElement(tc1, w_tcPr)
    tcW1 = ET.SubElement(tcPr1, w_tcW)
    tcW1.set(w_w, tw_str)
    tcW1.set(w_type, "dxa")
    for bp in body_paragraphs:
        tc1.append(bp)
    return tbl


def _format_algo_runs(ns: dict[str, str], p: ET.Element) -> None:
    """Format all runs: Times New Roman 10.5pt, remove bold."""
    w_r = _qn(ns, "w", "r")
    w_rPr = _qn(ns, "w", "rPr")
    w_rFonts = _qn(ns, "w", "rFonts")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_b = _qn(ns, "w", "b")
    w_bCs = _qn(ns, "w", "bCs")
    w_val = _qn(ns, "w", "val")
    w_ascii = _qn(ns, "w", "ascii")
    w_hAnsi = _qn(ns, "w", "hAnsi")
    for r in p.findall(f".//{w_r}"):
        rPr = r.find(w_rPr)
        if rPr is None:
            rPr = ET.Element(w_rPr)
            r.insert(0, rPr)
        rFonts = rPr.find(w_rFonts)
        if rFonts is None:
            rFonts = ET.SubElement(rPr, w_rFonts)
        rFonts.set(w_ascii, "Times New Roman")
        rFonts.set(w_hAnsi, "Times New Roman")
        sz_el = rPr.find(w_sz)
        if sz_el is None:
            sz_el = ET.SubElement(rPr, w_sz)
        sz_el.set(w_val, "21")
        szCs_el = rPr.find(w_szCs)
        if szCs_el is None:
            szCs_el = ET.SubElement(rPr, w_szCs)
        szCs_el.set(w_val, "21")
        for b_tag in (w_b, w_bCs):
            b_el = rPr.find(b_tag)
            if b_el is not None:
                rPr.remove(b_el)


def _set_algo_para_props(ns: dict[str, str], p: ET.Element) -> None:
    """Set algorithm paragraph properties: left-aligned, single spacing, no indent."""
    w_jc = _qn(ns, "w", "jc")
    w_val = _qn(ns, "w", "val")
    w_spacing = _qn(ns, "w", "spacing")
    w_ind = _qn(ns, "w", "ind")
    w_pBdr = _qn(ns, "w", "pBdr")
    pPr = _ensure_ppr(ns, p)
    jc = pPr.find(w_jc)
    if jc is None:
        jc = ET.SubElement(pPr, w_jc)
    jc.set(w_val, "left")
    sp = pPr.find(w_spacing)
    if sp is None:
        sp = ET.SubElement(pPr, w_spacing)
    sp.set(_qn(ns, "w", "line"), "240")
    sp.set(_qn(ns, "w", "lineRule"), "auto")
    sp.set(_qn(ns, "w", "before"), "0")
    sp.set(_qn(ns, "w", "after"), "0")
    ind = pPr.find(w_ind)
    if ind is not None:
        pPr.remove(ind)
    ind = ET.SubElement(pPr, w_ind)
    ind.set(_qn(ns, "w", "firstLine"), "0")
    ind.set(_qn(ns, "w", "firstLineChars"), "0")
    pBdr = pPr.find(w_pBdr)
    if pBdr is not None:
        pPr.remove(pBdr)


def _format_algorithm_blocks(ns: dict[str, str], root: ET.Element, body: ET.Element) -> None:
    """Detect algorithm blocks and apply academic formatting.

    Each algorithm block in the DOCX consists of:
      1. Title paragraph: text starts with "算法 N ..." (bold "算法 N" + caption)
      2. VML horizontal rule paragraph (top rule)
      3. Body paragraphs: input/output lines + numbered algorithm lines
         Each body line has a ⌊N⌋ indent marker prefix where N is the indent level
      4. VML horizontal rule paragraph (bottom rule)

    This function:
      - Replaces VML horizontal rules with proper paragraph top/bottom borders
      - Adds a top border to the title paragraph
      - Strips ⌊N⌋ markers and applies proper left indent
      - Removes first-line indent from algorithm paragraphs
      - Sets compact line spacing (single, no after spacing)
      - Applies 小五 (9pt) font size for algorithm body
    """
    w_p = _qn(ns, "w", "p")
    w_r = _qn(ns, "w", "r")
    w_t = _qn(ns, "w", "t")
    w_pPr = _qn(ns, "w", "pPr")
    w_rPr = _qn(ns, "w", "rPr")
    w_pStyle = _qn(ns, "w", "pStyle")
    w_val = _qn(ns, "w", "val")
    w_ind = _qn(ns, "w", "ind")
    w_left = _qn(ns, "w", "left")
    w_firstLine = _qn(ns, "w", "firstLine")
    w_firstLineChars = _qn(ns, "w", "firstLineChars")
    w_spacing = _qn(ns, "w", "spacing")
    w_line = _qn(ns, "w", "line")
    w_lineRule = _qn(ns, "w", "lineRule")
    w_before = _qn(ns, "w", "before")
    w_after = _qn(ns, "w", "after")
    w_pBdr = _qn(ns, "w", "pBdr")
    w_top = _qn(ns, "w", "top")
    w_bottom = _qn(ns, "w", "bottom")
    w_sz_attr = _qn(ns, "w", "sz")
    w_space = _qn(ns, "w", "space")
    w_color = _qn(ns, "w", "color")
    w_sz = _qn(ns, "w", "sz")
    w_szCs = _qn(ns, "w", "szCs")
    w_jc = _qn(ns, "w", "jc")
    w_pict = _qn(ns, "w", "pict")
    w_b = _qn(ns, "w", "b")
    w_bCs = _qn(ns, "w", "bCs")
    text_w = _sect_text_width_dxa(ns, root) or 8277

    # Indent marker regex: ⌊N⌋ where N is a digit
    indent_marker_re = re.compile(r"\u230A(\d+)\u230B")

    children = list(body)
    total = len(children)

    def _is_vml_hrule(el: ET.Element) -> bool:
        """Check if a paragraph contains only a VML horizontal rule."""
        if el.tag != w_p:
            return False
        pict = el.find(f".//{w_pict}")
        if pict is None:
            return False
        # VML hrule: <v:rect ... o:hr="t" />
        for child in pict:
            hr_attr = child.get("{urn:schemas-microsoft-com:office:office}hr")
            if hr_attr == "t":
                return True
        return False

    def _strip_indent_markers(p: ET.Element) -> int:
        """Find and remove ⌊N⌋ indent markers from text runs. Return indent level."""
        indent_level = 0
        for t in p.findall(f".//{w_t}"):
            if t.text and indent_marker_re.search(t.text):
                m = indent_marker_re.search(t.text)
                indent_level = int(m.group(1))
                t.text = indent_marker_re.sub("", t.text)
        return indent_level

    def _has_bold_alg_prefix(p: ET.Element) -> bool:
        """Check if paragraph starts with bold '算法' text (distinguishes
        algorithm titles from body text that mentions algorithms)."""
        for r in p.findall(f".//{w_r}"):
            rPr = r.find(w_rPr)
            if rPr is None:
                continue
            b_el = rPr.find(w_b)
            if b_el is None:
                continue
            b_val = b_el.get(w_val)
            if b_val is not None and b_val not in ("true", "1", ""):
                continue
            t_el = r.find(w_t)
            if t_el is not None and t_el.text and "算法" in t_el.text:
                return True
        return False

    INDENT_SPACES = 4
    # 行号匹配：以 "数字:" 开头（可能后面有空格），用于区分有行号的行
    lineno_re = re.compile(r"^(\d+:)\s*")

    alg_title_re = re.compile(r"^算法\s*\d+")
    alg_count = 0
    i = 0
    while i < total:
        el = children[i]
        if el.tag != w_p:
            i += 1
            continue

        text = _p_text(ns, el).strip()
        if not alg_title_re.match(text):
            i += 1
            continue

        # Verify this is an algorithm title (bold "算法") not body text mentioning algorithms
        if not _has_bold_alg_prefix(el):
            i += 1
            continue

        title_idx = i

        # Next paragraph should be VML horizontal rule (top rule)
        top_rule_idx = i + 1
        if top_rule_idx >= total or not _is_vml_hrule(children[top_rule_idx]):
            i += 1
            continue

        bottom_rule_idx = None
        j = top_rule_idx + 1
        while j < total:
            if _is_vml_hrule(children[j]):
                bottom_rule_idx = j
                break
            j += 1

        if bottom_rule_idx is None:
            i += 1
            continue

        alg_count += 1
        title_p = children[title_idx]
        body_ps = [children[k] for k in range(top_rule_idx + 1, bottom_rule_idx)]

        # Format title paragraph
        _format_algo_runs(ns, title_p)
        _set_algo_para_props(ns, title_p)

        # Format body paragraphs
        for bp in body_ps:
            if bp.tag != w_p:
                continue
            indent_level = _strip_indent_markers(bp)
            if indent_level > 0:
                indent_str = " " * (indent_level * INDENT_SPACES)
                # 行号始终左对齐：缩进空格应插入到行号之后，而不是行号之前。
                # 遍历所有 <w:t>，找到第一个有内容的文本元素：
                #   - 若文本以 "数字: " 开头（行号行），把缩进插在行号之后
                #   - 否则（输入/输出行等无行号行），把缩进插在文本开头
                for t_el in bp.findall(f".//{w_t}"):
                    if not t_el.text:
                        continue
                    lm = lineno_re.match(t_el.text)
                    if lm:
                        # 行号行：在行号之后插入缩进，保持行号左对齐
                        after_lineno = t_el.text[lm.end():]
                        t_el.text = lm.group(1) + " " + indent_str + after_lineno
                    else:
                        # 无行号行（输入/输出）：在开头插入缩进
                        t_el.text = indent_str + t_el.text
                    break
            _format_algo_runs(ns, bp)
            _set_algo_para_props(ns, bp)

        # Remove all elements from body
        for idx in sorted(range(title_idx, bottom_rule_idx + 1), reverse=True):
            body.remove(children[idx])

        # Build and insert three-line table
        tbl = _build_algorithm_table(ns, title_p, body_ps, text_w)
        body.insert(title_idx, tbl)

        # Refresh children list
        children = list(body)
        total = len(children)
        i = title_idx + 1

    if alg_count:
        print(f"  [algorithms] Wrapped {alg_count} algorithm block(s) in three-line tables")


def _postprocess_docx(
    input_docx: Path,
    output_docx: Path,
    display_math_flags: list[bool] | None,
    cn_keywords: str | None,
    en_keywords: str | None,
    caption_meta: dict[str, CaptionMeta],
    latex_col_ratios: dict[str, list[float]] | None = None,
) -> None:
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

        _prepend_template_cover_pages(doc_ns, body, TEMPLATE_DOCX)

        styles_xml = zin.read("word/styles.xml") if "word/styles.xml" in files else b""
        known_styles = _collect_style_ids(styles_xml) if styles_xml else set()
        table_style_id = _first_table_style_id(styles_xml) if styles_xml else None
        hyperlink_style_ids = _collect_hyperlink_char_style_ids(styles_xml) if styles_xml else set()

        sectPr = _get_body_sectPr(doc_ns, body)
        if sectPr is not None:
            sectPr_proto = copy.deepcopy(sectPr)
        else:
            sectPr_proto = None

        if sectPr_proto is not None:
            _insert_abstract_chapters_and_sections(doc_ns, body, sectPr_proto)

        _insert_abstract_keywords(doc_ns, body, cn_keywords, en_keywords)

        _insert_toc_before_first_chapter(doc_ns, body)
        _add_page_breaks_before_h1(doc_ns, body)
        _apply_three_line_tables(doc_ns, root, body, table_style_id, latex_col_ratios=latex_col_ratios)
        _number_paragraph_headings_in_main_body(doc_ns, body)
        _format_algorithm_blocks(doc_ns, root, body)
        _ensure_indent_for_body_paragraphs(doc_ns, body)
        _ensure_hanging_indent_for_bibliography(doc_ns, body)
        _split_mixed_script_runs(doc_ns, body)
        _normalize_ascii_run_fonts(doc_ns, body)
        _normalize_bibliography_run_style(doc_ns, body)
        _inject_captions_from_meta(doc_ns, body, caption_meta)
        _dedupe_body_level_anchor_bookmarks(doc_ns, body)
        _fix_ref_dot_to_hyphen(doc_ns, body)
        _strip_anchor_hyperlinks_in_main_body(doc_ns, body, hyperlink_style_ids)
        _number_display_equations(doc_ns, root, body, display_math_flags)
        if known_styles:
            _normalize_unknown_pstyles(doc_ns, body, known_styles)

        # Ensure the final/main section uses Arabic page numbers starting at 1.
        sectPr2 = _get_body_sectPr(doc_ns, body)
        if sectPr2 is not None:
            _set_sect_pgnum(doc_ns, sectPr2, fmt="decimal", start=1)

        # Remove docGrid type="lines" to prevent line-spacing inflation
        _remove_docgrid_lines_type(doc_ns, body)

        new_doc_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        numbering_xml = zin.read("word/numbering.xml") if "word/numbering.xml" in files else None
        new_numbering_xml = numbering_xml
        if new_numbering_xml:
            new_numbering_xml = _inject_heading_numbering(new_numbering_xml)
            new_numbering_xml = _fix_numbering_isLgl(doc_ns, new_numbering_xml)
            new_numbering_xml = _normalize_list_indents(new_numbering_xml)

        # Bind heading styles to numbering + align key style definitions + normalize Hyperlink style
        new_styles_xml = styles_xml
        if new_styles_xml:
            new_styles_xml = _bind_heading_styles_to_numbering(new_styles_xml)
            new_styles_xml = _align_styles_to_reference(new_styles_xml)
            new_styles_xml = _fix_hyperlink_style(new_styles_xml)

        # Collect all file data for footer replacement
        file_data: dict[str, bytes] = {}
        for name in files:
            file_data[name] = zin.read(name)

        # Replace WPS-legacy footer XML with clean PAGE field footers.
        # Pass modified document.xml so footer mapping is based on actual sectPr.
        # If cover section shares the same default footer rId as body sections,
        # _replace_wps_footers reassigns cover's footerReference and updates
        # file_data["word/document.xml"], which we pick up below.
        file_data["word/document.xml"] = new_doc_xml
        _replace_wps_footers(file_data, new_doc_xml)
        # Pick up potentially updated document.xml from footer reassignment
        new_doc_xml = file_data["word/document.xml"]

        # Write a new docx, copying everything else verbatim.
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
                else:
                    data = file_data[name]
                zout.writestr(name, data)
        tmp_out.replace(output_docx)


def _resolve_paths(thesis_dir: Path) -> None:
    """Rebind module-level paths to point at the provided thesis directory."""
    global ROOT, MAIN_TEX, CSL, BIB, FLAT_TEX, INTERMEDIATE_DOCX, OUTPUT_DOCX  # noqa: PLW0603

    ROOT = thesis_dir
    MAIN_TEX = ROOT / "main.tex"

    # Prefer project-local CSL; fallback to the copy bundled with this skill.
    default_csl = ROOT / "china-national-standard-gb-t-7714-2015-numeric.csl"
    if default_csl.exists():
        CSL = default_csl
    else:
        CSL = SCRIPT_DIR / "china-national-standard-gb-t-7714-2015-numeric.csl"

    BIB = Path(os.environ.get("SWUN_BIB", str(ROOT / "backmatter" / "references.bib"))).expanduser()

    FLAT_TEX = ROOT / ".main.flat.tex"
    INTERMEDIATE_DOCX = ROOT / ".main.pandoc.docx"
    OUTPUT_DOCX = ROOT / "main_版式1.docx"


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Default: use current working directory if it looks like a thesis root, else fallback.
    if argv:
        thesis_dir = Path(argv[0]).expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        thesis_dir = cwd if (cwd / "main.tex").exists() else Path("/Users/bit/LaTeX/SWUN_Thesis")

    _resolve_paths(thesis_dir)

    # Allow overriding CSL via env after we bind thesis dir (keeps old behavior).
    csl_override = os.environ.get("SWUN_CSL")
    if csl_override:
        global CSL  # noqa: PLW0603
        CSL = Path(csl_override).expanduser()

    for p in [TEMPLATE_DOCX, MAIN_TEX, CSL, BIB]:
        if not p.exists():
            raise SystemExit(f"missing required file: {p}")

    # Backup existing output.
    if OUTPUT_DOCX.exists():
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = OUTPUT_DOCX.with_suffix(f".docx.bak_{ts}")
        shutil.copy2(OUTPUT_DOCX, bak)

    # 1) latexpand -> flat tex
    # latexpand writes to stdout; capture ourselves to keep errors visible.
    flat = subprocess.run(
        ["latexpand", str(MAIN_TEX)],
        cwd=str(ROOT),
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode("utf-8", errors="ignore")

    flat = _preprocess_latex(flat)
    FLAT_TEX.write_text(flat, encoding="utf-8")
    caption_meta = _extract_caption_meta(flat)
    display_math_flags = _extract_display_math_number_flags(flat)
    cn_kw, en_kw = _extract_keywords(flat)
    latex_col_ratios = _parse_latex_table_col_specs(flat)

    # 2) pandoc -> intermediate docx
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
            '--metadata=reference-section-title:参考文献',
            '--resource-path=.:./media:./figures',
            f"-o",
            str(INTERMEDIATE_DOCX),
        ],
        cwd=ROOT,
    )

    # 3) OOXML postprocess -> final docx
    _postprocess_docx(
        INTERMEDIATE_DOCX,
        OUTPUT_DOCX,
        display_math_flags,
        cn_kw,
        en_kw,
        caption_meta,
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

    # Optional cleanup: keep FLAT_TEX for debugging, remove intermediate.
    if INTERMEDIATE_DOCX.exists():
        INTERMEDIATE_DOCX.unlink()
    if FLAT_TEX.exists():
        FLAT_TEX.unlink()

    print(f"OK: {OUTPUT_DOCX}")


if __name__ == "__main__":
    main()
