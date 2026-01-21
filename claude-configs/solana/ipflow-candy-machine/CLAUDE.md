# Candy Machine Program 架构说明

## 目录结构
```
program/
├── src/
│   ├── lib.rs
│   ├── constants.rs
│   ├── errors.rs
│   ├── state.rs
│   ├── utils.rs
│   └── processor/
│       ├── add_config_lines.rs
│       ├── add_item.rs
│       ├── initialize.rs
│       ├── mint_fulfill.rs
│       ├── mint_request.rs
│       ├── update.rs
│       └── withdraw.rs
```

## 模块职责
- `program/src/lib.rs`: 程序入口，导出指令与上下文类型。
- `program/src/processor/*`: 指令处理逻辑，按指令划分文件。
- `program/src/state.rs`: 账户与核心数据结构（含 IPPoolState、VrfState）。
- `program/src/utils.rs`: 工具函数与 CPI 占位封装。
- `program/src/constants.rs`: PDA 前缀与账户大小常量。
- `program/src/errors.rs`: 统一错误码。

## 依赖关系
- `processor/*` 依赖 `state.rs`、`utils.rs`、`constants.rs`、`errors.rs`。
- `state.rs` 与 `constants.rs` 无反向依赖。

## 变更日志
- 本次变更：新增 `add_item`、`mint_request`、`mint_fulfill` 指令，新增 `IPPoolState` 与 `VrfState`，入口裁剪掉 collection/freeze 相关指令。
- 本次变更：`mint_request` 使用 PDA 资金池收款，`mint_fulfill` 以链上伪随机数执行 Raydium CPI。
