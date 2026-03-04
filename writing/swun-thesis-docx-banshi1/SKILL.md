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
   - rebuilds figure/table captions from LaTeX metadata (`\label` + `\bilingualcaption`/`\caption`) and DOCX anchors (`fig:/tab:/tbl:`):
     - hard-fails if a figure/table environment in LaTeX is missing caption or label
     - hard-fails if `\bilingualcaption` has an empty English title
     - figure captions are placed below figure blocks
     - table captions are placed above table blocks
     - chapter-based numbering: `图{章}-{序号}` / `Figure {章}-{序号}` / `表{章}-{序号}` / `Table {章}-{序号}`
     - bilingual captions emit Chinese + English lines; plain `\caption{}` emits Chinese line only
     - idempotent rewrite: clears nearby old captions before writing normalized ones
     - caption paragraphs are centered and keep-together hints are applied
   - fixes figure/table reference format in body text:
     - replaces pandoc's dot-format refs (`图3.1`, `表4.2`) with hyphen format (`图3-1`, `表4-2`)
     - normalizes standalone hyperlink ref text for `fig:/tab:/tbl:` anchors (`3.16` -> `3-16`)
     - handles both single-node refs and split-across-runs refs (pandoc often splits `图` and `3.1` into separate XML runs with whitespace runs in between)
  - removes internal cross-reference hyperlinks in thesis main body (正文):
    - unwraps `w:hyperlink` nodes carrying internal `w:anchor` in chapter content and keeps plain text runs
    - preserves non-anchor external hyperlinks (e.g., DOI/URL `r:id`) by default
    - strips hyperlink-like run style (blue/underline) only on unwrapped anchor runs so cross-reference text renders as normal text
   - normalizes `\paragraph` headings in thesis main body:
     - writes explicit numbering prefix as `(n) 标题` on `Heading5`
     - resets numbering per `Heading3` (subsection), fallback reset per `Heading2`
   - fixes equation numbering (display math):
     - adds chapter-based numbering suffix: `(章-序号)` right-aligned
     - avoids numbering `\\[ ... \\]` blocks (keeps them unnumbered)
   - fixes mixed Chinese/Arabic section numbering by adding `w:isLgl` to `ilvl >= 1` (abstractNumId=0)
   - enforces data-table layout for three-line tables:
     - table width fills the whole text area (`tblW == text width`)
     - table layout is fixed (`w:tblLayout w:type="fixed"`)
     - column widths are redistributed by table content and written back to `tblGrid` + `tcW`
   - writes table metadata (`w:tblCaption`) from normalized Chinese table titles for stable downstream checks
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
     - English keyword splitting prefers semicolons; comma splitting is only fallback and avoids commas inside paired punctuation
   - validates experiment figure media type:
     - all `fig_3_*`/`fig_4_*` drawings must resolve to `media/*.png`
     - aborts build if any experiment figure is still embedded as PDF

## Refactored Architecture

- Thin CLI entrypoints:
  - `scripts/build_docx_banshi1.py`
  - `scripts/verify_extra.py`
  - `scripts/gate_loop.sh`
  - `scripts/gate_loop_runner.py`
- Core build module:
  - `scripts/modules/docx_builder.py`
- Facade modules (phase 3/4 extraction):
  - `scripts/modules/latex_parser.py`
  - `scripts/modules/style_processor.py`
  - `scripts/modules/reference_handler.py`
  - `scripts/modules/figure_table_handler.py`
  - `scripts/modules/equation_handler.py`
  - `scripts/modules/template_loader.py`
  - `scripts/modules/post_processor.py`
- Verification modules:
  - `scripts/verification/report_generator.py`
  - `scripts/verification/structure_checker.py`
  - `scripts/verification/style_checker.py`
  - `scripts/verification/reference_checker.py`
  - `scripts/verification/content_checker.py`
- Gate-loop phase modules:
  - `scripts/phase_checks/phase1_structure.py`
  - `scripts/phase_checks/phase2_style.py`
  - `scripts/phase_checks/phase3_caption.py`
  - `scripts/phase_checks/phase4_crossref.py`
  - `scripts/phase_checks/phase5_content.py`
  - `scripts/phase_checks/phase6_visual.py`

## Prerequisites

- Tools: `pandoc`, `latexpand`, `python3`
- Thesis workspace contains `main.tex` (and usually `backmatter/references.bib`, figures/media directories, etc.)
- Official template exists (default):
  - `/Users/bit/LaTeX/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx`

## Usage

```bash
# Default: /Users/bit/LaTeX/SWUN_Thesis
bash /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/main.sh

# Or specify thesis dir explicitly
bash /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/main.sh /path/to/SWUN_Thesis

# Optionally override template path for the build script
export SWUN_TEMPLATE_DOCX="/path/to/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx"
export SWUN_CSL="/path/to/china-national-standard-gb-t-7714-2015-numeric.csl"
export SWUN_BIB="/path/to/references.bib"
```

### Direct CLI examples

```bash
python3 /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/build_docx_banshi1.py /Users/bit/LaTeX/SWUN_Thesis
python3 /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/verify_extra.py /Users/bit/LaTeX/SWUN_Thesis/main_版式1.docx
```

### Gate-Loop Usage (6-Phase)

```bash
# Run all phases (default)
bash /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/gate_loop.sh /Users/bit/LaTeX/SWUN_Thesis --skip-build

# Run only one phase
python3 /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/gate_loop_runner.py \
  /Users/bit/LaTeX/SWUN_Thesis \
  --phase 1 --skip-build

# Tune retry count (used when codex auto-fix is enabled)
python3 /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/gate_loop_runner.py \
  /Users/bit/LaTeX/SWUN_Thesis \
  --max-retry 2
```

## Built-in Verification (via `main.sh`)

`main.sh` runs a 5-step pipeline:

1. Build DOCX by running `build_docx_banshi1.py`
   - includes hard validation that experiment figures are embedded as PNG
2. Run regression samples for ref normalization via `ref_hyphen_regression.py`
3. Run abstract section regression samples via `abstract_section_regression.py`
   - guards against duplicate `摘要` heading when heading/first paragraph are separated by blank lines
   - guards against truncating multi-paragraph English abstract
4. Run generic structural checks with `verify_extra.py`
   - includes regression guard: no forced page break between "摘要"/"Abstract" headings and their first content paragraph
   - includes regression guard: `\paragraph` mapped `Heading5` line MUST have first-line indent (matching PDF layout), and its first following body paragraph must also keep first-line indent
   - hard check: figure/table hyperlink refs (`fig:/tab:/tbl:`) must not contain dot numbering (`3.16`); must use hyphen (`3-16`)
   - hard check: main-body internal cross-reference links must be plain text (no `w:anchor` hyperlink nodes, no hyperlink-like blue/underline style residue)
   - hard check: if references contain DOI/URL text, `w:hyperlink r:id` external links must still exist
   - hard check: main-body `Heading5` (`\paragraph`) must start with explicit `(n)` prefix
  - hard check: each main-body `fig:/tab:/tbl:` anchor must have Chinese caption line with correct position and chapter-local numbering; if English caption line exists, its format/numbering must also be valid
   - hard check: figure captions must be below figure blocks, table captions must be above table blocks
5. Run table-specific checks to enforce:
   - data table full-width (`tblW=dxa` and equals text width)
   - fixed table layout (`tblLayout=fixed`)
   - `tblGrid` width sum equals table width
   - table captions are above tables (no caption-below)
   - table captions follow chapter numbering order (`表{章}-{序号}`)
   - when no data table exists, defaults to `SKIP` (set `SWUN_TABLE_VERIFY_ALLOW_EMPTY=0` to enforce hard-fail)

## Guardrails

- Never recreate styles/numbering from scratch. Always use the official template as `--reference-doc`.
- Do not manually type chapter/section heading numbering; rely on the template multilevel list mapping.
- `\paragraph` (`Heading5`) in main body is the exception: numbering is explicitly normalized to `(n)` text during post-processing.
- For three-line tables, do not keep `auto` table width and keep captions above tables.
- Figure/table references must use caption-style hyphen numbering (`图3-16`, `表4-2`), not dot numbering (`图3.16`, `表4.2`).
- Main body (正文) internal cross-reference links must be plain text (no blue underline clickable links).
- Experiment figures must be embedded as PNG in DOCX (`fig_3_*`, `fig_4_*`); PDF embeds are treated as build errors.
