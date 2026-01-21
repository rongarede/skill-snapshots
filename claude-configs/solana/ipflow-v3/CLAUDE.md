<hooks>
RPC 节点配置（强制）：

- **强制规则：** 所有涉及 Solana RPC 调用的操作，必须使用以下 Devnet RPC 节点
- **RPC URL:** `https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`
- **适用范围：**
  - 脚本中的 `Connection` 初始化
  - Anchor 命令的 `--provider.cluster` 参数
  - SDK 测试中的 RPC 配置
  - 任何需要连接 Solana 网络的操作
- **示例命令：**
  - `anchor deploy --provider.cluster https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`
  - `anchor idl fetch <PROGRAM_ID> --provider.cluster https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`

文档同步（架构级变更触发）：
- **触发条件：** 创建 / 删除 /移动文件或目录、模块重组、层级调整、职责重新划分
- **强制行为：** 必须同步更新目标目录下的 `GEMINI.md`（如无法直接修改文件系统，则在回答中给出完整建议内容）
- **内容要求：** 每个文件一句话说明用途与核心关注点；给出目录树；明确模块依赖与职责边界
- **原则：** 文档滞后是技术债务；架构无文档等同于系统失忆

合约变更部署（合约文件变更触发）：

- **触发条件：** 任何位于 `programs/` 下的合约文件被修改
- **强制行为：** 必须重新部署到测试网（devnet）
- **要求**：在变更说明中记录部署命令与结果

文档修改规范：

- **核心原则：** 仅允许删除或修改与当前任务强相关的文档内容。
- **弱相关处理：** 对于与当前任务弱相关的文档内容，仅允许添加新内容，严禁删除既有内容。
- **目的：** 保护项目历史上下文，防止在执行局部任务时意外丢失系统全局信息。

文件/结构变更汇报（涉及文件结构或代码组织设计时）：

- 执行前说明：做什么 / 为什么 / 预计改动哪些文件或模块
- 执行后说明：逐行列出被「设计上」改动的文件/模块（无真实文件系统则给建议清单）

bugs 复盘（仅在错误/问题修复后触发）：

- 每当你完成一次错误/问题修复后，必须立即生成一条复盘记录，并以 JSONL 形式追加写入当前工作目录下的 `bugs.jsonl`
- 字段必须包含：ts, id, title, symptom, root_cause, fix, files_changed, repro_steps, verification, impact, prevention, tags, followups
- 只输出一行合法 JSON（不要代码块、不要多余解释）；不确定的信息用 \"TODO\" 或空值占位，严禁编造
- tags 使用 3~8 个短标签；verification 写执行过的命令与结果
  </hooks>

## Task 标准

- **说明**：每个 Task 仅保留四个小节，统一格式如下：
  - **前提条件**
  - **任务执行步骤**
  - **验证标准**
  - **如何处理验证结果**

## 环境配置 (Environment)

- **Cluster:** `devnet` (Current Target)
- **Program ID:** `ALRWyaQkjVGznjAXsxhqXkyYDaETPUN2xj82W8uyji53`
- **RPC URL:** `https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61` (Alchemy Devnet 节点，见 hooks 强制规则)
- **ANCHOR_WALLET:** `deployer-keypair.json` (链上 Admin 钱包，用于管理员操作测试)
  - 公钥: `3TLCqGuFEUFokdF8BMrwtLKcjdupFcnnp5aoikU7W6qq`
  - 运行脚本前设置: `export ANCHOR_WALLET=/Users/bit/SolanaRust/ipflow-v3/deployer-keypair.json`

## 问题记录

- **问题**：本地 IDL 与链上 IDL 不一致导致 `claim` 调用失败。
- **根因**：`scripts/ipflow_v3.json` 未从链上同步，SDK 误删 `swap_router` 参数导致签名不匹配。
- **解决方案**：执行 `anchor idl fetch -o scripts/ipflow_v3.json <PROGRAM_ID>` 同步 IDL，并恢复 `claim` 4 参数调用。
- **相关命令**：`anchor idl fetch -o scripts/ipflow_v3.json ALRWyaQkjVGznjAXsxhqXkyYDaETPUN2xj82W8uyji53 --provider.cluster https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`、`bun scripts/devnet_sdk_raydium_sol.ts`
- **问题**：claim 完成后脚本误报 MintRequest PDA 未关闭。
- **根因**：脚本使用 `sdk.getMintRequest` 判断关闭状态，关闭后返回 null 但被当成异常处理。
- **解决方案**：改用 `connection.getAccountInfo` 检查账户是否存在。
- **相关命令**：`bun scripts/devnet_sdk_raydium_sol.ts`
- **问题**：新增 `prize_pool_count` 后 Devnet config 账户反序列化失败。
- **根因**：链上 config 仍为旧长度 (53 bytes)，Anchor 反序列化失败。
- **解决方案**：新增 `migrate_config` 指令扩容 config 并在脚本中自动迁移。
- **相关命令**：`anchor build`、`anchor deploy --provider.cluster https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`、`bun scripts/devnet_sdk_raydium_sol.ts`
- **问题**：Raydium CPMM Swap CPI 报 InstructionFallbackNotFound。
- **根因**：`raydium_cpi.rs` 内 hardcode 的 `swap_base_input` discriminator 与 Devnet IDL 不匹配，同时仅校验主网程序 ID。
- **解决方案**：按 Raydium Devnet IDL 更新 discriminator，并放开 Devnet Program ID 校验，同时 SDK 传入 Devnet 程序 ID。
- **相关命令**：`anchor idl fetch DRaycpLY18LhpbydsBWbVJtxpNv9oXPgjRSfpF2bWpYb --provider.cluster https://solana-devnet.g.alchemy.com/v2/VgGOBgswnuX7oivzzUG61`、`bun scripts/devnet_sdk_raydium_sol.ts`
- **问题**：Task 1.18 场景 B Vault 余额不足导致 claim 失败。
- **根因**：脚本最小 Vault 余额只补到 2 SOL，中奖金额高于 Vault 可用余额。
- **解决方案**：将 `Task_1.18_B.ts` 最小 Vault 余额提升至 4 SOL，确保大额中奖可覆盖。
- **相关命令**：`bun scripts/Task_1.18_B.ts`

## 流程图绘制标准 (Diagram Standards)

### Mermaid 序列图配置

#### 颜色主题配置

使用鲜明的颜色主题替代默认灰色，提高可读性和视觉冲击力。

```javascript
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#FF6B6B',
    'primaryTextColor': '#fff',
    'primaryBorderColor': '#C92A2A',
    'lineColor': '#E74C3C',              // 🔴 鲜红色线条
    'secondaryColor': '#4ECDC4',
    'tertiaryColor': '#FFE66D',
    'actorBorder': '#2C3E50',            // ⚫ 深灰色边框
    'actorBkg': '#34495E',               // ⚫ 深灰色背景
    'actorTextColor': '#ECF0F1',         // ⚪ 浅色文字
    'actorLineColor': '#E74C3C',         // 🔴 鲜红色生命线
    'signalColor': '#E74C3C',            // 🔴 鲜红色信号
    'signalTextColor': '#2C3E50',        // ⚫ 深色文字
    'labelBoxBkgColor': '#3498DB',       // 🔵 蓝色标签背景
    'labelBoxBorderColor': '#2980B9',
    'labelTextColor': '#FFFFFF',
    'loopTextColor': '#2C3E50',
    'noteBorderColor': '#F39C12',        // 🟠 橙色 Note 边框
    'noteBkgColor': '#FFF3CD',           // 🟡 浅黄色 Note 背景
    'noteTextColor': '#856404',
    'activationBorderColor': '#E74C3C',  // 🔴 鲜红色激活框边框
    'activationBkgColor': '#FADBD8',     // 🔴 浅红色激活框背景
    'sequenceNumberColor': '#FFFFFF',
    'altSectionBkgColor': '#E8F5E9,#FFF3E0'  // 🟢🟠 条件分支渐变
  }
}}%%
```

#### 视觉元素规范

**1. 阶段分隔符**
使用双线分隔符配合 Emoji 图标标记阶段：

```mermaid
Note over Admin,Oracle: ═══════════════════════════════════════════════════════════<br/>🔷 阶段一: 系统初始化<br/>═══════════════════════════════════════════════════════════
```

**2. 激活框（Activation Boxes）**
使用 `+` 和 `-` 符号显示对象活跃状态：

```mermaid
Admin->>+IPFlow: initialize(platform_fee_bps)  // 激活 IPFlow
IPFlow->>IPFlow: 创��� IPFlowState PDA
IPFlow-->>-Admin: 初始化成功                    // 停用 IPFlow
```

**3. Emoji 图标增强**

- ⏱️ 时间相关说明
- 🪐 Jupiter 相关功能
- 🔷 蓝色菱形（阶段标记）
- 🔶 橙色菱形（阶段标记）
- ✅ 成功返回
- 🔁 循环操作

**4. 自动编号**
在 `sequenceDiagram` 后添加 `autonumber` 启用步骤编号。

#### 推荐配色方案

| 主题         | 线条颜色  | 适用场景           |
| ------------ | --------- | ------------------ |
| 红色（默认） | `#E74C3C` | 强调流程，高对比度 |
| 蓝色         | `#3498DB` | 商务风格，专业感   |
| 绿色         | `#27AE60` | 环保主题，清新感   |
| 紫色         | `#9B59B6` | 科技感，创新风格   |
