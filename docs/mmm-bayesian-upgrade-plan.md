# MMM 贝叶斯化改造方案

> 版本：v1.0 | 日期：2026-04-09 | 分支：feature/mmm-bayesian-upgrade

---

## 一、改造目标

| 目标 | 当前状态 | 目标状态 |
|------|---------|---------|
| 统计框架 | Optuna TPE + Ridge 点估计 | PyMC 贝叶�� MCMC + 后验分布 |
| 不确定性量化 | 无（单一最优解） | 每个参数输出可信区间 |
| 增量实验校准 | 不支持 | 支持注入实验先验 |
| 时变系数 | 固定 beta | 高斯过程时变 beta（Phase 3） |
| 预算优化 | 确定性等边际原则 | 考虑不确定性的稳健优化 |

**核心原则**：渐进式改造，保持向后兼容，双引擎并行直到贝叶斯引擎稳定。

---

## 二、技术选型

### 2.1 框架对比

| 维度 | PyMC-Marketing | Google Meridian | 自研 PyMC |
|------|---------------|-----------------|-----------|
| 安装复杂度 | pip install | GPU 推荐，Python 3.11-3.13 | pip install pymc |
| MMM 内置 | ✅ 开箱即用 | ✅ 但重 | ❌ 需从零搭建 |
| Adstock/Hill | ✅ 内置多种 | ✅ 内置 | 需自定义 |
| 时变系数 | ✅ HSGP 内置 | 有限 | 需自定义 |
| 实验校准 | ✅ 支持 | ✅ 支持 | 需自定义 |
| 与现有代码兼容 | 中（需适配接口） | 低（完全不同架构） | 高（完全自控） |
| 社区活跃度 | 高 | 高 | N/A |

**选择：PyMC-Marketing**

理由：
1. 内置 MMM 类 (`MMM`)，直接支持 Adstock + Saturation + 贝叶斯
2. HSGP 时变系数开箱即用
3. 与现有 Python 技术栈兼容（Pandas/NumPy/Plotly）
4. 无需 GPU，CPU 可运行（NUTS 采样器）
5. 社区活跃，文档完善

### 2.2 新增依赖

```
pymc>=5.10
pymc-marketing>=0.9
arviz>=0.17          # 后验诊断和可视化
nutpie>=0.12         # 可选：Rust 加速采样器
```

---

## 三、架构设计

### 3.1 双引擎架构

```
engine/
├── mmm_engine.py           ← 现有 Optuna+Ridge 引擎（保留，标记为 legacy）
├── mmm_bayesian.py         ← 新增：PyMC 贝叶斯引擎
└── mmm_interface.py        ← 新增：统一接口层（策略模式切换引擎）
```

### 3.2 统一接口 `mmm_interface.py`

```python
class IMMModel(Protocol):
    """双引擎统一接口"""
    def predict(self, df: pd.DataFrame) -> np.ndarray: ...
    def channel_contribution(self, df: pd.DataFrame) -> Dict[str, np.ndarray]: ...
    def marginal_response(self, ch: str, spend_range: np.ndarray, ...) -> np.ndarray: ...
    def budget_optimization(self, total_budget: float, ...) -> Dict: ...
    def budget_scenarios(self, df_recent: pd.DataFrame, ...) -> List[Dict]: ...

class IMMTrainer(Protocol):
    """双引擎统一训练接口"""
    def fit(self, progress_callback=None) -> IMMModel: ...
```

### 3.3 贝叶斯引擎 `mmm_bayesian.py` 核心类

```python
class BayesianChannelParams:
    """单渠道参数（含后验分布）"""
    name: str
    adstock_type: str
    # 后验采样（非点估计）
    theta_samples: np.ndarray      # shape: (n_samples,)
    alpha_samples: np.ndarray
    gamma_samples: np.ndarray
    beta_samples: np.ndarray
    # 汇总统计
    beta_mean: float
    beta_hdi_low: float            # 94% HDI 下界
    beta_hdi_high: float           # 94% HDI 上界

class BayesianMMMModel:
    """贝叶斯 MMM 模型"""
    trace: az.InferenceData         # 完整后验 trace
    channel_params: Dict[str, BayesianChannelParams]
    # 诊断指标
    r_squared: float                # 后验均值 R²
    r_squared_hdi: Tuple[float, float]
    rhat_max: float                 # 收敛诊断（应 < 1.01）
    ess_min: float                  # 有效样本量（应 > 400）
    # 实验校准信息
    calibration_priors: Dict[str, Dict]  # {channel: {mu, sigma, source}}

class BayesianMMMTrainer:
    """贝叶斯训练器"""
    def __init__(self, df, dv_col, channel_cols, ...):
        ...
    def set_calibration_prior(self, channel: str, roas_mu: float, roas_sigma: float):
        """注入增量实验校准先验"""
        ...
    def fit(self, draws=2000, tune=1000, chains=4, progress_callback=None):
        """MCMC 采样"""
        ...
```

---

## 四、分阶段实施计划

### Phase 1：基础贝叶斯化（核心价值，预计 2-3 周）

**目标**：用 PyMC-Marketing 复现现有 Optuna+Ridge 的建模能力，输出后验分布。

#### 1.1 改动清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `engine/mmm_bayesian.py` | 新建 | 贝叶斯引擎核心（~600 行） |
| `engine/mmm_interface.py` | 新建 | 统一接口层（~100 行） |
| `engine/mmm_engine.py` | 微调 | 让 MMMModel/MMMTrainer 实现 IMMModel/IMMTrainer 接口 |
| `requirements.txt` | 修改 | 添加 pymc, pymc-marketing, arviz |
| `pages/mmm_模型洞察.py` | 修改 | 添加引擎选择开关 + 后验可视化 |
| `tests/test_mmm_bayesian.py` | 新建 | 贝叶斯引擎单元测试 |

#### 1.2 PyMC 模型定义（核心逻辑）

```python
import pymc as pm
from pymc_marketing.mmm import MMM, GeometricAdstock, LogisticSaturation

def build_pymc_model(df, channel_cols, dv_col, adstock_type="geometric"):
    """
    对标现有 _objective() + _ridge_fit() 的贝叶斯等价实现
    """
    mmm = MMM(
        date_column="week",
        channel_columns=channel_cols,
        adstock=GeometricAdstock(l_max=8),        # 对标现有 max_lag=8
        saturation=LogisticSaturation(),           # 对标现有 Hill 函数
    )

    # 默认先验（弱信息先验）
    # theta ~ Beta(1, 3)          对标现有 [0.0, 0.8]
    # alpha ~ Gamma(2, 1)         对标现有 [0.5, 4.0]
    # gamma ~ Beta(2, 2)          对标现有 [0.1, 0.9]
    # beta  ~ HalfNormal(sigma=2) 对标现有非负 Ridge 约束

    mmm.fit(
        X=df[channel_cols + control_cols],
        y=df[dv_col],
        draws=2000,
        tune=1000,
        chains=4,
        target_accept=0.9,
    )
    return mmm
```

#### 1.3 现有函数映射

| 现有函数 (mmm_engine.py) | 贝叶斯等价 (mmm_bayesian.py) |
|--------------------------|------------------------------|
| `MMMTrainer._objective()` (L716) | PyMC 模型定义 + 先验设定 |
| `MMMTrainer._ridge_fit()` (L677) | PyMC NUTS 采样（自动） |
| `MMMTrainer._build_features()` (L626) | PyMC-Marketing 自动处理 Adstock+Hill |
| `MMMTrainer._evaluate_cv()` (L993) | `mmm.sample_posterior_predictive()` + LOO-CV |
| `MMMTrainer._bootstrap_stability()` (L1107) | 后验分布天然包含不确定性（无需 bootstrap） |
| `MMMModel.predict()` (L157) | `mmm.predict()` 返回预测分布 |
| `MMMModel.channel_contribution()` (L212) | `mmm.compute_channel_contribution_original_scale()` |
| `MMMModel.marginal_response()` (L284) | 从后验采样计算边际响应分布 |
| `MMMModel.budget_optimization()` (L333) | 基于后验均值的等边际优化 + HDI 置信带 |

#### 1.4 UI 改动

```
pages/mmm_模型洞察.py 新增：
├── 引擎选择器：st.radio("引擎", ["Optuna (Legacy)", "贝叶斯 (PyMC)"])
├── 后验诊断面板：
│   ├── Trace plot（链收敛）
│   ├── R-hat / ESS 汇总表
│   └── 后验预测检查（PPC）
├── 渠道贡献分解：
│   ├── 带 94% HDI 的贡献柱状图（对比现有确定性柱状图）
│   └── ROAS 后验分布小提琴图
└── 预算优化：
    └── 带不确定性带的边际响应曲线
```

---

### Phase 2：增量实验校准（预计 1-2 周）

**目标**：支持将增量实验结果作为信息性先验注入模型。

#### 2.1 改动清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `engine/mmm_bayesian.py` | 修改 | 添加 `set_calibration_prior()` 方法 |
| `core/calibration_manager.py` | 新建 | 校准数据管理（存储/加载实验结果） |
| `pages/mmm_模型洞察.py` | 修改 | 添加校准数据输入面板 |

#### 2.2 校准先验注入机制

```python
def set_calibration_prior(self, channel: str, roas_mu: float, roas_sigma: float):
    """
    将增量实验的 ROAS 估计注入为 beta 先验
    
    示例：腾讯朋友圈增量测试 ROAS = 2.1 ± 0.4
    → beta_moments ~ Normal(mu=2.1, sigma=0.4)
    替代默认弱先验 HalfNormal(sigma=2)
    """
    self.calibration_priors[channel] = {
        "roas_mu": roas_mu,
        "roas_sigma": roas_sigma,
        "source": "incrementality_test",
    }
```

#### 2.3 可用的校准数据来源（无需额外投入）

| 来源 | 方法 | 可用性 |
|------|------|--------|
| 历史暂停投放事件 | 自然实验（某渠道暂停投放的周度数据） | 检查历史数据中是否存在 |
| 渠道上下线事件 | 差分分析（渠道启动/关停前后对比） | 需确认是否有此类事件 |
| 季节性预算波动 | 工具变量（预算分配受季节驱动，非效果驱动） | 可从现有数据提取 |

---

### Phase 3：时变系数（预计 1-2 周）

**目标**：捕捉渠道效率随时间的动态变化。

#### 3.1 改动清单

| 文件 | 动作 | 说明 |
|------|------|------|
| `engine/mmm_bayesian.py` | 修改 | 添加 HSGP 时变系数选项 |
| `pages/mmm_模型洞察.py` | 修改 | 添加时变效率可视化 |

#### 3.2 技术实现

```python
from pymc_marketing.mmm import MMM

# Phase 3：启用时变系数
mmm = MMM(
    ...,
    time_varying_intercept=True,         # 时变基线
    time_varying_media=True,             # 时变渠道效率
    # HSGP 近似参数
    yearly_seasonality=2,                # 年度季节性阶数
)
```

**收益**：
- 自动检测哪个渠道在什么时期效率下降/上升
- 最近 N 周的预测更准确（使用近期系数而非全窗口平均）
- 为预算调整提供时效性更强的依据

---

### Phase 4：跨渠道溢出建模（可选，预计 2 周）

**目标**：建模渠道间的协同/溢出效应。

#### 方案 A：交互项

```python
# 在模型中添加渠道交互特征
interaction_cols = [
    "tencent_video × tencent_search",    # 视频曝光驱动搜索
    "douyin × app_store",                 # 抖音引流应用商店
]
```

#### 方案 B：DAG 因果结构学习（高级）

使用 `causal-learn` 或 `DoWhy` 从数据中发现渠道间因果关系，再注入模型。

**建议**：Phase 4 优先级低，等 Phase 1-3 稳定后再考虑。

---

## 五、风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| MCMC 采样时间过长 | 训练从分钟级变为 10-30 分钟 | 高 | 使用 nutpie 加速；减少 draws；UI 添加进度条和预估时间 |
| PyMC 与 Streamlit 线程冲突 | 采样过程阻塞 UI | 中 | 使用 subprocess 或 threading 隔离采样 |
| 后验不收敛（R-hat > 1.01） | 模型结果不可信 | 中 | 增加 tune；调整先验；检查数据多重共线性 |
| PyMC-Marketing API 变更 | 升级后代码失效 | 低 | 锁定版本；关注 changelog |
| 模型结果与 Legacy 差异大 | 用户困惑 | 中 | 双引擎对比模式；文档说明差异原因 |
| Windows 环境兼容性 | PyMC 在 Windows 上安装/运行问题 | 中 | 优先测试 conda 安装；提供 WSL 备选方案 |

---

## 六、回滚策略

1. **双引擎并行**：Legacy 引擎始终可用，通过 UI 开关切换
2. **Git 分支隔离**：所有改动在 `feature/mmm-bayesian-upgrade` 上，不影响 main
3. **接口兼容**：BayesianMMMModel 实现与 MMMModel 相同的接口，UI 层无感知
4. **阶段性合并**：每个 Phase 完成并验证后单独合并到 main

---

## 七、验收标准

### Phase 1 完成标准

- [ ] `BayesianMMMTrainer.fit()` 可在 104 周 × 7 渠道数据上完成采样
- [ ] 后验 R-hat < 1.01，ESS > 400
- [ ] `BayesianMMMModel.predict()` 的后验均值 R² ≥ 0.7（与 Legacy 可比）
- [ ] `BayesianMMMModel.channel_contribution()` 输出带 HDI 的渠道贡献
- [ ] UI 可切换双引擎，后验诊断面板功能正常
- [ ] `test_mmm_bayesian.py` 全部通过

### Phase 2 完成标准

- [ ] `set_calibration_prior()` 可注入渠道级 ROAS 先验
- [ ] 注入先验后 beta 后验分布向先验偏移（视觉验证）
- [ ] 校准数据可从 UI 输入并持久化

### Phase 3 完成标准

- [ ] 时变系数模式可选启用
- [ ] 时变效率折线图在 UI 中展示
- [ ] 近期 ROAS 估计与全窗口估计可对比

---

## 八、参考资料

- [PyMC-Marketing 文档](https://www.pymc-marketing.io/)
- [PyMC-Marketing MMM 教程](https://www.pymc-marketing.io/en/stable/notebooks/mmm/mmm_example.html)
- [Bayesian MMM 实验校准](https://www.pymc-labs.com/blog-posts/reducing-customer-acquisition-costs-how-we-saved-our-clients-millions-in-ad-spend/)
- [时变系数建模](https://www.pymc-labs.com/blog-posts/modelling-changes-marketing-effectiveness-over-time)
- [Your MMM is Broken (Wharton/LBS)](https://arxiv.org/html/2408.07678v1)
- [WorkMagic 增量校准 MMM](https://www.workmagic.io/solutions/incrementality-calibrated-mmm)
