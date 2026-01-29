#!/bin/bash
# ============================================================
# changelog: 在当前目录追加每日变更记录
# ============================================================

set -e

# ==================== 配置 ====================
DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M:%S)
TIMEZONE=$(date +%z | sed 's/\([+-][0-9][0-9]\)\([0-9][0-9]\)/\1:\2/')
TIMESTAMP="${DATE}T${TIME}${TIMEZONE}"

# ==================== 参数解析 ====================
WORK_DIR="${1:-.}"
TASK_NAME="${2:-未命名任务}"
CHANGES="${3:-}"
FILES="${4:-}"
VERIFICATION="${5:-}"
ISSUES="${6:-}"

# 转换为绝对路径
WORK_DIR=$(cd "$WORK_DIR" && pwd)

# changelog 目录和文件
CHANGELOG_DIR="${WORK_DIR}/changelog"
CHANGELOG_FILE="${CHANGELOG_DIR}/${DATE}.md"

# ==================== 工具函数 ====================
create_changelog_dir() {
    if [ ! -d "$CHANGELOG_DIR" ]; then
        mkdir -p "$CHANGELOG_DIR"
        echo "创建 changelog 目录: $CHANGELOG_DIR"
    fi
}

create_daily_file() {
    if [ ! -f "$CHANGELOG_FILE" ]; then
        cat > "$CHANGELOG_FILE" << EOF
# Changelog - ${DATE}

> 本文件记录 ${DATE} 的所有变更。

---

EOF
        echo "创建每日 changelog: $CHANGELOG_FILE"
    fi
}

# 将逗号分隔的字符串转换为 Markdown 列表
to_list() {
    local input="$1"
    local prefix="${2:-}"

    if [ -z "$input" ]; then
        return
    fi

    # 使用 IFS 分割并输出列表项
    IFS=',' read -ra items <<< "$input"
    for item in "${items[@]}"; do
        # 去除首尾空格
        item=$(echo "$item" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ -n "$item" ]; then
            echo "- ${prefix}${item}"
        fi
    done
}

append_entry() {
    local entry=""

    # 标题行
    entry="## ${TIME} - ${TASK_NAME}\n\n"

    # 关键改动
    if [ -n "$CHANGES" ]; then
        entry+="**关键改动:**\n"
        entry+="$(to_list "$CHANGES")\n\n"
    fi

    # 涉及文件
    if [ -n "$FILES" ]; then
        entry+="**涉及文件:**\n"
        # 文件路径用反引号包裹
        IFS=',' read -ra file_items <<< "$FILES"
        for file in "${file_items[@]}"; do
            file=$(echo "$file" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
            if [ -n "$file" ]; then
                entry+="- \`${file}\`\n"
            fi
        done
        entry+="\n"
    fi

    # 验证结果
    if [ -n "$VERIFICATION" ]; then
        entry+="**验证:** ${VERIFICATION}\n\n"
    fi

    # 遗留问题
    if [ -n "$ISSUES" ]; then
        entry+="**遗留问题:** ${ISSUES}\n\n"
    fi

    entry+="---\n\n"

    # 追加到文件
    echo -e "$entry" >> "$CHANGELOG_FILE"
}

# ==================== JSON 输出模式 ====================
output_json() {
    cat << EOF
{
  "status": "success",
  "changelog_dir": "$CHANGELOG_DIR",
  "changelog_file": "$CHANGELOG_FILE",
  "date": "$DATE",
  "time": "$TIME",
  "timestamp": "$TIMESTAMP",
  "task": "$TASK_NAME"
}
EOF
}

# ==================== 主逻辑 ====================
main() {
    create_changelog_dir
    create_daily_file

    if [ -n "$TASK_NAME" ] && [ "$TASK_NAME" != "未命名任务" ]; then
        append_entry
        echo "已追加变更记录到: $CHANGELOG_FILE"
    fi

    # 如果有 --json 参数，输出 JSON
    if [[ "$*" == *"--json"* ]]; then
        output_json
    fi
}

main "$@"
