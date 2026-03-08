"""Text processing utilities for LaTeX."""
import re


_QUOTE_PAIR_RE = re.compile(r'(?P<open>["""])(?P<content>[^"\n""]+?)(?P<close>["""])')
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CJK_CONTEXT_RE = re.compile(r"[\u3000-\u303f\uff00-\uffef]")


def _nearest_non_space_left(text: str, start: int) -> str:
    idx = start - 1
    while idx >= 0 and text[idx].isspace():
        idx -= 1
    return text[idx] if idx >= 0 else ""


def _nearest_non_space_right(text: str, end: int) -> str:
    idx = end
    while idx < len(text) and text[idx].isspace():
        idx += 1
    return text[idx] if idx < len(text) else ""


def _is_chinese_quote_context(text: str, start: int, end: int, content: str) -> bool:
    if _CJK_RE.search(content):
        return True

    left = _nearest_non_space_left(text, start)
    right = _nearest_non_space_right(text, end)
    return bool(
        _CJK_RE.search(left)
        or _CJK_RE.search(right)
        or _CJK_CONTEXT_RE.search(left)
        or _CJK_CONTEXT_RE.search(right)
    )


def normalize_chinese_double_quotes(text: str) -> str:
    """Normalize quoted Chinese-context segments to paired Chinese quotes."""
    if not text:
        return text

    parts: list[str] = []
    last = 0
    changed = False

    for match in _QUOTE_PAIR_RE.finditer(text):
        start, end = match.span()
        content = match.group("content")
        parts.append(text[last:start])
        if _is_chinese_quote_context(text, start, end, content):
            parts.append(f"\u201c{content}\u201d")
            changed = True
        else:
            parts.append(match.group(0))
        last = end

    if not changed:
        return text

    parts.append(text[last:])
    return "".join(parts)


def preprocess_latex(s: str) -> str:
    """Preprocess LaTeX source for pandoc conversion.

    Args:
        s: LaTeX source string

    Returns:
        Preprocessed LaTeX string
    """
    # Pandoc LaTeX reader doesn't recognize \\< escape sequence
    s = s.replace("\\<", "<")

    # Let citeproc generate the references section
    s = re.sub(
        r"\\printbibliography\s*(\[[^\]]*\])?",
        "",
        s,
        flags=re.MULTILINE,
    )

    # Pandoc may drop titlepage env
    s = s.replace("\\begin{titlepage}", "")
    s = s.replace("\\end{titlepage}", "")

    # ulem's \\ul can get dropped
    s = re.sub(r"\\ul\{[^}]*\}", "__________", s)

    s = normalize_chinese_double_quotes(s)

    return s
