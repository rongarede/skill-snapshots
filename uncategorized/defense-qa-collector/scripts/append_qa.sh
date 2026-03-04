#!/bin/bash
# ============================================================
# defense-qa-collector: 追加答辩问题到 Obsidian 预设文件
# ============================================================

set -e

# ==================== 参数 ====================
TARGET_FILE="${1:-/Users/bit/Obsidian/100_Projects/Active/Project_SWUN_Thesis/答辩问题预设.md}"
QUESTION_TITLE="$2"
QUESTION_BODY="$3"

if [ -z "$QUESTION_TITLE" ] || [ -z "$QUESTION_BODY" ]; then
    echo "用法: append_qa.sh [目标文件] <问题标题> <问题内容(markdown)>"
    echo "  目标文件默认: /Users/bit/Obsidian/100_Projects/Active/Project_SWUN_Thesis/答辩问题预设.md"
    exit 1
fi

# ==================== 工具函数 ====================

# 获取当前最大 Q 编号
get_max_q_number() {
    if [ ! -f "$TARGET_FILE" ]; then
        echo 0
        return
    fi
    local max_num
    max_num=$(grep -oE '^## Q([0-9]+)' "$TARGET_FILE" | grep -oE '[0-9]+' | sort -n | tail -1)
    echo "${max_num:-0}"
}

# 创建文件（如果不存在）
ensure_file_exists() {
    if [ ! -f "$TARGET_FILE" ]; then
        mkdir -p "$(dirname "$TARGET_FILE")"
        cat > "$TARGET_FILE" << 'HEADER'
# 答辩问题预设

收集论文写作过程中预判的答辩问题，附带准备好的回答框架。
HEADER
        echo "已创建文件: $TARGET_FILE"
    fi
}

# ==================== 主逻辑 ====================
main() {
    ensure_file_exists

    local current_max
    current_max=$(get_max_q_number)
    local next_num=$((current_max + 1))

    # 追加到文件末尾
    {
        echo ""
        echo "---"
        echo ""
        echo "## Q${next_num}: ${QUESTION_TITLE}"
        echo ""
        echo "$QUESTION_BODY"
    } >> "$TARGET_FILE"

    echo "已追加 Q${next_num}: ${QUESTION_TITLE}"
    echo "文件: ${TARGET_FILE}"
}

main "$@"
