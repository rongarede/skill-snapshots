# Skill Snapshot

为 Claude Code 技能创建快照，支持版本回退。存储在 GitHub 私有仓库。

## 触发词

- "快照"、"snapshot"、"保存技能"、"备份技能"
- "回退技能"、"恢复技能"、"restore skill"
- "/skill-snapshot"

## 命令格式

```
/skill-snapshot <command> [args]
```

### 可用命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `init` | 初始化私有仓库 | `/skill-snapshot init` |
| `scan` | 扫描技能，判断哪些需要备份 | `/skill-snapshot scan` |
| `save <skill> [message]` | 保存快照 | `/skill-snapshot save my-skill "添加断点续写"` |
| `restore <skill> [version]` | 恢复版本 | `/skill-snapshot restore my-skill v2` |
| `list [skill]` | 列出快照 | `/skill-snapshot list my-skill` |
| `diff <skill> [version]` | 对比差异 | `/skill-snapshot diff my-skill v1` |

## 配置

- **私有仓库**: `skill-snapshots`（自动创建）
- **本地克隆**: `~/.claude/skill-snapshots/`
- **版本标签**: `<skill-name>/v<n>`（如 `my-skill/v1`）

## 忽略规则

scan 命令根据以下规则自动判断哪些技能需要备份：

| 规则 | 跳过原因 |
|------|----------|
| `archive/` 目录 | 归档目录 |
| 符号链接 | 外部安装的技能 |
| `skill-snapshot` | 快照工具本身 |
| 包含 `.git/` | 自带版本控制 |
| 包含 `.venv/` 或 `node_modules/` | 包含大量依赖 |
| 体积 > 10MB | 体积过大 |
| 缺少 `SKILL.md` | 可能不是有效技能 |

## 执行流程

### scan - 扫描技能

扫描所有技能，判断哪些需要备份、哪些应跳过。

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/scan.sh
```

输出示例：
```
【需要备份】
  ✓ my-skill (5 files, 68K) [已有: my-skill/v1]
  ○ new-skill (3 files, 12K) [未备份]

【跳过】
  ✗ git-managed-skill - 自带 Git 版本控制
  ✗ external-plugin - 符号链接（外部安装）
```

### init - 初始化

1. 检查 GitHub 私有仓库 `skill-snapshots` 是否存在
2. 如不存在，创建私有仓库
3. 克隆到本地 `~/.claude/skill-snapshots/`
4. 初始化目录结构

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/init.sh
```

### save - 保存快照

参数：
- `<skill>`: 技能名称（必填）
- `[message]`: 快照说明（可选，默认为时间戳）

流程：
1. 验证技能存在于 `~/.claude/skills/<skill>/`
2. 确定下一个版本号（检查现有 tags）
3. 复制技能目录到仓库 `~/.claude/skill-snapshots/<skill>/`
4. Git add, commit, tag, push

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/save.sh "<skill>" "[message]"
```

### restore - 恢复版本

参数：
- `<skill>`: 技能名称（必填）
- `[version]`: 版本号（可选，默认为最新）

流程：
1. 拉取最新仓库
2. 如未指定版本，列出可用版本让用户选择
3. Checkout 到指定 tag
4. 复制仓库中的技能目录到 `~/.claude/skills/<skill>/`
5. 切回 main 分支

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/restore.sh "<skill>" "[version]"
```

### list - 列出快照

参数：
- `[skill]`: 技能名称（可选，不填则列出所有）

流程：
1. 拉取最新 tags
2. 过滤匹配的 tags
3. 显示版本列表和提交信息

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/list.sh "[skill]"
```

### diff - 对比差异

参数：
- `<skill>`: 技能名称（必填）
- `[version]`: 版本号（可选，默认为最新快照）

流程：
1. Checkout 到指定版本
2. 对比仓库中的版本与当前 `~/.claude/skills/<skill>/`
3. 显示差异
4. 切回 main

执行脚本：
```bash
bash ~/.claude/skills/skill-snapshot/scripts/diff.sh "<skill>" "[version]"
```

## 存储结构

```
~/.claude/skill-snapshots/          # 本地仓库
├── my-skill/
│   ├── SKILL.md
│   └── scripts/
├── another-skill/
│   └── SKILL.md
└── README.md

GitHub Tags:
├── my-skill/v1
├── my-skill/v2
├── my-skill/v3
└── another-skill/v1
```

## 使用示例

### 场景 1：首次使用

```
用户: 帮我初始化技能快照
Claude: [执行 init]
```

### 场景 2：修改前保存

```
用户: 我要改 my-skill，先保存一下
Claude: [执行 save my-skill "修改前备份"]
输出: 已保存快照 my-skill/v3
```

### 场景 3：改坏了回退

```
用户: my-skill 改坏了，退回上一版
Claude: [执行 restore my-skill v2]
输出: 已恢复到 my-skill/v2
```

### 场景 4：查看历史

```
用户: my-skill 有哪些版本？
Claude: [执行 list my-skill]
输出:
  v1 - 2025-01-05 - 初始版本
  v2 - 2025-01-08 - 添加断点续写
  v3 - 2025-01-10 - 修改前备份
```

## 注意事项

1. **符号链接跳过**：如 `external-plugin` 等外部安装的技能（符号链接）不支持快照
2. **archive 目录忽略**：不对 archive 目录下的技能做快照
3. **首次使用需 init**：首次使用前需执行 `init` 创建仓库
4. **网络依赖**：save/restore 需要网络连接推送到 GitHub
