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


# ==================== 中文排版空格规范化 ====================

_CN_PUNCT = re.compile(r"[。，；：！？、\u201c\u201d\u2018\u2019）】》]")
_CN_CHAR = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_EN_CHAR = re.compile(r"[A-Za-z0-9\)\]\>）】》]")
_EN_LEFT = re.compile(r"[A-Za-z0-9\(\[\<（【《]")

def normalize_chinese_spaces(text: str) -> str:
    """移除中文排版中不应出现的空格。

    规则：
    1. 中文标点（。，；：！？等）后面紧跟的空格 → 删除
    2. 英文字符/右括号后 + 空格 + 中文字符 → 删除空格
    3. 中文字符后 + 空格 + 英文字母/左括号 → 删除空格

    保留：
    - 英文单词间的空格
    - 章节编号与标题间的空格（如"第1章 绪论"、"1.1 研究背景"）
    - 日期格式中的空格（如"2026 年 6 月"）
    """
    if not text or " " not in text:
        return text

    result = []
    i = 0
    while i < len(text):
        if text[i] == " ":
            # 查找空格前后的非空字符
            left = text[i - 1] if i > 0 else ""
            # 跳过连续空格
            j = i
            while j < len(text) and text[j] == " ":
                j += 1
            right = text[j] if j < len(text) else ""

            # 规则1: 中文标点后的空格
            if _CN_PUNCT.match(left):
                i = j
                continue

            # 规则2: 英文字符后 + 中文字符前
            if _EN_CHAR.match(left) and _CN_CHAR.match(right):
                # 排除：日期格式 "6 月"、"10 日" 等
                # 检查是否是 数字+年/月/日
                if re.match(r"\d", left) and right in "年月日时分秒":
                    result.append(" ")
                    i = j
                    continue
                i = j
                continue

            # 规则3: 中文字符后 + 英文字母/左括号前
            if _CN_CHAR.match(left) and _EN_LEFT.match(right):
                # 排除：日期格式 "年 6"、"月 10" 等
                if left in "年月日时分秒" and re.match(r"\d", right):
                    result.append(" ")
                    i = j
                    continue
                i = j
                continue

            # 其他情况保留空格（如英文间空格）
            result.append(text[i])
            i += 1
        else:
            result.append(text[i])
            i += 1

    return "".join(result)
