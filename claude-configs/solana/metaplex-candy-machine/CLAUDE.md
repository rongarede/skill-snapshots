# CLAUDE.md - Candy Machine Program Architecture

## 核心职责
Candy Machine 是 Solana 上用于公平分发 NFT 的核心程序。它管理 NFT 的配置、铸造逻辑、白名单验证、防脚本（Bot Tax）以及随机抽取逻辑。

## 目录结构
```bash
src/
├── lib.rs              # 程序入口，定义 Anchor 模块与指令路由
├── state.rs            # 核心数据结构 (CandyMachine, CandyMachineData, CollectionPDA 等)
├── constants.rs        # 常量定义 (如配置区起始位置、Bot Fee 等)
├── errors.rs           # 自定义错误码 (CandyError)
├── utils.rs            # 工具函数 (Pubkey 比较、Token 检查等)
└── processor/          # 业务逻辑实现
    ├── mod.rs              # 模块导出
    ├── initialize.rs       # 初始化 Candy Machine 账户
    ├── add_config_lines.rs # 添加 NFT 配置数据 (Name/URI)
    ├── mint.rs             # 核心铸造逻辑 (随机抽取、CPI 调用 Token Metadata)
    ├── update.rs           # 更新 Candy Machine 配置
    ├── withdraw.rs         # 提取资金
    ├── collection/         # 集合设置 (SetCollection 等)
    └── freeze/             # 冻结功能 (防止铸造后立即交易)
```

## 核心模块详解

### 1. State (`state.rs`)
- **CandyMachine**: 主账户结构，存储所有状态。
    - `data`: 配置数据 (`CandyMachineData`)。
    - `items_redeemed`: 已铸造数量。
    - `wallet`: 资金接收钱包。
    - `authority`: 管理员公钥。
- **CandyMachineData**: 静态配置信息（价格、总量、GoLiveDate、白名单设置等）。
- **Config Line**: 存储剩余 NFT 的元数据（Name, URI）。数据紧凑存储在 `CandyMachine` 账户数据区的尾部，不通过 Anchor 序列化管理，手动通过 offset 读写以节省因 Account Size 限制带来的开销。

### 2. Initialization (`processor/initialize.rs`)
- 创建账户时计算所需空间。
- 空间计算公式复杂：包括基础结构体大小 + (总量 * ConfigLine 大小) + Bitmask 大小（用于标记哪些 Index 已被抽取）。

### 3. Minting Logic (`processor/mint.rs`)
这是最复杂的模块，处理流程如下：
1. **Bot 检查**: 检查 metadata 是否为空，剩余账户数是否匹配，避免 CPI 攻击。
2. **状态检查**: 检查是否售罄、是否开始（GoLiveDate）、白名单验证（Gatekeeper/Whitelist Token）。
3. **随机抽取**:
    - 使用 `recent_blockhashes` 生成伪随机数（Index）。
    - 结合 Bitmask 查找一个未使用的 Index (`get_good_index`)。
    - 这是为了保证在链上无法轻易预测下一个抽到的 NFT。
4. **Token 转移**: 扣除 SOL 或 SPL Token 作为铸造费用。
5. **CPI 调用**:
    - 调用 `spl_token_metadata` 创建 Metadata 账户。
    - 调用 `spl_token_metadata` 创建 Master Edition 账户。
    - 调用 `update_metadata_accounts_v2` 处理权限。
6. **Freeze 处理**: 如果开启 Freeze 功能，冻结用户 Token 账户，防止立即交易。

### 4. Config Management (`processor/add_config_lines.rs`)
- 分批次将 NFT 数据的 Name 和 URI 写入账户数据区。
- 直接操作 `account.data` 的字节切片，绕过 Anchor 的序列化层以提高性能和利用率。

## 架构特点
- **手动内存管理**: 为了在 Solana 10MB 账户限制下存储成千上万个 NFT 配置，程序手动管理 Account Data 的内存布局，计算偏移量读写 Config Lines。
- **防脚本机制 (Bot Tax)**: 如果检测到非法操作（如直接调用、参数错误等），不是直接报错返回，而是扣除 `BOT_FEE` (0.01 SOL) 并成功返回，让 Bot 付出代价。
- **模块化 CPI**: 强依赖 `mpl-token-metadata` 程序来完成 NFT 的最终生成。

## 开发规范
- 关键常量定义在 `constants.rs`。
- 修改 `state.rs` 需谨慎，涉及数据布局兼容性。
- 使用 `utils.rs` 中的辅助函数进行 Pubkey 比较（避免直接 `==` 产生的计算开销或安全隐患）。
