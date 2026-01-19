#!/bin/bash
# sync.sh - 同步本地文章到 NotebookLM 知识库
# 自动检测环境：有 Obsidian 时运行分类脚本，否则从 Git 拉取
#
# 用法: bash sync.sh [--skip-classify] [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$SKILL_DIR/config.json"

# ========== 配置解析 ==========
if [ ! -f "$CONFIG_FILE" ]; then
    echo "错误: 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

REPO_URL=$(jq -r '.articles_repo_url' "$CONFIG_FILE")
NOTEBOOK_ID=$(jq -r '.notebooklm_notebook_id' "$CONFIG_FILE")
NOTEBOOK_NAME=$(jq -r '.notebooklm_notebook_name' "$CONFIG_FILE")

# ========== 参数解析 ==========
SKIP_CLASSIFY=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --skip-classify)
            SKIP_CLASSIFY=true
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
    esac
done

# ========== 环境检测函数 ==========
detect_environment() {
    # 尝试查找 Dropbox 目录（跨平台）
    local dropbox_paths=(
        "$HOME/Dropbox"
        "$HOME/dropbox"
        "/mnt/dropbox"
    )

    DROPBOX_DIR=""
    for path in "${dropbox_paths[@]}"; do
        if [ -d "$path" ]; then
            DROPBOX_DIR="$path"
            break
        fi
    done

    # 检测 markdown_converter 项目
    MARKDOWN_CONVERTER=""
    if [ -n "$DROPBOX_DIR" ]; then
        local converter_path="$DROPBOX_DIR/markdown_converter"
        if [ -d "$converter_path" ] && [ -f "$converter_path/classify_published_articles.py" ]; then
            MARKDOWN_CONVERTER="$converter_path"
        fi
    fi

    # 检测本地文章仓库
    LOCAL_REPO=""
    if [ -n "$DROPBOX_DIR" ]; then
        local repo_path="$DROPBOX_DIR/cn_articles_published"
        if [ -d "$repo_path/.git" ]; then
            LOCAL_REPO="$repo_path"
        fi
    fi

    # 设置文章目录
    if [ -n "$LOCAL_REPO" ]; then
        ARTICLES_DIR="$LOCAL_REPO/all"
    else
        # 使用临时目录
        ARTICLES_DIR="/tmp/cn_articles_published/all"
    fi

    # 判断模式
    if [ -n "$MARKDOWN_CONVERTER" ] && [ -n "$LOCAL_REPO" ]; then
        ENV_MODE="local"
    else
        ENV_MODE="remote"
    fi
}

# ========== Git 操作函数 ==========
git_pull_repo() {
    local target_dir="/tmp/cn_articles_published"

    if [ -d "$target_dir/.git" ]; then
        echo "  更新已有克隆..."
        cd "$target_dir"
        git pull --quiet
    else
        echo "  克隆仓库..."
        rm -rf "$target_dir"
        git clone --quiet --depth 1 "$REPO_URL" "$target_dir"
    fi

    ARTICLES_DIR="$target_dir/all"
}

git_push_repo() {
    if [ -z "$LOCAL_REPO" ]; then
        return
    fi

    cd "$LOCAL_REPO"

    # 检查是否有变更
    git add -A
    if git diff --cached --quiet; then
        echo "  无变更需要提交"
        return
    fi

    # 提交并推送
    local commit_msg="chore: 自动同步文章分类 $(date '+%Y-%m-%d %H:%M:%S')"
    git commit -m "$commit_msg" --quiet
    git push --quiet
    echo "  已推送到远端仓库"
}

# ========== 分类脚本 ==========
run_classify_script() {
    if [ -z "$MARKDOWN_CONVERTER" ]; then
        echo "  错误: 未找到 markdown_converter"
        return 1
    fi

    export PYTHONPATH="$MARKDOWN_CONVERTER:$PYTHONPATH"
    cd "$MARKDOWN_CONVERTER"
    python classify_published_articles.py 2>&1 | tail -5
}

# ========== 主流程 ==========
echo "======================================"
echo "同步 NotebookLM 知识库"
echo "======================================"

# 检测环境
detect_environment

echo "笔记本: $NOTEBOOK_NAME"
echo "模式: $ENV_MODE"
if [ "$ENV_MODE" = "local" ]; then
    echo "本地仓库: $LOCAL_REPO"
    echo "分类脚本: $MARKDOWN_CONVERTER"
fi
echo ""

# 步骤 1: 获取文章（分类或拉取）
if [ "$ENV_MODE" = "local" ]; then
    if [ "$SKIP_CLASSIFY" = false ]; then
        echo "[1/4] 运行文章分类脚本..."
        if [ "$DRY_RUN" = false ]; then
            run_classify_script
            echo ""
            echo "  推送分类结果到 Git..."
            git_push_repo
        else
            echo "  [DRY RUN] 跳过分类和推送"
        fi
    else
        echo "[1/4] 跳过文章分类（--skip-classify）"
    fi
else
    echo "[1/4] 从远端仓库拉取文章..."
    if [ "$DRY_RUN" = false ]; then
        git_pull_repo
    else
        echo "  [DRY RUN] 跳过拉取"
    fi
fi
echo ""

# 步骤 2: 获取本地文件列表
echo "[2/4] 获取本地文件列表..."
LOCAL_FILES=$(mktemp)
if [ -d "$ARTICLES_DIR" ]; then
    # 使用 find + -print0 + xargs -0 正确处理带空格的文件名
    # 使用 LC_ALL=C 确保排序一致性（中文 locale 排序顺序不同会导致 comm 失效）
    find "$ARTICLES_DIR" -maxdepth 1 -name "*.md" -print0 | xargs -0 -I {} basename {} | LC_ALL=C sort > "$LOCAL_FILES"
    LOCAL_COUNT=$(wc -l < "$LOCAL_FILES" | tr -d ' ')
    echo "  本地文章: $LOCAL_COUNT 篇"
else
    echo "  错误: 文章目录不存在: $ARTICLES_DIR"
    exit 1
fi
echo ""

# 步骤 3: 获取 NotebookLM sources 列表
echo "[3/4] 获取 NotebookLM sources 列表..."
notebooklm use "$NOTEBOOK_ID" > /dev/null 2>&1
NOTEBOOKLM_FILES=$(mktemp)
# 使用 LC_ALL=C 确保与本地列表排序一致
notebooklm source list --json 2>/dev/null | jq -r '.sources[].title' | LC_ALL=C sort > "$NOTEBOOKLM_FILES"
NOTEBOOKLM_COUNT=$(wc -l < "$NOTEBOOKLM_FILES" | tr -d ' ')
echo "  NotebookLM sources: $NOTEBOOKLM_COUNT 篇"
echo ""

# 步骤 4: 对比并添加新文件（严格匹配）
echo "[4/4] 对比分析..."
NEW_FILES=$(mktemp)
# 使用 LC_ALL=C 确保 comm 比较正确
LC_ALL=C comm -23 "$LOCAL_FILES" "$NOTEBOOKLM_FILES" > "$NEW_FILES"
NEW_COUNT=$(wc -l < "$NEW_FILES" | tr -d ' ')

if [ "$NEW_COUNT" -eq 0 ]; then
    echo "  知识库已同步，无需添加新文件。"
else
    echo "  发现 $NEW_COUNT 篇新文章需要添加："
    echo ""
    cat "$NEW_FILES" | while read -r file; do
        echo "    - $file"
    done
    echo ""

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] 跳过实际添加操作"
    else
        echo "  开始添加新文章到 NotebookLM..."
        cat "$NEW_FILES" | while read -r file; do
            FILE_PATH="$ARTICLES_DIR/$file"
            if [ -f "$FILE_PATH" ]; then
                echo "    添加: $file"
                notebooklm source add "$FILE_PATH" > /dev/null 2>&1 || echo "      [失败]"
            fi
        done
        echo ""
        echo "  添加完成！"
    fi
fi

# 清理临时文件
rm -f "$LOCAL_FILES" "$NOTEBOOKLM_FILES" "$NEW_FILES"

echo ""
echo "======================================"
echo "同步完成"
echo "======================================"
