# Claude 配置文件备份

本目录备份了各项目的 `CLAUDE.md` 配置文件和自定义子代理。

## 目录结构

```
skill-snapshots/
├── claude-configs/      # CLAUDE.md 配置文件
│   ├── global/          # 全局配置 (~/.claude/CLAUDE.md)
│   ├── obsidian/        # Obsidian 知识库
│   ├── solidity/        # Solidity 项目
│   │   ├── interview/
│   │   ├── denglian-nft-market/
│   │   ├── denglian-launchpad/
│   │   ├── denglian-daobank/
│   │   └── denglian-module7/
│   ├── solana/          # Solana/Rust 项目
│   │   ├── ipflow-candy-machine/
│   │   ├── ipflow-v3/
│   │   └── metaplex-candy-machine/
│   └── misc/            # 其他项目
│       └── sumo-viz/
└── agents/              # 自定义子代理
    ├── code-reviewer.md
    ├── codex-executor.md
    ├── codex-reviewer.md
    └── research-analyst.md
```

## 子代理列表

| 子代理 | 说明 |
|--------|------|
| `code-reviewer` | tools: Read, Write, Edit, Bash, Glob, Grep... |
| `codex-executor` | tools: Bash, Read, Glob, Grep... |
| `codex-reviewer` | tools: Bash, Read, Glob, Grep... |
| `research-analyst` | 增强版研究分析师，支持 NotebookLM 查询、论文... |

## 配置文件来源映射

| 备份路径 | 原始路径 |
|----------|----------|
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md` |
| `obsidian/CLAUDE.md` | `~/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/CLAUDE.md` |
| `solidity/interview/CLAUDE.md` | `~/SolidityProject/面试文档/CLAUDE.md` |
| `solidity/denglian-nft-market/CLAUDE.md` | `~/SolidityProject/denglian/modoule3/NFTMarket/CLAUDE.md` |
| `solidity/denglian-launchpad/CLAUDE.md` | `~/SolidityProject/denglian/modoule6/launchpund/CLAUDE.md` |
| `solidity/denglian-daobank/CLAUDE.md` | `~/SolidityProject/denglian/modoule6/DAOBank/claude.md` |
| `solidity/denglian-module7/CLAUDE.md` | `~/SolidityProject/denglian/modoule7/claude.md` |
| `solana/ipflow-candy-machine/CLAUDE.md` | `~/SolanaRust/IPFlow/programs/candy-machine/program/CLAUDE.md` |
| `solana/ipflow-v3/CLAUDE.md` | `~/SolanaRust/ipflow-v3/CLAUDE.md` |
| `solana/metaplex-candy-machine/CLAUDE.md` | `~/SolanaRust/metaplex-program-library/candy-machine/program/src/CLAUDE.md` |
| `misc/sumo-viz/CLAUDE.md` | `~/v2x_ws/bisai/sumo_intersection_viz/CLAUDE.md` |
| `agents/*.md` | `~/.claude/agents/*.md` |

## 同步命令

```bash
bash ~/.claude/skills/skill-snapshot/scripts/sync-configs.sh
```

或通过 Claude Code:

```
/skill-snapshot sync-configs
```

## 最后更新

- **日期**: 2026-01-21 14:30
- **配置文件数**: 11
- **子代理数**: 4
