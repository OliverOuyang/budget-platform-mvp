# 信贷获客预算管理平台

基于 Streamlit 的信贷获客预算推算与优化平台，提供 **规则推导** 和 **MMM 模型驱动** 两套预算分配方案。

## 功能概览

| 模块 | 方法 | 适用场景 |
|------|------|---------|
| **V01 - 规则推导预算** | 历史系数 + 漏斗链路模拟 | 快速试算、规则口径预算推算 |
| **MMM - 模型驱动预算** | Adstock + Hill 饱和曲线 + 贝叶斯优化 | 量化渠道 ROI、数据驱动的预算再分配 |

**覆盖渠道**：腾讯朋友圈、腾讯视频、腾讯微信、腾讯搜索、抖音、应用商店、精准营销（共 7 个投放渠道）

## 架构设计

```
budget-platform-mvp/
├── Home.py                     # Streamlit 入口，页面注册与导航
├── requirements.txt            # Python 依赖
│
├── app/                        # 应用层（UI 工具 & 配置）
│   ├── config.py               #   业务常量、渠道配置、单位转换
│   ├── ui_utils.py             #   Session State 管理、参数构建、计算触发
│   └── flow_components.py      #   流程组件
│
├── core/                       # 核心业务逻辑（无 Streamlit 依赖，可独立测试）
│   ├── models.py               #   数据模型（BudgetParameters, Table1/2Result, Scenario）
│   ├── calculation_pipeline.py #   计算流水线编排（参数 → 系数 → Table1 → Table2）
│   ├── coefficient_engine.py   #   系数计算（M0/T0 比值、存量 CPS 均值）
│   ├── channel_calculator.py   #   渠道维度计算（Table1: 花费分配 → 交易额推算）
│   ├── customer_group_calculator.py  # 客群维度计算（Table2: 层级交易额汇总）
│   ├── template_manager.py     #   参数模板管理（保存/加载/对比）
│   ├── data_loader.py          #   数据加载与校验
│   └── exporter.py             #   结果导出
│
├── engine/                     # 推算引擎
│   ├── rule_engine.py          #   规则层引擎（历史系数 → 漏斗模拟）
│   └── mmm_engine.py           #   MMM 引擎（Robyn 风格 Python 实现）
│
├── pages/                      # Streamlit 多页面
│   ├── 1_预算输入与配置.py      #   V01: 数据上传与质量检查
│   ├── 2_预算推算结果.py        #   V01: 参数配置 → 计算 → 结果展示
│   ├── mmm_1_数据检查.py        #   MMM: 数据探索与质量校验
│   ├── mmm_2_MMM洞察.py         #   MMM: 模型训练 → 渠道贡献分解
│   ├── mmm_3_预算调整.py        #   MMM: 预算再分配优化
│   ├── mmm_4_方案对比.py        #   MMM: 多方案横向对比
│   ├── mmm_5_结果联动.py        #   MMM: V01 与 MMM 结果联动分析
│   └── _tab_*.py               #   V01 结果页 Tab 子模块
│
├── data/                       # 数据目录（本地文件不提交）
│   └── generate_mock.py        #   Mock 数据生成脚本（104 周周度数据）
│
├── tests/                      # 单元测试
│   ├── test_calculation_pipeline.py
│   ├── test_coefficient_engine.py
│   ├── test_mmm_engine.py
│   └── test_models.py
│
├── utils/                      # 通用工具
│   └── data_loader.py
│
└── .streamlit/
    └── config.toml             # Streamlit 服务配置 & 主题
```

### 分层说明

```
┌─────────────────────────────────────────────┐
│              pages/ (Streamlit UI)           │  展示层：多页面交互
├─────────────────────────────────────────────┤
│              app/ (应用层)                    │  Session 管理、参数构建、配置
├─────────────────────────────────────────────┤
│              core/ (核心业务逻辑)             │  纯 Python，无框架依赖
│  models → coefficient_engine → pipeline      │  数据模型 → 系数 → 流水线编排
│           → channel_calculator               │
│           → customer_group_calculator        │
├─────────────────────────────────────────────┤
│              engine/ (推算引擎)               │  两套独立引擎
│  rule_engine (规则层)  │  mmm_engine (模型层)  │
└─────────────────────────────────────────────┘
```

## V01 规则推导预算

**数据流向**：上传 Excel → 数据质量检查 → 配置参数（总预算 / 渠道分配 / 过件率 / CPS）→ 计算 → 结果展示

**核心计算逻辑**：
1. **系数提取**：从历史数据计算 M0/T0 交易比值（前 6 月均值）和存量首登 CPS（前 3/6 月均值）
2. **Table1 渠道推算**：总预算 × 渠道占比 → 各渠道花费 → 经 CPS 推算 T0 交易额 → 经 M0/T0 比值推算 M0 交易额
3. **Table2 客群汇总**：初审授信户（当月首登 M0 + 存量首登 M0）+ 非初审授信户 → 整体首借交易额 + 全业务 CPS

**输入数据**：
- `raw_达成情况`：渠道维度月度历史数据（花费、过件率、CPS、交易额等）
- `raw_客群首借金额`：客群维度月度数据（授信人数、首贷金额等）

## MMM 模型驱动预算

基于 [Robyn](https://github.com/facebookexperimental/Robyn) 方法论的 Python 实现。

**建模流程**：

```
渠道周度 Spend
    ↓
Adstock 变换（Geometric / Weibull 衰减）
    ↓
Hill 饱和曲线（S 形响应函数）
    ↓
Ridge 回归（媒体系数非负约束）
    ↓
Optuna TPE 贝叶斯优化（300 trials）
    ↓
┌──────────────────────────────────┐
│  渠道贡献分解  │  边际响应曲线    │
│  预算再分配    │  方案对比        │
└──────────────────────────────────┘
```

**关键算法**：
- **Adstock**：几何衰减 `x'_t = x_t + θ · x'_{t-1}` 或 Weibull PDF 权重
- **Hill 饱和**：`f(x) = x^α / (x^α + γ^α)`，α 控制斜率，γ 为半饱和点
- **目标函数**：`min(NRMSE + 0.3 × DecompRSSD - 0.1 × R²)`
- **预算优化**：等边际原则，在总预算约束下最大化预测借款金额

## 快速开始

### 环境要求

- Python >= 3.10

### 安装与运行

```bash
# 克隆仓库
git clone git@gitlab.caijj.net:acquisition-strategy/budget_platform.git
cd budget_platform

# 安装依赖
pip install -r requirements.txt

# 启动应用（默认端口 8506）
streamlit run Home.py
```

### 生成 Mock 数据（可选）

```bash
python data/generate_mock.py
```

生成 104 周（2 年）周度模拟数据，包含 7 渠道花费、曝光/点击、业务漏斗、风险指标、宏观经济变量等。

## 运行测试

```bash
pytest tests/ -v
```

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | Streamlit >= 1.40 |
| 数据处理 | Pandas, NumPy |
| 可视化 | Plotly |
| 超参数优化 | Optuna (TPE Sampler) |
| 统计建模 | SciPy, scikit-learn (Ridge) |
| Excel 处理 | openpyxl |
