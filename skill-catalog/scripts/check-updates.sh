#!/bin/bash
# ============================================================
# skill-catalog check-updates
# 检查已安装的 Claude Code plugins 是否有 GitHub 更新
# ============================================================

set -e

# ==================== 配置 ====================
PLUGINS_DIR="$HOME/.claude/plugins"
INSTALLED_FILE="$PLUGINS_DIR/installed_plugins.json"
MARKETPLACES_FILE="$PLUGINS_DIR/known_marketplaces.json"

# 代理配置（可选）
if [[ -n "$https_proxy" ]]; then
    CURL_PROXY="--proxy $https_proxy"
else
    CURL_PROXY=""
fi

# ==================== 工具函数 ====================
check_dependencies() {
    if ! command -v jq &> /dev/null; then
        echo "错误: 需要安装 jq"
        echo "  brew install jq"
        exit 1
    fi
}

get_github_latest_commit() {
    local repo="$1"
    local result
    result=$(curl -s $CURL_PROXY "https://api.github.com/repos/$repo/commits/main" 2>/dev/null)

    if echo "$result" | jq -e '.sha' &>/dev/null; then
        local sha=$(echo "$result" | jq -r '.sha[:8]')
        local msg=$(echo "$result" | jq -r '.commit.message | split("\n")[0]')
        local date=$(echo "$result" | jq -r '.commit.author.date[:10]')
        echo "$sha|$msg|$date"
    else
        echo "error|无法获取|N/A"
    fi
}

get_github_latest_tag() {
    local repo="$1"
    local result
    result=$(curl -s $CURL_PROXY "https://api.github.com/repos/$repo/tags?per_page=1" 2>/dev/null)

    if echo "$result" | jq -e '.[0].name' &>/dev/null; then
        echo "$result" | jq -r '.[0].name // "无 tag"'
    else
        echo "无 tag"
    fi
}

# ==================== 主逻辑 ====================
check_dependencies

echo "=== 🔄 GitHub Skill/Plugin 更新检查 ==="
echo ""

# -------------------- 检查已安装 Plugins --------------------
echo "【已安装 Plugins】"
echo ""

if [[ -f "$INSTALLED_FILE" ]]; then
    # 解析已安装的 plugins
    plugins=$(jq -r '.plugins | keys[]' "$INSTALLED_FILE" 2>/dev/null)

    printf "%-35s %-12s %-12s %-8s\n" "Plugin" "本地版本" "安装日期" "Commit"
    printf "%-35s %-12s %-12s %-8s\n" "-----------------------------------" "------------" "------------" "--------"

    while IFS= read -r plugin; do
        [[ -z "$plugin" ]] && continue

        version=$(jq -r ".plugins[\"$plugin\"][0].version // \"unknown\"" "$INSTALLED_FILE")
        installed_at=$(jq -r ".plugins[\"$plugin\"][0].installedAt[:10] // \"unknown\"" "$INSTALLED_FILE")
        commit_sha=$(jq -r ".plugins[\"$plugin\"][0].gitCommitSha[:8] // \"N/A\"" "$INSTALLED_FILE")

        printf "%-35s %-12s %-12s %-8s\n" "$plugin" "$version" "$installed_at" "$commit_sha"
    done <<< "$plugins"
else
    echo "  未找到已安装 plugins 配置文件"
fi

echo ""

# -------------------- 检查 Marketplaces 远程状态 --------------------
echo "【Marketplaces 远程状态】"
echo ""

if [[ -f "$MARKETPLACES_FILE" ]]; then
    printf "%-25s %-35s %-10s %-12s %s\n" "Marketplace" "GitHub 仓库" "最新 Commit" "更新日期" "说明"
    printf "%-25s %-35s %-10s %-12s %s\n" "-------------------------" "-----------------------------------" "----------" "------------" "--------------------"

    marketplaces=$(jq -r 'keys[]' "$MARKETPLACES_FILE" 2>/dev/null)

    while IFS= read -r marketplace; do
        [[ -z "$marketplace" ]] && continue

        repo=$(jq -r ".[\"$marketplace\"].source.repo // \"unknown\"" "$MARKETPLACES_FILE")

        if [[ "$repo" != "unknown" && "$repo" != "null" ]]; then
            # 获取远程最新信息
            remote_info=$(get_github_latest_commit "$repo")
            IFS='|' read -r sha msg date <<< "$remote_info"

            # 截断过长的消息
            if [[ ${#msg} -gt 30 ]]; then
                msg="${msg:0:27}..."
            fi

            printf "%-25s %-35s %-10s %-12s %s\n" "$marketplace" "$repo" "$sha" "$date" "$msg"
        fi
    done <<< "$marketplaces"
else
    echo "  未找到 marketplaces 配置文件"
fi

echo ""

# -------------------- 对比并给出建议 --------------------
echo "【更新建议】"
echo ""

needs_update=false

if [[ -f "$INSTALLED_FILE" && -f "$MARKETPLACES_FILE" ]]; then
    # 检查 superpowers
    if jq -e '.plugins["superpowers@superpowers-marketplace"]' "$INSTALLED_FILE" &>/dev/null; then
        local_version=$(jq -r '.plugins["superpowers@superpowers-marketplace"][0].version' "$INSTALLED_FILE")
        local_sha=$(jq -r '.plugins["superpowers@superpowers-marketplace"][0].gitCommitSha[:8] // "N/A"' "$INSTALLED_FILE")

        remote_info=$(get_github_latest_commit "obra/superpowers-marketplace")
        IFS='|' read -r remote_sha msg date <<< "$remote_info"

        if [[ "$local_sha" != "$remote_sha" && "$remote_sha" != "error" ]]; then
            echo "  ⚠️  superpowers: 本地 $local_sha → 远程 $remote_sha"
            echo "      更新命令: /plugins update superpowers@superpowers-marketplace"
            needs_update=true
        fi
    fi

    # 检查 code-simplifier
    if jq -e '.plugins["code-simplifier@claude-plugins-official"]' "$INSTALLED_FILE" &>/dev/null; then
        local_version=$(jq -r '.plugins["code-simplifier@claude-plugins-official"][0].version' "$INSTALLED_FILE")

        remote_info=$(get_github_latest_commit "anthropics/claude-plugins-official")
        IFS='|' read -r remote_sha msg date <<< "$remote_info"

        if [[ "$remote_sha" != "error" ]]; then
            echo "  ℹ️  claude-plugins-official: 最新 commit $remote_sha ($date)"
            echo "      检查是否有新 plugin: /plugins list claude-plugins-official"
        fi
    fi
fi

if [[ "$needs_update" == false ]]; then
    echo "  ✅ 所有已安装 plugins 均为最新版本"
fi

echo ""
echo "=== 检查完成 ==="
