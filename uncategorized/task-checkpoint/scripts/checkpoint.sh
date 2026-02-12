#!/bin/bash
# ============================================================
# task-checkpoint: 任务完成后自动 commit + push
# 用法: checkpoint.sh <task-id> <commit-message> [files...]
# ============================================================

set -e

# ==================== 参数解析 ====================
TASK_ID="${1:?错误: 需要提供 task-id（如 T-FIX-02）}"
COMMIT_MSG="${2:?错误: 需要提供 commit message}"
shift 2
FILES=("$@")

# ==================== 颜色 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ==================== 工具函数 ====================
log_info()  { echo -e "${GREEN}[checkpoint]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[checkpoint]${NC} $1"; }
log_error() { echo -e "${RED}[checkpoint]${NC} $1"; }

check_git_repo() {
    if ! git rev-parse --is-inside-work-tree &>/dev/null; then
        log_error "当前目录不是 git 仓库"
        exit 1
    fi
}

check_large_files() {
    local threshold=$((10 * 1024 * 1024))  # 10MB
    local large_files=()
    for f in "$@"; do
        if [ -f "$f" ]; then
            local size
            size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
            if [ "$size" -gt "$threshold" ]; then
                large_files+=("$f ($(( size / 1024 / 1024 ))MB)")
            fi
        fi
    done
    if [ ${#large_files[@]} -gt 0 ]; then
        log_warn "以下文件超过 10MB:"
        for f in "${large_files[@]}"; do
            echo "  - $f"
        done
        echo ""
    fi
}

# ==================== 主逻辑 ====================
main() {
    check_git_repo

    local branch
    branch=$(git branch --show-current)
    local remote
    remote=$(git remote | head -1)

    log_info "Task: ${TASK_ID}"
    log_info "Branch: ${branch}"

    # 暂存文件
    if [ ${#FILES[@]} -gt 0 ]; then
        check_large_files "${FILES[@]}"
        log_info "暂存 ${#FILES[@]} 个指定文件..."
        git add "${FILES[@]}"
    else
        # 默认暂存所有已修改的跟踪文件（不包括 untracked）
        log_info "暂存所有已修改的跟踪文件..."
        git add -u
    fi

    # 检查是否有变更
    if git diff --cached --quiet; then
        log_warn "没有需要提交的变更"
        exit 0
    fi

    # 显示暂存摘要
    local file_count
    file_count=$(git diff --cached --numstat | wc -l | tr -d ' ')
    log_info "暂存了 ${file_count} 个文件"

    # 提交
    log_info "提交中..."
    git commit -m "${COMMIT_MSG}"

    local commit_hash
    commit_hash=$(git rev-parse --short HEAD)

    # 推送
    log_info "推送到 ${remote}/${branch}..."
    if git push 2>&1; then
        log_info "推送成功"
    else
        log_error "推送失败，请手动处理"
        exit 1
    fi

    # 输出摘要
    echo ""
    echo "============================================================"
    echo -e "${GREEN}✅ Checkpoint: ${TASK_ID}${NC}"
    echo "  - Commit: ${commit_hash} ${COMMIT_MSG}"
    echo "  - Push: ${branch} → ${remote}"
    echo "  - Files: ${file_count}"
    echo "============================================================"
}

main "$@"
