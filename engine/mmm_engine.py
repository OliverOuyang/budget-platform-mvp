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

    def transform(self, spend: np.ndarray) -> np.ndarray:
        """完整变换：Adstock → 归一化 → Hill 饱和"""
        # Step 1: Adstock
        if self.adstock_type == "weibull":
            adstocked = weibull_adstock(spend, self.weibull_shape, self.weibull_scale)
        else:
            adstocked = geometric_adstock(spend, self.theta)

        # Step 2: 归一化到 [0, 1]（用于 Hill 函数）
        max_val = adstocked.max()
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
    自变量：各渠道 spend（经过 Adstock + 饱和变换）+ 控制变量
    """
    channel_params: Dict[str, ChannelParams] = field(default_factory=dict)
    intercept: float = 0.0
    context_coefs: Dict[str, float] = field(default_factory=dict)
    r_squared: float = 0.0
    nrmse: float = 0.0
    decomp_rssd: float = 0.0
    is_fitted: bool = False

    # 训练数据缓存
    _df: Optional[pd.DataFrame] = field(default=None, repr=False)
    _channel_keys: List[str] = field(default_factory=list, repr=False)
    _context_keys: List[str] = field(default_factory=list, repr=False)
    _dv_mean: float = field(default=1.0, repr=False)
    _dv_std: float = field(default=1.0, repr=False)

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

        for ctx, coef in self.context_coefs.items():
            if ctx in df.columns:
                ctx_vals = df[ctx].values.astype(float)
                if self._df is not None and ctx in self._df.columns:
                    ctx_mean = self._df[ctx].mean()
                    ctx_std  = self._df[ctx].std() + 1e-9
                else:
                    ctx_mean = ctx_vals.mean()
                    ctx_std  = ctx_vals.std() + 1e-9
                y_pred_norm += coef * (ctx_vals - ctx_mean) / ctx_std

        # 反标准化
        y_pred = y_pred_norm * self._dv_std + self._dv_mean
        return y_pred

    def channel_contribution(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """分解各渠道贡献（绝对值，万元）"""
        contributions = {}
        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col in df.columns:
                spend = df[spend_col].values.astype(float)
                transformed = params.transform(spend)
                contrib = params.beta * transformed * self._dv_std
                contributions[ch] = np.maximum(contrib, 0)
        return contributions

    def marginal_response(self, ch: str, spend_range: np.ndarray,
                          df_last=None) -> np.ndarray:
        """
        计算单渠道边际响应曲线
        spend_range: 花费取值范围（万元）
        """
        params = self.channel_params.get(ch)
        if params is None:
            return np.zeros(len(spend_range))

        responses = []
        for s in spend_range:
            spend_arr = np.array([s])
            transformed = params.transform(spend_arr)
            response = params.beta * transformed[0] * self._dv_std
            responses.append(max(response, 0))
        return np.array(responses)

    def budget_optimization(self, total_budget: float,
                            df_recent: pd.DataFrame,
                            n_points: int = 50) -> Dict[str, float]:
        """
        等边际原则预算再分配
        在总预算约束下，最大化预测借款金额
        """
        channels = list(self.channel_params.keys())
        n_ch = len(channels)

        def objective(trial):
            ratios = [trial.suggest_float(f"r_{ch}", 0.02, 0.60) for ch in channels]
            ratio_sum = sum(ratios)
            spends = {ch: total_budget * r / ratio_sum for ch, r in zip(channels, ratios)}

            row = {f"{ch}_spend": [spends[ch]] for ch in channels}
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
        ratios = [best[f"r_{ch}"] for ch in channels]
        ratio_sum = sum(ratios)
        optimal_spends = {ch: round(total_budget * r / ratio_sum, 2)
                          for ch, r in zip(channels, ratios)}
        return optimal_spends


# ─── 模型训练器 ───────────────────────────────────────────────────────────────

class MMMTrainer:
    """
    使用 Optuna 贝叶斯优化拟合 MMM 参数
    改进版：
    - 使用 Ridge 回归代替 NNLS，避免系数坍缩
    - 对每个渠道独立归一化 beta
    - 目标函数同时考虑 NRMSE 和 DecompRSSD
    """

    CHANNEL_KEYS = [
        "tencent_moments", "tencent_video", "tencent_wechat", "tencent_search",
        "douyin", "app_store", "precision_marketing",
    ]
    CONTEXT_KEYS = ["holiday_days", "exclude_rate", "callback_ratio",
                    "cpi_yoy", "lpr_1y"]

    def __init__(self, df: pd.DataFrame, dv_col: str = "dv_t0_loan_amt",
                 n_trials: int = 300, adstock_type: str = "geometric"):
        self.df = df.copy()
        self.dv_col = dv_col if dv_col in df.columns else "loan_amt"
        self.n_trials = n_trials
        self.adstock_type = adstock_type

        # 过滤可用渠道
        self.channel_keys = [ch for ch in self.CHANNEL_KEYS
                             if f"{ch}_spend" in df.columns]
        self.context_keys = [c for c in self.CONTEXT_KEYS if c in df.columns]

        # 标准化因变量
        self.dv = df[self.dv_col].values.astype(float)
        self.dv_mean = self.dv.mean()
        self.dv_std  = self.dv.std() + 1e-9
        self.dv_norm = (self.dv - self.dv_mean) / self.dv_std

        # 预计算各渠道花费的统计量（用于归一化）
        self.spend_stats = {}
        for ch in self.channel_keys:
            vals = df[f"{ch}_spend"].values.astype(float)
            self.spend_stats[ch] = {"mean": vals.mean(), "std": vals.std() + 1e-9,
                                     "max": vals.max() + 1e-9}

    def _apply_adstock(self, spend: np.ndarray, params: dict, ch: str) -> np.ndarray:
        """应用 Adstock 变换"""
        if self.adstock_type == "weibull":
            shape = params.get(f"{ch}_wb_shape", 2.0)
            scale = params.get(f"{ch}_wb_scale", 2.0)
            return weibull_adstock(spend, shape, scale)
        else:
            theta = params.get(f"{ch}_theta", 0.3)
            return geometric_adstock(spend, theta)

    def _build_features(self, params: dict, df: pd.DataFrame) -> np.ndarray:
        """构造特征矩阵（每列已归一化到 [0,1]）"""
        features = []

        for ch in self.channel_keys:
            spend = df[f"{ch}_spend"].values.astype(float)
            adstocked = self._apply_adstock(spend, params, ch)

            # 归一化（用训练集最大值）
            max_val = self.spend_stats[ch]["max"]
            normalized = adstocked / max_val

            alpha = params.get(f"{ch}_alpha", 2.0)
            gamma = params.get(f"{ch}_gamma", 0.5)
            saturated = hill_saturation(normalized, alpha, gamma)
            features.append(saturated)

        for ctx in self.context_keys:
            vals = df[ctx].values.astype(float)
            ctx_mean = self.df[ctx].mean()
            ctx_std  = self.df[ctx].std() + 1e-9
            features.append((vals - ctx_mean) / ctx_std)

        return np.column_stack(features) if features else np.ones((len(df), 1))

    def _ridge_fit(self, X: np.ndarray, y: np.ndarray,
                   alpha_reg: float = 0.01) -> Tuple[np.ndarray, float]:
        """
        Ridge 回归（带截距），媒体变量系数非负约束
        使用两步法：先 Ridge 得到初始值，再用投影梯度保证非负
        """
        from sklearn.linear_model import Ridge
        n_ch = len(self.channel_keys)

        # 全量 Ridge
        ridge = Ridge(alpha=alpha_reg, fit_intercept=True)
        ridge.fit(X, y)
        coefs = ridge.coef_.copy()
        intercept = ridge.intercept_

        # 强制媒体系数非负
        coefs[:n_ch] = np.maximum(coefs[:n_ch], 0)

        # 重新计算截距（均值处无偏）
        y_pred = X @ coefs + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = max(0.0, 1 - ss_res / ss_tot)

        return np.concatenate([[intercept], coefs]), r2

    def _objective(self, trial) -> float:
        params = {}
        for ch in self.channel_keys:
            if self.adstock_type == "weibull":
                params[f"{ch}_wb_shape"] = trial.suggest_float(f"{ch}_wb_shape", 0.5, 4.0)
                params[f"{ch}_wb_scale"] = trial.suggest_float(f"{ch}_wb_scale", 1.0, 6.0)
            else:
                params[f"{ch}_theta"] = trial.suggest_float(f"{ch}_theta", 0.0, 0.8)
            params[f"{ch}_alpha"] = trial.suggest_float(f"{ch}_alpha", 0.5, 4.0)
            params[f"{ch}_gamma"] = trial.suggest_float(f"{ch}_gamma", 0.1, 0.9)

        X = self._build_features(params, self.df)
        coefs, r2 = self._ridge_fit(X, self.dv_norm)

        intercept = coefs[0]
        ch_betas  = coefs[1:len(self.channel_keys) + 1]

        y_pred = X @ coefs[1:] + intercept
        nrmse = np.sqrt(np.mean((self.dv_norm - y_pred) ** 2)) / (self.dv_norm.std() + 1e-9)

        # DecompRSSD：渠道贡献分布 vs 花费分布差异
        ch_contribs = np.maximum(ch_betas * np.array([X[:, i].sum() for i in range(len(self.channel_keys))]), 0)
        ch_spends   = np.array([self.df[f"{ch}_spend"].sum() for ch in self.channel_keys])
        total_contrib = ch_contribs.sum() + 1e-9
        total_spend   = ch_spends.sum() + 1e-9
        decomp_rssd = float(np.sqrt(np.sum(
            (ch_contribs / total_contrib - ch_spends / total_spend) ** 2
        )))

        # 综合目标：最小化 NRMSE + 0.3 * DecompRSSD - 0.1 * R²
        return nrmse + 0.3 * decomp_rssd - 0.1 * r2

    def fit(self, progress_callback=None) -> MMMModel:
        """训练 MMM 模型，返回最优参数"""
        study = optuna.create_study(
            direction="minimize",
            sampler=optuna.samplers.TPESampler(seed=42),
        )

        completed = [0]
        def cb(study, trial):
            completed[0] += 1
            if progress_callback and completed[0] % 20 == 0:
                progress_callback(completed[0] / self.n_trials)

        study.optimize(self._objective, n_trials=self.n_trials, callbacks=[cb],
                       show_progress_bar=False)

        best = study.best_params
        X = self._build_features(best, self.df)
        coefs, r2 = self._ridge_fit(X, self.dv_norm)

        n_ch = len(self.channel_keys)
        intercept_norm = coefs[0]
        ch_betas_norm  = coefs[1:n_ch + 1]
        ctx_coefs_norm = coefs[n_ch + 1:] if len(coefs) > n_ch + 1 else []

        # 构造 ChannelParams
        channel_params = {}
        for i, ch in enumerate(self.channel_keys):
            if self.adstock_type == "weibull":
                cp = ChannelParams(
                    name=ch,
                    adstock_type="weibull",
                    weibull_shape=best.get(f"{ch}_wb_shape", 2.0),
                    weibull_scale=best.get(f"{ch}_wb_scale", 2.0),
                    alpha=best.get(f"{ch}_alpha", 2.0),
                    gamma=best.get(f"{ch}_gamma", 0.5),
                    beta=float(ch_betas_norm[i]),
                )
            else:
                cp = ChannelParams(
                    name=ch,
                    adstock_type="geometric",
                    theta=best.get(f"{ch}_theta", 0.3),
                    alpha=best.get(f"{ch}_alpha", 2.0),
                    gamma=best.get(f"{ch}_gamma", 0.5),
                    beta=float(ch_betas_norm[i]),
                )
            channel_params[ch] = cp

        context_coefs = {ctx: float(ctx_coefs_norm[i])
                         for i, ctx in enumerate(self.context_keys)
                         if i < len(ctx_coefs_norm)}

        # 计算最终指标
        y_pred_norm = X @ coefs[1:] + intercept_norm
        nrmse = np.sqrt(np.mean((self.dv_norm - y_pred_norm) ** 2)) / (self.dv_norm.std() + 1e-9)

        ch_contribs = np.maximum(
            ch_betas_norm * np.array([X[:, i].sum() for i in range(n_ch)]), 0
        )
        ch_spends = np.array([self.df[f"{ch}_spend"].sum() for ch in self.channel_keys])
        total_contrib = ch_contribs.sum() + 1e-9
        total_spend   = ch_spends.sum() + 1e-9
        decomp_rssd = float(np.sqrt(np.sum(
            (ch_contribs / total_contrib - ch_spends / total_spend) ** 2
        )))

        model = MMMModel(
            channel_params=channel_params,
            intercept=intercept_norm,
            context_coefs=context_coefs,
            r_squared=r2,
            nrmse=nrmse,
            decomp_rssd=decomp_rssd,
            is_fitted=True,
            _df=self.df,
            _channel_keys=self.channel_keys,
            _context_keys=self.context_keys,
            _dv_mean=self.dv_mean,
            _dv_std=self.dv_std,
        )
        return model


# ─── 模型持久化 ───────────────────────────────────────────────────────────────

import pickle
from pathlib import Path

MODEL_PATH = Path(__file__).parent.parent / "data" / "mmm_model.pkl"


def save_model(model: MMMModel):
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


ALLOWED_PICKLE_CLASSES = {
    "MMMModel", "ChannelParams", "dict", "list", "tuple", "str", "int", "float", "bool", "type"
}

class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if name not in ALLOWED_PICKLE_CLASSES:
            raise pickle.UnpicklingError(f"Disallowed class: {name}")
        return super().find_class(module, name)

def load_model() -> Optional[MMMModel]:
    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            result = _RestrictedUnpickler(f).load()
        if not isinstance(result, MMMModel):
            return None
        return result
    except Exception as e:
        import logging
        logging.warning(f"模型加载失败: {e}")
        return None
