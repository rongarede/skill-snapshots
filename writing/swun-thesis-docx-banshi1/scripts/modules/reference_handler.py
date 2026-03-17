"""交叉引用/超链接清理模块。"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

try:
    from utils.ooxml import collect_ns, qn, p_text, p_style
except ModuleNotFoundError:  # pragma: no cover - pytest imports via scripts.modules
    from scripts.utils.ooxml import collect_ns, qn, p_text, p_style


def fix_ref_dot_to_hyphen(ns: dict[str, str], body: ET.Element) -> None:
    """Replace dot-format figure/table refs (图3.1, 表4.2) with hyphen format (图3-1, 表4-2)."""
    w_p = qn(ns, "w", "p")
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")
    w_hyperlink = qn(ns, "w", "hyperlink")
    w_anchor = qn(ns, "w", "anchor")

    inline_re = re.compile(r"((?:图|表)\s*)(\d+)\.(\d+)")
    compact_re = re.compile(r"((?:图|表))[\s\u00a0]+(\d+-\d+)")
    num_re = re.compile(r"^(\s*)(\d+)[\.\-．](\d+)")

    for p in body.iter(w_p):
        for t in p.iter(w_t):
            if not t.text:
                continue
            new_text = inline_re.sub(r"\1\2-\3", t.text)
            new_text = compact_re.sub(r"\1\2", new_text)
            t.text = new_text

        runs = list(p.findall(f".//{w_r}"))
        for i in range(len(runs) - 1):
            cur_texts = list(runs[i].iter(w_t))
            if not cur_texts:
                continue
            tail = (cur_texts[-1].text or "").rstrip()
            if not tail.endswith(("图", "表")):
                continue
            for j in range(i + 1, min(i + 4, len(runs))):
                nxt_texts = list(runs[j].iter(w_t))
                if not nxt_texts:
                    continue
                nxt_val = nxt_texts[0].text or ""
                if nxt_val.strip() == "":
                    continue
                if num_re.match(nxt_val):
                    nxt_texts[0].text = num_re.sub(r"\1\2-\3", nxt_val, count=1)
                    for k in range(i + 1, j):
                        for tk in runs[k].iter(w_t):
                            tk.text = ""
                break

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


def collect_hyperlink_char_style_ids(styles_xml: bytes) -> set[str]:
    """Return style IDs whose name contains 'hyperlink' (case-insensitive)."""
    if not styles_xml:
        return set()
    sns = collect_ns(styles_xml)
    sroot = ET.fromstring(styles_xml)
    w_style = qn(sns, "w", "style")
    w_name = qn(sns, "w", "name")
    w_val = qn(sns, "w", "val")
    w_type = qn(sns, "w", "type")
    ids: set[str] = set()
    for s in sroot.iter(w_style):
        if s.get(w_type) != "character":
            continue
        name_el = s.find(w_name)
        if name_el is None:
            continue
        name_val = (name_el.get(w_val) or "").lower()
        if "hyperlink" in name_val:
            sid = s.get(qn(sns, "w", "styleId"), "")
            if sid:
                ids.add(sid)
    return ids


def strip_hyperlink_run_style(
    ns: dict[str, str],
    node: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> None:
    """Remove hyperlink-like run formatting so unwrapped refs render as normal text."""
    w_r = qn(ns, "w", "r")
    w_rPr = qn(ns, "w", "rPr")
    w_rStyle = qn(ns, "w", "rStyle")
    w_color = qn(ns, "w", "color")
    w_u = qn(ns, "w", "u")
    w_val = qn(ns, "w", "val")
    w_themeColor = qn(ns, "w", "themeColor")
    hl_ids = hyperlink_style_ids or set()

    for r in node.iter(w_r):
        rPr = r.find(w_rPr)
        if rPr is None:
            continue

        for rs in list(rPr.findall(w_rStyle)):
            sval = rs.get(w_val) or ""
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


def unwrap_selected_hyperlinks_in_node(
    ns: dict[str, str],
    node: ET.Element,
    anchor_prefixes: tuple[str, ...] | None = None,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Replace selected anchor hyperlinks with child runs, preserving visible text order."""
    w_hyperlink = qn(ns, "w", "hyperlink")
    w_anchor = qn(ns, "w", "anchor")
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
                strip_hyperlink_run_style(ns, sub, hyperlink_style_ids)
                new_children.append(sub)

        if changed:
            parent[:] = new_children

    return removed


def is_fig_table_ref_number_token(text: str) -> bool:
    return bool(re.match(r"^\d+-\d+[）)\]】,，.。:：;；]*$", text.strip()))


def collect_fig_table_ref_run_indexes(ns: dict[str, str], node: ET.Element) -> set[int]:
    """Collect run indexes that belong to figure/table refs like 图2-1 / 表 3-2."""
    w_r = qn(ns, "w", "r")
    w_t = qn(ns, "w", "t")

    runs = list(node.iter(w_r))
    run_texts = ["".join((t.text or "") for t in r.iter(w_t)) for r in runs]
    target: set[int] = set()

    same_run_re = re.compile(r"[图表]\s*\d+-\d+")
    for i, txt in enumerate(run_texts):
        if same_run_re.search(txt):
            target.add(i)

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
            if is_fig_table_ref_number_token(nxt):
                target.update({i, j})
                for k in range(i + 1, j):
                    if run_texts[k].strip() == "":
                        target.add(k)
            break

    return target


def strip_fig_table_ref_link_style_in_node(
    ns: dict[str, str],
    node: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Strip hyperlink-like style only on fig/table reference runs."""
    w_r = qn(ns, "w", "r")
    runs = list(node.iter(w_r))
    targets = collect_fig_table_ref_run_indexes(ns, node)
    touched = 0
    for i, r in enumerate(runs):
        if i not in targets:
            continue
        strip_hyperlink_run_style(ns, r, hyperlink_style_ids)
        touched += 1
    return touched


def strip_anchor_hyperlinks_in_main_body(
    ns: dict[str, str],
    body: ET.Element,
    hyperlink_style_ids: set[str] | None = None,
) -> int:
    """Remove internal anchor hyperlinks from thesis main-body section (正文)."""
    w_p = qn(ns, "w", "p")
    w_tbl = qn(ns, "w", "tbl")
    excluded_h1 = {"目录", "摘要", "Abstract", "致谢", "参考文献", "攻读硕士学位期间所取得的相关科研成果"}
    stop_h1 = {"参考文献", "致谢", "攻读硕士学位期间所取得的相关科研成果"}

    in_main_body = False
    removed = 0

    for el in list(body):
        if el.tag == w_p:
            style = p_style(ns, el)
            txt = p_text(ns, el).strip()
            if style == "1":
                if txt in stop_h1:
                    in_main_body = False
                elif txt and txt not in excluded_h1:
                    in_main_body = True

        if not in_main_body:
            continue
        if el.tag not in {w_p, w_tbl}:
            continue
        removed += unwrap_selected_hyperlinks_in_node(ns, el, hyperlink_style_ids=hyperlink_style_ids)
        strip_hyperlink_run_style(ns, el, hyperlink_style_ids)

    return removed


def strip_doi_hyperlinks_in_bibliography(
    ns: dict[str, str],
    body: ET.Element,
) -> int:
    """Remove DOI external hyperlinks from the bibliography section."""
    w_p = qn(ns, "w", "p")
    w_hyperlink = qn(ns, "w", "hyperlink")
    w_t = qn(ns, "w", "t")
    r_id_attr = qn(ns, "r", "id") if "r" in ns else (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    )

    stop_h1 = {"致谢", "攻读硕士学位期间所取得的相关科研成果"}
    children = list(body)
    ref_start: int | None = None
    ref_end: int = len(children)

    for idx, el in enumerate(children):
        if el.tag != w_p:
            continue
        style = p_style(ns, el)
        txt = p_text(ns, el).strip()
        if style == "1":
            if txt == "参考文献":
                ref_start = idx + 1
            elif ref_start is not None and txt in stop_h1:
                ref_end = idx
                break

    if ref_start is None:
        return 0

    doi_re = re.compile(r"(10\.\d{4,9}/\S+|https?://doi\.org/\S*)", re.IGNORECASE)
    pure_doi_url_re = re.compile(r"^https?://doi\.org/\S+$", re.IGNORECASE)

    removed = 0
    for el in children[ref_start:ref_end]:
        for parent in el.iter():
            child_list = list(parent)
            if not child_list:
                continue

            changed = False
            new_children: list[ET.Element] = []
            for child in child_list:
                if child.tag != w_hyperlink:
                    new_children.append(child)
                    continue

                rid = child.get(r_id_attr, "")
                if not rid:
                    new_children.append(child)
                    continue

                hl_text = "".join((t.text or "") for t in child.iter(w_t)).strip()
                if not doi_re.search(hl_text):
                    new_children.append(child)
                    continue

                changed = True
                removed += 1
                if pure_doi_url_re.match(hl_text):
                    pass
                else:
                    for sub in list(child):
                        new_children.append(sub)

            if changed:
                parent[:] = new_children

    if removed:
        print(f"  [bib] Removed {removed} DOI hyperlink(s) from bibliography")
    return removed


__all__ = [
    "fix_ref_dot_to_hyphen",
    "collect_hyperlink_char_style_ids",
    "strip_hyperlink_run_style",
    "unwrap_selected_hyperlinks_in_node",
    "is_fig_table_ref_number_token",
    "collect_fig_table_ref_run_indexes",
    "strip_fig_table_ref_link_style_in_node",
    "strip_anchor_hyperlinks_in_main_body",
    "strip_doi_hyperlinks_in_bibliography",
]
