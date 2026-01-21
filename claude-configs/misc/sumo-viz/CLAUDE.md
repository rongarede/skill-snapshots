# SUMO 交通控制算法完整实验框架 Prompt 文档

## 🎯 项目目标

在 SUMO + TraCI + Python 环境下，实现一个完整的交通信号控制系统，用于比较两种控制算法（Fixed-Time 和 Weighted-Time）在多种交通场景下的性能表现。

### 系统架构
```
SUMO 仿真引擎（后台双实例运行）
    ↑ TraCI 实时通信
Python 控制器（算法逻辑）
    ↓ matplotlib 实时并排对比可视化
```

### 核心特性
- ✅ 双算法并排实时对比
- ✅ 完全中文化界面
- ✅ 单方向独占通行控制
- ✅ 实时性能指标统计
- ✅ 一键重启实验功能
- ✅ 多场景自动化测试框架

---

## 🧩 控制算法模块说明

系统实现两种独立算法，使用统一接口 `update(sim_time)`，支持动态切换。

### ✅ 算法一：单方向循环红绿灯（Fixed-Time Controller）

#### 逻辑目标
固定时间周期的红绿灯控制，每个时刻只有一个方向绿灯，其他方向红灯。

#### 相位设计（四方向循环）
- **状态 0**：北(N)绿灯，东南西红灯
- **状态 1**：东(E)绿灯，北南西红灯
- **状态 2**：南(S)绿灯，北东西红灯
- **状态 3**：西(W)绿灯，北东南红灯

#### 控制逻辑
1. 四方向严格循环：N → E → S → W → N...
2. 固定周期：每个方向绿灯 30 秒（可配置），完整周期 120 秒
3. 不根据实时流量调整
4. **关键**：初始化时立即设置红绿灯状态，覆盖SUMO默认配置

#### 实现代码框架

```python
class FixedController:
    """固定时长循环控制器"""

    DIRECTIONS = ['N', 'E', 'S', 'W']
    EDGE_NAMES = {
        'N': 'north_in',
        'E': 'east_in',
        'S': 'south_in',
        'W': 'west_in'
    }

    def __init__(self, tls_id, green_time=30):
        """初始化控制器"""
        self.tls_id = tls_id
        self.green_time = green_time
        self.current_index = 0
        self.last_switch = 0

        # ⚠️ 关键：立即设置初始状态
        state = self._get_light_state()
        traci.trafficlight.setRedYellowGreenState(self.tls_id, state)

    def update(self, sim_time):
        """更新控制器状态"""
        if sim_time - self.last_switch >= self.green_time:
            old_index = self.current_index
            self.current_index = (self.current_index + 1) % 4
            self.last_switch = sim_time

            state = self._get_light_state()
            traci.trafficlight.setRedYellowGreenState(self.tls_id, state)

            # 日志输出
            old_dir = self.DIRECTIONS[old_index]
            new_dir = self.DIRECTIONS[self.current_index]
            print(f"[FixedController] t={sim_time:.1f}s - {old_dir}→{new_dir}")

    def _get_light_state(self):
        """生成20字符红绿灯状态字符串"""
        state = ['r'] * 20

        if self.current_index == 0:    # North
            state[0:5] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 1:  # East
            state[5:10] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 2:  # South
            state[10:15] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 3:  # West
            state[15:20] = ['G', 'G', 'G', 'G', 'g']

        return ''.join(state)

    def get_current_state(self):
        """获取当前状态"""
        return {
            'direction': self.DIRECTIONS[self.current_index],
            'green_time': self.green_time
        }
```

---

### ⏳ 算法二：基于等待时间权重的调度（Weighted-Time Controller）

#### 逻辑目标
动态读取各进口的累计等待时间，优先为等待时间最长的方向放行，实现自适应信号控制。

#### 核心思想
1. 实时监测四个进口方向：N, E, S, W
2. 每个仿真步从 TraCI 获取各方向累计等待时间
3. 选择等待时间最长的方向放行
4. 保证最短绿灯时间（`min_green`，默认10秒），避免频繁切换
5. 每次切换记录时间，防止抖动

#### 实现代码框架

```python
class WeightedController:
    """加权调度控制器"""

    DIRECTIONS = ['N', 'E', 'S', 'W']
    EDGE_NAMES = {
        'N': 'north_in',
        'E': 'east_in',
        'S': 'south_in',
        'W': 'west_in'
    }

    def __init__(self, tls_id, min_green=10):
        """初始化控制器"""
        self.tls_id = tls_id
        self.min_green = min_green
        self.current_index = 0
        self.last_switch = 0

        # ⚠️ 关键：立即设置初始状态
        state = self._get_light_state()
        traci.trafficlight.setRedYellowGreenState(self.tls_id, state)

    def get_waiting_times(self):
        """获取四个方向的累计等待时间"""
        waits = {}
        for direction in self.DIRECTIONS:
            edge_name = self.EDGE_NAMES[direction]
            waits[direction] = traci.edge.getWaitingTime(edge_name)
        return waits

    def update(self, sim_time):
        """更新控制器状态"""
        # 最短绿灯时间保护
        if sim_time - self.last_switch < self.min_green:
            return

        # 获取等待时间
        waits = self.get_waiting_times()

        # 选择等待时间最长的方向
        max_direction = max(waits, key=waits.get)
        target_index = self.DIRECTIONS.index(max_direction)

        # 判断是否需要切换
        if target_index != self.current_index:
            old_index = self.current_index
            self.current_index = target_index
            self.last_switch = sim_time

            state = self._get_light_state()
            traci.trafficlight.setRedYellowGreenState(self.tls_id, state)

            # 日志输出
            old_dir = self.DIRECTIONS[old_index]
            new_dir = self.DIRECTIONS[self.current_index]
            wait_time = waits[new_dir]
            print(f"[WeightedController] t={sim_time:.1f}s - {old_dir}→{new_dir} (wait={wait_time:.1f}s)")

    def _get_light_state(self):
        """生成20字符红绿灯状态字符串"""
        state = ['r'] * 20

        if self.current_index == 0:    # North
            state[0:5] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 1:  # East
            state[5:10] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 2:  # South
            state[10:15] = ['G', 'G', 'G', 'G', 'g']
        elif self.current_index == 3:  # West
            state[15:20] = ['G', 'G', 'G', 'G', 'g']

        return ''.join(state)

    def get_current_state(self):
        """获取当前状态"""
        return {
            'direction': self.DIRECTIONS[self.current_index],
            'min_green': self.min_green
        }
```

---

## 📊 双算法并排对比可视化

### 可视化界面布局

```
┌─────────────────────────────────────────────────────────────────┐
│                  SUMO 交通信号控制算法对比实验                      │
├──────────────────────────┬──────────────────────────────────────┤
│   固定时长算法 (30秒周期)   │     加权调度算法 (自适应)              │
├──────────────────────────┼──────────────────────────────────────┤
│  ┌────────────┐           │  ┌────────────┐                      │
│  │ 时间: 120s │           │  │ 时间: 120s │                      │
│  │ 车辆数: 25 │           │  │ 车辆数: 25 │                      │
│  │ 平均速度   │           │  │ 平均速度   │                      │
│  │ 平均等待   │           │  │ 平均等待   │                      │
│  └────────────┘           │  └────────────┘                      │
│                           │                                      │
│     [路网可视化]           │     [路网可视化]                      │
│     + 实时车辆             │     + 实时车辆                        │
│                           │                                      │
│  ┌────────────┐           │  ┌────────────┐                      │
│  │ 红绿灯状态  │           │  │ 红绿灯状态  │                      │
│  │  北: 绿    │           │  │  北: 红    │                      │
│  │  南: 红    │           │  │  南: 绿    │                      │
│  │  东: 红    │           │  │  东: 红    │                      │
│  │  西: 红    │           │  │  西: 红    │                      │
│  └────────────┘           │  └────────────┘                      │
├──────────────────────────┴──────────────────────────────────────┤
│                        ━━━ 性能对比 ━━━                          │
│  指标            固定时长        加权调度        改善幅度          │
│  ───────────────────────────────────────────────────────────   │
│  平均等待时间     12.5秒         4.2秒          66.4%  ↓        │
│  总延误时间       60541秒        18666秒        69.2%  ↓        │
│  完成车辆数       185            185            0.0%            │
│  最大等待时间     45.0秒         33.0秒         26.7%  ↓        │
├──────────────────────────────────────────────────────────────┤
│                            [重新开始]                            │
└──────────────────────────────────────────────────────────────┘
```

### 界面特性

1. **双画面并排显示**：左侧Fixed算法，右侧Weighted算法
2. **实时统计面板**：时间、车辆数、平均速度、平均等待
3. **红绿灯状态显示**：实时显示四个方向的红绿灯状态（中文）
4. **性能对比表格**：底部中央实时对比关键指标
5. **重新开始按钮**：右下角绿色按钮，一键重启实验

### 核心代码片段

```python
# 启动双SUMO实例
traci.start([SUMO_BIN, "-c", CONFIG_FILE, "--seed", "42"],
            port=8813, label="fixed")
traci.start([SUMO_BIN, "-c", CONFIG_FILE, "--seed", "42"],
            port=8814, label="weighted")

# 获取连接
conn_fixed = traci.getConnection("fixed")
conn_weighted = traci.getConnection("weighted")

# 初始化控制器
controller_fixed = FixedController(tls_id="center", green_time=30)
controller_weighted = WeightedController(tls_id="center", min_green=10)

# matplotlib双图布局
fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(24, 12))

# 添加重新开始按钮
button_ax = plt.axes([0.85, 0.01, 0.12, 0.04])
restart_button = Button(button_ax, '重新开始',
                        color='#4CAF50', hovercolor='#45a049')

def restart_simulation(event):
    """重启仿真"""
    plt.close('all')
    conn_fixed.close()
    conn_weighted.close()
    os.execv(sys.executable, ['python3'] + sys.argv)

restart_button.on_clicked(restart_simulation)
```

---

## 🧪 实验场景设计与自动化测试框架

### 场景定义与实验参数

| 场景ID | 场景名称 | 车辆到达率<br>(辆/分钟) | 特殊设定 | 测试算法 | 仿真时长 | 评测重点 |
|:------:|:---------|:----------------------:|:--------|:--------|:--------:|:---------|
| **LD** | 低密度交通 | 10 | 流量稀疏，偶有空相 | Fixed / Weighted | 300s | 检查等待时间与信号利用率 |
| **MD** | 中等密度（基准） | 30 | 正常流量 | Fixed / Weighted | 300s | 比较平均等待与吞吐率 |
| **HD** | 高密度（晚高峰） | 60 | 持续高流量输入 | Fixed / Weighted | 300s | 分析算法稳定性与延误增长 |
| **EV** | 紧急车辆优先 | 30 + 每60s一辆EV | 含 type="ev" 车辆 | Weighted | 300s | 验证紧急车优先放行能力 |

### 实验配置生成规则

#### 1. 路由配置文件（intersection.rou.xml）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<routes>
    <!-- 车辆类型定义 -->
    <vType id="car" accel="2.6" decel="4.5" sigma="0.5"
          length="5" maxSpeed="15" color="1,0,0"/>
    <vType id="ev" accel="3.0" decel="5.0" sigma="0.3"
          length="5.5" maxSpeed="18" color="1,0,0"/>

    <!-- LD场景：低密度 probability=0.02~0.04 -->
    <flow id="flow_N_S" type="car" route="route_N_S"
          begin="0" end="300" probability="0.02"/>
    <flow id="flow_S_N" type="car" route="route_S_N"
          begin="0" end="300" probability="0.03"/>

    <!-- MD场景：中密度 probability=0.08~0.12 -->
    <flow id="flow_N_S" type="car" route="route_N_S"
          begin="0" end="300" probability="0.08"/>
    <flow id="flow_E_W" type="car" route="route_E_W"
          begin="0" end="300" probability="0.10"/>

    <!-- HD场景：高密度 probability=0.15~0.20 -->
    <flow id="flow_N_S" type="car" route="route_N_S"
          begin="0" end="300" probability="0.15"/>
    <flow id="flow_W_E" type="car" route="route_W_E"
          begin="0" end="300" probability="0.18"/>

    <!-- EV场景：紧急车辆 -->
    <flow id="flow_ev" type="ev" route="route_N_S"
          begin="0" end="300" period="60" number="5"/>
</routes>
```

#### 2. 场景配置映射表

```python
SCENARIOS = {
    'LD': {
        'name': '低密度交通',
        'arrival_rate': 10,  # 辆/分钟
        'flow_probability': 0.03,
        'sim_time': 300,
        'algorithms': ['fixed', 'weighted']
    },
    'MD': {
        'name': '中等密度（基准）',
        'arrival_rate': 30,
        'flow_probability': 0.10,
        'sim_time': 300,
        'algorithms': ['fixed', 'weighted']
    },
    'HD': {
        'name': '高密度（晚高峰）',
        'arrival_rate': 60,
        'flow_probability': 0.17,
        'sim_time': 300,
        'algorithms': ['fixed', 'weighted']
    },
    'EV': {
        'name': '紧急车辆优先',
        'arrival_rate': 30,
        'flow_probability': 0.10,
        'ev_period': 60,
        'sim_time': 300,
        'algorithms': ['weighted']
    }
}
```

### 输出指标定义

每个场景需记录以下性能指标：

```python
metrics = {
    'scenario': str,           # 场景ID (LD/MD/HD/EV)
    'algorithm': str,          # 算法名称 (fixed/weighted)
    'avg_wait_time': float,    # 平均等待时间 (秒)
    'max_wait_time': float,    # 最大等待时间 (秒)
    'total_delay': float,      # 总延误时间 (秒)
    'throughput': int,         # 完成车辆数
    'switch_count': int,       # 相位切换次数
    'avg_speed': float,        # 平均速度 (m/s)
    'ev_avg_delay': float      # 紧急车平均延误 (仅EV场景)
}
```

### 结果文件命名规范

```
results/
├── LD_fixed.csv
├── LD_weighted.csv
├── MD_fixed.csv
├── MD_weighted.csv
├── HD_fixed.csv
├── HD_weighted.csv
├── EV_weighted.csv
└── summary.csv          # 汇总对比表
```

### 自动化测试脚本框架

```python
#!/usr/bin/env python3
"""
自动化实验脚本
运行所有场景并生成对比报告
"""

import subprocess
import pandas as pd

def run_experiment(scenario, algorithm):
    """运行单个实验"""
    cmd = [
        'python3', 'run_scenario.py',
        '--scenario', scenario,
        '--algo', algorithm,
        '--output', f'results/{scenario}_{algorithm}.csv'
    ]
    subprocess.run(cmd, check=True)

def generate_summary():
    """生成汇总报告"""
    results = []
    for scenario in ['LD', 'MD', 'HD', 'EV']:
        for algo in ['fixed', 'weighted']:
            if scenario == 'EV' and algo == 'fixed':
                continue

            df = pd.read_csv(f'results/{scenario}_{algo}.csv')
            results.append({
                '场景': scenario,
                '算法': algo,
                '平均等待(s)': df['avg_wait_time'].mean(),
                '通过量(veh)': df['throughput'].sum(),
                '切换次数': df['switch_count'].sum()
            })

    summary_df = pd.DataFrame(results)
    summary_df.to_csv('results/summary.csv', index=False)
    print(summary_df)

if __name__ == '__main__':
    # 运行所有实验
    for scenario in ['LD', 'MD', 'HD']:
        for algo in ['fixed', 'weighted']:
            print(f"Running {scenario} with {algo}...")
            run_experiment(scenario, algo)

    # EV场景只运行weighted
    run_experiment('EV', 'weighted')

    # 生成汇总报告
    generate_summary()
```

### 预期输出格式

#### summary.csv 示例

```csv
场景,算法,平均等待(s),通过量(veh),切换次数,备注
LD,fixed,3.1,180,12,基准
LD,weighted,2.4,185,14,优化
MD,fixed,8.5,285,12,基准
MD,weighted,4.2,295,28,优化 (50.6% ↓)
HD,fixed,25.3,320,12,基准
HD,weighted,12.1,340,42,优化 (52.2% ↓)
EV,weighted,5.8,290,32,EV平均延误1.2s
```

---

## 🧱 实现目标总结

### 核心功能清单

- [x] FixedController 固定时长循环控制器
- [x] WeightedController 基于等待时间的自适应控制器
- [x] 双SUMO实例并排对比可视化
- [x] 完全中文化界面
- [x] 实时性能指标统计与对比
- [x] 一键重启实验按钮
- [ ] 四场景自动化测试框架
- [ ] 结果汇总报告生成
- [ ] 紧急车辆优先放行逻辑

### 预期演示效果

1. **可视化对比**：
   - 左侧固定算法：一个方向等待积压，其他方向空闲
   - 右侧加权算法：优先放行等待时间长的方向

2. **性能提升**：
   - 平均等待时间改善 50%~70%
   - 总延误时间改善 65%~70%
   - 最大等待时间降低 25%~30%

3. **场景差异**：
   - LD场景：两种算法差异较小（流量低）
   - MD场景：加权算法显著优于固定算法
   - HD场景：加权算法优势更明显
   - EV场景：验证紧急车辆优先放行能力

---

## 🗂️ 项目文件结构

```
sumo_intersection_viz/
├── CLAUDE.md                      # 本文档
├── README.md                      # 项目说明
├── visualize_compare.py           # 双算法并排对比可视化
├── run_scenario.py                # 单场景实验脚本
├── run_all_experiments.py         # 自动化批量实验
├── generate_summary.py            # 结果汇总报告生成
├── intersection.nod.xml           # 路网节点定义
├── intersection.edg.xml           # 路网边定义
├── intersection.net.xml           # 生成的路网文件
├── intersection.sumocfg           # SUMO配置文件
├── scenarios/                     # 场景配置目录
│   ├── LD.rou.xml                # 低密度场景路由
│   ├── MD.rou.xml                # 中密度场景路由
│   ├── HD.rou.xml                # 高密度场景路由
│   └── EV.rou.xml                # 紧急车辆场景路由
├── controllers/                   # 控制算法目录
│   ├── __init__.py
│   ├── controller_fixed.py       # 固定时长算法
│   └── controller_weighted.py    # 权重调度算法
└── results/                       # 实验结果目录
    ├── LD_fixed.csv
    ├── LD_weighted.csv
    ├── MD_fixed.csv
    ├── MD_weighted.csv
    ├── HD_fixed.csv
    ├── HD_weighted.csv
    ├── EV_weighted.csv
    └── summary.csv               # 汇总对比表
```

---

## 🔧 环境要求

### 必需软件
- Python 3.8+
- SUMO 1.24.0+
- TraCI API

### Python依赖包
```bash
pip install matplotlib numpy pandas
```

---

## 📝 快速开始

### 1. 基础安装

```bash
# 克隆项目
cd sumo_intersection_viz

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行双算法对比可视化

```bash
# 启动实时对比界面
python3 visualize_compare.py

# 界面特性：
# - 左侧：固定时长算法 (30秒周期)
# - 右侧：加权调度算法 (自适应)
# - 底部：实时性能对比表格
# - 右下角：绿色"重新开始"按钮
```

### 3. 运行单场景实验

```bash
# 运行中密度场景 + 固定算法
python3 run_scenario.py --scenario MD --algo fixed

# 运行高密度场景 + 加权算法
python3 run_scenario.py --scenario HD --algo weighted
```

### 4. 运行完整自动化实验

```bash
# 运行所有场景并生成汇总报告
python3 run_all_experiments.py

# 查看结果
cat results/summary.csv
```

---

## 🎨 可视化界面说明

### 中文化配置

```python
# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
```

### 关键界面元素

1. **统计信息面板**（左上/右上）
   - 时间: X秒
   - 车辆数: X
   - 平均速度: X km/h
   - 平均等待: X秒

2. **红绿灯状态面板**（左上/右上）
   - 北: 红/绿
   - 南: 红/绿
   - 东: 红/绿
   - 西: 红/绿

3. **性能对比表格**（底部中央）
   ```
   ━━━━━━━━━━━━━━━━━━ 性能对比 ━━━━━━━━━━━━━━━━━━
   指标              固定时长      加权调度      改善幅度
   ────────────────────────────────────────────
   平均等待时间      12.5秒       4.2秒        66.4%
   总延误时间        60541秒      18666秒      69.2%
   完成车辆数        185          185          0.0%
   最大等待时间      45.0秒       33.0秒       26.7%
   ```

4. **重新开始按钮**（右下角）
   - 颜色：绿色 (#4CAF50)
   - 功能：一键重启实验

---

## 🪶 可扩展功能

### 优先级高
- [ ] 实现紧急车辆优先放行逻辑
- [ ] 增加黄灯与全红时段
- [ ] 优化权重函数（等待时间 + 队长 + 延误综合）

### 优先级中
- [ ] 增加公平性指标与等待方差
- [ ] 支持多路口协调控制
- [ ] 添加实时流量预测

### 优先级低
- [ ] Web界面展示
- [ ] 机器学习优化信号控制
- [ ] 支持更多路网拓扑

---

## 📖 参考资料

- [SUMO官方文档](https://sumo.dlr.de/docs/)
- [TraCI接口文档](https://sumo.dlr.de/docs/TraCI.html)
- [matplotlib中文显示配置](https://matplotlib.org/stable/tutorials/text/usetex.html)

---

## 📄 许可证

本项目采用 MIT 许可证。

---

**Generated with Claude Code**
**Co-Authored-By: Claude <noreply@anthropic.com>**
