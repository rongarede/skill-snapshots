#!/bin/bash
# ============================================================
# skill-snapshot sync-configs - 同步所有 CLAUDE.md 配置文件
# ============================================================

set -e

LOCAL_REPO="$HOME/.claude/skill-snapshots"
CONFIGS_DIR="$LOCAL_REPO/claude-configs"

# ==================== 配置映射 ====================
# 格式: "源路径|目标子目录"
declare -a CONFIG_MAPPINGS=(
    # 核心配置
    "$HOME/.claude/CLAUDE.md|global"
    "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/CLAUDE.md|obsidian"

    # Solidity 项目
    "$HOME/SolidityProject/面试文档/CLAUDE.md|solidity/interview"
    "$HOME/SolidityProject/denglian/modoule3/NFTMarket/CLAUDE.md|solidity/denglian-nft-market"
    "$HOME/SolidityProject/denglian/modoule6/launchpund/CLAUDE.md|solidity/denglian-launchpad"
    "$HOME/SolidityProject/denglian/modoule6/DAOBank/claude.md|solidity/denglian-daobank"
    "$HOME/SolidityProject/denglian/modoule7/claude.md|solidity/denglian-module7"

    # Solana 项目
    "$HOME/SolanaRust/IPFlow/programs/candy-machine/program/CLAUDE.md|solana/ipflow-candy-machine"
    "$HOME/SolanaRust/ipflow-v3/CLAUDE.md|solana/ipflow-v3"
    "$HOME/SolanaRust/metaplex-program-library/candy-machine/program/src/CLAUDE.md|solana/metaplex-candy-machine"

    # 其他项目
    "$HOME/v2x_ws/bisai/sumo_intersection_viz/CLAUDE.md|misc/sumo-viz"
)

# ==================== 工具函数 ====================
log_info() {
    echo "[INFO] $1"
}

log_success() {
    echo "[✓] $1"
}

log_skip() {
    echo "[SKIP] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

# ==================== 主逻辑 ====================
main() {
    # 检查仓库是否已初始化
    if [ ! -d "$LOCAL_REPO/.git" ]; then
        log_error "仓库未初始化，请先执行 init"
        exit 1
    fi

    cd "$LOCAL_REPO"

    # 拉取最新
    git pull --quiet origin main 2>/dev/null || true

    echo "=== 同步 CLAUDE.md 配置文件 ==="
    echo ""

    # 创建配置目录
    mkdir -p "$CONFIGS_DIR"

    # 统计
    local synced=0
    local skipped=0
    local total=${#CONFIG_MAPPINGS[@]}

    # 遍历配置映射
    for mapping in "${CONFIG_MAPPINGS[@]}"; do
        local src="${mapping%%|*}"
        local dest_subdir="${mapping##*|}"
        local dest_dir="$CONFIGS_DIR/$dest_subdir"
        local dest_file="$dest_dir/CLAUDE.md"

        # 检查源文件是否存在
        if [ ! -f "$src" ]; then
            log_skip "$dest_subdir (源文件不存在)"
            ((skipped++))
            continue
        fi

        # 创建目标目录
        mkdir -p "$dest_dir"

        # 复制文件
        cp "$src" "$dest_file"
        log_success "$dest_subdir"
        ((synced++))
    done

    echo ""
    echo "=== 生成索引 ==="

    # 生成 README.md
    generate_readme

    echo ""
    echo "=== 提交变更 ==="

    # Git 操作
    git add claude-configs/

    # 检查是否有变化
    if git diff --cached --quiet; then
        log_info "无变化 - 所有配置与远程一致"
        echo ""
        echo "统计: 同步 $synced, 跳过 $skipped, 总计 $total"
        exit 0
    fi

    # 提交并推送
    local commit_msg="sync: update CLAUDE.md configs ($(date '+%Y-%m-%d %H:%M'))"
    git commit --quiet -m "$commit_msg"
    git push --quiet origin main

    log_success "已推送到 GitHub"
    echo ""
    echo "统计: 同步 $synced, 跳过 $skipped, 总计 $total"
}

generate_readme() {
    local readme="$CONFIGS_DIR/README.md"
    local file_count=$(find "$CONFIGS_DIR" -name "CLAUDE.md" -type f | wc -l | tr -d ' ')

    cat > "$readme" << 'HEADER'
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

HEADER

    echo "## 最后更新" >> "$readme"
    echo "" >> "$readme"
    echo "- **日期**: $(date '+%Y-%m-%d %H:%M')" >> "$readme"
    echo "- **文件数**: $file_count" >> "$readme"

    log_success "README.md 已更新"
}

main "$@"
