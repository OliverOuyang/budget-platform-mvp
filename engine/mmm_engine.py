"""
MMM 引擎（Robyn 风格 Python 实现）
核心功能：
  1. Adstock 变换（几何衰减 + Weibull 衰减）
  2. Hill 饱和曲线（S 形响应函数）
  3. 贝叶斯超参数优化（Optuna）
  4. 渠道贡献分解
  5. 边际响应曲线
  6. 预算再分配建议（等边际原则）
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import warnings
import optuna
from pathlib import Path
warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ─── Adstock 变换 ──────────────────────────────────────────────────────────────

def geometric_adstock(x: np.ndarray, theta: float) -> np.ndarray:
    """
    几何衰减 Adstock
    x_t' = x_t + theta * x_{t-1}'
    theta ∈ [0, 1)：衰减率，越大滞后效应越强
    """
    n = len(x)
    out = np.zeros(n)
    out[0] = x[0]
    for t in range(1, n):
        out[t] = x[t] + theta * out[t - 1]
    return out


def weibull_adstock(x: np.ndarray, shape: float, scale: float, maxlag: int = 8) -> np.ndarray:
    """
    Weibull PDF Adstock（Robyn 默认方式）
    shape: 形状参数（控制峰值位置）
    scale: 尺度参数（控制衰减速度）
    maxlag: 最大滞后周数
    """
    from scipy.stats import weibull_min
    lags = np.arange(1, maxlag + 1)
    weights = weibull_min.pdf(lags, c=shape, scale=scale)
    w_sum = weights.sum()
    if w_sum > 0:
        weights = weights / w_sum
    else:
        weights = np.ones(maxlag) / maxlag

    n = len(x)
    out = np.zeros(n)
    for t in range(n):
        for lag, w in enumerate(weights):
            if t - lag >= 0:
                out[t] += w * x[t - lag]
    return out


# ─── Hill 饱和曲线 ─────────────────────────────────────────────────────────────

def hill_saturation(x: np.ndarray, alpha: float, gamma: float) -> np.ndarray:
    """
    Hill 函数（S 形饱和曲线）
    f(x) = x^alpha / (x^alpha + gamma^alpha)
    alpha: 曲线斜率（>1 S形，<1 凹形）
    gamma: 半饱和点（x=gamma 时响应为 0.5）
    """
    x_safe = np.maximum(x, 1e-10)
    return x_safe ** alpha / (x_safe ** alpha + gamma ** alpha)


# ─── 渠道参数 ──────────────────────────────────────────────────────────────────

@dataclass
class ChannelParams:
    """单渠道 MMM 参数"""
    name: str
    # Adstock
    adstock_type: str = "geometric"   # "geometric" or "weibull"
    theta: float = 0.3                # 几何衰减率
    weibull_shape: float = 2.0        # Weibull 形状
    weibull_scale: float = 2.0        # Weibull 尺度
    # 饱和
    alpha: float = 2.0                # Hill alpha
    gamma: float = 0.5                # Hill gamma（相对归一化后的值）
    # 线性系数
    beta: float = 1.0                 # 渠道贡献系数
    _norm_max: float = 0.0            # 训练集归一化 max（0=动态计算，向后兼容）

    def transform(self, spend: np.ndarray) -> np.ndarray:
        """完整变换：Adstock → 归一化 → Hill 饱和"""
        spend = np.nan_to_num(spend, nan=0.0)
        # Step 1: Adstock
        if self.adstock_type == "weibull":
            adstocked = weibull_adstock(spend, self.weibull_shape, self.weibull_scale)
        else:
            adstocked = geometric_adstock(spend, self.theta)

        # Step 2: 归一化到 [0, 1]（用固定 train max 保证一致性）
        max_val = self._norm_max if self._norm_max > 0 else adstocked.max()
        if max_val > 0:
            normalized = adstocked / max_val
        else:
            normalized = adstocked

        # Step 3: Hill 饱和
        saturated = hill_saturation(normalized, self.alpha, self.gamma)
        return saturated


# ─── MMM 模型 ─────────────────────────────────────────────────────────────────

@dataclass
class MMMModel:
    """
    Robyn 风格 MMM 模型
    因变量：dv_t0_loan_amt（借款金额）
    自变量：各渠道 spend（经过 Adstock + 饱和变换）+ organic + 控制变量
    """
    channel_params: Dict[str, ChannelParams] = field(default_factory=dict)
    intercept: float = 0.0
    context_coefs: Dict[str, float] = field(default_factory=dict)
    organic_params: Dict[str, ChannelParams] = field(default_factory=dict)
    impressions_params: Dict[str, ChannelParams] = field(default_factory=dict)
    r_squared: float = 0.0
    nrmse: float = 0.0
    decomp_rssd: float = 0.0
    test_r_squared: float = 0.0
    train_nrmse: float = 0.0
    mape_holdout: float = 0.0
    dw_stat: float = 0.0
    is_fitted: bool = False
    pareto_results: List[Dict] = field(default_factory=list)
    # US-701: Generalization diagnostics
    cv_results: Dict = field(default_factory=dict)
    bootstrap_stability: Dict = field(default_factory=dict)
    # US-702/705: Training metadata
    dv_col: str = ""
    training_meta: Dict = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)

    # 训练数据缓存
    _df: Optional[pd.DataFrame] = field(default=None, repr=False)
    _channel_keys: List[str] = field(default_factory=list, repr=False)
    _context_keys: List[str] = field(default_factory=list, repr=False)
    _organic_keys: List[str] = field(default_factory=list, repr=False)
    _impressions_keys: List[str] = field(default_factory=list, repr=False)
    _dv_mean: float = field(default=1.0, repr=False)
    _dv_std: float = field(default=1.0, repr=False)
    _use_log_dv: bool = field(default=False, repr=False)
    _context_stats: Dict[str, Tuple[float, float]] = field(default_factory=dict, repr=False)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """给定数据预测因变量（返回原始量纲，万元）"""
        n = len(df)
        y_pred_norm = np.full(n, self.intercept)

        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col in df.columns:
                spend = df[spend_col].values.astype(float)
                transformed = params.transform(spend)
                y_pred_norm += params.beta * transformed

        # Impressions media features (Adstock + Hill, separate from spend)
        for ch, params in self.impressions_params.items():
            imp_col = f"{ch}_impressions"
            if imp_col in df.columns:
                imp = df[imp_col].values.astype(float)
                transformed = params.transform(imp)
                y_pred_norm += params.beta * transformed

        # Organic variables (Adstock only, no Hill)
        for org_key, params in self.organic_params.items():
            org_col = f"{org_key}_first_login"
            if org_col in df.columns:
                vals = np.nan_to_num(df[org_col].values.astype(float), nan=0.0)
                if params.adstock_type == "weibull":
                    adstocked = weibull_adstock(vals, params.weibull_shape, params.weibull_scale)
                else:
                    adstocked = geometric_adstock(vals, params.theta)
                norm_max = params._norm_max if params._norm_max > 0 else (adstocked.max() if adstocked.max() > 0 else 1.0)
                y_pred_norm += params.beta * (adstocked / norm_max)

        for ctx, coef in self.context_coefs.items():
            if ctx in df.columns:
                ctx_vals = df[ctx].values.astype(float)
                # Trend features use _context_stats=(0.0, 1.0) sentinel to skip z-score,
                # keeping them in [0,1] range. See _build_features:624-628 for training equivalent.
                if ctx in self._context_stats:
                    ctx_mean, ctx_std = self._context_stats[ctx]
                elif self._df is not None and ctx in self._df.columns:
                    ctx_mean = self._df[ctx].mean()
                    ctx_std  = self._df[ctx].std() + 1e-9
                else:
                    ctx_mean = np.nanmean(ctx_vals)
                    ctx_std  = np.nanstd(ctx_vals) + 1e-9
                ctx_vals = np.nan_to_num(ctx_vals, nan=ctx_mean)
                y_pred_norm += coef * (ctx_vals - ctx_mean) / ctx_std

        # 反标准化
        y_pred = y_pred_norm * self._dv_std + self._dv_mean
        # Log DV inverse transform
        if self._use_log_dv:
            y_pred = np.expm1(y_pred)
        return y_pred

    def channel_contribution(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """分解各渠道贡献（绝对值，万元），包含organic和impressions渠道"""
        norm_contribs = {}

        # Paid spend contributions (normalized space)
        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col in df.columns:
                spend = df[spend_col].values.astype(float)
                transformed = params.transform(spend)
                norm_contribs[ch] = np.maximum(params.beta * transformed, 0)

        # Impressions contributions (merged into same channel key)
        for ch, params in self.impressions_params.items():
            imp_col = f"{ch}_impressions"
            if imp_col in df.columns:
                imp = df[imp_col].values.astype(float)
                transformed = params.transform(imp)
                imp_contrib = np.maximum(params.beta * transformed, 0)
                if ch in norm_contribs:
                    norm_contribs[ch] = norm_contribs[ch] + imp_contrib
                else:
                    norm_contribs[ch] = imp_contrib

        # Organic channel contributions
        for org_key, params in self.organic_params.items():
            org_col = f"{org_key}_first_login"
            if org_col in df.columns:
                vals = np.nan_to_num(df[org_col].values.astype(float), nan=0.0)
                if params.adstock_type == "weibull":
                    adstocked = weibull_adstock(vals, params.weibull_shape, params.weibull_scale)
                else:
                    adstocked = geometric_adstock(vals, params.theta)
                norm_max = params._norm_max if params._norm_max > 0 else (adstocked.max() if adstocked.max() > 0 else 1.0)
                norm_contribs[org_key] = np.maximum(params.beta * (adstocked / norm_max), 0)

        if self._use_log_dv:
            # Proportional decomposition for log-transformed DV
            y_pred = self.predict(df)  # original scale via expm1

            # Base prediction (intercept + context, no media)
            base_norm = np.full(len(df), self.intercept)
            for ctx, coef in self.context_coefs.items():
                if ctx in df.columns:
                    ctx_vals = df[ctx].values.astype(float)
                    if ctx in self._context_stats:
                        ctx_mean, ctx_std = self._context_stats[ctx]
                    else:
                        ctx_mean = np.nanmean(ctx_vals)
                        ctx_std = np.nanstd(ctx_vals) + 1e-9
                    ctx_vals = np.nan_to_num(ctx_vals, nan=ctx_mean)
                    base_norm += coef * (ctx_vals - ctx_mean) / ctx_std
            base_pred = np.expm1(base_norm * self._dv_std + self._dv_mean)
            media_effect = np.maximum(y_pred - base_pred, 0)

            # Proportional allocation based on normalized contributions
            total_norm = np.zeros(len(df))
            for v in norm_contribs.values():
                total_norm += v

            contributions = {}
            for key, nc in norm_contribs.items():
                share = nc / (total_norm + 1e-9)
                contributions[key] = np.maximum(share * media_effect, 0)
        else:
            # Linear decomposition (original approach)
            contributions = {}
            for key, nc in norm_contribs.items():
                contributions[key] = nc * self._dv_std

        return contributions

    def marginal_response(self, ch: str, spend_range: np.ndarray,
                          df_last=None) -> np.ndarray:
        """
        计算单渠道边际响应曲线
        spend_range: 花费取值范围（万元）
        df_last: 近期数据（用于计算其他渠道的操作点基线）
        返回值为原始量纲（万元），log-DV 模型通过 expm1 逆变换还原
        """
        params = self.channel_params.get(ch)
        if params is None:
            return np.zeros(len(spend_range))

        # Base prediction: intercept + other channels' contributions at operating point
        base_norm = self.intercept
        if df_last is not None and len(df_last) > 0:
            # Add other paid channels at their recent mean
            for other_ch, other_params in self.channel_params.items():
                if other_ch == ch:
                    continue
                col = f"{other_ch}_spend"
                if col in df_last.columns:
                    mean_spend = np.array([float(df_last[col].mean())])
                    t = other_params.transform(mean_spend)
                    base_norm += other_params.beta * t[0]
            # Add impressions at their recent mean
            for imp_ch, imp_params in self.impressions_params.items():
                col = f"{imp_ch}_impressions"
                if col in df_last.columns:
                    mean_imp = np.array([float(df_last[col].mean())])
                    t = imp_params.transform(mean_imp)
                    base_norm += imp_params.beta * t[0]
        base_denorm = base_norm * self._dv_std + self._dv_mean

        responses = []
        for s in spend_range:
            spend_arr = np.array([s])
            transformed = params.transform(spend_arr)
            contrib_norm = params.beta * transformed[0]

            if self._use_log_dv:
                # log-DV: response = expm1(base + contrib) - expm1(base)
                full_denorm = (base_norm + contrib_norm) * self._dv_std + self._dv_mean
                response = float(np.expm1(full_denorm) - np.expm1(base_denorm))
            else:
                response = float(contrib_norm * self._dv_std)

            responses.append(max(response, 0))
        return np.array(responses)

    def budget_optimization(self, total_budget: float,
                            df_recent: pd.DataFrame,
                            n_points: int = 50,
                            channel_constr_low: float = 0.3,
                            channel_constr_up: float = 5.0) -> Dict[str, float]:
        """
        等边际原则预算再分配（Robyn 风格渠道约束）

        Parameters
        ----------
        total_budget : float  总预算（万元）
        df_recent : pd.DataFrame  近期数据（用于context变量均值）
        channel_constr_low : float  渠道下限倍数（相对当前均值，默认0.3x）
        channel_constr_up : float  渠道上限倍数（默认5.0x）
        """
        channels = list(self.channel_params.keys())

        # Current spend per channel (mean)
        current_spends = {}
        for ch in channels:
            col = f"{ch}_spend"
            if col in df_recent.columns:
                current_spends[ch] = max(float(df_recent[col].mean()), 1.0)
            else:
                current_spends[ch] = total_budget / len(channels)

        def objective(trial):
            spends = {}
            for ch in channels:
                lo = current_spends[ch] * channel_constr_low
                hi = current_spends[ch] * channel_constr_up
                spends[ch] = trial.suggest_float(f"s_{ch}", lo, hi)

            # Normalize to total budget
            raw_total = sum(spends.values())
            if raw_total > 0:
                spends = {ch: total_budget * v / raw_total for ch, v in spends.items()}

            row = {f"{ch}_spend": [spends[ch]] for ch in channels}
            # Include impressions vars at recent mean
            for imp_ch in self._impressions_keys:
                imp_col = f"{imp_ch}_impressions"
                if imp_col in df_recent.columns:
                    row[imp_col] = [float(np.nan_to_num(df_recent[imp_col].mean(), nan=0.0))]
            # Include organic vars at recent mean
            for org_key in self._organic_keys:
                org_col = f"{org_key}_first_login"
                if org_col in df_recent.columns:
                    row[org_col] = [df_recent[org_col].mean()]
            for ctx in self._context_keys:
                if ctx in df_recent.columns:
                    row[ctx] = [df_recent[ctx].mean()]
            df_sim = pd.DataFrame(row)

            y_pred = self.predict(df_sim)[0]
            return -y_pred

        study = optuna.create_study(direction="minimize",
                                    sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=200, show_progress_bar=False)

        best = study.best_params
        raw_spends = {ch: best[f"s_{ch}"] for ch in channels}
        raw_total = sum(raw_spends.values())
        optimal_spends = {ch: round(total_budget * v / raw_total, 2)
                          for ch, v in raw_spends.items()}
        return optimal_spends

    def budget_scenarios(self, df_recent: pd.DataFrame,
                         multipliers: List[float] = None,
                         channel_constr_low: float = 0.3,
                         channel_constr_up: float = 5.0) -> Dict[str, Dict[str, float]]:
        """
        多场景预算分配（Robyn 风格：80%~120% 预算水平）

        Returns dict of {scenario_label: {channel: spend}}
        """
        if multipliers is None:
            multipliers = [0.8, 0.9, 1.0, 1.1, 1.2]

        current_total = sum(
            float(df_recent[f"{ch}_spend"].mean())
            for ch in self.channel_params
            if f"{ch}_spend" in df_recent.columns
        )

        scenarios = {}
        for mult in multipliers:
            label = f"{int(mult * 100)}%"
            budget = current_total * mult
            allocation = self.budget_optimization(
                budget, df_recent,
                channel_constr_low=channel_constr_low,
                channel_constr_up=channel_constr_up,
            )
            scenarios[label] = allocation
        return scenarios


# ─── 模型训练器 ───────────────────────────────────────────────────────────────

class MMMTrainer:
    """
    使用 Optuna 贝叶斯优化拟合 MMM 参数（Robyn 风格）
    特性：
    - Ridge 回归 + 媒体/organic 系数非负约束
    - 支持 organic_keys（Adstock 无 Hill）
    - Prophet 风格控制变量（trend, season, holiday）
    - 多试验 Pareto 前沿选模型（NRMSE vs DecompRSSD）
    - 时间序列 train/test 切分（后 20% hold-out）
    - 自动检测渠道列，适配月度/周度数据
    """

    DEFAULT_CHANNEL_KEYS = [
        "tencent_moments", "tencent_video", "tencent_wechat", "tencent_search",
        "douyin", "app_store", "precision_marketing",
    ]
    DEFAULT_CONTEXT_KEYS = [
        "holiday_days", "exclude_rate", "callback_ratio",
        "cpi_yoy", "lpr_1y",
        "trend", "trend_cp_1", "trend_cp_2",
        "season_sin", "season_cos",
        "season_sin2", "season_cos2",
        "season_sin3", "season_cos3",
        "holiday_week",
    ]

    # Robyn-style RSSD weight in composite selection score: NRMSE + w*RSSD
    RSSD_WEIGHT = 0.3

    # Backward compat aliases
    CHANNEL_KEYS = DEFAULT_CHANNEL_KEYS
    CONTEXT_KEYS = DEFAULT_CONTEXT_KEYS

    def __init__(self, df: pd.DataFrame, dv_col: str = "dv_t0_loan_amt",
                 n_trials: int = 300, adstock_type: str = "auto",
                 channel_keys: Optional[List[str]] = None,
                 context_keys: Optional[List[str]] = None,
                 organic_keys: Optional[List[str]] = None,
                 n_models: int = 5,
                 use_log_dv: Optional[bool] = None,
                 train_weeks: Optional[int] = None,
                 use_interactions: bool = False,
                 regularization: str = "ridge",
                 n_bag: int = 7):
        # US-801: Trim to recent N weeks if specified
        if train_weeks is not None and train_weeks < len(df):
            df = df.iloc[-train_weeks:].reset_index(drop=True)

        self.df = df.copy()
        self.dv_col = dv_col if dv_col in df.columns else "loan_amt"
        self.use_interactions = use_interactions
        self.regularization = regularization
        self.n_bag = n_bag

        # Fill NaN in numeric columns (spend/organic/context may have gaps)
        for col in self.df.select_dtypes(include=[np.number]).columns:
            self.df[col] = self.df[col].fillna(0)

        # Auto-select adstock type: Weibull for weekly (>30 rows), geometric for monthly
        if adstock_type == "auto":
            self.adstock_type = "weibull" if len(df) > 30 else "geometric"
        else:
            self.adstock_type = adstock_type

        # Auto-detect paid channels from _spend columns
        if channel_keys is None:
            detected = [col.replace("_spend", "") for col in df.columns
                        if col.endswith("_spend") and col != "total_spend"]
            self.channel_keys = (detected if detected
                                 else [ch for ch in self.DEFAULT_CHANNEL_KEYS
                                       if f"{ch}_spend" in df.columns])
        else:
            self.channel_keys = [ch for ch in channel_keys
                                  if f"{ch}_spend" in df.columns]

        # Auto-detect impressions columns (non-zero data required)
        self.impressions_keys = []
        for ch in self.channel_keys:
            imp_col = f"{ch}_impressions"
            if imp_col in self.df.columns and self.df[imp_col].sum() > 0:
                self.impressions_keys.append(ch)

        # Auto-detect organic keys from _first_login columns (excluding paid channels)
        if organic_keys is None:
            paid_set = set(self.channel_keys)
            self.organic_keys = [
                col.replace("_first_login", "") for col in df.columns
                if col.endswith("_first_login")
                and col.replace("_first_login", "") not in paid_set
            ]
        else:
            self.organic_keys = [k for k in organic_keys
                                  if f"{k}_first_login" in df.columns]

        # Auto-detect context keys (exogenous variables only — no per-channel endogenous vars)
        if context_keys is None:
            self.context_keys = [c for c in self.DEFAULT_CONTEXT_KEYS if c in df.columns]
        else:
            self.context_keys = [c for c in context_keys if c in df.columns]

        # Note: STL features (stl_trend, stl_seasonal) are excluded from regression
        # because stl_trend is derived from the DV itself (target leakage).
        # STL remains in the DataFrame for visualization only.
        # Fourier features (trend, season_sin, etc.) are purely exogenous.

        # Spend × Impressions interaction features (US-704)
        # For channels with both spend and impressions, add normalized interaction term
        # to capture synergy (e.g., tencent's spend effect depends on impressions level)
        # US-802: Off by default to reduce collinearity; enable with use_interactions=True
        self.interaction_keys = []
        if self.use_interactions:
            for ch in self.impressions_keys:
                spend_col = f"{ch}_spend"
                imp_col = f"{ch}_impressions"
                if spend_col in self.df.columns and imp_col in self.df.columns:
                    interact_col = f"{ch}_spend_x_imp"
                    spend_vals = self.df[spend_col].values.astype(float)
                    imp_vals = self.df[imp_col].values.astype(float)
                    # Normalize each to [0,1] then multiply → interaction in [0,1]
                    s_norm = spend_vals / (spend_vals.max() + 1e-9)
                    i_norm = imp_vals / (imp_vals.max() + 1e-9)
                    self.df[interact_col] = s_norm * i_norm
                    self.interaction_keys.append(interact_col)
                    self.context_keys.append(interact_col)

        # Scale down trials for small datasets
        if n_trials > 200 and len(df) < 30:
            self.n_trials = min(n_trials, 150)
        else:
            self.n_trials = n_trials

        self.n_models = max(1, n_models)

        # Log DV transform: default True for weekly data (>30 rows)
        self.use_log_dv = use_log_dv if use_log_dv is not None else (len(df) > 30)

        # Adstock lag: shorter for monthly data
        self.max_adstock_lag = 8 if len(df) > 30 else 3

        # ── Train/test split (chronological, last 20% held out) ──────────
        self.n_train = int(len(self.df) * 0.8)
        self.df_train = self.df.iloc[:self.n_train].copy()
        self.df_test = self.df.iloc[self.n_train:].copy()

        # 因变量 (on TRAIN set only to prevent leakage)
        self.dv_train = self.df_train[self.dv_col].values.astype(float)

        # Log transform DV before normalization
        if self.use_log_dv:
            self.dv_train = np.log1p(self.dv_train)

        self.dv_mean = self.dv_train.mean()
        self.dv_std  = self.dv_train.std() + 1e-9
        self.dv_train_norm = (self.dv_train - self.dv_mean) / self.dv_std

        # Full DV for final metrics (normalized with train stats)
        self.dv_full = df[self.dv_col].values.astype(float)
        if self.use_log_dv:
            self.dv_full = np.log1p(self.dv_full)
        self.dv_full_norm = (self.dv_full - self.dv_mean) / self.dv_std

        # 预计算各渠道花费的统计量（train set）
        self.spend_stats = {}
        for ch in self.channel_keys:
            vals = self.df_train[f"{ch}_spend"].values.astype(float)
            self.spend_stats[ch] = {"mean": vals.mean(), "std": vals.std() + 1e-9,
                                     "max": vals.max() + 1e-9}

        # Impressions stats (train set)
        self.impressions_stats = {}
        for ch in self.impressions_keys:
            col = f"{ch}_impressions"
            vals = self.df_train[col].values.astype(float)
            self.impressions_stats[ch] = {"max": vals.max() + 1e-9}

        # Organic stats (train set)
        self.organic_stats = {}
        for org in self.organic_keys:
            col = f"{org}_first_login"
            vals = self.df_train[col].values.astype(float)
            self.organic_stats[org] = {"mean": vals.mean(), "max": vals.max() + 1e-9}

    def _apply_adstock(self, spend: np.ndarray, params: dict, ch: str) -> np.ndarray:
        """应用 Adstock 变换"""
        if self.adstock_type == "weibull":
            shape = params.get(f"{ch}_wb_shape", 2.0)
            scale = params.get(f"{ch}_wb_scale", 2.0)
            return weibull_adstock(spend, shape, scale, maxlag=self.max_adstock_lag)
        else:
            theta = params.get(f"{ch}_theta", 0.3)
            return geometric_adstock(spend, theta)

    def _build_features(self, params: dict, df: pd.DataFrame) -> np.ndarray:
        """构造特征矩阵：[paid_saturated..., impressions_saturated..., organic_adstocked..., context_normalized...]"""
        features = []

        # Paid channels: Adstock → normalize → Hill saturation
        for ch in self.channel_keys:
            spend = df[f"{ch}_spend"].values.astype(float)
            adstocked = self._apply_adstock(spend, params, ch)
            max_val = self.spend_stats[ch]["max"]
            normalized = adstocked / max_val
            alpha = params.get(f"{ch}_alpha", 2.0)
            gamma = params.get(f"{ch}_gamma", 0.5)
            saturated = hill_saturation(normalized, alpha, gamma)
            features.append(saturated)

        # Impressions: Adstock → normalize → Hill (separate params from spend)
        for ch in self.impressions_keys:
            col = f"{ch}_impressions"
            vals = df[col].values.astype(float)
            adstocked = self._apply_adstock(vals, params, f"{ch}_imp")
            max_val = self.impressions_stats[ch]["max"]
            normalized = adstocked / max_val
            alpha = params.get(f"{ch}_imp_alpha", 2.0)
            gamma = params.get(f"{ch}_imp_gamma", 0.5)
            saturated = hill_saturation(normalized, alpha, gamma)
            features.append(saturated)

        # Organic channels: Adstock → normalize only (no Hill)
        for org in self.organic_keys:
            col = f"{org}_first_login"
            vals = df[col].values.astype(float)
            adstocked = self._apply_adstock(vals, params, org)
            max_val = self.organic_stats[org]["max"]
            features.append(adstocked / max_val)

        # Context variables: z-score normalize (except trend features which are pre-scaled)
        # Trend features (trend, trend_cp_*) are already in [0,1] range and designed
        # to extrapolate linearly. Z-scoring them would cause holdout values to be
        # extreme outliers relative to train distribution.
        trend_prefixes = ("trend",)
        for ctx in self.context_keys:
            vals = df[ctx].values.astype(float)
            if ctx.startswith(trend_prefixes):
                features.append(vals)  # pre-scaled, no z-score
            else:
                ctx_mean = self.df_train[ctx].mean()
                ctx_std  = self.df_train[ctx].std() + 1e-9
                features.append((vals - ctx_mean) / ctx_std)

        return np.column_stack(features) if features else np.ones((len(df), 1))

    def _ridge_fit(self, X: np.ndarray, y: np.ndarray,
                   alpha_reg: float = None, l1_ratio: float = None) -> Tuple[np.ndarray, float]:
        """Ridge/ElasticNet 回归（带截距），媒体+impressions+organic 系数非负约束"""
        if alpha_reg is None:
            n = len(y)
            alpha_reg = 0.01 if n > 50 else 0.1 if n > 20 else 1.0
        n_ch = len(self.channel_keys)
        n_imp = len(self.impressions_keys)
        n_org = len(self.organic_keys)
        n_nonneg = n_ch + n_imp + n_org  # paid + impressions + organic must be non-negative

        if self.regularization == "elasticnet" and l1_ratio is not None:
            from sklearn.linear_model import ElasticNet
            model = ElasticNet(alpha=alpha_reg, l1_ratio=l1_ratio, fit_intercept=True, max_iter=5000)
        else:
            from sklearn.linear_model import Ridge
            model = Ridge(alpha=alpha_reg, fit_intercept=True)

        model.fit(X, y)
        coefs = model.coef_.copy()
        intercept = model.intercept_

        # Non-negative intercept in DENORMALIZED scale (Robyn: intercept_sign='non_negative')
        # denorm = intercept * dv_std + dv_mean; for log DV, expm1 ensures non-negative
        # In normalized space: intercept >= -dv_mean / dv_std
        min_intercept = -self.dv_mean / self.dv_std
        intercept = max(min_intercept, intercept)

        # 强制媒体+impressions+organic系数非负
        coefs[:n_nonneg] = np.maximum(coefs[:n_nonneg], 0)

        # 重新计算 R²
        y_pred = X @ coefs + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = max(0.0, 1 - ss_res / ss_tot)

        return np.concatenate([[intercept], coefs]), r2

    def _objective(self, trial) -> float:
        """Optuna objective: (train_nrmse, train_decomp_rssd) — Robyn-aligned.

        Train NRMSE is used for optimization (smooth signal, full training set).
        Holdout NRMSE is evaluated separately in _build_model_from_params for
        model selection and diagnostics (Robyn one-pager style).
        """
        params = {}
        for ch in self.channel_keys:
            if self.adstock_type == "weibull":
                params[f"{ch}_wb_shape"] = trial.suggest_float(f"{ch}_wb_shape", 0.5, 4.0)
                params[f"{ch}_wb_scale"] = trial.suggest_float(f"{ch}_wb_scale", 1.0, 6.0)
            else:
                theta_max = 0.8 if len(self.df) > 30 else 0.5
                params[f"{ch}_theta"] = trial.suggest_float(f"{ch}_theta", 0.0, theta_max)
            params[f"{ch}_alpha"] = trial.suggest_float(f"{ch}_alpha", 0.5, 4.0)
            params[f"{ch}_gamma"] = trial.suggest_float(f"{ch}_gamma", 0.1, 0.9)

        # Impressions: separate Adstock + Hill params
        for ch in self.impressions_keys:
            if self.adstock_type == "weibull":
                params[f"{ch}_imp_wb_shape"] = trial.suggest_float(f"{ch}_imp_wb_shape", 0.5, 4.0)
                params[f"{ch}_imp_wb_scale"] = trial.suggest_float(f"{ch}_imp_wb_scale", 1.0, 6.0)
            else:
                theta_max = 0.8 if len(self.df) > 30 else 0.5
                params[f"{ch}_imp_theta"] = trial.suggest_float(f"{ch}_imp_theta", 0.0, theta_max)
            params[f"{ch}_imp_alpha"] = trial.suggest_float(f"{ch}_imp_alpha", 0.5, 4.0)
            params[f"{ch}_imp_gamma"] = trial.suggest_float(f"{ch}_imp_gamma", 0.1, 0.9)

        # Organic channels: only Adstock params (no Hill)
        for org in self.organic_keys:
            if self.adstock_type == "weibull":
                params[f"{org}_wb_shape"] = trial.suggest_float(f"{org}_wb_shape", 0.5, 4.0)
                params[f"{org}_wb_scale"] = trial.suggest_float(f"{org}_wb_scale", 1.0, 6.0)
            else:
                theta_max = 0.8 if len(self.df) > 30 else 0.5
                params[f"{org}_theta"] = trial.suggest_float(f"{org}_theta", 0.0, theta_max)

        # Build features and fit on TRAIN set
        # US-803: Optuna searches regularization alpha (log-uniform)
        alpha_reg = trial.suggest_float("alpha_reg", 0.1, 200.0, log=True)
        l1_ratio = None
        if self.regularization == "elasticnet":
            l1_ratio = trial.suggest_float("l1_ratio", 0.1, 0.9)
        X_train = self._build_features(params, self.df_train)
        coefs, r2 = self._ridge_fit(X_train, self.dv_train_norm,
                                     alpha_reg=alpha_reg, l1_ratio=l1_ratio)

        intercept = coefs[0]
        n_ch = len(self.channel_keys)
        n_imp = len(self.impressions_keys)
        ch_betas = coefs[1:n_ch + 1]
        imp_betas = coefs[n_ch + 1:n_ch + 1 + n_imp]

        # NRMSE on TRAIN (Robyn optimizes on train, holdout is diagnostic)
        y_pred = X_train @ coefs[1:] + intercept
        nrmse = np.sqrt(np.mean((self.dv_train_norm - y_pred) ** 2)) / (self.dv_train_norm.std() + 1e-9)

        # DecompRSSD on TRAIN (spend decomposition is a training property)
        ch_contribs = np.maximum(ch_betas * np.array([X_train[:, i].sum() for i in range(n_ch)]), 0)
        # Merge impressions contributions into corresponding paid channels
        for j, imp_ch in enumerate(self.impressions_keys):
            imp_contrib = max(float(imp_betas[j]) * X_train[:, n_ch + j].sum(), 0)
            ch_idx = self.channel_keys.index(imp_ch)
            ch_contribs[ch_idx] += imp_contrib
        ch_spends = np.array([self.df_train[f"{ch}_spend"].sum() for ch in self.channel_keys])
        total_contrib = ch_contribs.sum() + 1e-9
        total_spend   = ch_spends.sum() + 1e-9
        decomp_rssd = float(np.sqrt(np.sum(
            (ch_contribs / total_contrib - ch_spends / total_spend) ** 2
        )))

        return nrmse, decomp_rssd

    def _build_model_from_params(self, best_params: dict) -> MMMModel:
        """Given Optuna best_params, build and return a fitted MMMModel."""
        n_ch = len(self.channel_keys)
        n_imp = len(self.impressions_keys)
        n_org = len(self.organic_keys)

        # Build features on FULL dataset for proper adstock carryover,
        # then split into train/test portions
        X_full = self._build_features(best_params, self.df)
        X_train = X_full[:self.n_train]
        X_test = X_full[self.n_train:]

        # Fit Ridge/ElasticNet on train portion only (use Optuna-selected alpha)
        # US-901: Bagged Ridge — average N bootstrap resampled fits for stability
        _best_alpha = best_params.get("alpha_reg")
        _best_l1 = best_params.get("l1_ratio")
        n_bag = self.n_bag
        rng = np.random.RandomState(42)
        bag_coefs_list = []
        for _ in range(n_bag):
            idx = rng.choice(len(X_train), size=len(X_train), replace=True)
            c, _ = self._ridge_fit(X_train[idx], self.dv_train_norm[idx],
                                    alpha_reg=_best_alpha, l1_ratio=_best_l1)
            bag_coefs_list.append(c)
        coefs_full = np.mean(bag_coefs_list, axis=0)
        # Defensive: re-enforce non-negativity on media coefficients after averaging
        n_nonneg = len(self.channel_keys) + len(self.impressions_keys) + len(self.organic_keys)
        coefs_full[1:1 + n_nonneg] = np.maximum(coefs_full[1:1 + n_nonneg], 0)
        # Compute R² with averaged coefficients
        y_pred_r2 = X_train @ coefs_full[1:] + coefs_full[0]
        ss_res_r2 = np.sum((self.dv_train_norm - y_pred_r2) ** 2)
        ss_tot_r2 = np.sum((self.dv_train_norm - self.dv_train_norm.mean()) ** 2)
        r2_full = max(0.0, 1 - ss_res_r2 / (ss_tot_r2 + 1e-9))

        intercept_norm = coefs_full[0]
        idx = 1
        ch_betas_norm = coefs_full[idx:idx + n_ch]; idx += n_ch
        imp_betas_norm = coefs_full[idx:idx + n_imp]; idx += n_imp
        org_betas_norm = coefs_full[idx:idx + n_org]; idx += n_org
        ctx_coefs_norm = coefs_full[idx:]

        # Paid channel params (with _norm_max for consistent normalization)
        channel_params = {}
        for i, ch in enumerate(self.channel_keys):
            norm_max = self.spend_stats[ch]["max"]
            if self.adstock_type == "weibull":
                cp = ChannelParams(
                    name=ch, adstock_type="weibull",
                    weibull_shape=best_params.get(f"{ch}_wb_shape", 2.0),
                    weibull_scale=best_params.get(f"{ch}_wb_scale", 2.0),
                    alpha=best_params.get(f"{ch}_alpha", 2.0),
                    gamma=best_params.get(f"{ch}_gamma", 0.5),
                    beta=float(ch_betas_norm[i]),
                    _norm_max=norm_max,
                )
            else:
                cp = ChannelParams(
                    name=ch, adstock_type="geometric",
                    theta=best_params.get(f"{ch}_theta", 0.3),
                    alpha=best_params.get(f"{ch}_alpha", 2.0),
                    gamma=best_params.get(f"{ch}_gamma", 0.5),
                    beta=float(ch_betas_norm[i]),
                    _norm_max=norm_max,
                )
            channel_params[ch] = cp

        # Impressions params (separate Adstock + Hill)
        impressions_params = {}
        for i, ch in enumerate(self.impressions_keys):
            norm_max = self.impressions_stats[ch]["max"]
            if self.adstock_type == "weibull":
                ip = ChannelParams(
                    name=f"{ch}_imp", adstock_type="weibull",
                    weibull_shape=best_params.get(f"{ch}_imp_wb_shape", 2.0),
                    weibull_scale=best_params.get(f"{ch}_imp_wb_scale", 2.0),
                    alpha=best_params.get(f"{ch}_imp_alpha", 2.0),
                    gamma=best_params.get(f"{ch}_imp_gamma", 0.5),
                    beta=float(imp_betas_norm[i]) if i < len(imp_betas_norm) else 0.0,
                    _norm_max=norm_max,
                )
            else:
                ip = ChannelParams(
                    name=f"{ch}_imp", adstock_type="geometric",
                    theta=best_params.get(f"{ch}_imp_theta", 0.3),
                    alpha=best_params.get(f"{ch}_imp_alpha", 2.0),
                    gamma=best_params.get(f"{ch}_imp_gamma", 0.5),
                    beta=float(imp_betas_norm[i]) if i < len(imp_betas_norm) else 0.0,
                    _norm_max=norm_max,
                )
            impressions_params[ch] = ip

        # Organic params (with _norm_max)
        organic_params = {}
        for i, org in enumerate(self.organic_keys):
            norm_max = self.organic_stats[org]["max"]
            if self.adstock_type == "weibull":
                op = ChannelParams(
                    name=org, adstock_type="weibull",
                    weibull_shape=best_params.get(f"{org}_wb_shape", 2.0),
                    weibull_scale=best_params.get(f"{org}_wb_scale", 2.0),
                    beta=float(org_betas_norm[i]) if i < len(org_betas_norm) else 0.0,
                    _norm_max=norm_max,
                )
            else:
                op = ChannelParams(
                    name=org, adstock_type="geometric",
                    theta=best_params.get(f"{org}_theta", 0.3),
                    beta=float(org_betas_norm[i]) if i < len(org_betas_norm) else 0.0,
                    _norm_max=norm_max,
                )
            organic_params[org] = op

        # Context coefficients + train-set stats for consistent normalization
        context_coefs = {ctx: float(ctx_coefs_norm[i])
                         for i, ctx in enumerate(self.context_keys)
                         if i < len(ctx_coefs_norm)}
        context_stats = {}
        for ctx in self.context_keys:
            if ctx.startswith("trend"):
                context_stats[ctx] = (0.0, 1.0)  # pre-scaled, no z-score
            else:
                ctx_mean = float(self.df_train[ctx].mean())
                ctx_std = float(self.df_train[ctx].std() + 1e-9)
                context_stats[ctx] = (ctx_mean, ctx_std)

        # Train metrics (using properly split features)
        y_pred_train = X_train @ coefs_full[1:] + intercept_norm
        train_nrmse = np.sqrt(np.mean((self.dv_train_norm - y_pred_train) ** 2)) / (self.dv_train_norm.std() + 1e-9)

        # Durbin-Watson statistic on train residuals (tests autocorrelation)
        train_resid = self.dv_train_norm - y_pred_train
        dw_stat = 0.0
        if len(train_resid) > 2:
            diff_resid = np.diff(train_resid)
            dw_stat = float(np.sum(diff_resid ** 2) / (np.sum(train_resid ** 2) + 1e-9))

        ch_contribs = np.maximum(
            ch_betas_norm * np.array([X_train[:, i].sum() for i in range(n_ch)]), 0
        )
        # Merge impressions contributions into corresponding paid channels
        for j, imp_ch in enumerate(self.impressions_keys):
            imp_contrib = max(float(imp_betas_norm[j]) * X_train[:, n_ch + j].sum(), 0)
            ch_idx = self.channel_keys.index(imp_ch)
            ch_contribs[ch_idx] += imp_contrib
        ch_spends = np.array([self.df_train[f"{ch}_spend"].sum() for ch in self.channel_keys])
        total_contrib = ch_contribs.sum() + 1e-9
        total_spend   = ch_spends.sum() + 1e-9
        decomp_rssd = float(np.sqrt(np.sum(
            (ch_contribs / total_contrib - ch_spends / total_spend) ** 2
        )))

        # Holdout metrics (Robyn-aligned: NRMSE on holdout)
        test_r2 = 0.0
        holdout_nrmse = train_nrmse  # fallback if no holdout
        mape_holdout = 0.0
        if len(self.df_test) > 1:
            dv_test = self.df_test[self.dv_col].values.astype(float)
            if self.use_log_dv:
                dv_test = np.log1p(dv_test)
            dv_test_norm = (dv_test - self.dv_mean) / self.dv_std
            y_pred_test = X_test @ coefs_full[1:] + intercept_norm
            ss_res = np.sum((dv_test_norm - y_pred_test) ** 2)
            ss_tot = np.sum((dv_test_norm - dv_test_norm.mean()) ** 2)
            test_r2 = max(0.0, 1 - ss_res / (ss_tot + 1e-9))
            holdout_nrmse = np.sqrt(np.mean((dv_test_norm - y_pred_test) ** 2)) / (dv_test_norm.std() + 1e-9)
            # MAPE on holdout (original scale)
            y_pred_orig = y_pred_test * self.dv_std + self.dv_mean
            dv_test_orig = dv_test
            if self.use_log_dv:
                y_pred_orig = np.expm1(y_pred_orig)
                dv_test_orig = np.expm1(dv_test)
            nonzero = np.abs(dv_test_orig) > 1e-6
            if nonzero.any():
                mape_holdout = float(np.mean(np.abs(
                    (dv_test_orig[nonzero] - y_pred_orig[nonzero]) / dv_test_orig[nonzero]
                )))

        model = MMMModel(
            channel_params=channel_params,
            intercept=intercept_norm,
            context_coefs=context_coefs,
            organic_params=organic_params,
            impressions_params=impressions_params,
            r_squared=r2_full,
            nrmse=holdout_nrmse,
            train_nrmse=train_nrmse,
            decomp_rssd=decomp_rssd,
            test_r_squared=test_r2,
            mape_holdout=mape_holdout,
            dw_stat=dw_stat,
            is_fitted=True,
            _df=self.df,
            _channel_keys=self.channel_keys,
            _context_keys=self.context_keys,
            _organic_keys=self.organic_keys,
            _impressions_keys=self.impressions_keys,
            _dv_mean=self.dv_mean,
            _dv_std=self.dv_std,
            _use_log_dv=self.use_log_dv,
            _context_stats=context_stats,
        )
        return model

    def _evaluate_cv(self, params: dict, n_folds: int = 3) -> float:
        """
        Expanding-window time-series CV for robust generalization estimate.

        Splits data into expanding training windows with fixed-size test folds.
        Returns average test R² across folds.

        CV normalization uses global train-set dv_mean/dv_std (not per-fold stats)
        so that Ridge coefficients remain coherent with the feature matrix, which
        is also normalized using global train-set statistics. Per-fold normalization
        would create a coefficient-scale mismatch between CV and the final model.
        """
        n = len(self.df)
        min_train = max(int(n * 0.4), 30)  # Minimum training window
        fold_size = (n - min_train) // (n_folds + 1)  # Reserve last fold as holdout

        if fold_size < 5:
            # Not enough data for CV — fall back to single split
            return self._build_model_from_params(params).test_r_squared

        test_r2s = []
        for fold in range(n_folds):
            train_end = min_train + fold * fold_size
            test_end = min(train_end + fold_size, n)
            if test_end <= train_end + 2:
                continue

            # Build features on full series for proper adstock carryover
            X_full = self._build_features(params, self.df)
            X_train_cv = X_full[:train_end]
            X_test_cv = X_full[train_end:test_end]

            # DV normalized with global train-set stats for consistency
            # (features also use global train stats, so coefficients stay coherent)
            dv_train_cv = self.dv_full[:train_end]
            dv_train_norm_cv = (dv_train_cv - self.dv_mean) / self.dv_std

            # Fit on this CV fold's training set
            coefs_cv, _ = self._ridge_fit(X_train_cv, dv_train_norm_cv,
                                           alpha_reg=params.get("alpha_reg"),
                                           l1_ratio=params.get("l1_ratio"))

            # Test on this CV fold
            dv_test_cv = self.dv_full[train_end:test_end]
            dv_test_norm_cv = (dv_test_cv - self.dv_mean) / self.dv_std
            y_pred_test = X_test_cv @ coefs_cv[1:] + coefs_cv[0]
            ss_res = np.sum((dv_test_norm_cv - y_pred_test) ** 2)
            ss_tot = np.sum((dv_test_norm_cv - dv_test_norm_cv.mean()) ** 2)
            test_r2 = max(0.0, 1 - ss_res / (ss_tot + 1e-9))
            test_r2s.append(test_r2)

        return float(np.mean(test_r2s)) if test_r2s else 0.0

    def _evaluate_rolling_cv(self, params: dict, n_origins: int = 5) -> Dict:
        """
        Rolling-origin CV: slide the forecast origin forward, predict next block.

        Unlike fixed holdout, this evaluates generalization across multiple time
        periods, reducing sensitivity to a single (possibly anomalous) test window.

        Returns dict with mean_r2, std_r2, mean_nrmse, fold_details.
        """
        n = len(self.df)
        min_train = max(int(n * 0.5), 40)
        step = max((n - min_train) // (n_origins + 1), 4)
        horizon = step  # predict one step ahead

        fold_details = []
        for i in range(n_origins):
            train_end = min_train + i * step
            test_end = min(train_end + horizon, n)
            if test_end <= train_end + 1 or train_end >= n:
                continue

            X_full = self._build_features(params, self.df)
            X_tr = X_full[:train_end]
            X_te = X_full[train_end:test_end]

            dv_tr = self.dv_full[:train_end]
            dv_tr_norm = (dv_tr - self.dv_mean) / self.dv_std
            coefs_cv, _ = self._ridge_fit(X_tr, dv_tr_norm,
                                           alpha_reg=params.get("alpha_reg"),
                                           l1_ratio=params.get("l1_ratio"))

            dv_te = self.dv_full[train_end:test_end]
            dv_te_norm = (dv_te - self.dv_mean) / self.dv_std
            y_pred = X_te @ coefs_cv[1:] + coefs_cv[0]

            ss_res = np.sum((dv_te_norm - y_pred) ** 2)
            ss_tot = np.sum((dv_te_norm - dv_te_norm.mean()) ** 2)
            r2 = max(0.0, 1 - ss_res / (ss_tot + 1e-9))
            nrmse = np.sqrt(np.mean((dv_te_norm - y_pred) ** 2)) / (dv_te_norm.std() + 1e-9)

            fold_details.append({
                "origin": int(train_end),
                "horizon": int(test_end - train_end),
                "r2": float(r2),
                "nrmse": float(nrmse),
            })

        if not fold_details:
            return {"mean_r2": 0.0, "std_r2": 0.0, "mean_nrmse": 0.0, "fold_details": []}

        r2s = [f["r2"] for f in fold_details]
        nrmses = [f["nrmse"] for f in fold_details]
        return {
            "mean_r2": float(np.mean(r2s)),
            "std_r2": float(np.std(r2s)),
            "mean_nrmse": float(np.mean(nrmses)),
            "std_nrmse": float(np.std(nrmses)),
            "n_folds": len(fold_details),
            "fold_details": fold_details,
        }

    def _bootstrap_stability(self, best_params: dict, n_bootstrap: int = 50) -> Dict:
        """
        Block bootstrap coefficient stability analysis.

        Resample training data with replacement (block-wise to preserve time structure),
        refit, collect channel betas. Report mean/std/CV for each channel.
        High CV (>0.5) indicates unstable coefficient.
        """
        n_train = self.n_train
        block_size = max(4, n_train // 10)
        n_ch = len(self.channel_keys)
        n_imp = len(self.impressions_keys)
        n_org = len(self.organic_keys)

        beta_samples = {ch: [] for ch in self.channel_keys}
        imp_samples = {ch: [] for ch in self.impressions_keys}
        rng = np.random.RandomState(42)

        for _ in range(n_bootstrap):
            # Block bootstrap: sample contiguous blocks with replacement
            n_blocks = (n_train + block_size - 1) // block_size
            block_starts = rng.randint(0, max(1, n_train - block_size), size=n_blocks)
            indices = np.concatenate([np.arange(s, min(s + block_size, n_train)) for s in block_starts])
            indices = indices[:n_train]  # trim to original size

            df_boot = self.df_train.iloc[indices].reset_index(drop=True)
            X_boot = self._build_features(best_params, df_boot)

            dv_boot = self.dv_full[indices]
            dv_boot_norm = (dv_boot - self.dv_mean) / self.dv_std
            coefs, _ = self._ridge_fit(X_boot, dv_boot_norm,
                                        alpha_reg=best_params.get("alpha_reg"),
                                        l1_ratio=best_params.get("l1_ratio"))

            idx = 1
            for i, ch in enumerate(self.channel_keys):
                beta_samples[ch].append(float(coefs[idx + i]))
            idx += n_ch
            for i, ch in enumerate(self.impressions_keys):
                imp_samples[ch].append(float(coefs[idx + i]))

        result = {}
        for ch in self.channel_keys:
            vals = np.array(beta_samples[ch])
            mean_val = float(np.mean(vals))
            std_val = float(np.std(vals))
            cv = std_val / (abs(mean_val) + 1e-9)
            result[ch] = {
                "mean": mean_val, "std": std_val, "cv": cv,
                "p5": float(np.percentile(vals, 5)),
                "p95": float(np.percentile(vals, 95)),
                "stable": cv < 0.5,
            }
        for ch in self.impressions_keys:
            vals = np.array(imp_samples[ch])
            mean_val = float(np.mean(vals))
            std_val = float(np.std(vals))
            cv = std_val / (abs(mean_val) + 1e-9)
            result[f"{ch}_imp"] = {
                "mean": mean_val, "std": std_val, "cv": cv,
                "p5": float(np.percentile(vals, 5)),
                "p95": float(np.percentile(vals, 95)),
                "stable": cv < 0.5,
            }
        return result

    def fit(self, progress_callback=None) -> MMMModel:
        """
        训练 MMM 模型（Robyn-aligned）:
        - Multi-objective Optuna (NRMSE × DecompRSSD Pareto front)
        - Expanding-window CV for robust test R²
        - Select best generalizing model from Pareto candidates
        - Rolling-origin CV + Bootstrap stability for generalization diagnostics
        """
        import time as _time
        _t_start = _time.time()
        all_pareto_trials = []

        for model_idx in range(self.n_models):
            study = optuna.create_study(
                directions=["minimize", "minimize"],
                sampler=optuna.samplers.TPESampler(seed=42 + model_idx),
            )

            completed = [0]
            def cb(study, trial, _idx=model_idx):
                completed[0] += 1
                if progress_callback:
                    total_progress = (model_idx * self.n_trials + completed[0]) / (self.n_models * self.n_trials)
                    if completed[0] % 20 == 0:
                        progress_callback(min(total_progress, 0.95))

            study.optimize(self._objective, n_trials=self.n_trials, callbacks=[cb],
                           show_progress_bar=False)

            # Collect Pareto-optimal trials (limit top 3 per study to control cost)
            pareto_trials = study.best_trials
            # Sort by combined score and take top 3
            pareto_trials.sort(key=lambda t: t.values[0] + self.RSSD_WEIGHT * t.values[1])
            for trial in pareto_trials[:3]:
                all_pareto_trials.append({
                    "params": trial.params,
                    "nrmse_obj": trial.values[0],
                    "rssd_obj": trial.values[1],
                    "study_idx": model_idx,
                })

        # Build candidate models and evaluate with expanding-window CV
        pareto_results = []
        candidates_params = []
        for i, cand in enumerate(all_pareto_trials):
            model = self._build_model_from_params(cand["params"])
            # CV-averaged test R² for robust generalization
            cv_test_r2 = self._evaluate_cv(cand["params"], n_folds=3)
            combined = model.train_nrmse + self.RSSD_WEIGHT * model.decomp_rssd
            pareto_results.append({
                "study_idx": cand["study_idx"],
                "r_squared": model.r_squared,
                "nrmse": model.nrmse,
                "train_nrmse": model.train_nrmse,
                "decomp_rssd": model.decomp_rssd,
                "test_r_squared": model.test_r_squared,
                "cv_test_r_squared": cv_test_r2,
                "mape_holdout": model.mape_holdout,
                "dw_stat": model.dw_stat,
                "combined": combined,
            })
            candidates_params.append(cand["params"])

            if progress_callback:
                cv_progress = 0.95 + 0.04 * (i + 1) / len(all_pareto_trials)
                progress_callback(min(cv_progress, 0.99))

        # Robyn-aligned selection: train NRMSE + RSSD for Pareto, holdout R² as bonus.
        # Optimization uses train NRMSE (stable signal). Holdout R² validates generalization.
        r2_values = [r["r_squared"] for r in pareto_results]
        r2_floor = max(0.6, min(r2_values))
        selection_reason = ""

        # Qualify: R² above floor
        qualified = [(i, r) for i, r in enumerate(pareto_results)
                     if r["r_squared"] >= r2_floor]
        if not qualified:
            qualified = list(enumerate(pareto_results))

        # Robyn-style composite: minimize train_NRMSE + RSSD_WEIGHT*RSSD
        # Holdout R² is diagnostic only — not used for selection because the holdout
        # period may contain structural breaks (e.g., regime change in DV level)
        # that no train-period model can predict. CV also limited for same reason.
        def _selection_score(item):
            _, r = item
            base = r["train_nrmse"] + self.RSSD_WEIGHT * r["decomp_rssd"]
            return base  # lower is better

        best_idx, best_r = min(qualified, key=_selection_score)
        selection_reason = (f"robyn_pareto: combined={best_r['train_nrmse'] + self.RSSD_WEIGHT * best_r['decomp_rssd']:.4f}, "
                            f"R2={best_r['r_squared']:.4f}, trainNRMSE={best_r['train_nrmse']:.4f}, "
                            f"holdoutNRMSE={best_r['nrmse']:.4f}, testR2={best_r['test_r_squared']:.4f}, "
                            f"RSSD={best_r['decomp_rssd']:.4f}")

        best_model = self._build_model_from_params(candidates_params[best_idx])
        best_params = candidates_params[best_idx]
        # Store holdout test R² (from _build_model_from_params) for display
        for r in pareto_results:
            r["selection_reason"] = selection_reason
        best_model.pareto_results = pareto_results

        # Rolling-origin CV for robust generalization estimate (P0)
        best_model.cv_results = self._evaluate_rolling_cv(best_params, n_origins=5)
        _saved_cv_results = best_model.cv_results

        # Bootstrap coefficient stability (P0)
        best_model.bootstrap_stability = self._bootstrap_stability(best_params, n_bootstrap=50)

        # US-902: Adaptive alpha boost — if >50% spend channels unstable, boost alpha 3x and refit
        _alpha_boosted = False
        _bs = best_model.bootstrap_stability
        _n_spend_ch = len(self.channel_keys)
        _n_unstable_spend = sum(
            1 for ch in self.channel_keys
            if ch in _bs and isinstance(_bs[ch], dict) and _bs[ch].get("cv", 99) >= 0.5
        )
        if _n_unstable_spend > _n_spend_ch * 0.5:
            _old_alpha = best_params.get("alpha_reg", 1.0)
            best_params["alpha_reg"] = min(_old_alpha * 3.0, 500.0)
            _alpha_boosted = True
            best_model = self._build_model_from_params(best_params)
            best_model.cv_results = _saved_cv_results
            best_model.bootstrap_stability = self._bootstrap_stability(best_params, n_bootstrap=50)
            _bs = best_model.bootstrap_stability

        # US-804: Auto-prune unstable impressions (CV > 1.0) and refit
        _pruned_impressions = []
        _bs = best_model.bootstrap_stability
        _unstable_imps = [
            ch for ch in self.impressions_keys
            if f"{ch}_imp" in _bs and _bs[f"{ch}_imp"].get("cv", 0) > 1.0
        ]
        if _unstable_imps and len(self.impressions_keys) > len(_unstable_imps):
            # Only prune if at least one impression channel remains
            _pruned_impressions = _unstable_imps
            self.impressions_keys = [ch for ch in self.impressions_keys if ch not in _unstable_imps]
            # Rebuild model without unstable impressions
            best_model = self._build_model_from_params(best_params)
            # Re-run bootstrap to verify improvement
            best_model.bootstrap_stability = self._bootstrap_stability(best_params, n_bootstrap=50)
            best_model.cv_results = _saved_cv_results  # preserve original CV

        # Training metadata (US-705)
        import time as _time
        _duration = _time.time() - _t_start
        best_model.dv_col = self.dv_col
        best_model.training_meta = {
            "dv_col": self.dv_col,
            "n_trials": self.n_trials,
            "n_models": self.n_models,
            "adstock_type": self.adstock_type,
            "n_train": self.n_train,
            "n_test": len(self.df_test),
            "n_total": len(self.df),
            "channel_keys": list(self.channel_keys),
            "context_keys": list(self.context_keys),
            "organic_keys": list(self.organic_keys),
            "impressions_keys": list(self.impressions_keys),
            "use_log_dv": self.use_log_dv,
            "training_duration_sec": round(_duration, 1),
            "regularization": self.regularization,
            "best_alpha": best_params.get("alpha_reg"),
            "best_l1_ratio": best_params.get("l1_ratio"),
            "use_interactions": self.use_interactions,
            "pruned_impressions": _pruned_impressions,
            "n_ensemble": self.n_bag,
            "alpha_boosted": _alpha_boosted,
            "final_alpha": best_params.get("alpha_reg"),
            "feature_names": (
                [f"{ch}_spend" for ch in self.channel_keys]
                + [f"{ch}_impressions" for ch in self.impressions_keys]
                + list(self.organic_keys)
                + list(self.context_keys)
            ),
        }

        # Feature importance: |beta| * feature_std (proxy for contribution magnitude)
        feature_importance = {}
        for ch, cp in best_model.channel_params.items():
            feature_importance[f"{ch}_spend"] = abs(cp.beta)
        for ch, ip in best_model.impressions_params.items():
            feature_importance[f"{ch}_impressions"] = abs(ip.beta)
        for org, op in best_model.organic_params.items():
            feature_importance[f"{org}_organic"] = abs(op.beta)
        for ctx, coef in best_model.context_coefs.items():
            feature_importance[ctx] = abs(coef)
        best_model.feature_importance = feature_importance

        if progress_callback:
            progress_callback(1.0)
        return best_model


# ─── 模型持久化 ───────────────────────────────────────────────────────────────

import pickle

MODEL_PATH = Path(__file__).parent.parent / "data" / "mmm_model.pkl"


def save_model(model: MMMModel):
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


ALLOWED_PICKLE_CLASSES = {
    "MMMModel", "ChannelParams", "dict", "list", "tuple", "str", "int", "float", "bool"
}

# Modules safe to unpickle (numpy/pandas types needed for model internals)
ALLOWED_PICKLE_MODULES = {
    "numpy", "pandas", "numpy.core", "numpy._core",
    "builtins", "collections", "codecs", "copy", "copyreg",
    "_codecs", "_collections_abc",
}

class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if name in ALLOWED_PICKLE_CLASSES:
            return super().find_class(module, name)
        if any(module == m or module.startswith(m + ".") for m in ALLOWED_PICKLE_MODULES):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Disallowed class: {module}.{name}")

def load_model() -> Optional[MMMModel]:
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            result = _RestrictedUnpickler(f).load()
        if not isinstance(result, MMMModel):
            return None
        # Patch missing fields from older model versions
        if not hasattr(result, 'impressions_params'):
            result.impressions_params = {}
        if not hasattr(result, '_impressions_keys'):
            result._impressions_keys = []
        if not hasattr(result, '_use_log_dv'):
            result._use_log_dv = False
        if not hasattr(result, 'train_nrmse'):
            result.train_nrmse = result.nrmse
        if not hasattr(result, 'mape_holdout'):
            result.mape_holdout = 0.0
        if not hasattr(result, 'dw_stat'):
            result.dw_stat = 0.0
        if not hasattr(result, 'cv_results'):
            result.cv_results = {}
        if not hasattr(result, 'bootstrap_stability'):
            result.bootstrap_stability = {}
        if not hasattr(result, 'dv_col'):
            result.dv_col = ""
        if not hasattr(result, 'training_meta'):
            result.training_meta = {}
        if not hasattr(result, 'feature_importance'):
            result.feature_importance = {}
        return result
    except Exception as e:
        import logging
        logging.warning(f"模型加载失败: {e}")
        return None


# ─── 模型注册表 (US-703) ───────────────────────────────────────────────────────

import json
import uuid
from datetime import datetime

MODELS_DIR = Path(__file__).parent.parent / "data" / "models"
REGISTRY_INDEX = MODELS_DIR / "_index.json"


class ModelRegistry:
    """Multi-model registry with metadata. Stores models as individual pkl files."""

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.index_path = models_dir / "_index.json"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._index = self._load_index()
        self._auto_import_legacy()

    def _load_index(self) -> List[Dict]:
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    def _auto_import_legacy(self):
        """Import old single-file mmm_model.pkl if it exists and isn't already indexed."""
        # Only auto-import when using the default models directory
        if self.models_dir != MODELS_DIR:
            return
        legacy = MODEL_PATH
        if not legacy.exists():
            return
        # Check if already imported
        if any(e.get("legacy_import") for e in self._index):
            return
        model = load_model()
        if model and model.is_fitted:
            model_id = self.save(model, name="legacy_import", auto=True)
            # Mark as legacy import
            for entry in self._index:
                if entry["id"] == model_id:
                    entry["legacy_import"] = True
            self._save_index()

    def save(self, model: MMMModel, name: str = "", auto: bool = False) -> str:
        """Save model to registry. Returns model_id."""
        model_id = str(uuid.uuid4())[:8]
        if not name:
            dv = model.dv_col or "unknown_dv"
            name = f"{dv}_{datetime.now().strftime('%m%d_%H%M')}"

        pkl_path = self.models_dir / f"{model_id}.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(model, f)

        entry = {
            "id": model_id,
            "name": name,
            "dv_col": model.dv_col or "",
            "r_squared": round(model.r_squared, 4),
            "train_nrmse": round(model.train_nrmse, 4),
            "test_r_squared": round(model.test_r_squared, 4),
            "decomp_rssd": round(model.decomp_rssd, 4),
            "mape_holdout": round(model.mape_holdout, 4),
            "dw_stat": round(model.dw_stat, 4),
            "cv_mean_r2": round(model.cv_results.get("mean_r2", 0.0), 4),
            "n_channels": len(model.channel_params),
            "created_at": datetime.now().isoformat(),
            "config_summary": {
                "adstock_type": model.training_meta.get("adstock_type", ""),
                "n_trials": model.training_meta.get("n_trials", 0),
                "n_train": model.training_meta.get("n_train", 0),
                "duration_sec": model.training_meta.get("training_duration_sec", 0),
            },
        }
        self._index.append(entry)
        self._save_index()
        return model_id

    def list(self) -> List[Dict]:
        """Return list of all saved models with metadata."""
        return list(self._index)

    def load(self, model_id: str) -> Optional[MMMModel]:
        """Load a specific model by ID."""
        pkl_path = self.models_dir / f"{model_id}.pkl"
        if not pkl_path.exists():
            return None
        try:
            with open(pkl_path, "rb") as f:
                result = _RestrictedUnpickler(f).load()
            if not isinstance(result, MMMModel):
                return None
            # Patch fields (same as load_model)
            for attr, default in [
                ('impressions_params', {}), ('_impressions_keys', []),
                ('_use_log_dv', False), ('train_nrmse', result.nrmse if hasattr(result, 'nrmse') else 0.0),
                ('mape_holdout', 0.0), ('dw_stat', 0.0),
                ('cv_results', {}), ('bootstrap_stability', {}),
                ('dv_col', ""), ('training_meta', {}), ('feature_importance', {}),
            ]:
                if not hasattr(result, attr):
                    setattr(result, attr, default)
            return result
        except Exception:
            return None

    def delete(self, model_id: str) -> bool:
        """Delete a model by ID. Returns True if found and deleted."""
        pkl_path = self.models_dir / f"{model_id}.pkl"
        if pkl_path.exists():
            pkl_path.unlink()
        before = len(self._index)
        self._index = [e for e in self._index if e["id"] != model_id]
        if len(self._index) < before:
            self._save_index()
            return True
        return False

    def get_entry(self, model_id: str) -> Optional[Dict]:
        """Get metadata entry for a model."""
        for entry in self._index:
            if entry["id"] == model_id:
                return entry
        return None
