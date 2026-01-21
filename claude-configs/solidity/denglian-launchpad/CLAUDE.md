# 🚀 Meme Launchpad - 项目设计方案

## 📋 项目概述

### 核心目标
- 让用户低成本创建 Meme 代币
- 自动管理代币流动性  
- 防止常见的 Rug Pull 攻击

### 技术亮点
- **EIP-1167 克隆部署** - 降低 80% 部署成本
- **Uniswap V2 集成** - 自动流动性管理
- **标准化模板** - 统一的安全代币标准

## 🏗️ 技术架构

### 系统架构
```
用户 → MemeFactory(工厂) → MemeToken(代币克隆) → Uniswap(流动性)
```

### 核心组件
- **MemeToken** - ERC20 代币模板
- **MemeFactory** - 工厂合约 (核心逻辑)
- **Uniswap V2** - 流动性和交易

### 关键流程

#### 1. 部署代币
```
deployMeme(symbol, totalSupply, perMint, price)
↓ EIP-1167 克隆 MemeToken 模板
↓ 初始化代币参数
↓ 返回新代币地址
```

#### 2. 铸造代币
```
mintMeme(tokenAddr) + ETH
↓ 验证支付: ETH = perMint × price
↓ 铸造代币给用户
↓ 分配 ETH: 95% 创建者, 5% 平台
↓ 达到阈值时自动添加 Uniswap 流动性
```

#### 3. 购买代币
```
buyMeme(tokenAddr) + ETH
↓ 检查 Uniswap 价格 < 初始价格
↓ 通过 Uniswap 交换 ETH → 代币
↓ 代币发送给用户
```

## 🔧 核心合约设计

### MemeToken.sol (代币模板)

```solidity
contract MemeToken is ERC20, Ownable {
    struct TokenConfig {
        string symbol;
        uint256 totalSupply;
        uint256 perMint;
        uint256 price;
        address creator;
        bool liquidityAdded;
    }
    
    TokenConfig public config;
    address public factory;
    uint256 public totalMinted;
    
    modifier onlyFactory() {
        require(msg.sender == factory, "Only factory");
        _;
    }
    
    function initialize(
        string memory _symbol,
        uint256 _totalSupply,
        uint256 _perMint,
        uint256 _price,
        address _creator,
        address _factory
    ) external {
        require(factory == address(0), "Already initialized");
        
        // 初始化 ERC20
        _name = string.concat("Meme", _symbol);
        _symbol = _symbol;
        
        config = TokenConfig({
            symbol: _symbol,
            totalSupply: _totalSupply,
            perMint: _perMint,
            price: _price,
            creator: _creator,
            liquidityAdded: false
        });
        
        factory = _factory;
        _transferOwnership(_factory);
    }
    
    function mint(address to, uint256 amount) external onlyFactory {
        require(totalMinted + amount <= config.totalSupply, "Exceeds supply");
        require(amount == config.perMint, "Wrong amount");
        
        totalMinted += amount;
        _mint(to, amount);
    }
    
    function getTokenInfo() external view returns (
        string memory symbol,
        uint256 totalSupply,
        uint256 perMint,
        uint256 price,
        address creator,
        bool liquidityAdded
    ) {
        return (
            config.symbol,
            config.totalSupply,
            config.perMint,
            config.price,
            config.creator,
            config.liquidityAdded
        );
    }
}
```

### MemeFactory.sol (工厂合约)

```solidity
contract MemeFactory is ReentrancyGuard, Ownable {
    address public immutable MEME_TEMPLATE;
    address public immutable UNISWAP_ROUTER;
    address public immutable WETH;
    address public platformWallet;
    
    uint256 public constant PLATFORM_FEE_RATE = 500; // 5%
    uint256 public constant MIN_LIQUIDITY_ETH = 0.1 ether;
    
    mapping(address => bool) public isMemeToken;
    mapping(string => address) public symbolToToken;
    mapping(address => uint256) public liquidityEthAmount;
    
    event MemeCreated(address indexed token, string symbol, address creator);
    event MemeMinted(address indexed token, address minter, uint256 amount);
    event LiquidityAdded(address indexed token, uint256 ethAmount);
    
    constructor(
        address _template,
        address _router,
        address _weth,
        address _platformWallet
    ) {
        MEME_TEMPLATE = _template;
        UNISWAP_ROUTER = _router;
        WETH = _weth;
        platformWallet = _platformWallet;
    }
    
    /**
     * @dev 部署新的 Meme 代币
     */
    function deployMeme(
        string calldata symbol,
        uint256 totalSupply,
        uint256 perMint,
        uint256 price
    ) external returns (address tokenAddress) {
        require(bytes(symbol).length >= 2 && bytes(symbol).length <= 10, "Invalid symbol");
        require(symbolToToken[symbol] == address(0), "Symbol exists");
        require(totalSupply > 0 && perMint > 0 && price > 0, "Invalid params");
        require(perMint <= totalSupply / 10, "PerMint too large");
        
        // 克隆代币合约
        bytes32 salt = keccak256(abi.encodePacked(symbol, msg.sender, block.timestamp));
        tokenAddress = Clones.cloneDeterministic(MEME_TEMPLATE, salt);
        
        // 初始化代币
        IMemeToken(tokenAddress).initialize(
            symbol,
            totalSupply,
            perMint,
            price,
            msg.sender,
            address(this)
        );
        
        // 更新状态
        isMemeToken[tokenAddress] = true;
        symbolToToken[symbol] = tokenAddress;
        
        emit MemeCreated(tokenAddress, symbol, msg.sender);
    }
    
    /**
     * @dev 铸造 Meme 代币
     */
    function mintMeme(address tokenAddr) external payable nonReentrant {
        require(isMemeToken[tokenAddr], "Invalid token");
        
        IMemeToken token = IMemeToken(tokenAddr);
        (,, uint256 perMint, uint256 price, address creator,) = token.getTokenInfo();
        
        uint256 totalCost = perMint * price;
        require(msg.value == totalCost, "Wrong payment");
        
        // 铸造代币
        token.mint(msg.sender, perMint);
        
        // 分配 ETH
        uint256 platformFee = (msg.value * PLATFORM_FEE_RATE) / 10000;
        uint256 creatorAmount = msg.value - platformFee;
        
        // 转账给创建者
        (bool success1,) = creator.call{value: creatorAmount}("");
        require(success1, "Creator payment failed");
        
        // 处理平台费用和流动性
        _handlePlatformFee(tokenAddr, platformFee);
        
        emit MemeMinted(tokenAddr, msg.sender, perMint);
    }
    
    /**
     * @dev 购买 Meme 代币
     */
    function buyMeme(address tokenAddr) external payable nonReentrant {
        require(isMemeToken[tokenAddr], "Invalid token");
        require(msg.value > 0, "Must send ETH");
        require(liquidityEthAmount[tokenAddr] > 0, "No liquidity");
        
        // 检查价格优势
        uint256 currentPrice = _getCurrentPrice(tokenAddr);
        (,, , uint256 initialPrice,,) = IMemeToken(tokenAddr).getTokenInfo();
        require(currentPrice < initialPrice, "Price not favorable");
        
        // 通过 Uniswap 购买
        address[] memory path = new address[](2);
        path[0] = WETH;
        path[1] = tokenAddr;
        
        IUniswapV2Router02(UNISWAP_ROUTER).swapExactETHForTokens{value: msg.value}(
            0, // 接受任何数量的代币
            path,
            msg.sender,
            block.timestamp + 300
        );
    }
    
    /**
     * @dev 处理平台费用，部分用于添加流动性
     */
    function _handlePlatformFee(address tokenAddr, uint256 platformFee) internal {
        if (liquidityEthAmount[tokenAddr] == 0 && platformFee >= MIN_LIQUIDITY_ETH) {
            // 第一次添加流动性
            uint256 liquidityETH = platformFee / 2;
            uint256 operatingFee = platformFee - liquidityETH;
            
            _addInitialLiquidity(tokenAddr, liquidityETH);
            
            // 剩余转给平台
            (bool success,) = platformWallet.call{value: operatingFee}("");
            require(success, "Platform fee failed");
        } else {
            // 直接转给平台
            (bool success,) = platformWallet.call{value: platformFee}("");
            require(success, "Platform fee failed");
        }
    }
    
    /**
     * @dev 添加初始流动性
     */
    function _addInitialLiquidity(address tokenAddr, uint256 ethAmount) internal {
        IMemeToken token = IMemeToken(tokenAddr);
        (,, uint256 perMint, uint256 price,,) = token.getTokenInfo();
        
        // 计算代币数量
        uint256 tokenAmount = (ethAmount * 1e18) / price;
        
        // 铸造代币用于流动性
        token.mint(address(this), tokenAmount);
        
        // 批准并添加流动性
        IERC20(tokenAddr).approve(UNISWAP_ROUTER, tokenAmount);
        
        IUniswapV2Router02(UNISWAP_ROUTER).addLiquidityETH{value: ethAmount}(
            tokenAddr,
            tokenAmount,
            0,
            0,
            address(this), // LP token 锁定在合约中
            block.timestamp + 300
        );
        
        liquidityEthAmount[tokenAddr] = ethAmount;
        emit LiquidityAdded(tokenAddr, ethAmount);
    }
    
    /**
     * @dev 获取当前价格
     */
    function _getCurrentPrice(address tokenAddr) internal view returns (uint256) {
        address factory = IUniswapV2Router02(UNISWAP_ROUTER).factory();
        address pair = IUniswapV2Factory(factory).getPair(tokenAddr, WETH);
        
        if (pair == address(0)) return 0;
        
        (uint112 reserve0, uint112 reserve1,) = IUniswapV2Pair(pair).getReserves();
        if (reserve0 == 0 || reserve1 == 0) return 0;
        
        address token0 = IUniswapV2Pair(pair).token0();
        if (token0 == WETH) {
            return (uint256(reserve0) * 1e18) / uint256(reserve1);
        } else {
            return (uint256(reserve1) * 1e18) / uint256(reserve0);
        }
    }
}
```

## 💰 经济模型

### ETH 分配机制
```
用户支付 ETH
├── 95% → Meme 创建者
└── 5% → 平台方
    ├── 2.5% → 添加 Uniswap 流动性
    └── 2.5% → 平台运营费用
```

### 流动性管理
- **触发条件**: 平台费用累积 ≥ 0.1 ETH
- **添加比例**: 使用初始价格计算代币数量
- **LP 锁定**: LP Token 锁定在工厂合约中

### 价格保护
- 只允许在 Uniswap 价格 < 初始价格时购买
- 防止价格操纵和恶意拉盘

## 🔒 安全机制

### 重入攻击防护
```solidity
modifier nonReentrant() {
    require(!_reentrancyGuard, "Reentrant call");
    _reentrancyGuard = true;
    _;
    _reentrancyGuard = false;
}
```

### 权限控制
- 只有工厂合约能铸造代币
- 只有合约所有者能修改平台参数
- 创建者无法控制代币合约

### 参数验证
- 符号长度: 2-10 字符
- 每次铸造量: ≤ 总供应量的 10%
- 价格和供应量: > 0

## 🧪 测试策略

### 单元测试
```solidity
function testDeployMeme() public {
    address token = factory.deployMeme("TEST", 1000000e18, 1000e18, 0.001 ether);
    assertTrue(factory.isMemeToken(token));
}

function testMintMeme() public {
    address token = factory.deployMeme("TEST", 1000000e18, 1000e18, 0.001 ether);
    
    vm.deal(user, 1 ether);
    vm.prank(user);
    factory.mintMeme{value: 1 ether}(token);
    
    assertEq(IMemeToken(token).balanceOf(user), 1000e18);
}

function testBuyMeme() public {
    // 先部署和添加流动性
    address token = _deployAndAddLiquidity();
    
    vm.deal(buyer, 1 ether);
    vm.prank(buyer);
    factory.buyMeme{value: 0.1 ether}(token);
    
    assertGt(IMemeToken(token).balanceOf(buyer), 0);
}
```

### 集成测试
```solidity
function testUniswapIntegration() public {
    // Fork 主网测试真实 Uniswap 交互
    vm.createFork("https://eth-mainnet.alchemyapi.io/v2/API-KEY");
    
    // 测试流动性添加和交易
}
```

### 模糊测试
```solidity
function testFuzzDeployParams(
    string calldata symbol,
    uint256 totalSupply,
    uint256 perMint,
    uint256 price
) public {
    // 测试各种参数组合
}
```

## 🚀 部署指南

### 网络配置
```solidity
// 主网
address constant MAINNET_ROUTER = 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;
address constant MAINNET_WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;

// Sepolia 测试网
address constant SEPOLIA_ROUTER = 0xC532a74256D3Db42D0Bf7a0400fEFDbad7694008;
address constant SEPOLIA_WETH = 0x7b79995e5f793A07Bc00c21412e50Ecae098E7f9;
```

### 部署步骤
```bash
# 1. 部署模板合约
forge create --rpc-url $RPC_URL --private-key $PRIVATE_KEY src/MemeToken.sol:MemeToken

# 2. 部署工厂合约
forge create --rpc-url $RPC_URL --private-key $PRIVATE_KEY \
  --constructor-args $TEMPLATE $ROUTER $WETH $PLATFORM_WALLET \
  src/MemeFactory.sol:MemeFactory

# 3. 验证合约
forge verify-contract --chain-id 1 --etherscan-api-key $API_KEY $CONTRACT_ADDRESS src/MemeFactory.sol:MemeFactory
```

### 验证清单
- [ ] 模板合约部署成功
- [ ] 工厂合约初始化正确
- [ ] Uniswap 路由器地址正确
- [ ] 平台钱包地址正确
- [ ] 测试部署一个代币
- [ ] 测试铸造和流动性添加

## 📈 优化建议

### Gas 优化
- 使用 packed struct 减少存储槽
- 批量操作减少交易次数
- 优化循环和条件判断

### 功能扩展
- 添加代币暂停/恢复功能
- 实现批量铸造
- 支持多种 DEX
- 集成价格预言机

### 监控和维护
- 异常交易监控
- 价格异动告警
- 合约升级机制
- 紧急停止功能

## 🔍 风险提示

### 技术风险
- 智能合约漏洞
- Uniswap 依赖风险
- 价格操纵攻击

### 经济风险
- 代币价值波动
- 流动性枯竭
- 市场操纵

### 合规风险
- 监管政策变化
- KYC/AML 要求
- 税务申报义务

---

**免责声明**: 本项目仅用于技术学习和研究目的，请在使用前充分了解相关风险并遵守当地法律法规。