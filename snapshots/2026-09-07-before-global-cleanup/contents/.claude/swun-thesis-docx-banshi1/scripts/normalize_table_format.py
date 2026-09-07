#!/usr/bin/env python3
"""
SWUN 论文 DOCX 格式规约（独立后处理脚本）

目标：在 build_docx_banshi1 输出的 main_版式1.docx 上执行：
  ⭐⭐⭐ 表格列宽再分配：等宽数字列 + 最小列宽保护（≥1.3cm）+ 首列含标题列 ≥2.6cm
  ⭐⭐⭐ 表格表头行加粗（所有 run 加 w:b / w:bCs）
  ⭐⭐⭐ 参考文献区段落 keepLines（每条文献整段不跨页）

判定"真数据表"：表前 1-3 段 paragraph 含 `表X-Y` 模式。
判定"参考文献区"：从含"参考文献"的 Heading1 段开始，到含"致谢"或"攻读"的下一 Heading1 之前结束。

用法：
  python3 normalize_table_format.py /path/to/main_版式1.docx
  # 默认原地写回（同时备份 .bak.前序时间戳）
"""
from __future__ import annotations

import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

from lxml import etree as ET  # type: ignore

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + NS + "}"
NSE = {"w": NS}

# 单位换算
TWIPS_PER_CM = 567

# 配置
MIN_COL_WIDTH = int(1.3 * TWIPS_PER_CM)         # 1.3 cm = ~737 twips
MIN_LABEL_COL_WIDTH = int(2.6 * TWIPS_PER_CM)   # 2.6 cm = ~1474 twips（首列含中文标题）

NUMERIC_RE = re.compile(r"^[\s\d.\-+%/×\(\)（）]*$")  # 数字/百分号/区间/连字符
PCT_RE = re.compile(r"\d+\.?\d*\s*%?$")


def get_para_text(p: ET.Element) -> str:
    return "".join(t.text or "" for t in p.iter(f"{W}t"))


def has_chinese(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def is_numeric_column(col_texts: list[str]) -> bool:
    """全列内容（除表头）皆数字/百分号 → 数字列。"""
    if not col_texts:
        return False
    non_empty = [t.strip() for t in col_texts if t.strip()]
    if not non_empty:
        return False
    numeric_cnt = sum(1 for t in non_empty if NUMERIC_RE.match(t))
    return numeric_cnt / len(non_empty) >= 0.7


CAPTION_RE_CN = re.compile(r"^表\s*\d+-\d")
CAPTION_RE_EN = re.compile(r"^Table\s*\d+-\d", re.IGNORECASE)


def is_table_caption(txt: str) -> bool:
    """中英文表标题任一匹配。"""
    return bool(CAPTION_RE_CN.match(txt) or CAPTION_RE_EN.match(txt))


def find_data_tables(body: ET.Element) -> list[tuple[int, ET.Element, str]]:
    """返回 [(pos, tbl, caption), ...]，仅含 caption 形如 "表X-Y" / "Table X-Y" 的真数据表。

    向上扫描表前 6 段：跳过 bookmarkStart / 空段 / 英文 caption，遇到中文 caption 即记录；
    若仅找到英文 caption，也视为真数据表。
    """
    paras = list(body)
    out = []
    for i, e in enumerate(paras):
        if e.tag != f"{W}tbl":
            continue
        cap_cn = ""
        cap_en = ""
        for j in range(i - 1, max(i - 7, -1), -1):
            ej = paras[j]
            tag = ej.tag.split("}")[-1]
            if tag != "p":
                # bookmarkStart 等非段元素跳过
                continue
            txt = get_para_text(ej).strip()
            if not txt:
                continue
            if CAPTION_RE_CN.match(txt):
                cap_cn = txt
                break
            if CAPTION_RE_EN.match(txt):
                cap_en = txt
                # 继续向上找中文 caption（中文通常在英文上一段）
                continue
            # 非 caption 非空段 → 已超出 caption 区域
            break
        cap = cap_cn or cap_en
        if cap:
            out.append((i, e, cap))
    return out


def collect_col_texts(tbl: ET.Element) -> tuple[list[list[str]], int]:
    """返回 (per_col_texts, n_rows)。per_col_texts[i] 是第 i 列除表头的所有单元格文本。"""
    rows = tbl.findall(f"{W}tr")
    if not rows:
        return [], 0
    n_cols = max(len(r.findall(f"{W}tc")) for r in rows)
    cols_texts: list[list[str]] = [[] for _ in range(n_cols)]
    # rows[0] 是表头，跳过
    for r in rows[1:]:
        cells = r.findall(f"{W}tc")
        for ci, c in enumerate(cells):
            if ci >= n_cols:
                continue
            txt = "".join(get_para_text(p) for p in c.findall(f"{W}p"))
            cols_texts[ci].append(txt)
    return cols_texts, len(rows)


def get_total_width(tbl: ET.Element) -> int:
    """读取表格总宽（dxa twips）。"""
    tblPr = tbl.find(f"{W}tblPr")
    if tblPr is None:
        return 0
    tblW = tblPr.find(f"{W}tblW")
    if tblW is None:
        return 0
    return int(tblW.get(f"{W}w", 0))


def get_header_texts(tbl: ET.Element) -> list[str]:
    """返回表头行各列文本。"""
    rows = tbl.findall(f"{W}tr")
    if not rows:
        return []
    header_cells = rows[0].findall(f"{W}tc")
    return ["".join(get_para_text(p) for p in c.findall(f"{W}p")) for c in header_cells]


def reallocate_columns(tbl: ET.Element) -> dict:
    """重新分配列宽，返回操作摘要。

    算法：
    1. 各列先分配最小列宽（标签列 ≥ MIN_LABEL_COL_WIDTH，其他 ≥ MIN_COL_WIDTH）
    2. 剩余空间按权重分配：
       - 标签列权重 = 1
       - 数字列权重 = 1（与其他数字列等宽）
       - 文字列权重 = max(1, max_chars / 6)（按字符数加权）
    3. 舍入差额给最大列吸收，永不破坏最小宽度
    """
    rows = tbl.findall(f"{W}tr")
    if not rows:
        return {"skipped": "no rows"}

    n_cols = max(len(r.findall(f"{W}tc")) for r in rows)
    if n_cols < 2:
        return {"skipped": "single column"}

    total = get_total_width(tbl)
    if total <= 0:
        return {"skipped": "total width missing"}

    cols_texts, _ = collect_col_texts(tbl)
    while len(cols_texts) < n_cols:
        cols_texts.append([])
    headers = get_header_texts(tbl)
    while len(headers) < n_cols:
        headers.append("")

    # 判别每列类型
    is_numeric = [is_numeric_column(c) for c in cols_texts]
    is_label = [(i == 0 and has_chinese(headers[0])) for i in range(n_cols)]

    # 各列最大字符数
    max_chars = []
    for i in range(n_cols):
        mc = max((len(t) for t in cols_texts[i]), default=0)
        mc = max(mc, len(headers[i]), 1)
        max_chars.append(mc)

    # Step 1: 最小列宽
    fixed_widths = [0] * n_cols
    for i in range(n_cols):
        if is_label[i]:
            fixed_widths[i] = MIN_LABEL_COL_WIDTH
        else:
            fixed_widths[i] = MIN_COL_WIDTH

    base_sum = sum(fixed_widths)
    if base_sum > total:
        # 总宽不够分最小列宽，等比缩放（兜底，不应触发）
        scale = total / base_sum
        fixed_widths = [int(w * scale) for w in fixed_widths]
        diff = total - sum(fixed_widths)
        max_i = max(range(n_cols), key=lambda i: fixed_widths[i])
        fixed_widths[max_i] += diff
        return {
            "n_cols": n_cols, "total": total, "widths": fixed_widths,
            "is_numeric": is_numeric, "is_label": is_label,
            "warning": "total width insufficient for min col widths",
        }

    # Step 2: 剩余按权重分配
    extra = total - base_sum
    weights = []
    for i in range(n_cols):
        if is_label[i]:
            weights.append(1.0)
        elif is_numeric[i]:
            weights.append(1.0)
        else:
            # 文字列按字符数 / 6 加权（中文每字 ~ 240 twips ≈ 字符 * 6 cm/字）
            weights.append(max(1.0, max_chars[i] / 6))
    total_w = sum(weights)
    for i in range(n_cols):
        fixed_widths[i] += int(extra * weights[i] / total_w)

    # Step 3: 舍入差给最大列吸收（不破坏最小宽度）
    diff = total - sum(fixed_widths)
    if diff != 0:
        max_i = max(range(n_cols), key=lambda i: fixed_widths[i])
        fixed_widths[max_i] += diff

    # 写回 tblGrid
    tblGrid = tbl.find(f"{W}tblGrid")
    if tblGrid is not None:
        for gc in list(tblGrid.findall(f"{W}gridCol")):
            tblGrid.remove(gc)
        for w in fixed_widths:
            gc = ET.SubElement(tblGrid, f"{W}gridCol")
            gc.set(f"{W}w", str(w))

    # 写回每行每列 tcW
    for r in rows:
        cells = r.findall(f"{W}tc")
        for ci, c in enumerate(cells):
            if ci >= n_cols:
                continue
            tcPr = c.find(f"{W}tcPr")
            if tcPr is None:
                tcPr = ET.SubElement(c, f"{W}tcPr")
                # 移到第一位
                c.remove(tcPr)
                c.insert(0, tcPr)
            tcW = tcPr.find(f"{W}tcW")
            if tcW is None:
                tcW = ET.SubElement(tcPr, f"{W}tcW")
            tcW.set(f"{W}type", "dxa")
            tcW.set(f"{W}w", str(fixed_widths[ci]))

    return {
        "n_cols": n_cols,
        "total": total,
        "widths": fixed_widths,
        "is_numeric": is_numeric,
        "is_label": is_label,
    }


REF_HEADING_RE = re.compile(r"^\s*参考文献\s*$")
REF_END_RE = re.compile(r"^\s*(致谢|攻读|科研成果|学位期间)")

# 匹配 ≥2 个连续大写字母的英文词（保留如 "M"、"A"、"B" 这类单字母缩写）
ALL_CAPS_WORD_RE = re.compile(r"\b([A-Z])([A-Z]+)\b")


def fix_reference_author_case(body: ET.Element) -> int:
    """把参考文献作者全大写姓氏转为首字母大写（按样文 GB/T 7714-2015 实践）。

    作者列表特征：
    - 段落以 [N] 编号开头
    - 紧随其后的 <w:t> 文本以 ≥2 大写字母词开头，且含逗号或句点
    - "ABBASI S, KHALEDIAN N, RAHMANI A M." → "Abbasi S, Khaledian N, Rahmani A M."

    保留：单字母缩写（M / B / A）、中文作者、专有名词大小写（不在此 <w:t> 内）。
    """
    paras = list(body)
    in_refs = False
    cnt = 0
    for p in paras:
        if p.tag != f"{W}p":
            continue
        txt = get_para_text(p).strip()
        if REF_HEADING_RE.match(txt):
            in_refs = True
            continue
        if in_refs and REF_END_RE.match(txt):
            break
        if not in_refs:
            continue
        if not re.match(r"^\s*\[\d+\]", txt):
            continue
        # 遍历段内 <w:t>，找首个匹配作者列表特征的节点（≥2 大写字母词起首，含 .）
        for t in p.iter(f"{W}t"):
            text = t.text or ""
            if not text:
                continue
            stripped = text.lstrip()
            if not stripped:
                continue
            # 必须以 ≥2 大写字母词起首
            if not re.match(r"^[A-Z]{2,}", stripped):
                continue
            # 找作者列表与标题分界：首个 ' [A-Z][a-z]' 位置（即标题首个 Title Case 词之前）
            # 形如 "CASTRO M, LISKOV B. Practical byzantine..." → 作者前缀 "CASTRO M, LISKOV B."
            m_split = re.search(r"\s[A-Z][a-z]", text)
            if m_split:
                head = text[: m_split.start()]
                tail = text[m_split.start():]
            else:
                head = text
                tail = ""
            # head 应是作者列表区：起首大写字母 + 不含"非作者特征"字符（数字/方括号/冒号/圆括号）
            head_strip = head.strip()
            if re.search(r"[\d\[\]:()]", head_strip):
                continue
            if not re.search(r"\b[A-Z]{2,}\b", head):
                continue
            new_head = ALL_CAPS_WORD_RE.sub(
                lambda m: m.group(1) + m.group(2).lower(), head
            )
            if new_head != head:
                t.text = new_head + tail
                cnt += 1
            break  # 每段只处理首个作者节点
    return cnt


def remove_all_hyperlinks(body: ET.Element) -> int:
    """彻底移除文档中所有 <w:hyperlink>，仅保留内部 run 文本。

    扫描整个 body：
    - 把每个 w:hyperlink 节点用其 children（runs）就地替换
    - 移除 run 中的 Hyperlink 字符样式（rStyle val="Hyperlink" / "22" 等）
    - 不区分内部 anchor / 外部 r:id，所有超链接均拆为纯文本
    """
    cnt = 0
    # 使用 lxml 的 findall 找所有 hyperlink
    hyperlinks = list(body.iter(f"{W}hyperlink"))
    for hl in hyperlinks:
        parent = hl.getparent()
        if parent is None:
            continue
        idx = list(parent).index(hl)
        # 取出 hyperlink 内所有 children（通常是 <w:r>），原位插入到 parent
        children = list(hl)
        for offset, child in enumerate(children):
            parent.insert(idx + offset, child)
        parent.remove(hl)
        cnt += 1

    # 进一步清理 hyperlink 字符样式（rStyle val 含 "Hyperlink"/"超链接"，常见 styleId 别名："a3"/"22" 等取决于 docx）
    for rPr in body.iter(f"{W}rPr"):
        rStyle = rPr.find(f"{W}rStyle")
        if rStyle is None:
            continue
        val = rStyle.get(f"{W}val", "")
        if val.lower() == "hyperlink" or val == "22":
            rPr.remove(rStyle)
        # 同时去除蓝色/下划线（可能是超链接残留样式）
        for tag in (f"{W}color", f"{W}u"):
            el = rPr.find(tag)
            if el is None:
                continue
            color_val = el.get(f"{W}val", "")
            if tag.endswith("}color") and color_val.lower() in ("0563c1", "0000ff", "0000ee"):
                rPr.remove(el)
            elif tag.endswith("}u") and el.get(f"{W}val", "") in ("single",):
                rPr.remove(el)
    return cnt


def _is_english_entry(full_text: str) -> bool:
    """判定参考文献条目是否为英文条目。

    作者部分含英文姓氏（≥3 字母 Title Case 词如 'Abbasi'）
    或 ≥3 字母全大写姓氏（如 'OLIVEIRA'，未经 case-fix 时）。
    允许 head 中含 '等' 等中文连接词（不排除中文字符）。
    """
    head = full_text.split(".", 1)[0] if "." in full_text else full_text
    return bool(
        re.search(r"\b[A-Z][a-z]{2,}\b", head)  # Title Case 词
        or re.search(r"\b[A-Z]{3,}\b", head)     # 全大写姓氏
    )


def fix_reference_et_al(body: ET.Element) -> int:
    """英文参考文献中 '等' → 'et al.'。"""
    paras = list(body)
    in_refs = False
    cnt = 0
    for p in paras:
        if p.tag != f"{W}p":
            continue
        full = get_para_text(p).strip()
        if REF_HEADING_RE.match(full):
            in_refs = True
            continue
        if in_refs and REF_END_RE.match(full):
            break
        if not in_refs:
            continue
        if not re.match(r"^\s*\[\d+\]", full):
            continue
        if not _is_english_entry(full):
            continue
        for t in p.iter(f"{W}t"):
            text = t.text or ""
            # 仅替换独立 "等"（前后非中文字符）
            if "等" in text:
                # 替换为 et al，保留前后空格/标点
                new = re.sub(r"等(?=\s*[\.,])", "et al", text)
                new = re.sub(r"\s*等\s*$", " et al", new)
                if new != text:
                    t.text = new
                    cnt += 1
    return cnt


# Title Case → sentence case 转换辅助
TC_WORD_RE = re.compile(r"\b[A-Z][a-z]+\b")


def _to_sentence_case(text: str) -> str:
    """把 Title Case 词转小写，保留全大写缩写（≥2 字母全大写）和单字母。"""
    return TC_WORD_RE.sub(lambda m: m.group(0).lower(), text)


def fix_reference_title_case(body: ET.Element) -> int:
    """英文参考文献标题 Title Case → sentence case。

    策略：
    - 拼接段落所有 <w:t> 文本（及其偏移）得到 full
    - 找标题区间：作者结尾 '. ' 之后到 '[J]/[C]/[D]/[M]/[R]/[N]/[P]/[A]/[Z]' 类型标识之前
    - 标题首词保留首字母大写，其余 Title Case 词转小写
    - 长度不变，分配回各 <w:t>
    """
    paras = list(body)
    in_refs = False
    cnt = 0
    for p in paras:
        if p.tag != f"{W}p":
            continue
        full_strip = get_para_text(p).strip()
        if REF_HEADING_RE.match(full_strip):
            in_refs = True
            continue
        if in_refs and REF_END_RE.match(full_strip):
            break
        if not in_refs:
            continue
        if not re.match(r"^\s*\[\d+\]", full_strip):
            continue
        if not _is_english_entry(full_strip):
            continue

        # 拼接 <w:t> 文本与偏移
        runs = []  # [(t_node, start_offset, length)]
        full = ""
        for t in p.iter(f"{W}t"):
            txt = t.text or ""
            runs.append((t, len(full), len(txt)))
            full += txt
        if not runs:
            continue

        # 找标题区间：首个作者结尾 '. ' 之后（跳过 [n] 编号 + 作者部分）
        # 作者结尾常是 ' 等.' / 'et al.' / 名字+'.'
        # 简化：找首个 '. ' 后跟大写字母的位置
        m_start = re.search(r"\.\s+(?=[A-Z])", full)
        if not m_start:
            continue
        title_start = m_start.end()
        # 找类型标识 '[J]/[C]/[D]/[M]/[R]/[N]/[P]/[A]/[Z]/[J/OL]'
        m_end = re.search(r"\[[A-Z](?:/[A-Z]+)?\]", full[title_start:])
        if not m_end:
            continue
        title_end = title_start + m_end.start()
        title = full[title_start:title_end]
        if not title.strip():
            continue
        # 标题中至少含 3 个 Title Case 词才转换
        if len(TC_WORD_RE.findall(title)) < 3:
            continue

        # 转 sentence case：所有 TC 词转小写
        new_title = _to_sentence_case(title)
        # 恢复首词首字母大写
        m_first = re.search(r"[A-Za-z]", new_title)
        if m_first:
            i = m_first.start()
            new_title = new_title[:i] + new_title[i].upper() + new_title[i + 1:]
        if new_title == title:
            continue

        # 写回：长度不变（仅大小写改），按 runs 偏移分配
        new_full = full[:title_start] + new_title + full[title_end:]
        for t, off, ln in runs:
            t.text = new_full[off:off + ln]
        cnt += 1
    return cnt


def protect_reference_paragraphs(body: ET.Element) -> int:
    """对参考文献区每段加 <w:keepLines/>，使整段不被分页拆断。返回处理段数。"""
    paras = list(body)
    in_refs = False
    cnt = 0
    for p in paras:
        if p.tag != f"{W}p":
            continue
        txt = get_para_text(p).strip()
        if REF_HEADING_RE.match(txt):
            in_refs = True
            continue
        if in_refs and REF_END_RE.match(txt):
            in_refs = False
            break
        if not in_refs:
            continue
        if not txt:
            continue  # 跳过空段
        # 在 pPr 中插入 <w:keepLines/>
        pPr = p.find(f"{W}pPr")
        if pPr is None:
            pPr = ET.Element(f"{W}pPr")
            p.insert(0, pPr)
        existing = pPr.find(f"{W}keepLines")
        if existing is None:
            kl = ET.SubElement(pPr, f"{W}keepLines")
            # keepLines 顺序应在 widowControl 之后、ind 之前；lxml 会把它加在末尾，docx schema 兼容
            cnt += 1
    return cnt


def bold_header_row(tbl: ET.Element) -> int:
    """给表头行（rows[0]）的所有 run 加 <w:b/> 和 <w:bCs/>。返回处理 run 数。"""
    rows = tbl.findall(f"{W}tr")
    if not rows:
        return 0
    header = rows[0]
    cnt = 0
    for r in header.iter(f"{W}r"):
        rPr = r.find(f"{W}rPr")
        if rPr is None:
            rPr = ET.Element(f"{W}rPr")
            r.insert(0, rPr)
        # remove existing b/bCs first
        for tag in (f"{W}b", f"{W}bCs"):
            existing = rPr.find(tag)
            if existing is not None:
                rPr.remove(existing)
        # add fresh b + bCs（值默认 true，不需要 val 属性）
        ET.SubElement(rPr, f"{W}b")
        ET.SubElement(rPr, f"{W}bCs")
        cnt += 1
    return cnt


def normalize(docx_path: Path) -> dict:
    """主入口：读 docx → 修改 → 写回。"""
    if not docx_path.exists():
        raise FileNotFoundError(docx_path)

    # 备份
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = docx_path.with_suffix(f".docx.bak_{ts}")
    shutil.copy2(docx_path, backup)

    # 解析 word/document.xml
    with zipfile.ZipFile(docx_path) as zin:
        with zin.open("word/document.xml") as f:
            tree = ET.parse(f)

    body = tree.getroot().find(f"{W}body")
    if body is None:
        raise RuntimeError("no <w:body> found")

    data_tables = find_data_tables(body)
    summary = {"backup": str(backup), "data_tables": len(data_tables), "details": []}

    for pos, tbl, cap in data_tables:
        col_info = reallocate_columns(tbl)
        bold_cnt = bold_header_row(tbl)
        summary["details"].append({
            "caption": cap[:50],
            "pos": pos,
            "col_info": col_info,
            "bolded_runs": bold_cnt,
        })

    # 完全移除所有超链接（外链 + 内链）→ 纯文本
    hl_removed = remove_all_hyperlinks(body)
    summary["hyperlinks_removed"] = hl_removed

    # 参考文献区不跨页保护
    refs_kept = protect_reference_paragraphs(body)
    summary["refs_keepLines"] = refs_kept

    # 参考文献作者大小写规范化（按样文格式：首字母大写）
    refs_case_fixed = fix_reference_author_case(body)
    summary["refs_author_case_fixed"] = refs_case_fixed

    # 参考文献 '等' → 'et al.'（仅英文条目）
    refs_et_al = fix_reference_et_al(body)
    summary["refs_et_al"] = refs_et_al

    # 参考文献英文标题 Title Case → sentence case
    refs_title_case = fix_reference_title_case(body)
    summary["refs_title_case"] = refs_title_case

    # 写回 zip：仅替换 word/document.xml（lxml 保留原 namespace 前缀）
    new_xml_bytes = ET.tostring(tree.getroot(), xml_declaration=True, encoding="UTF-8", standalone=True)

    tmp_path = docx_path.with_suffix(".docx.tmp")
    with zipfile.ZipFile(docx_path) as zin:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml_bytes)
                else:
                    zout.writestr(item, zin.read(item.filename))

    tmp_path.replace(docx_path)
    return summary


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    docx_path = Path(sys.argv[1]).resolve()
    summary = normalize(docx_path)
    print(f"OK: {docx_path}")
    print(f"  备份: {summary['backup']}")
    print(f"  处理真数据表: {summary['data_tables']} 个")
    print(f"  参考文献 keepLines: {summary.get('refs_keepLines', 0)} 段")
    print(f"  参考文献作者大小写规范化: {summary.get('refs_author_case_fixed', 0)} 条")
    for d in summary["details"]:
        ci = d["col_info"]
        if "skipped" in ci:
            print(f"  - {d['caption']!r}: SKIP ({ci['skipped']})")
            continue
        widths_cm = [f"{w/TWIPS_PER_CM:.2f}" for w in ci["widths"]]
        print(f"  - {d['caption']!r}: cols={ci['n_cols']}, widths={widths_cm}cm, header bolded {d['bolded_runs']} runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
