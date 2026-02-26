---
name: swun-thesis-docx-banshi1
description: "Build SWUN thesis DOCX (Format 1 / 版式1) from LaTeX using the official SWUN reference template, with post-processing fixes (TOC, chapter page breaks, indents, isLgl numbering fix, and three-line table layout normalization)."
version: 1.2.3
---

# SWUN Thesis DOCX (版式1)

Generate a `.docx` from a SWUN thesis LaTeX project while treating the official SWUN Format 1 template as the source of truth.

## Output

- `main_版式1.docx` in the thesis directory.

## Pipeline

1. `latexpand` flattens `main.tex`
2. LaTeX preprocessing (`_preprocess_latex`):
   - flattens `subfigure` environments: replaces subfigure `\ref{}` with parent figure `\ref{}`, strips subfigure `\caption`/`\label` to prevent pandoc from inflating the figure counter, deduplicates adjacent identical refs
   - rewrites experiment figure references from `.pdf` to `.png` when PNG assets exist
   - hard-fails if any experiment figure still points to `.pdf` after rewrite
3. `pandoc` converts LaTeX -> DOCX with:
   - `--reference-doc` pointing at the official template
   - `--citeproc` + GB/T 7714-2015 numeric CSL
   - `--resource-path` so `\\includegraphics` assets are embedded
4. OOXML post-processing:
   - inserts Word TOC field
   - adds page breaks before each chapter (Heading 1)
   - adds first-line indents for body paragraphs
   - adds hanging indents for bibliography entries
   - fixes figure captions:
     - adds chapter-based numbering prefix: `图{章}-{序号} 图题`
     - centers figure + caption, removes empty caption paras, keeps figure+caption together
   - fixes figure/table reference format in body text:
     - replaces pandoc's dot-format refs (`图3.1`, `表4.2`) with hyphen format (`图3-1`, `表4-2`)
     - normalizes standalone hyperlink ref text for `fig:/tab:/tbl:` anchors (`3.16` -> `3-16`)
     - handles both single-node refs and split-across-runs refs (pandoc often splits `图` and `3.1` into separate XML runs with whitespace runs in between)
   - fixes equation numbering (display math):
     - adds chapter-based numbering suffix: `(章-序号)` right-aligned
     - avoids numbering `\\[ ... \\]` blocks (keeps them unnumbered)
   - fixes mixed Chinese/Arabic section numbering by adding `w:isLgl` to `ilvl >= 1` (abstractNumId=0)
   - enforces data-table layout for three-line tables:
     - table width fills the whole text area (`tblW == text width`)
     - table layout is fixed (`w:tblLayout w:type="fixed"`)
     - column widths are redistributed by table content and written back to `tblGrid` + `tcW`
   - normalizes table captions:
     - move table title below each data table
     - caption format is chapter-based: `表{章}-{序号} 表题`
     - numbering is continuous within a chapter and restarts at each new chapter
   - normalizes unknown paragraph styles produced by pandoc back to template `Normal` (prevents template/style drift)
   - splits sections for page numbering:
     - "摘要" + "Abstract" is a separate major chapter block with Roman numeral footer page numbers
     - the rest of the thesis uses Arabic numeral footer page numbers starting from 1
   - resolves abstract pagination conflicts:
     - removes stale `w:pageBreakBefore` from abstract anchor paragraphs before inserting Heading 1 ("摘要"/"Abstract")
     - prevents "摘要标题后空白页" regression caused by cover-page boundary pagination
   - inserts abstract keywords:
     - leaves one blank line before the keywords line
     - summarizes to 3-4 keyword groups (merges extras into the last group)
     - emits `关键词：...` for Chinese and `Keywords: ...` for English
   - validates experiment figure media type:
     - all `fig_3_*`/`fig_4_*` drawings must resolve to `media/*.png`
     - aborts build if any experiment figure is still embedded as PDF

## Prerequisites

- Tools: `pandoc`, `latexpand`, `python3`
- Thesis workspace contains `main.tex` (and usually `backmatter/references.bib`, figures/media directories, etc.)
- Official template exists (default):
  - `/Users/bit/LaTeX/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx`

## Usage

```bash
# Default: /Users/bit/LaTeX/SWUN_Thesis
bash /Users/bit/.codex/skills/swun-thesis-docx-banshi1/scripts/main.sh

# Or specify thesis dir explicitly
bash /Users/bit/.codex/skills/swun-thesis-docx-banshi1/scripts/main.sh /path/to/SWUN_Thesis

# Optionally override template path for the build script
export SWUN_TEMPLATE_DOCX="/path/to/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx"
export SWUN_CSL="/path/to/china-national-standard-gb-t-7714-2015-numeric.csl"
export SWUN_BIB="/path/to/references.bib"
```

## Built-in Verification (via `main.sh`)

`main.sh` runs a 4-step pipeline:

1. Build DOCX by running `build_docx_banshi1.py`
   - includes hard validation that experiment figures are embedded as PNG
2. Run regression samples for ref normalization via `ref_hyphen_regression.py`
3. Run generic structural checks with `verify_extra.py`
   - includes regression guard: no forced page break between "摘要"/"Abstract" headings and their first content paragraph
   - hard check: figure/table hyperlink refs (`fig:/tab:/tbl:`) must not contain dot numbering (`3.16`); must use hyphen (`3-16`)
4. Run table-specific checks to enforce:
   - data table full-width (`tblW=dxa` and equals text width)
   - fixed table layout (`tblLayout=fixed`)
   - `tblGrid` width sum equals table width
   - table captions are below tables (no caption-above)
   - table captions follow chapter numbering order (`表{章}-{序号}`)

## Guardrails

- Never recreate styles/numbering from scratch. Always use the official template as `--reference-doc`.
- Do not manually type heading numbering; rely on the template multilevel list mapping.
- For three-line tables, do not keep `auto` table width and do not leave captions above tables.
- Figure/table references must use caption-style hyphen numbering (`图3-16`, `表4-2`), not dot numbering (`图3.16`, `表4.2`).
- Experiment figures must be embedded as PNG in DOCX (`fig_3_*`, `fig_4_*`); PDF embeds are treated as build errors.
