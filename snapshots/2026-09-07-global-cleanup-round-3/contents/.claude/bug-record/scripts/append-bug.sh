#!/bin/bash
# ============================================================
# append-bug: 追加 bug 记录到 bugs.jsonl
# ============================================================

set -e

# ==================== 参数解析 ====================
WORK_DIR="${1:-.}"
TITLE="${2:-未命名 Bug}"
SYMPTOM="${3:-}"
ROOT_CAUSE="${4:-}"
FIX="${5:-}"
FILES_CHANGED="${6:-}"
REPRO_STEPS="${7:-}"
VERIFICATION="${8:-}"
IMPACT="${9:-}"
PREVENTION="${10:-}"
TAGS="${11:-}"
FOLLOWUPS="${12:-}"

# 转换为绝对路径
WORK_DIR=$(cd "$WORK_DIR" && pwd)
BUGS_FILE="${WORK_DIR}/bugs.jsonl"

# ==================== 生成记录 ====================
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || echo "bug-$(date +%s)")

# 构建 JSON（使用 jq 确保正确转义）
if command -v jq &> /dev/null; then
    jq -n -c \
        --arg ts "$TS" \
        --arg id "$ID" \
        --arg title "$TITLE" \
        --arg symptom "$SYMPTOM" \
        --arg root_cause "$ROOT_CAUSE" \
        --arg fix "$FIX" \
        --arg files_changed "$FILES_CHANGED" \
        --arg repro_steps "$REPRO_STEPS" \
        --arg verification "$VERIFICATION" \
        --arg impact "$IMPACT" \
        --arg prevention "$PREVENTION" \
        --arg tags "$TAGS" \
        --arg followups "$FOLLOWUPS" \
        '{
            ts: $ts,
            id: $id,
            title: $title,
            symptom: $symptom,
            root_cause: $root_cause,
            fix: $fix,
            files_changed: $files_changed,
            repro_steps: $repro_steps,
            verification: $verification,
            impact: $impact,
            prevention: $prevention,
            tags: $tags,
            followups: $followups
        }' >> "$BUGS_FILE"
else
    # 无 jq 时使用简单转义
    echo "{\"ts\":\"$TS\",\"id\":\"$ID\",\"title\":\"$TITLE\",\"symptom\":\"$SYMPTOM\",\"root_cause\":\"$ROOT_CAUSE\",\"fix\":\"$FIX\",\"files_changed\":\"$FILES_CHANGED\",\"repro_steps\":\"$REPRO_STEPS\",\"verification\":\"$VERIFICATION\",\"impact\":\"$IMPACT\",\"prevention\":\"$PREVENTION\",\"tags\":\"$TAGS\",\"followups\":\"$FOLLOWUPS\"}" >> "$BUGS_FILE"
fi

echo "已追加 bug 记录到: $BUGS_FILE"
echo "Bug ID: $ID"
