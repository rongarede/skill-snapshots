#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LaTeX 预处理与元数据提取模块。

从 docx_builder.py 提取，供 DOCX 构建管线和其他工具复用。
"""

from __future__ import annotations

import copy  # noqa: F401  保留供外部可能的 import
import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from modules.caption_profile import (
        CaptionFormatProfile,
        extract_caption_profiles,
    )
except ModuleNotFoundError:  # pragma: no cover
    from scripts.modules.caption_profile import (
        CaptionFormatProfile,
        extract_caption_profiles,
    )

try:
    from utils.text_utils import normalize_chinese_double_quotes
except ModuleNotFoundError:  # pragma: no cover
    from scripts.utils.text_utils import normalize_chinese_double_quotes

# ---------------------------------------------------------------------------
# 全局常量（与 docx_builder.py 共享路径约定）
# ---------------------------------------------------------------------------

ROOT = Path("/Users/bit/LaTeX/SWUN_Thesis")

CAPTION_PROFILE_DOCX = Path(
    os.environ.get(
        "SWUN_CAPTION_PROFILE_DOCX",
        "/Users/bit/LaTeX/SWUN_Thesis/网络与信息安全_高春琴.docx",
    )
).expanduser()

# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

_DEFAULT_CAPTION_PROFILES: dict[str, CaptionFormatProfile] | None = None


@dataclass
class CaptionMeta:
    kind: str  # "figure" | "table"
    label: str
    cn_title: str
    en_title: str | None
    source: str  # "bilingualcaption" | "caption"


# ---------------------------------------------------------------------------
# Caption profile 加载
# ---------------------------------------------------------------------------

def load_caption_profiles(profile_docx: Path) -> dict[str, CaptionFormatProfile]:
    try:
        return extract_caption_profiles(profile_docx)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"missing caption profile source: {profile_docx} "
            "(override with SWUN_CAPTION_PROFILE_DOCX)"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"failed to extract caption profile from {profile_docx}: {exc}"
        ) from exc


def default_caption_profiles() -> dict[str, CaptionFormatProfile]:
    global _DEFAULT_CAPTION_PROFILES  # noqa: PLW0603
    if _DEFAULT_CAPTION_PROFILES is None:
        _DEFAULT_CAPTION_PROFILES = load_caption_profiles(CAPTION_PROFILE_DOCX)
    return _DEFAULT_CAPTION_PROFILES


def infer_caption_kind(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith(("表", "Table")):
        return "table"
    return "figure"


# ---------------------------------------------------------------------------
# 跨引用解析：解析 main.aux，将 \ref/\eqref 替换为已解析编号
# ---------------------------------------------------------------------------

def parse_aux_labels(aux_path: Path) -> dict[str, str]:
    """解析 main.aux，返回 {label: number}（alg:/eq:/tab:/fig:/sec: 前缀）。"""
    if not aux_path.exists():
        return {}
    text = aux_path.read_text(encoding="utf-8", errors="ignore")
    labels: dict[str, str] = {}
    for m in re.finditer(
        r"\\newlabel\{((?:alg|eq|tab|fig|sec):[^}]+)\}\{\{([^}]+)\}", text
    ):
        labels[m.group(1)] = m.group(2)
    return labels


def resolve_latex_refs(s: str, labels: dict[str, str]) -> str:
    """将 \\ref{alg/eq/tab/fig/sec:...} 和 \\eqref{eq:...} 替换为已解析文本。

    - \\eqref{eq:X} → (4-2)
    - \\ref{eq:X}   → (4-2)
    - \\ref{alg:X}  → 2
    - \\ref{tab:X}  → 3-4
    - \\ref{fig:X}  → 3-1
    - \\ref{sec:X}  → 2.2.4
    前置波浪线会被消耗以避免多余空格。
    """
    if not labels:
        return s

    def _eq_num(raw: str) -> str:
        """'4.2' → '4-2'（DOCX 连字符约定）。"""
        return raw.replace(".", "-")

    def _repl_eqref(m: re.Match) -> str:
        label = m.group(1)
        num = labels.get(label)
        if num is None:
            return m.group(0)
        return f"({_eq_num(num)})"

    def _repl_ref(m: re.Match) -> str:
        label = m.group(1)
        num = labels.get(label)
        if num is None:
            return m.group(0)
        if label.startswith("eq:"):
            return f"({_eq_num(num)})"
        return num

    s = re.sub(r"~?\\eqref\{(eq:[^}]+)\}", _repl_eqref, s)
    s = re.sub(
        r"~?\\ref\{((?:alg|eq|tab|fig|sec):[^}]+)\}", _repl_ref, s
    )
    return s


# ---------------------------------------------------------------------------
# Algorithm 环境转换为 pandoc 友好的纯文本
# ---------------------------------------------------------------------------

def convert_algorithms_to_plain_text(s: str) -> str:
    """将 \\begin{algorithm}...\\end{algorithm} 转换为 pandoc 可识别的纯文本段落。"""
    alg_re = re.compile(
        r"\\begin\{algorithm\}[^\n]*\n(.*?)\\end\{algorithm\}",
        re.DOTALL,
    )
    alg_counter = 0

    def _parse_algorithmic_body(body: str) -> list[tuple[int, int, str]]:
        """返回 (line_number, indent_level, text) 列表。"""
        lines: list[tuple[int, int, str]] = []
        indent = 0
        num = 0

        def _strip_comment(t: str) -> str:
            return re.sub(r"\\COMMENT\{([^}]*)\}", r"  ▷ \1", t)

        for raw in body.strip().splitlines():
            raw = raw.strip()
            if not raw:
                continue

            m = re.match(r"\\REQUIRE\s+(.*)", raw)
            if m:
                lines.append((0, 0, "\\textbf{输入：}" + _strip_comment(m.group(1).strip())))
                continue
            m = re.match(r"\\ENSURE\s+(.*)", raw)
            if m:
                lines.append((0, 0, "\\textbf{输出：}" + _strip_comment(m.group(1).strip())))
                continue

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

            m = re.match(r"\\ELSIF\{(.*)\}", raw)
            if m:
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{else if} " + m.group(1).strip() + " \\textbf{then}"))
                indent += 1
                continue

            if re.match(r"\\ELSE\b", raw):
                indent = max(0, indent - 1)
                num += 1
                lines.append((num, indent, "\\textbf{else}"))
                indent += 1
                continue

            m = re.match(r"\\IF\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{if} " + m.group(1).strip() + " \\textbf{then}"))
                indent += 1
                continue

            m = re.match(r"\\FOR\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{for} " + m.group(1).strip() + " \\textbf{do}"))
                indent += 1
                continue

            m = re.match(r"\\WHILE\{(.*)\}", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{while} " + m.group(1).strip() + " \\textbf{do}"))
                indent += 1
                continue

            m = re.match(r"\\RETURN\s+(.*)", raw)
            if m:
                num += 1
                lines.append((num, indent, "\\textbf{return} " + _strip_comment(m.group(1).strip())))
                continue

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

        cap_m = re.search(r"\\caption\{([^}]*)\}", block)
        caption = cap_m.group(1) if cap_m else f"算法 {alg_counter}"

        lab_m = re.search(r"\\label\{([^}]*)\}", block)
        label_str = f"\\label{{{lab_m.group(1)}}}" if lab_m else ""

        alg_m = re.search(
            r"\\begin\{algorithmic\}[^\n]*\n(.*?)\\end\{algorithmic\}",
            block, re.DOTALL
        )
        if not alg_m:
            return m.group(0)

        parsed = _parse_algorithmic_body(alg_m.group(1))

        out = []
        out.append("")
        out.append(f"\\textbf{{算法 {alg_counter}}} {caption}{label_str}")
        out.append("")
        out.append("\\noindent\\rule{\\textwidth}{0.4pt}")
        out.append("")

        for num, indent, text in parsed:
            indent_marker = f"\u230AN\u230B".replace("N", str(indent))
            if num == 0:
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


# ---------------------------------------------------------------------------
# tabularx 自定义列类型展开
# ---------------------------------------------------------------------------

def expand_custom_column_types(s: str) -> str:
    """将 tabularx 列规格中的自定义列类型 Y 替换为 X。"""
    nc_marker = "\\newcolumntype{Y}"
    nc_idx = s.find(nc_marker)
    if nc_idx >= 0:
        end = nc_idx + len(nc_marker)
        depth = 0
        while end < len(s):
            if s[end] == "{":
                depth += 1
            elif s[end] == "}":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1
        s = s[:nc_idx] + s[end:]

    MARKER = "begin{tabularx}"
    result_parts: list[str] = []
    pos = 0

    while True:
        idx = s.find(MARKER, pos)
        if idx < 0:
            break
        cursor = idx + len(MARKER)

        if cursor >= len(s) or s[cursor] != "{":
            result_parts.append(s[pos:cursor])
            pos = cursor
            continue
        depth = 1
        i = cursor + 1
        while i < len(s) and depth > 0:
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
            i += 1
        if depth != 0:
            result_parts.append(s[pos:i])
            pos = i
            continue
        cursor = i

        if cursor >= len(s) or s[cursor] != "{":
            result_parts.append(s[pos:cursor])
            pos = cursor
            continue
        col_start = cursor + 1
        depth = 1
        i = col_start
        while i < len(s) and depth > 0:
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
            i += 1
        if depth != 0:
            result_parts.append(s[pos:i])
            pos = i
            continue
        col_end = i

        colspec = s[col_start:col_end - 1]
        new_colspec = colspec.replace("Y", "X")
        result_parts.append(s[pos:col_start])
        result_parts.append(new_colspec)
        result_parts.append("}")
        pos = col_end

    result_parts.append(s[pos:])
    return "".join(result_parts)


# ---------------------------------------------------------------------------
# 主预处理入口
# ---------------------------------------------------------------------------

def preprocess_latex(s: str) -> str:
    """对 flattened LaTeX 源码进行 DOCX 构建前预处理。"""
    s = s.replace("\\<", "<")

    s = re.sub(
        r"\\printbibliography\s*(\[[^\]]*\])?",
        "",
        s,
        flags=re.MULTILINE,
    )

    s = s.replace("\\begin{titlepage}", "")
    s = s.replace("\\end{titlepage}", "")

    s = re.sub(r"\\ul\\{[^}]*\\}", "__________", s)

    s = re.sub(
        r"(\\[bp]?mod)\s+([A-Za-z])\s*\n",
        r"\1{\2}\n",
        s,
    )

    aux_path = ROOT / "main.aux"
    labels = parse_aux_labels(aux_path)
    if labels:
        s = resolve_latex_refs(s, labels)

    s = convert_algorithms_to_plain_text(s)

    s = expand_custom_column_types(s)

    s = expand_if_file_exists(s)

    s = flatten_subfigures(s)
    s = prefer_png_for_docx_images(s)
    unresolved = find_unresolved_pdf_experiment_refs(s)
    if unresolved:
        lines = "\n".join(f"  - {p}" for p in unresolved)
        raise RuntimeError(
            "DOCX build blocked: experiment figures must use PNG, "
            "but some includegraphics still point to PDF and no PNG fallback was found:\n"
            f"{lines}"
        )

    s = normalize_chinese_double_quotes(s)

    return s


# ---------------------------------------------------------------------------
# 实验图路径检测与 PDF 引用检查
# ---------------------------------------------------------------------------

def is_experiment_figure_path(path: str) -> bool:
    p = path.strip()
    return (
        p.startswith("experiments/ch3_v2/results/figures/")
        or p.startswith("figures/ch4/")
        or "/fig_3_" in p
        or "/fig_4_" in p
    )


def find_unresolved_pdf_experiment_refs(s: str) -> list[str]:
    pat = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}")
    unresolved: list[str] = []
    for m in pat.finditer(s):
        p = m.group(1).strip()
        if is_experiment_figure_path(p) and p.lower().endswith(".pdf"):
            unresolved.append(p)
    seen = set()
    out = []
    for p in unresolved:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# \IfFileExists 展开
# ---------------------------------------------------------------------------

def expand_if_file_exists(s: str) -> str:
    """展开 \\IfFileExists{path}{true-branch}{false-branch}，使 pandoc 能识别其中的图片。"""

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
        return None

    result = []
    i = 0
    pattern = r"\\IfFileExists\s*"
    compiled = re.compile(pattern)

    while i < len(s):
        m = compiled.search(s, i)
        if m is None:
            result.append(s[i:])
            break

        result.append(s[i : m.start()])

        pos = m.end()
        r1 = _read_brace_group(s, pos)
        if r1 is None:
            result.append(s[m.start()])
            i = m.start() + 1
            continue
        file_path_arg, pos = r1

        r2 = _read_brace_group(s, pos)
        if r2 is None:
            result.append(s[m.start()])
            i = m.start() + 1
            continue
        true_branch, pos = r2

        while pos < len(s) and s[pos] in (" ", "\t", "\n", "%"):
            if s[pos] == "%":
                while pos < len(s) and s[pos] != "\n":
                    pos += 1
            else:
                pos += 1

        r3 = _read_brace_group(s, pos)
        if r3 is not None:
            false_branch, pos = r3
        else:
            false_branch = ""

        fp = file_path_arg.strip()
        png_fp = str(Path(fp).with_suffix(".png"))
        if (ROOT / png_fp).exists() or (ROOT / fp).exists():
            result.append(true_branch)
        else:
            result.append(false_branch)

        i = pos

    return "".join(result)


# ---------------------------------------------------------------------------
# PNG 优先替换
# ---------------------------------------------------------------------------

def prefer_png_for_docx_images(s: str) -> str:
    """在 DOCX 构建阶段优先将 includegraphics 的 PDF 路径替换为 PNG。"""

    def _pick_png_path(raw_path: str) -> str | None:
        p = Path(raw_path.strip())
        if p.suffix.lower() != ".pdf":
            return None

        candidates = [p.with_suffix(".png")]
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


# ---------------------------------------------------------------------------
# LaTeX 注释剥除
# ---------------------------------------------------------------------------

def strip_latex_comments(s: str) -> str:
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


# ---------------------------------------------------------------------------
# LaTeX 底层解析工具
# ---------------------------------------------------------------------------

def skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def read_balanced(s: str, i: int, open_ch: str, close_ch: str) -> tuple[str, int] | None:
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


def extract_command_args(text: str, cmd: str, nargs: int) -> list[str] | None:
    pat = re.compile(rf"\\{re.escape(cmd)}(?![A-Za-z])")
    for m in pat.finditer(text):
        i = m.end()
        while True:
            i = skip_ws(text, i)
            if i < len(text) and text[i] == "[":
                got = read_balanced(text, i, "[", "]")
                if got is None:
                    break
                _, i = got
                continue
            break

        args: list[str] = []
        ok = True
        for _ in range(nargs):
            i = skip_ws(text, i)
            got = read_balanced(text, i, "{", "}")
            if got is None:
                ok = False
                break
            val, i = got
            args.append(re.sub(r"\s+", " ", val).strip())
        if ok:
            return args
    return None


# ---------------------------------------------------------------------------
# 元数据提取
# ---------------------------------------------------------------------------

def extract_caption_meta(flat_tex: str) -> dict[str, CaptionMeta]:
    """从 flattened LaTeX 提取图/表 caption 元数据，键为 label。"""
    s = strip_latex_comments(flat_tex)
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

        label_args = extract_command_args(block, "label", 1)
        label = label_args[0].strip() if label_args else ""
        bi = extract_command_args(block, "bilingualcaption", 2)
        cap = extract_command_args(block, "caption", 1) if bi is None else None

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


def parse_latex_table_col_specs(latex_src: str) -> dict[str, list[float]]:
    """从 flattened LaTeX 源码解析每个带 label 的表格的列宽比例。

    返回 ``{label: [ratio, ...]}``，仅包含有显式宽度（``p{...}`` 或 ``X``）的表格。

    特殊值约定：
    - ``float > 0``：显式比例
    - ``-1.0``：tabularX 的 ``X`` 列
    - ``0.0``：自动列（``l/c/r``）
    """
    LINEWIDTH_CM = 15.0

    src = strip_latex_comments(latex_src)
    result: dict[str, list[float]] = {}

    table_env_re = re.compile(
        r"\\begin\{table\*?\}.*?\\end\{table\*?\}", re.DOTALL
    )
    tabular_begin_re = re.compile(r"\\begin\{tabular\}")
    tabularx_begin_re = re.compile(r"\\begin\{tabularx\}")
    label_re = re.compile(r"\\label\{(tab:[^}]+)\}")

    def _parse_colspec(spec: str, is_tabularx: bool) -> list[float] | None:
        cols: list[float] = []
        i = 0
        while i < len(spec):
            ch = spec[i]
            if ch in "lcr":
                cols.append(0.0)
                i += 1
            elif ch in "XY" and is_tabularx:
                cols.append(-1.0)
                i += 1
            elif ch == "p" and i + 1 < len(spec) and spec[i + 1] == "{":
                got = read_balanced(spec, i + 1, "{", "}")
                if got is None:
                    i += 1
                    continue
                width_str, i = got
                ratio = parse_width_to_ratio(width_str, LINEWIDTH_CM)
                cols.append(ratio if ratio is not None else 0.0)
            elif ch in "|@!>< {}":
                i += 1
            else:
                i += 1
        if not cols:
            return None
        if all(c == 0.0 for c in cols):
            return None
        return cols

    for m in table_env_re.finditer(src):
        block = m.group(0)
        label_m = label_re.search(block)
        if label_m is None:
            continue
        label = label_m.group(1)

        colspec_str: str | None = None
        is_tabularx = False
        tx_m = tabularx_begin_re.search(block)
        t_m = tabular_begin_re.search(block)
        if tx_m is not None:
            is_tabularx = True
            pos = tx_m.end()
            got = read_balanced(block, pos, "{", "}")
            if got is None:
                continue
            _, pos = got
            got = read_balanced(block, pos, "{", "}")
            if got is None:
                continue
            colspec_str, _ = got
        elif t_m is not None:
            pos = t_m.end()
            got = read_balanced(block, pos, "{", "}")
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


def parse_width_to_ratio(width_str: str, linewidth_cm: float) -> float | None:
    """将 LaTeX 宽度定义转换为 \\linewidth 比例。"""
    s = width_str.strip()
    m = re.match(r"([\d.]+)\s*\\(?:linewidth|textwidth)", s)
    if m:
        return float(m.group(1))
    m = re.match(r"([\d.]+)\s*cm", s)
    if m:
        return float(m.group(1)) / linewidth_cm
    m = re.match(r"([\d.]+)\s*mm", s)
    if m:
        return float(m.group(1)) / 10.0 / linewidth_cm
    m = re.match(r"([\d.]+)\s*in", s)
    if m:
        return float(m.group(1)) * 2.54 / linewidth_cm
    return None


# ---------------------------------------------------------------------------
# subfigure 展平
# ---------------------------------------------------------------------------

def flatten_subfigures(s: str) -> str:
    """将 subfigure \\ref 替换为父图 \\ref，并剥除 subfigure 内部的 caption/label。"""
    subfig_to_parent: dict[str, str] = {}

    fig_re = re.compile(
        r"\\begin\{figure\}.*?\\end\{figure\}", re.DOTALL
    )
    subfig_label_re = re.compile(
        r"\\begin\{subfigure\}.*?\\label\{([^}]+)\}.*?\\end\{subfigure\}", re.DOTALL
    )
    parent_label_re = re.compile(r"\\label\{([^}]+)\}")

    for fig_m in fig_re.finditer(s):
        fig_block = fig_m.group(0)
        sub_labels = [m.group(1) for m in subfig_label_re.finditer(fig_block)]
        if not sub_labels:
            continue

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

    for sub_lbl, par_lbl in subfig_to_parent.items():
        s = s.replace(f"\\ref{{{sub_lbl}}}", f"\\ref{{{par_lbl}}}")

    def _strip_subfig_internals(m: re.Match) -> str:
        block = m.group(0)
        block = re.sub(r"\\caption\{[^}]*\}\s*", "", block)
        block = re.sub(r"\\label\{[^}]*\}\s*", "", block)
        return block

    s = re.sub(
        r"\\begin\{subfigure\}.*?\\end\{subfigure\}",
        _strip_subfig_internals,
        s,
        flags=re.DOTALL,
    )

    s = re.sub(r"\\begin\{subfigure\}(\[[^\]]*\])?\{[^}]*\}", "", s)
    s = re.sub(r"\\end\{subfigure\}", "", s)

    s = re.sub(
        r"(图[~\s]*)\\ref\{([^}]+)\}\s*[与和及]\s*图[~\s]*\\ref\{\2\}",
        r"\1\\ref{\2}",
        s,
    )

    return s


# ---------------------------------------------------------------------------
# 数学公式编号标志提取
# ---------------------------------------------------------------------------

def extract_display_math_number_flags(latex: str) -> list[bool]:
    """
    返回与 pandoc display-math 段落顺序对齐的序列。

    - 有编号：equation/align/gather/multline（无 * 后缀）
    - 无编号：星号变体和 \\[ ... \\] 块
    """
    blocks: list[tuple[int, bool]] = []

    env_re = re.compile(
        r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}[\s\S]*?\\end\{\1\}"
    )
    for m in env_re.finditer(latex):
        env = m.group(1)
        blocks.append((m.start(), not env.endswith("*")))

    br_re = re.compile(r"(?<!\\)\\\[[\s\S]*?\\\]")
    for m in br_re.finditer(latex):
        blocks.append((m.start(), False))

    blocks.sort(key=lambda x: x[0])
    return [b for _, b in blocks]


# ---------------------------------------------------------------------------
# 关键词提取与分组
# ---------------------------------------------------------------------------

def extract_keywords(latex: str) -> tuple[str | None, str | None]:
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


def split_keywords(raw: str, max_groups: int = 4, lang: str = "cn") -> str:
    """
    将关键词分为 3-4 组（默认最多 4 组），不丢失信息。

    超出 max_groups 时，将末尾分组合并。
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


# ---------------------------------------------------------------------------
# 下划线别名（向后兼容 docx_builder.py 内部调用）
# ---------------------------------------------------------------------------

_load_caption_profiles = load_caption_profiles
_default_caption_profiles = default_caption_profiles
_infer_caption_kind = infer_caption_kind
_parse_aux_labels = parse_aux_labels
_resolve_latex_refs = resolve_latex_refs
_convert_algorithms_to_plain_text = convert_algorithms_to_plain_text
_expand_custom_column_types = expand_custom_column_types
_preprocess_latex = preprocess_latex
_is_experiment_figure_path = is_experiment_figure_path
_find_unresolved_pdf_experiment_refs = find_unresolved_pdf_experiment_refs
_expand_if_file_exists = expand_if_file_exists
_prefer_png_for_docx_images = prefer_png_for_docx_images
_strip_latex_comments = strip_latex_comments
_skip_ws = skip_ws
_read_balanced = read_balanced
_extract_command_args = extract_command_args
_extract_caption_meta = extract_caption_meta
_parse_latex_table_col_specs = parse_latex_table_col_specs
_parse_width_to_ratio = parse_width_to_ratio
_flatten_subfigures = flatten_subfigures
_extract_display_math_number_flags = extract_display_math_number_flags
_extract_keywords = extract_keywords
_split_keywords = split_keywords


__all__ = [
    # 数据类
    "CaptionMeta",
    # caption profile
    "load_caption_profiles",
    "default_caption_profiles",
    "infer_caption_kind",
    # 跨引用
    "parse_aux_labels",
    "resolve_latex_refs",
    # 预处理子函数
    "convert_algorithms_to_plain_text",
    "expand_custom_column_types",
    "expand_if_file_exists",
    "flatten_subfigures",
    "prefer_png_for_docx_images",
    "strip_latex_comments",
    # 底层解析
    "skip_ws",
    "read_balanced",
    "extract_command_args",
    # 元数据提取
    "extract_caption_meta",
    "parse_latex_table_col_specs",
    "parse_width_to_ratio",
    "extract_display_math_number_flags",
    "extract_keywords",
    "split_keywords",
    # 实验图检测
    "is_experiment_figure_path",
    "find_unresolved_pdf_experiment_refs",
    # 主入口
    "preprocess_latex",
]
