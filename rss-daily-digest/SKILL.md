---
name: rss-daily-digest
description: Use when user wants to fetch RSS feeds, get today's news, or mentions "RSS日报", "今日新闻", "抓取RSS", "新闻摘要"
---

# RSS Daily Digest

从 OPML 订阅源抓取当日内容，生成结构化新闻摘要。

## 触发条件

- `/rss日报`
- `/今日新闻`
- 「抓取今天的 RSS」
- 「检索今日新闻」
- 「获取订阅内容」

## 配置

```yaml
script_path: /Users/bit/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Reeder/opml_parser.py
output_dir: /Users/bit/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/Reeder
opml_file: Reeder.opml
proxy: http://127.0.0.1:7897
```

## 工作流程

### 第一步：运行抓取脚本

```bash
cd "{output_dir}" && \
export https_proxy={proxy} http_proxy={proxy} all_proxy=socks5://127.0.0.1:7897 && \
python3 opml_parser.py
```

**预期输出：**
- `daily_{date}.json` - 原始数据
- `daily_{date}.md` - Markdown 日报

### 第二步：读取生成的日报

读取 `daily_{date}.md` 文件，获取抓取结果。

### 第三步：生成摘要

按以下格式输出：

```markdown
## 今日新闻摘要 ({date})

**共 {total} 条内容**（原创 {original} / 转发 {retweet}）

### 主题分布
| 主题 | 数量 |
|------|------|
| {topic} | {count} |

### 重点内容

**{topic_name}**
- {highlight_1} [→]({url})
- {highlight_2} [→]({url})

---
文件已保存至：
- `Reeder/daily_{date}.json`
- `Reeder/daily_{date}.md`
```

## 主题分类

脚本内置以下主题分类：

| 主题 | 关键词示例 |
|------|-----------|
| 地缘政治 | trump, iran, ukraine, military, 制裁 |
| 加密货币 | bitcoin, ethereum, crypto, defi, 交易所 |
| AI与开发 | ai, gpt, claude, llm, code, rust |
| 科技动态 | spacex, tesla, apple, google, 火箭 |
| 市场金融 | stock, market, invest, etf, 基金 |
| 其他 | 未匹配的内容 |

## 可选参数

脚本支持以下参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-o, --opml` | OPML 文件路径 | Reeder.opml |
| `-f, --format` | 输出格式 (json/md/both) | both |
| `-w, --workers` | 并发数 | 10 |
| `--no-rt` | Markdown 排除转发 | false |

## 使用示例

### 示例 1：获取今日新闻

```
用户: 抓取今天的 RSS
Claude: [运行脚本 → 读取日报 → 输出摘要]
输出: 今日新闻摘要 (2026-01-19)，共 29 条...
```

### 示例 2：仅获取原创内容

```
用户: 获取今日新闻，不要转发
Claude: [运行脚本 --no-rt → 输出摘要]
输出: 今日新闻摘要，共 17 条原创内容...
```

### 示例 3：指定输出格式

```
用户: 抓取 RSS 只要 JSON
Claude: [运行脚本 -f json]
输出: 已保存 daily_2026-01-19.json
```

## 注意事项

1. **网络代理**: 必须配置代理才能访问部分订阅源
2. **超时处理**: 脚本设置 180 秒超时，大量订阅源时可能较慢
3. **时区**: 抓取基于 UTC 时间判断「当日」
4. **去重**: 脚本自动处理空标题和 RT 内容标记
