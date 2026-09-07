#!/bin/bash
# skill-snapshot list - 列出快照版本

set -e

SKILL_NAME="$1"
LOCAL_REPO="$HOME/.claude/skill-snapshots"

# 检查仓库是否已初始化
if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

# 拉取最新 tags
git fetch --tags --quiet 2>/dev/null || true

if [ -z "$SKILL_NAME" ]; then
    # 列出所有技能的快照
    echo "=== 所有技能快照 ==="
    echo ""

    ALL_TAGS=$(git tag -l "*/v*" 2>/dev/null | sort)

    if [ -z "$ALL_TAGS" ]; then
        echo "暂无快照"
        exit 0
    fi

    # 按技能分组
    SKILLS=$(echo "$ALL_TAGS" | sed 's|/v.*||' | sort -u)

    for skill in $SKILLS; do
        SKILL_TAGS=$(git tag -l "$skill/v*" | sort -V)
        COUNT=$(echo "$SKILL_TAGS" | wc -l | tr -d ' ')
        LATEST=$(echo "$SKILL_TAGS" | tail -1 | sed "s|$skill/||")
        echo "  $skill ($COUNT 个版本, 最新: $LATEST)"
    done

    echo ""
    echo "查看特定技能: list <skill-name>"
else
    # 列出指定技能的快照
    AVAILABLE_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V)

    if [ -z "$AVAILABLE_TAGS" ]; then
        echo "没有找到 $SKILL_NAME 的快照"
        exit 0
    fi

    echo "=== $SKILL_NAME 快照历史 ==="
    echo ""

    for tag in $AVAILABLE_TAGS; do
        ver=$(echo "$tag" | sed "s|$SKILL_NAME/||")
        msg=$(git tag -l "$tag" -n1 | sed "s|$tag[[:space:]]*||")
        date=$(git log -1 --format="%ci" "$tag" 2>/dev/null | cut -d' ' -f1)
        echo "  $ver - $date - $msg"
    done

    echo ""
    LATEST=$(echo "$AVAILABLE_TAGS" | tail -1 | sed "s|$SKILL_NAME/||")
    echo "最新版本: $LATEST"
fi
