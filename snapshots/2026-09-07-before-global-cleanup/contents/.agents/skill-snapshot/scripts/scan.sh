#!/bin/bash
# skill-snapshot scan - 扫描技能，判断哪些需要备份

SKILLS_DIR="$HOME/.claude/skills"
LOCAL_REPO="$HOME/.claude/skill-snapshots"

# 忽略规则
SKIP_REASONS=()

check_skill() {
    local skill_path="${1%/}"  # 去掉尾部斜杠
    local skill_name="$(basename "$skill_path")"

    # 规则 1: archive 目录
    if [ "$skill_name" = "archive" ]; then
        echo "SKIP|$skill_name|归档目录"
        return
    fi

    # 规则 2: 符号链接（外部安装）
    if [ -L "$skill_path" ]; then
        echo "SKIP|$skill_name|符号链接（外部安装）"
        return
    fi

    # 规则 3: 快照工具本身
    if [ "$skill_name" = "skill-snapshot" ]; then
        echo "SKIP|$skill_name|快照工具本身"
        return
    fi

    # 规则 4: 包含 .git（自带版本控制）
    if [ -d "$skill_path/.git" ]; then
        echo "SKIP|$skill_name|自带 Git 版本控制"
        return
    fi

    # 规则 5: 包含 .venv 或 node_modules（大量依赖）
    if [ -d "$skill_path/.venv" ] || [ -d "$skill_path/node_modules" ]; then
        echo "SKIP|$skill_name|包含依赖目录 (.venv/node_modules)"
        return
    fi

    # 规则 6: 体积超过 10MB
    local size_kb=$(du -sk "$skill_path" 2>/dev/null | cut -f1)
    if [ "$size_kb" -gt 10240 ]; then
        local size_mb=$((size_kb / 1024))
        echo "SKIP|$skill_name|体积过大 (${size_mb}MB > 10MB)"
        return
    fi

    # 规则 7: 没有 SKILL.md（可能不是有效技能）
    if [ ! -f "$skill_path/SKILL.md" ]; then
        echo "SKIP|$skill_name|缺少 SKILL.md"
        return
    fi

    # 通过所有检查，需要备份
    local files=$(find "$skill_path" -type f ! -name '.DS_Store' | wc -l | tr -d ' ')
    local size=$(du -sh "$skill_path" 2>/dev/null | cut -f1)

    # 检查是否已有快照
    local has_snapshot=""
    if [ -d "$LOCAL_REPO/.git" ]; then
        cd "$LOCAL_REPO"
        local latest=$(git tag -l "$skill_name/v*" 2>/dev/null | sort -V | tail -1)
        if [ -n "$latest" ]; then
            has_snapshot="$latest"
        fi
    fi

    echo "BACKUP|$skill_name|$files files, $size|$has_snapshot"
}

echo "=== 技能快照扫描 ==="
echo ""

# 收集结果
BACKUP_LIST=()
SKIP_LIST=()

for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    result=$(check_skill "$skill_dir")

    type=$(echo "$result" | cut -d'|' -f1)
    if [ "$type" = "BACKUP" ]; then
        BACKUP_LIST+=("$result")
    else
        SKIP_LIST+=("$result")
    fi
done

# 输出需要备份的
echo "【需要备份】"
if [ ${#BACKUP_LIST[@]} -eq 0 ]; then
    echo "  (无)"
else
    for item in "${BACKUP_LIST[@]}"; do
        name=$(echo "$item" | cut -d'|' -f2)
        info=$(echo "$item" | cut -d'|' -f3)
        snapshot=$(echo "$item" | cut -d'|' -f4)
        if [ -n "$snapshot" ]; then
            echo "  ✓ $name ($info) [已有: $snapshot]"
        else
            echo "  ○ $name ($info) [未备份]"
        fi
    done
fi

echo ""
echo "【跳过】"
if [ ${#SKIP_LIST[@]} -eq 0 ]; then
    echo "  (无)"
else
    for item in "${SKIP_LIST[@]}"; do
        name=$(echo "$item" | cut -d'|' -f2)
        reason=$(echo "$item" | cut -d'|' -f3)
        echo "  ✗ $name - $reason"
    done
fi

# 统计
echo ""
echo "----------------------------------------"
echo "需要备份: ${#BACKUP_LIST[@]} 个"
echo "跳过: ${#SKIP_LIST[@]} 个"

# 检查未备份的
NEED_BACKUP=()
for item in "${BACKUP_LIST[@]}"; do
    snapshot=$(echo "$item" | cut -d'|' -f4)
    if [ -z "$snapshot" ]; then
        name=$(echo "$item" | cut -d'|' -f2)
        NEED_BACKUP+=("$name")
    fi
done

if [ ${#NEED_BACKUP[@]} -gt 0 ]; then
    echo ""
    echo "【待备份】${#NEED_BACKUP[@]} 个技能尚未创建快照:"
    for name in "${NEED_BACKUP[@]}"; do
        echo "  - $name"
    done
fi
