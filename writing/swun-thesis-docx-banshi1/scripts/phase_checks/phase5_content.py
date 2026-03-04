#!/usr/bin/env python3
"""Phase 5: 内容规范检查（新增）。

检查 DOCX 正文中的：
- 半角标点（正文段落中 , . : ; ( ) 应为全角）
- A + B 非正式连接残留
- 三线表边框（从 main.sh step 5 提取）
"""
from __future__ import annotations

import re
import sys
import zipfile
import xml.etree.ElementTree as ET


_HALFWIDTH_SKIP_PATTERNS = [
    re.compile(r"\d+\.\d+"),
    re.compile(r"[A-Za-z]\.[A-Za-z]"),
    re.compile(r"https?://"),
    re.compile(r"\[\d+\]"),
    re.compile(r"\(\d+[-–]\d+\)"),
    re.compile(r"[A-Za-z]+\([A-Za-z]"),
]

_HALFWIDTH_PUNCTS = {
    ",": "，",
    ".": "。",
    ":": "：",
    ";": "；",
    "(": "（",
    ")": "）",
}


def _iter_main_body_text(doc_xml: str) -> list[str]:
    """提取正文段落的纯文本列表。"""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    root = ET.fromstring(doc_xml)
    body = root.find("w:body", ns)
    if body is None:
        return []

    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}
    heading_styles = {"1", "2", "3", "4", "5", "Heading1", "Heading2", "Heading3", "Heading4", "Heading5"}
    in_main = False
    texts: list[str] = []

    for el in list(body):
        if el.tag != f"{{{ns['w']}}}p":
            continue
        p_style = el.find("w:pPr/w:pStyle", ns)
        style_val = p_style.get(f"{{{ns['w']}}}val") if p_style is not None else None
        p_txt = "".join((t.text or "") for t in el.findall(".//w:t", ns)).strip()

        if style_val == "1":
            if p_txt in stop_h1:
                in_main = False
            elif p_txt and p_txt not in excluded_h1:
                in_main = True

        if not in_main:
            continue
        if style_val in heading_styles:
            continue
        if p_txt:
            texts.append(p_txt)

    return texts


def _is_in_skip_context(text: str, pos: int, char: str) -> bool:
    """判断半角标点是否在可豁免的上下文中。"""
    window = text[max(0, pos - 10):pos + 11]
    for pat in _HALFWIDTH_SKIP_PATTERNS:
        if pat.search(window):
            return True
    if char in (".", ",") and pos > 0 and pos < len(text) - 1:
        prev_c = text[pos - 1]
        next_c = text[pos + 1] if pos + 1 < len(text) else ""
        if prev_c.isascii() and prev_c.isalpha() and next_c.isascii() and next_c.isalpha():
            return True
    return False


def _check_halfwidth_punctuation(texts: list[str]) -> list[str]:
    """检测正文中的半角标点。"""
    errors: list[str] = []
    found_count = 0
    for text in texts:
        for i, c in enumerate(text):
            if c not in _HALFWIDTH_PUNCTS:
                continue
            if _is_in_skip_context(text, i, c):
                continue
            found_count += 1
            if found_count <= 3:
                snippet = text[max(0, i - 15):i + 16]
                errors.append(f"半角标点 '{c}' (应为 '{_HALFWIDTH_PUNCTS[c]}') in: ...{snippet}...")
    if found_count > 3:
        errors.append(f"（共发现 {found_count} 处半角标点，仅展示前 3 处）")
    return errors


def _check_plus_connector(texts: list[str]) -> list[str]:
    """检测 A + B 非正式连接残留。"""
    errors: list[str] = []
    pat = re.compile(r"[\u4e00-\u9fff]\s*\+\s*[\u4e00-\u9fff]")
    for text in texts:
        m = pat.search(text)
        if m:
            snippet = text[max(0, m.start() - 10):m.end() + 10]
            errors.append(f"非正式 '+' 连接: ...{snippet}...")
    return errors


def _check_three_line_tables(doc_xml: str) -> list[str]:
    """检查三线表边框（从 main.sh step 5 提取核心逻辑）。"""
    errors: list[str] = []
    tables = re.findall(r"(<w:tbl[\s\S]*?</w:tbl>)", doc_xml)
    data_tables = [t for t in tables if "<w:tblCaption" in t]

    for idx, t in enumerate(data_tables, 1):
        m = re.search(r"(<w:tblBorders[\s\S]*?</w:tblBorders>)", t)
        if not m:
            errors.append(f"数据表 #{idx} 缺少 w:tblBorders（应为三线表）")
            continue
        b = m.group(1)
        need = [
            'w:top w:val="single"',
            'w:bottom w:val="single"',
            'w:left w:val="nil"',
            'w:right w:val="nil"',
            'w:insideH w:val="nil"',
            'w:insideV w:val="nil"',
        ]
        missing = [x for x in need if x not in b]
        if missing:
            errors.append(f"数据表 #{idx} 边框不符合三线表: missing {', '.join(missing)}")

    return errors


def run(docx_path: str) -> list[str]:
    """运行 Phase 5 检查，返回错误列表。"""
    with zipfile.ZipFile(docx_path, "r") as zf:
        doc = zf.read("word/document.xml").decode("utf-8", errors="ignore")

    errors: list[str] = []
    texts = _iter_main_body_text(doc)

    errors.extend(_check_halfwidth_punctuation(texts))
    errors.extend(_check_plus_connector(texts))
    errors.extend(_check_three_line_tables(doc))

    return errors


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: phase5_content.py /path/to/main_版式1.docx", file=sys.stderr)
        sys.exit(2)
    errors = run(sys.argv[1])
    if errors:
        print("PHASE 5 (内容规范): FAIL")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("PHASE 5 (内容规范): PASS")
