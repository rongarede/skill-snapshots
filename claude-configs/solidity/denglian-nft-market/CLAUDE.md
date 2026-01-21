# NFTMarket 部署到 Polygon 方案

## 1. 环境配置
创建 `.env` 文件：
```bash
POLYGON_RPC_URL=https://polygon-rpc.com
PRIVATE_KEY=your_private_key_here
POLYGONSCAN_API_KEY=your_api_key
```

## 2. 更新 foundry.toml
```toml
[rpc_endpoints]
polygon = "${POLYGON_RPC_URL}"

[etherscan]
polygon = { key = "${POLYGONSCAN_API_KEY}" }
```

## 3. 创建部署脚本
创建 `script/Deploy.s.sol`：
```solidity
pragma solidity ^0.8.13;
import "forge-std/Script.sol";
import "../src/MyCollectible.sol";
import "../src/NFTMarketDutchAuction.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast(vm.envUint("PRIVATE_KEY"));
        
        MyCollectible nft = new MyCollectible("NFT", "NFT", "https://api.example.com/");
        NFTMarketDutchAuction market = new NFTMarketDutchAuction();
        
        vm.stopBroadcast();
    }
}
```

## 4. 执行部署
```bash
# 测试网部署
forge script script/Deploy.s.sol --rpc-url polygon --broadcast --verify

# 主网部署 
forge script script/Deploy.s.sol --rpc-url polygon --broadcast --verify
```

## 5. 验证合约（如自动验证失败）
```bash
forge verify-contract <CONTRACT_ADDRESS> src/MyCollectible.sol:MyCollectible --chain polygon
```