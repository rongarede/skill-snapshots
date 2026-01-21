# Claude 配置文件备份

本目录备份了各项目的 `CLAUDE.md` 配置文件。

## 目录结构

```
claude-configs/
├── global/              # 全局配置 (~/.claude/CLAUDE.md)
├── obsidian/            # Obsidian 知识库
├── solidity/            # Solidity 项目
│   ├── interview/       # 面试文档
│   ├── denglian-nft-market/
│   ├── denglian-launchpad/
│   ├── denglian-daobank/
│   └── denglian-module7/
├── solana/              # Solana/Rust 项目
│   ├── ipflow-candy-machine/
│   ├── ipflow-v3/
│   └── metaplex-candy-machine/
└── misc/                # 其他项目
    └── sumo-viz/        # SUMO 交通仿真可视化
```

## 文件来源映射

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

## 同步命令

```bash
bash ~/.claude/skills/skill-snapshot/scripts/sync-configs.sh
```

或通过 Claude Code:

```
/skill-snapshot sync-configs
```

## 最后更新

- **日期**: 2026-01-21 14:04
- **文件数**: 11
