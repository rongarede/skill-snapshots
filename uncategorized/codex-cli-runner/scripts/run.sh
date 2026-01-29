#!/bin/bash
# ============================================================
# run.sh - Codex CLI 执行包装器
# 用法: run.sh "任务描述" [--extract message|exit_code|all]
# ============================================================

set -e

# ==================== 帮助信息 ====================
show_help() {
    cat << 'EOF'
Codex CLI 执行包装器

用法:
    run.sh "任务描述"                        # 执行任务，输出完整 JSON
    run.sh "任务描述" --extract message      # 只提取最终消息
    run.sh "任务描述" --extract exit_code    # 只提取退出码
    run.sh "任务描述" --extract all          # 输出完整 JSON（默认）

选项:
    --extract message    提取 agent 最终回复
    --extract exit_code  提取命令退出码
    --extract all        输出完整 JSONL（默认）
    -h, --help           显示帮助信息

依赖:
    - codex CLI (已安装并配置)
    - jq (用于 JSON 解析)

示例:
    run.sh "列出当前目录文件"
    run.sh "运行测试" --extract message
    run.sh "检查 git 状态" --extract exit_code
EOF
    exit 0
}

# ==================== 依赖检查 ====================
check_deps() {
    if ! command -v codex &>/dev/null; then
        echo "❌ 未找到 codex CLI"
        echo "   安装: npm install -g @anthropic/codex-cli"
        exit 1
    fi

    if ! command -v jq &>/dev/null; then
        echo "❌ 未找到 jq"
        echo "   macOS: brew install jq"
        echo "   Linux: apt install jq"
        exit 1
    fi
}

# ==================== 主逻辑 ====================
main() {
    local task=""
    local extract_mode="all"

    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                ;;
            --extract)
                extract_mode="$2"
                shift 2
                ;;
            *)
                if [[ -z "$task" ]]; then
                    task="$1"
                fi
                shift
                ;;
        esac
    done

    # 校验参数
    if [[ -z "$task" ]]; then
        show_help
    fi

    # 校验 extract_mode
    case "$extract_mode" in
        message|exit_code|all) ;;
        *)
            echo "❌ 无效的 --extract 值: $extract_mode"
            echo "   有效值: message, exit_code, all"
            exit 1
            ;;
    esac

    # 依赖检查
    check_deps

    # 执行 codex
    local output
    output=$(codex exec --yolo --json "$task" 2>/dev/null) || {
        echo "❌ codex 执行失败"
        exit 1
    }

    # 根据模式提取输出
    case "$extract_mode" in
        message)
            echo "$output" | jq -s 'map(select(.msg.type == "agent_message")) | last | .msg.message // "无消息"'
            ;;
        exit_code)
            echo "$output" | jq -s 'map(select(.msg.type == "exec_command_end")) | last | .msg.exit_code // "无命令执行"'
            ;;
        all)
            echo "$output"
            ;;
    esac
}

main "$@"
