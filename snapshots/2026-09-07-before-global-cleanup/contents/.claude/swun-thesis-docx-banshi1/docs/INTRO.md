# 用 Claude Code 一键把 SWUN 学位论文从 LaTeX 构建成合规 Word

> 面向西南民族大学研究生的使用指南。你用 LaTeX 写论文，导师和学校要 Word——
> 这个 skill 把「LaTeX → 版式1 合规 docx」变成一条命令的事。

---

## 0. 这是什么（30 秒）

你在 Claude Code 里输入：

```
/swun-docx
```

skill 会把你的 LaTeX 论文项目（`main.tex` + 各章节）自动转换成
`main_版式1.docx`，并完成学校《研究生学位论文写作规范》版式1 要求的全部排版：

| 你写的 LaTeX | 产出的 Word |
|--------------|-------------|
| `\chapter{绪论}` | 章标题 + 自动编号 + 每章另起一页 |
| `\bilingualcaption{中文题注}{English Caption}` | 图下/表上双语题注，`图3-1` / `Figure 3-1` 编号 |
| `\ref{fig:arch}` | 正文交叉引用 `图3-1`（连字符格式，黑色纯文本） |
| `\cite{zhang2023}` + `references.bib` | GB/T 7714-2015 格式参考文献表 |
| 摘要/Abstract | 罗马数字页码前置区 + 关键词行 |

转换全程带校验：题注缺失、实验图用了 PDF、引用格式错误等问题会**直接报错中止**，
不会产出一份「看起来能交」实际不合规的半成品。

---

## 1. 前置知识自查

**需要会**（缺一项先补课）：

- LaTeX 基本写作：`\chapter`/`\section`、figure/table 环境、`\label`/`\ref`、`\cite`
- 终端基本操作：会 `cd`、会复制粘贴命令、看得懂报错输出
- Claude Code 日常使用：会发指令、会用斜杠命令（你既然在深度使用，这条已达标）

**不需要会**（复杂度已被 skill 封装）：

- ❌ pandoc 的任何用法
- ❌ Word/OOXML 内部格式（document.xml、样式表那些）
- ❌ Python（构建脚本自动运行，你不用读也不用改）

---

## 2. 前置环境

按依赖链安装，每步都带验证命令——**验证通过再进行下一步**。

### 2.1 MacTeX（提供 xelatex 和 latexpand）

```bash
brew install --cask mactex
# 装完重开终端，验证：
xelatex --version | head -1
latexpand --version | head -1
```

两条命令都有版本输出即通过（安装路径通常在 `/Library/TeX/texbin/`）。

### 2.2 pandoc（LaTeX → Word 的转换引擎）

```bash
brew install pandoc
pandoc --version | head -1
```

### 2.3 python3（运行构建与校验脚本）

macOS 自带或 `brew install python3`，验证：

```bash
python3 --version
```

**无需 pip 安装任何第三方包**——构建主链路只用 Python 标准库。

### 2.4 skill 本体

确认 skill 已安装在 Claude Code 的 skills 目录：

```bash
ls ~/.claude/skills/swun-thesis-docx-banshi1/SKILL.md
ls ~/.claude/skills/swun-thesis-docx-banshi1/assets/swun_banshi1_reference.docx
```

第二条是**内置参考模板**（约 91KB）：学校版式1 的全套样式、页眉页脚、封面
已经打包在 skill 里，你**不需要**自己去找学校的模板 docx 文件。

---

## 3. 搭建你的 LaTeX 论文项目

### 3.1 目录结构（照抄即可）

```
你的论文目录/
├── main.tex                 # 主文件：\documentclass{swunthesis}
├── swunthesis.cls           # 学校格式文档类（含 \bilingualcaption 宏定义）
├── chapters/
│   ├── chapter1.tex         # 各章正文，main.tex 里 \input 引入
│   └── ...
├── frontmatter/
│   ├── abstract_zh.tex      # 中文摘要
│   └── abstract_en.tex      # 英文摘要
├── backmatter/
│   ├── references.bib       # 参考文献库（biblatex）
│   ├── acknowledgements.tex # 致谢
│   └── publications.tex     # 攻读学位期间科研成果
└── figures/                 # 图片资源（实验图必须有 PNG）
```

### 3.2 写作约定 = 一份 CLAUDE.md

与其记住所有约定，不如让你的 Claude 替你守约——把下面这份 `CLAUDE.md`
**完整复制到论文根目录**，之后用 Claude Code 写论文时它会自动执行这些约束：

````markdown
# 论文写作约束（SWUN 版式1 DOCX 构建契约）

本项目最终用 swun-thesis-docx-banshi1 skill 导出 Word。
以下约束违反任何一条会导致 DOCX 构建硬失败，写作时必须遵守。

## 图表铁律

1. 每个 figure/table 环境必须同时有题注和 `\label`：
   - 图用 `fig:` 前缀，表用 `tab:` 前缀（如 `\label{fig:arch}`）
   - label 全文唯一，禁止重复
2. 题注优先用双语宏：`\bilingualcaption{中文标题}{English Title}`
   - 英文参数禁止留空
   - 单语场景才允许 `\caption{中文标题}`
3. 实验图（fig_3_*、fig_4_* 命名）必须存在 PNG 版本；
   `\includegraphics` 不得只有 PDF 资源
4. 表格一律三线表（booktabs：`\toprule`/`\midrule`/`\bottomrule`），
   题注放表格上方

## 编号与引用铁律

5. 禁止手写任何编号：章节号、图表号、`\paragraph` 序号都由模板
   和构建流程生成；正文引用一律 `\ref{...}`/`\eqref{...}`
6. 参考文献只走 `backmatter/references.bib` + `\cite{...}`，
   禁止手敲文献条目；bib 条目不要依赖 DOI 字段排版
   （最终输出会移除 DOI 超链接）

## 构建纪律

- 改完 .tex 先 `xelatex` 编译通过，再考虑导出 Word
- 构建命令不修改任何 .tex 源文件，放心运行
````

这份约束就是 skill 的「输入契约」：满足它，构建一次通过；
违反它，§6 的报错排查表告诉你怎么修。

### 3.3 构建前最后一步：编译出 main.aux

```bash
cd 你的论文目录
xelatex main.tex
```

交叉引用（`图3-1` 这类编号）以 `main.aux` 里 LaTeX 解析的编号为准，
所以**先编译再导出**。日常用 latexmk 的同学保持习惯即可。

---

## 4. 构建你的 Word

### 4.1 主路径：Claude Code

在论文目录打开 Claude Code，输入：

```
/swun-docx
```

Claude 会调起 skill 完成「模板归一化 → 构建 → 四道回归校验」全流程，
失败时还能直接帮你定位和修复。

### 4.2 等价命令行（不依赖 AI）

```bash
bash ~/.claude/skills/swun-thesis-docx-banshi1/scripts/main.sh /path/to/你的论文目录
```

### 4.3 产物

- `main_版式1.docx` —— 最终交付文件，每次构建覆盖
- `main_版式1.docx.bak_时间戳` —— 旧产物自动备份，误覆盖可找回
- 模板解析顺序：环境变量 `SWUN_REFERENCE_DOCX` > 论文目录内参考论文 >
  skill 内置模板（默认走内置，零配置）

---

## 5. 质量保障：怎么判断「构建成功」

`main.sh` 输出全部 6 步均 OK/PASS 才算成功：

| 步骤 | 输出标志 | 检查内容 |
|------|---------|---------|
| 1/6 | `OK: normalized N style IDs` | 模板样式 ID 归一化 |
| 2/6 | `PNG VERIFY: PASS` + `OK: main_版式1.docx` | 构建 + 实验图 PNG 校验 |
| 3/6 | `REF REGRESSION: PASS` | 交叉引用连字符格式回归 |
| 4/6 | `ABSTRACT REGRESSION: PASS` | 摘要分节回归 |
| 5/6 | `EXTRA VERIFY: PASS` | 结构/样式/引用通用检查 |
| 6/6 | `TABLE VERIFY: PASS` | 三线表布局与题注检查 |

要更严格的体检，可跑六阶段质量门（gate-loop）：

```bash
bash ~/.claude/skills/swun-thesis-docx-banshi1/scripts/gate_loop.sh /path/to/论文目录 --skip-build
```

| 阶段 | 检查维度 |
|------|---------|
| Phase 1 | 标题层级、目录结构、页码分区 |
| Phase 2 | 正文样式、字体、段落缩进 |
| Phase 3 | 图表题注格式、位置、编号 |
| Phase 4 | 正文交叉引用格式 |
| Phase 5 | 内容规范（参考文献、关键词、标点） |
| Phase 6 | 可视化抽样（可选） |

判读标准：**全 PASS 或 SKIP，无 FAIL**。

---

## 6. 常见报错排查表

| 报错（原文摘录） | 原因 | 修法 |
|------------------|------|------|
| `error: missing dependency: pandoc` | 依赖未装 | 回 §2 装对应工具 |
| `error: missing: .../main.tex` | 目录不对或主文件名不是 main.tex | `cd` 到论文根目录；主文件须命名 `main.tex` |
| `DOCX build blocked: failed to extract figure/table captions from LaTeX` | 下列子项之一 | 看子项逐条修 |
| └ `missing \label{...}` | 图/表没打标签 | 补 `\label{fig:...}`/`\label{tab:...}`（铁律 1） |
| └ `missing \bilingualcaption{...}{...} or \caption{...}` | 图/表没题注 | 补题注（铁律 2） |
| └ `bilingualcaption English title is empty` | 双语题注英文参数为空 | 补英文标题（铁律 2） |
| └ `duplicate label in figure/table environments` | label 重复 | 改成全文唯一（铁律 1） |
| 实验图 PDF 嵌入（PNG VERIFY 失败） | `fig_3_*`/`fig_4_*` 只有 PDF 资源 | 导出同名 PNG 放进图目录（铁律 3） |
| `error: reference template not found` | 内置模板被删且无替代 | 重装 skill，或 `SWUN_REFERENCE_DOCX` 指定模板 |
| Phase 5 `半角标点 ',' (应为 '，')` | 中文语境用了英文标点 | 按提示位置改全角（中文句内逗号/冒号用全角） |
| 交叉引用显示 `??` | 没先编译，`main.aux` 缺失或过期 | `xelatex main.tex` 后重新构建（§3.3） |

---

## 7. 附录

### 7.1 流水线一图流

```
main.tex ──latexpand──> 扁平 LaTeX ──pandoc(--reference-doc=内置模板)──> 初版 docx
                                                                          │
              OOXML 后处理（目录/分页/题注/编号/分节/页码/字体）<──────────┘
                                  │
                      四道回归 + 结构校验 ──> main_版式1.docx
```

### 7.2 内置模板从哪来

skill 自带 `assets/swun_banshi1_reference.docx`（约 91KB）：由
`scripts/make_slim_template.py` 从完整参考论文瘦身生成——保留全部样式、
编号、页眉页脚、封面和题注格式样本，剥离正文与图片（7.4MB → 91KB）。
需要换参考模板时跑该脚本重新生成即可。

### 7.3 环境变量速查

| 变量 | 作用 | 默认 |
|------|------|------|
| `SWUN_REFERENCE_DOCX` | 指定参考模板（最高优先级） | 不设，走解析链 |
| `SWUN_CSL` | 参考文献 CSL 样式 | skill 内置 GB/T 7714-2015 |
| `SWUN_BIB` | bib 文件路径 | `backmatter/references.bib` |
| `SWUN_TABLE_VERIFY_ALLOW_EMPTY` | 无三线表时表格校验是否放行 | `1`（放行） |

### 7.4 FAQ

**Q: 必须用 Claude Code 吗？**
不必须。`/swun-docx` 是主路径，但 §4.2 的 `main.sh` 命令完全独立可跑；
区别是出错时没有 AI 帮你自动定位修复。

**Q: 构建会改我的 LaTeX 源文件吗？**
不会。构建只读 `.tex`/`.bib`，所有中间产物在临时区，这是 skill 的硬约束。

**Q: Word 打开时提示「是否更新域」？**
点「是」。目录页码是 Word 域，首次打开更新一次即可。

**Q: 我论文目录里已有一份参考论文 docx，会用哪个模板？**
解析链第 2 级会优先用论文目录里的参考论文；删掉它就回落到 skill 内置模板。
两者构建产物经核验语义等价。
