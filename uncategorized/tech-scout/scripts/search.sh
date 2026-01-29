#!/bin/bash
# ============================================================
# tech-scout: 并行搜索脚本
# 聚合多个数据源的搜索结果
# ============================================================

set -e

# ==================== 配置 ====================
QUERY="$1"
TECH_STACK="${2:-}"
OUTPUT_FILE="${3:-/tmp/tech-scout-results.json}"

# 代理配置（如需）
if [ -n "$https_proxy" ]; then
    export https_proxy="$https_proxy"
    export http_proxy="$http_proxy"
fi

# ==================== 依赖检查 ====================
check_dependencies() {
    local missing=()

    command -v curl >/dev/null 2>&1 || missing+=("curl")
    command -v jq >/dev/null 2>&1 || missing+=("jq")

    if [ ${#missing[@]} -ne 0 ]; then
        echo "缺少依赖: ${missing[*]}" >&2
        echo "请安装: brew install ${missing[*]}" >&2
        exit 1
    fi
}

# ==================== GitHub 搜索 ====================
search_github() {
    local query="$1"
    local tech="$2"

    local search_query="${query}"
    [ -n "$tech" ] && search_query="${query} language:${tech}"

    # URL encode
    local encoded_query=$(echo "$search_query" | sed 's/ /+/g')

    echo "搜索 GitHub: $search_query" >&2

    curl -s "https://api.github.com/search/repositories?q=${encoded_query}&sort=stars&per_page=10" \
        -H "Accept: application/vnd.github.v3+json" \
        2>/dev/null | jq '{
            source: "github",
            results: [.items[]? | {
                name: .full_name,
                description: .description,
                stars: .stargazers_count,
                url: .html_url,
                updated: .updated_at,
                language: .language
            }]
        }' 2>/dev/null || echo '{"source":"github","results":[],"error":"API 调用失败"}'
}

# ==================== 结果聚合 ====================
aggregate_results() {
    local github_results="$1"

    jq -s '{
        timestamp: now | todate,
        query: $query,
        sources: .
    }' --arg query "$QUERY" <<< "$github_results"
}

# ==================== 主逻辑 ====================
main() {
    check_dependencies

    if [ -z "$QUERY" ]; then
        echo "用法: $0 <搜索关键词> [技术栈] [输出文件]" >&2
        exit 1
    fi

    echo "开始搜索: $QUERY" >&2
    echo "技术栈: ${TECH_STACK:-无限制}" >&2
    echo "" >&2

    # GitHub 搜索
    local github_results
    github_results=$(search_github "$QUERY" "$TECH_STACK")

    # 聚合结果
    local final_results
    final_results=$(aggregate_results "$github_results")

    # 输出
    echo "$final_results" > "$OUTPUT_FILE"
    echo "" >&2
    echo "结果已保存到: $OUTPUT_FILE" >&2

    # 打印摘要
    echo "" >&2
    echo "=== 搜索摘要 ===" >&2
    echo "$final_results" | jq -r '.sources[0].results[:5][] | "- \(.name) ⭐\(.stars) - \(.description // "无描述")[0:50]"' 2>/dev/null || true
}

main "$@"
