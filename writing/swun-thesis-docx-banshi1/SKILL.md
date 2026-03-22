---
name: swun-thesis-docx-banshi1
description: "Build SWUN thesis DOCX (Format 1 / 版式1) from LaTeX using the official SWUN reference template, with post-processing fixes (TOC, chapter page breaks, indents, isLgl numbering fix, and three-line table layout normalization)."
version: 1.6.0
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
   - enforces data-table layout and typography for three-line tables:
     - table width fills the whole text area (`tblW == text width`)
     - table layout is fixed (`w:tblLayout w:type="fixed"`)
     - column widths are redistributed by table content and written back to `tblGrid` + `tcW`
     - cell text font: Chinese = 宋体 (`w:eastAsia`), English/digits = Times New Roman (`w:ascii/w:hAnsi`), size = 五号 10.5pt (`w:sz="21"`)
     - table font normalization runs AFTER `_normalize_ascii_run_fonts` to prevent English runs losing `eastAsia` attribute
     - clears theme font attributes (`asciiTheme`, `hAnsiTheme`, `eastAsiaTheme`) to prevent theme override
   - writes table metadata (`w:tblCaption`) from normalized Chinese table titles for stable downstream checks
   - disables chapter numbering for backmatter headings (致谢, 参考文献, 科研成果):
     - adds paragraph-level `numPr` with `numId=0` to override style-level numbering
     - same technique used for 目录/摘要/Abstract
   - enables automatic field update on open (`<w:updateFields w:val="true"/>` in settings.xml):
     - Word/WPS will prompt to update TOC when the document is opened
   - normalizes unknown paragraph styles produced by pandoc back to template `Normal` (prevents template/style drift)
   - splits sections for page numbering:
     - front matter (目录 + 摘要 + Abstract) is a separate section with Roman numeral footer page numbers
     - TOC is inserted before 摘要 (目录在前, 摘要在后) inside the Roman-numbered section
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
   - removes `docGrid type="lines"` from all sections to prevent line-spacing inflation:
     - root cause: when `type="lines"` is set and paragraph `line` value exceeds `linePitch`, LibreOffice snaps to the next grid multiple (e.g. 312×2=624 twips ≈ 2.6x instead of 1.5x)
     - fix reduces page count from ~151 to ~114 (matching reference thesis density of ~25 lines/page)
   - replaces WPS-legacy footer XML with clean PAGE field footers:
     - WPS Office embeds complex textbox drawing elements that render as phantom "X" characters in LibreOffice
     - footer3 = Roman (摘要区), footer5 = Arabic (正文区), others = empty
   - strips DOI external hyperlinks from bibliography section:
     - removes `w:hyperlink r:id` wrappers whose text matches DOI patterns (`10.xxxx/` or `https://doi.org/`)
     - pure DOI URL text (e.g. `https://doi.org/10.xxxx`) is deleted entirely (project rule: no DOI in final output)
     - non-DOI-only hyperlink text is kept as plain text (hyperlink wrapper removed)
   - changes Hyperlink character style to black with no underline:
     - fallback safety: any surviving hyperlink-styled text renders as normal black text
     - removes `w14:textFill` gradient fill if present

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
   - hard check: references must NOT contain DOI external hyperlinks (`w:hyperlink r:id` with DOI text); builder strips them
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

## 触发条件 / Trigger

### 触发词

本 skill 在以下情形下被激活：

- `/swun-docx` — 快捷触发词
- `构建版式1` / `build docx banshi1` / `build banshi1 docx`
- `生成 DOCX` / `导出 DOCX` / `DOCX 构建`
- `swun-thesis-docx` / `swun thesis docx`
- 用户要求构建 SWUN 论文的 Word 格式文件时

### 应触发（Should Trigger）

```
用户: 帮我构建一下版式1 DOCX
→ 触发本 skill，调用 scripts/main.sh

用户: /swun-docx
→ 触发本 skill

用户: 论文写完了，需要导出 Word 给导师
→ 触发本 skill（SWUN 毕业论文场景）
```

### 不应触发（Should NOT Trigger）

```
用户: 帮我修改 chapter3.tex 的内容
→ 不触发（这是 LaTeX 编辑任务，不是 DOCX 构建）

用户: 检查论文的引用格式
→ 不触发（这是审查任务）

用户: 构建普通 Word 文档
→ 不触发（必须是 SWUN 学位论文项目）
```

## Constraints / 约束

### CAN（允许）

- 可以调用 `pandoc` + `latexpand` 转换 LaTeX → DOCX
- 可以对生成的 DOCX 进行 OOXML 后处理（TOC、段落样式、标题、脚注等）
- 可以覆盖写入 `main_版式1.docx`（每次构建均覆盖）
- 可以读取 `main.tex` 及其 `\include` 的子文件（只读）
- 可以修改构建临时文件（`/tmp/` 下的中间产物）
- 可以运行回归测试脚本（`ref_hyphen_regression.py`、`abstract_section_regression.py`）

### CANNOT（禁止）

- 不可修改 `chapters/*.tex`、`backmatter/references.bib` 等源文件（构建不改源）
- 不可删除用户的 LaTeX 源文件或图片资产
- 不可重建 Word 样式/编号（必须从官方模板继承，禁止从零创建）
- 不可手动写入章节标题编号（由模板多级列表映射处理）
- 不可跳过 PNG 验证步骤（实验图必须为 PNG，PDF 嵌入视为构建错误）
- 不可将 DOI 超链接写入参考文献区（项目规则：最终输出无 DOI）
- 不可使用 ZIP 重打包方式修改 DOCX（会损坏文件内部引用）

## Error Handling / 错误处理

### 常见错误与处理策略

| 错误类型 | 触发条件 | 处理方式 |
|----------|---------|---------|
| **Build failure** | `pandoc` / `latexpand` 返回非零退出码 | 立即终止，输出完整错误日志，不生成部分 DOCX |
| **PDF embed error** | `fig_3_*` / `fig_4_*` 实验图以 PDF 嵌入 | hard-fail，提示用户将对应图转为 PNG |
| **Missing caption/label** | LaTeX 浮动体缺少 `\caption` 或 `\label` | hard-fail，输出缺失的环境位置 |
| **Empty English caption** | `\bilingualcaption` 英文标题为空 | hard-fail，提示补全英文标题 |
| **Timeout** | `pandoc` / 后处理脚本超过 300s | 超时退出，提示检查文档大小或依赖工具 |
| **Template not found** | 官方模板文件不存在于默认路径 | 报错并提示设置 `SWUN_TEMPLATE_DOCX` 环境变量 |
| **Crash / 异常** | Python 后处理脚本未捕获异常 | 输出完整 traceback，保留已生成的中间 DOCX 以供调试 |
| **Gate loop failure** | 6 阶段校验中任一阶段不通过 | 输出失败阶段和具体违规项，等待人工修复或 codex 自动修复 |

### 自动恢复策略

- **回归测试失败**：打印失败用例的 input/expected/actual，不中断整体流程（继续后续阶段）
- **表格样式警告**：`SWUN_TABLE_VERIFY_ALLOW_EMPTY=1`（默认）时无三线表则跳过（SKIP），不报错
- **subagent 隔离**：每次构建在独立 Python 进程中运行，崩溃不影响主会话

## 评估 / Evaluation

### 构建质量评估

gate-loop（`gate_loop.sh` / `gate_loop_runner.py`）按 6 个阶段逐步评估输出质量：

| 阶段 | 评估脚本 | 检查内容 |
|------|---------|---------|
| Phase 1 | `phase1_structure.py` | 标题层级、目录结构、页码分区 |
| Phase 2 | `phase2_style.py` | 正文样式、字体、段落缩进 |
| Phase 3 | `phase3_caption.py` | 图表标题格式、位置、编号 |
| Phase 4 | `phase4_crossref.py` | 正文内交叉引用格式（连字符编号） |
| Phase 5 | `phase5_content.py` | 参考文献、摘要关键词 |
| Phase 6 | `phase6_visual.py` | 可视化抽样检查（可选） |

### 评分标准（keep / discard）

- **keep**：所有阶段 PASS 或 SKIP，无 FAIL
- **discard**：任一阶段 FAIL 且无法自动修复
- 回归测试：`ref_hyphen_regression.py` + `abstract_section_regression.py` 全部 PASS 为基准条件

### 辅助评估工具

```bash
# 运行 gate-loop 全部阶段
bash scripts/gate_loop.sh /path/to/SWUN_Thesis

# 运行 normalize_template 检查模板状态
python3 scripts/normalize_template.py /path/to/template.docx

# 运行 verify_extra 结构检查
python3 scripts/verify_extra.py /path/to/main_版式1.docx
```

## Execution Isolation / 执行隔离

- 本 skill 通过 subagent 派发执行，每次构建在独立 Python 进程中运行
- 构建脚本之间无共享全局状态（无单例、无全局缓存）
- 多个 SWUN 论文项目可并发构建（使用不同 `thesis_dir` 参数），互不干扰
- Gate-loop 各阶段顺序执行，不并发（保证前置阶段数据供后置阶段使用）
- 临时文件写入 `/tmp/`，构建完成后可安全清理

## Setup / 安装与配置

1. 确保依赖工具已安装：
   ```bash
   brew install pandoc latexmk
   pip3 install python-docx lxml
   ```

2. 确认官方模板存在：
   ```bash
   ls /Users/bit/LaTeX/西南民族大学研究生学位论文写作规范_模板部分_版式1.docx
   ```

3. （可选）配置环境变量覆盖默认路径：
   ```bash
   export SWUN_TEMPLATE_DOCX="/path/to/template.docx"
   export SWUN_CSL="/path/to/gb-t-7714-2015-numeric.csl"
   export SWUN_BIB="/path/to/references.bib"
   ```

4. 验证安装：
   ```bash
   bash /Users/bit/.claude/skills/swun-thesis-docx-banshi1/scripts/main.sh /Users/bit/LaTeX/SWUN_Thesis
   ```

## 输出格式 / Output Format

```
构建成功时输出示例:
  [build] latexpand done
  [build] pandoc done
  [postprocess] TOC inserted
  [postprocess] chapter page breaks done
  [verify] Phase 1: PASS
  [verify] Phase 2: PASS
  ...
  [done] main_版式1.docx written (N pages)

构建失败时输出示例:
  [ERROR] experiment figure fig_4_2 is embedded as PDF, not PNG
  Build aborted.
```

**输出文件**：`{thesis_dir}/main_版式1.docx`
