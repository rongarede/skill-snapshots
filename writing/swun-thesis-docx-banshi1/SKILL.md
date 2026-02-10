---
name: swun-thesis-docx-banshi1
description: "Build SWUN thesis DOCX (Format 1 / 版式1) from LaTeX using the official SWUN reference template, with post-processing fixes (TOC, chapter page breaks, indents, isLgl numbering fix)."
version: 1.0.0
---

# SWUN Thesis DOCX (版式1)

Generate a `.docx` from a SWUN thesis LaTeX project while treating the official SWUN Format 1 template as the source of truth.

## Output

- `main_版式1.docx` in the thesis directory.

## Pipeline

1. `latexpand` flattens `main.tex`
2. `pandoc` converts LaTeX -> DOCX with:
   - `--reference-doc` pointing at the official template
   - `--citeproc` + GB/T 7714-2015 numeric CSL
   - `--resource-path` so `\\includegraphics` assets are embedded
3. OOXML post-processing:
   - inserts Word TOC field
   - adds page breaks before each chapter (Heading 1)
   - adds first-line indents for body paragraphs
   - adds hanging indents for bibliography entries
   - fixes figure captions:
     - adds chapter-based numbering prefix: `图{章}-{序号} 图题`
     - centers figure + caption, removes empty caption paras, keeps figure+caption together
   - fixes equation numbering (display math):
     - adds chapter-based numbering suffix: `(章-序号)` right-aligned
     - avoids numbering `\\[ ... \\]` blocks (keeps them unnumbered)
   - fixes mixed Chinese/Arabic section numbering by adding `w:isLgl` to `ilvl >= 1` (abstractNumId=0)
   - normalizes unknown paragraph styles produced by pandoc back to template `Normal` (prevents template/style drift)
   - splits sections for page numbering:
     - "摘要" + "Abstract" is a separate major chapter block with Roman numeral footer page numbers
     - the rest of the thesis uses Arabic numeral footer page numbers starting from 1
   - inserts abstract keywords:
     - leaves one blank line before the keywords line
     - summarizes to 3-4 keyword groups (merges extras into the last group)
     - emits `关键词：...` for Chinese and `Keywords: ...` for English

## Prerequisites

- Tools: `pandoc`, `latexpand`, `python3`
- Thesis workspace contains `build_docx_banshi1.py` and `verify_docx.py`
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

## Guardrails

- Never recreate styles/numbering from scratch. Always use the official template as `--reference-doc`.
- Do not manually type heading numbering; rely on the template multilevel list mapping.
