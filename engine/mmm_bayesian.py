"""Bayesian MMM Engine (PyMC-based) — interface-compatible with Legacy MMMModel."""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

_HAS_PYMC = False
_HAS_PYMC_MARKETING = False

try:
    import pymc as pm
    import pytensor.tensor as pt
    import arviz as az
    _HAS_PYMC = True
except ImportError:
    pass

try:
    from pymc_marketing.mmm import MMM as PyMCMarketingMMM
    _HAS_PYMC_MARKETING = True
except ImportError:
    pass


def _check_pymc():
    if not _HAS_PYMC:
        raise ImportError(
            "PyMC is required for BayesianMMMTrainer. "
            "Install with: pip install pymc arviz pytensor")

# ─── NumPy transforms (post-fit evaluation) ──────────────────────────────────

def geometric_adstock(x: np.ndarray, theta: float) -> np.ndarray:
    n = len(x)
    out = np.zeros(n)
    out[0] = x[0]
    for t in range(1, n):
        out[t] = x[t] + theta * out[t - 1]
    return out

def hill_saturation(x: np.ndarray, alpha: float, gamma: float) -> np.ndarray:
    x_safe = np.maximum(x, 1e-10)
    return x_safe ** alpha / (x_safe ** alpha + gamma ** alpha)

# ─── PyTensor transforms (inside PyMC model) ─────────────────────────────────

def geometric_adstock_pymc(x, theta, l_max: int = 8):
    """Geometric adstock via convolution weights (pytensor)."""
    _check_pymc()
    weights = pt.power(theta, pt.arange(l_max))
    weights = weights / weights.sum()
    x_padded = pt.concatenate([pt.zeros(l_max - 1), x])
    result = pt.zeros_like(x)
    for k in range(l_max):
        result = result + weights[k] * x_padded[l_max - 1 - k: l_max - 1 - k + x.shape[0]]
    return result

def hill_saturation_pymc(x, alpha, gamma):
    """Hill saturation (pytensor)."""
    _check_pymc()
    x_safe = pt.maximum(x, 1e-10)
    return x_safe ** alpha / (x_safe ** alpha + gamma ** alpha)

@dataclass
class BayesianChannelParams:
    """Single channel Bayesian MMM parameters (posterior summaries)."""
    name: str
    adstock_type: str = "geometric"
    theta_mean: float = 0.0
    alpha_mean: float = 1.0
    gamma_mean: float = 0.5
    beta_mean: float = 0.0
    beta_hdi_low: float = 0.0
    beta_hdi_high: float = 0.0
    _norm_max: float = 0.0

    def transform(self, spend: np.ndarray) -> np.ndarray:
        spend = np.nan_to_num(spend, nan=0.0)
        adstocked = geometric_adstock(spend, self.theta_mean)
        max_val = self._norm_max if self._norm_max > 0 else (adstocked.max() or 1.0)
        normalized = adstocked / max_val if max_val > 0 else adstocked
        return hill_saturation(normalized, self.alpha_mean, self.gamma_mean)

# ─── Bayesian MMM Model ─────────────────────────────────────────────────────

@dataclass
class BayesianMMMModel:
    """Bayesian MMM with full posterior uncertainty (mirrors Legacy interface)."""
    channel_params: Dict[str, BayesianChannelParams] = field(default_factory=dict)
    intercept: float = 0.0
    context_coefs: Dict[str, float] = field(default_factory=dict)

    # Fit metrics
    r_squared: float = 0.0
    nrmse: float = 0.0
    test_r_squared: float = 0.0
    train_nrmse: float = 0.0
    mape_holdout: float = 0.0
    is_fitted: bool = False

    # Bayesian diagnostics
    _trace: object = field(default=None, repr=False)  # arviz InferenceData
    _posterior_samples: Dict = field(default_factory=dict, repr=False)

    # Training data cache (same as Legacy)
    _df: Optional[pd.DataFrame] = field(default=None, repr=False)
    _channel_keys: List[str] = field(default_factory=list, repr=False)
    _context_keys: List[str] = field(default_factory=list, repr=False)
    _organic_keys: List[str] = field(default_factory=list, repr=False)
    _dv_mean: float = field(default=1.0, repr=False)
    _dv_std: float = field(default=1.0, repr=False)
    _use_log_dv: bool = field(default=False, repr=False)
    _context_stats: Dict[str, Tuple[float, float]] = field(default_factory=dict, repr=False)

    # Training metadata (US-705 compat)
    dv_col: str = ""
    training_meta: Dict = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict DV using posterior mean parameters (original scale)."""
        n = len(df)
        y_pred_norm = np.full(n, self.intercept)

        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col in df.columns:
                spend = df[spend_col].values.astype(float)
                transformed = params.transform(spend)
                y_pred_norm += params.beta_mean * transformed

        for ctx, coef in self.context_coefs.items():
            if ctx in df.columns:
                ctx_vals = df[ctx].values.astype(float)
                if ctx in self._context_stats:
                    ctx_mean, ctx_std = self._context_stats[ctx]
                elif self._df is not None and ctx in self._df.columns:
                    ctx_mean = self._df[ctx].mean()
                    ctx_std = self._df[ctx].std() + 1e-9
                else:
                    ctx_mean = np.nanmean(ctx_vals)
                    ctx_std = np.nanstd(ctx_vals) + 1e-9
                ctx_vals = np.nan_to_num(ctx_vals, nan=ctx_mean)
                y_pred_norm += coef * (ctx_vals - ctx_mean) / ctx_std

        y_pred = y_pred_norm * self._dv_std + self._dv_mean
        if self._use_log_dv:
            y_pred = np.expm1(y_pred)
        return y_pred

    def channel_contribution(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Decompose per-channel contribution (posterior mean, original scale)."""
        norm_contribs = {}
        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col in df.columns:
                spend = df[spend_col].values.astype(float)
                transformed = params.transform(spend)
                norm_contribs[ch] = np.maximum(params.beta_mean * transformed, 0)

        if self._use_log_dv:
            y_pred = self.predict(df)
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
            total_norm = sum(norm_contribs.values())
            total_norm_safe = total_norm + 1e-9
            contributions = {}
            for key, nc in norm_contribs.items():
                share = nc / total_norm_safe
                contributions[key] = np.maximum(share * media_effect, 0)
        else:
            contributions = {}
            for key, nc in norm_contribs.items():
                contributions[key] = nc * self._dv_std

        return contributions

    def marginal_response(self, ch: str, spend_range: np.ndarray,
                          df_last=None, n_points: int = 50) -> np.ndarray:
        """Compute marginal response curve for a channel (posterior mean)."""
        params = self.channel_params.get(ch)
        if params is None:
            return np.zeros(len(spend_range))

        base_norm = self.intercept
        if df_last is not None and len(df_last) > 0:
            for other_ch, other_params in self.channel_params.items():
                if other_ch == ch:
                    continue
                col = f"{other_ch}_spend"
                if col in df_last.columns:
                    mean_spend = np.array([float(df_last[col].mean())])
                    t = other_params.transform(mean_spend)
                    base_norm += other_params.beta_mean * t[0]
        base_denorm = base_norm * self._dv_std + self._dv_mean

        responses = []
        for s in spend_range:
            spend_arr = np.array([s])
            transformed = params.transform(spend_arr)
            contrib_norm = params.beta_mean * transformed[0]

            if self._use_log_dv:
                full_denorm = (base_norm + contrib_norm) * self._dv_std + self._dv_mean
                response = float(np.expm1(full_denorm) - np.expm1(base_denorm))
            else:
                response = float(contrib_norm * self._dv_std)

            responses.append(max(response, 0))
        return np.array(responses)

    def budget_optimization(self, total_budget: float,
                            current_allocation: Optional[Dict[str, float]] = None,
                            bounds_pct: Tuple[float, float] = (0.3, 5.0),
                            df_recent: Optional[pd.DataFrame] = None) -> Dict:
        """Equal-marginal-principle budget optimization (scipy SLSQP)."""
        channels = list(self.channel_params.keys())
        if not channels:
            return {}
        current_spends = {}
        if df_recent is not None:
            for ch in channels:
                col = f"{ch}_spend"
                if col in df_recent.columns:
                    current_spends[ch] = max(float(df_recent[col].mean()), 1.0)
                else:
                    current_spends[ch] = total_budget / len(channels)
        elif current_allocation:
            current_spends = current_allocation
        else:
            current_spends = {ch: total_budget / len(channels) for ch in channels}

        lo_pct, hi_pct = bounds_pct

        try:
            from scipy.optimize import minimize as scipy_minimize

            def neg_response(alloc_vec):
                total = 0.0
                for i, ch in enumerate(channels):
                    spend_arr = np.array([alloc_vec[i]])
                    params = self.channel_params[ch]
                    transformed = params.transform(spend_arr)
                    total += params.beta_mean * transformed[0]
                return -total

            x0 = np.array([current_spends.get(ch, total_budget / len(channels))
                           for ch in channels])
            x0 = x0 / x0.sum() * total_budget

            bounds = [(current_spends.get(ch, 1.0) * lo_pct,
                       current_spends.get(ch, 1.0) * hi_pct)
                      for ch in channels]
            constraints = [{"type": "eq",
                            "fun": lambda x: np.sum(x) - total_budget}]

            result = scipy_minimize(neg_response, x0, method="SLSQP",
                                    bounds=bounds, constraints=constraints,
                                    options={"maxiter": 500})
            if result.success:
                raw = {ch: float(result.x[i]) for i, ch in enumerate(channels)}
            else:
                raw = {ch: float(x0[i]) for i, ch in enumerate(channels)}
        except ImportError:
            # Fallback: proportional to beta
            betas = {ch: max(p.beta_mean, 1e-6) for ch, p in self.channel_params.items()}
            total_beta = sum(betas.values())
            raw = {ch: total_budget * b / total_beta for ch, b in betas.items()}

        raw_total = sum(raw.values()) or 1.0
        optimal = {ch: round(total_budget * v / raw_total, 2) for ch, v in raw.items()}

        return {
            "optimal_allocation": optimal,
            "total_budget": total_budget,
            "channels": channels,
        }

    def budget_scenarios(self, df_recent: pd.DataFrame,
                         total_budget: Optional[float] = None,
                         ratios: Optional[List[float]] = None,
                         top_n: int = 5) -> List[Dict]:
        """Multi-scenario budget allocation (matches Legacy interface)."""
        if ratios is None:
            ratios = [0.8, 0.9, 1.0, 1.1, 1.2]

        if total_budget is None:
            total_budget = sum(
                float(df_recent[f"{ch}_spend"].mean())
                for ch in self.channel_params
                if f"{ch}_spend" in df_recent.columns
            )

        scenarios = []
        for mult in ratios:
            budget = total_budget * mult
            result = self.budget_optimization(
                total_budget=budget, df_recent=df_recent)
            scenarios.append({
                "label": f"{int(mult * 100)}%",
                "multiplier": mult,
                "budget": budget,
                "allocation": result.get("optimal_allocation", {}),
            })
        return scenarios

    def get_posterior_summary(self) -> Dict:
        """Return R-hat, ESS, HDI for all model parameters."""
        if self._trace is None:
            return {"warning": "No trace available (model may have been loaded from disk)"}

        _check_pymc()
        summary = {}
        try:
            az_summary = az.summary(
                self._trace,
                hdi_prob=0.94,
                stat_funcs={"mean": np.mean, "sd": np.std},
            )
            for param_name in az_summary.index:
                row = az_summary.loc[param_name]
                summary[param_name] = {
                    "mean": float(row.get("mean", 0)),
                    "sd": float(row.get("sd", 0)),
                    "hdi_3%": float(row.get("hdi_3%", 0)),
                    "hdi_97%": float(row.get("hdi_97%", 0)),
                    "r_hat": float(row.get("r_hat", 0)),
                    "ess_bulk": float(row.get("ess_bulk", 0)),
                    "ess_tail": float(row.get("ess_tail", 0)),
                }
        except Exception as e:
            summary["error"] = str(e)
        return summary

    def get_channel_roas_distribution(self, ch: str) -> np.ndarray:
        """Return posterior samples of ROAS for a channel."""
        beta_key = f"{ch}_beta"
        if beta_key in self._posterior_samples:
            return np.array(self._posterior_samples[beta_key])
        return np.array([self.channel_params[ch].beta_mean] if ch in self.channel_params else [0.0])

    def get_contribution_with_hdi(self, df: pd.DataFrame,
                                  hdi_prob: float = 0.94) -> Dict[str, Dict]:
        """Channel contributions with HDI: {ch: {mean, hdi_low, hdi_high}}."""
        results = {}
        for ch, params in self.channel_params.items():
            spend_col = f"{ch}_spend"
            if spend_col not in df.columns:
                continue
            spend = df[spend_col].values.astype(float)
            transformed = params.transform(spend)

            beta_key = f"{ch}_beta"
            if beta_key in self._posterior_samples:
                beta_samples = np.array(self._posterior_samples[beta_key])
                contrib_samples = np.outer(beta_samples, transformed)
                contrib_samples = np.maximum(contrib_samples, 0)
                if not self._use_log_dv:
                    contrib_samples = contrib_samples * self._dv_std

                mean_contrib = contrib_samples.mean(axis=0)
                lo = (1 - hdi_prob) / 2
                hi = 1 - lo
                hdi_low = np.quantile(contrib_samples, lo, axis=0)
                hdi_high = np.quantile(contrib_samples, hi, axis=0)
            else:
                mean_contrib = np.maximum(params.beta_mean * transformed, 0)
                if not self._use_log_dv:
                    mean_contrib = mean_contrib * self._dv_std
                hdi_low = mean_contrib
                hdi_high = mean_contrib

            results[ch] = {
                "mean": mean_contrib,
                "hdi_low": hdi_low,
                "hdi_high": hdi_high,
            }
        return results


# ─── Bayesian MMM Trainer ────────────────────────────────────────────────────

class BayesianMMMTrainer:
    """Bayesian MMM Trainer using PyMC MCMC sampling."""

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

    def __init__(self, df: pd.DataFrame, dv_col: str = "dv_t0_loan_amt",
                 channel_keys: Optional[List[str]] = None,
                 context_keys: Optional[List[str]] = None,
                 organic_keys: Optional[List[str]] = None,
                 adstock_type: str = "geometric",
                 draws: int = 2000, tune: int = 1000,
                 chains: int = 4, target_accept: float = 0.9,
                 train_weeks: Optional[int] = None,
                 use_log_dv: Optional[bool] = None):
        _check_pymc()

        if train_weeks is not None and train_weeks < len(df):
            df = df.iloc[-train_weeks:].reset_index(drop=True)

        self.df = df.copy()
        self.dv_col = dv_col if dv_col in df.columns else "loan_amt"

        # Fill NaN
        for col in self.df.select_dtypes(include=[np.number]).columns:
            self.df[col] = self.df[col].fillna(0)

        self.adstock_type = adstock_type
        self.draws = draws
        self.tune = tune
        self.chains = chains
        self.target_accept = target_accept

        # Auto-detect channels
        if channel_keys is None:
            detected = [col.replace("_spend", "") for col in df.columns
                        if col.endswith("_spend") and col != "total_spend"]
            self.channel_keys = (detected if detected
                                 else [ch for ch in self.DEFAULT_CHANNEL_KEYS
                                       if f"{ch}_spend" in df.columns])
        else:
            self.channel_keys = [ch for ch in channel_keys
                                 if f"{ch}_spend" in df.columns]

        # Organic keys
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

        # Context keys
        if context_keys is None:
            self.context_keys = [c for c in self.DEFAULT_CONTEXT_KEYS if c in df.columns]
        else:
            self.context_keys = [c for c in context_keys if c in df.columns]

        # Log DV
        self.use_log_dv = use_log_dv if use_log_dv is not None else (len(df) > 30)

        # Train/test split (last 20% holdout)
        self.n_train = int(len(self.df) * 0.8)
        self.df_train = self.df.iloc[:self.n_train].copy()
        self.df_test = self.df.iloc[self.n_train:].copy()

        # DV processing (train set only)
        self.dv_train = self.df_train[self.dv_col].values.astype(float)
        if self.use_log_dv:
            self.dv_train = np.log1p(self.dv_train)
        self.dv_mean = self.dv_train.mean()
        self.dv_std = self.dv_train.std() + 1e-9
        self.dv_train_norm = (self.dv_train - self.dv_mean) / self.dv_std

        # Spend stats (train set, for normalization)
        self.spend_stats = {}
        for ch in self.channel_keys:
            vals = self.df_train[f"{ch}_spend"].values.astype(float)
            self.spend_stats[ch] = {
                "mean": vals.mean(), "std": vals.std() + 1e-9,
                "max": vals.max() + 1e-9,
            }

        # Calibration priors
        self._calibration_priors: Dict[str, Tuple[float, float]] = {}

        # Adstock max lag
        self.l_max = 8

    def set_calibration_prior(self, channel: str, roas_mu: float, roas_sigma: float):
        """
        Inject incrementality experiment results as informative priors.
        The beta prior for this channel will be Normal(roas_mu, roas_sigma)
        instead of the default HalfNormal.
        """
        if channel not in self.channel_keys:
            logger.warning(f"Channel '{channel}' not in channel_keys, ignoring calibration prior")
            return
        self._calibration_priors[channel] = (roas_mu, roas_sigma)

    def _prepare_channel_data(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Prepare normalized spend data for all channels."""
        data = {}
        for ch in self.channel_keys:
            spend = df[f"{ch}_spend"].values.astype(float)
            max_val = self.spend_stats[ch]["max"]
            data[ch] = spend / max_val  # normalize to ~[0, 1]
        return data

    def _prepare_context_data(self, df: pd.DataFrame) -> Tuple[np.ndarray, Dict[str, Tuple[float, float]]]:
        """Prepare z-scored context features. Returns (matrix, stats_dict)."""
        context_stats = {}
        features = []
        for ctx in self.context_keys:
            vals = df[ctx].values.astype(float)
            if ctx.startswith("trend"):
                features.append(vals)
                context_stats[ctx] = (0.0, 1.0)
            else:
                ctx_mean = float(self.df_train[ctx].mean())
                ctx_std = float(self.df_train[ctx].std() + 1e-9)
                features.append((vals - ctx_mean) / ctx_std)
                context_stats[ctx] = (ctx_mean, ctx_std)
        if features:
            return np.column_stack(features), context_stats
        return np.zeros((len(df), 0)), context_stats

    def _build_pymc_model(self, X_channels: Dict[str, np.ndarray],
                          X_context: np.ndarray, y: np.ndarray) -> "pm.Model":
        """Build PyMC model with adstock + Hill transforms and priors."""
        n_obs = len(y)
        n_ctx = X_context.shape[1] if X_context.ndim == 2 else 0

        with pm.Model() as model:
            # Intercept
            intercept = pm.Normal("intercept", mu=0, sigma=2)

            # Channel-level parameters
            mu_contributions = intercept
            for ch in self.channel_keys:
                x_data = pm.Data(f"{ch}_x", X_channels[ch])

                # Adstock: geometric decay
                theta = pm.Beta(f"{ch}_theta", alpha=1, beta=3)

                # Hill saturation
                hill_alpha = pm.Gamma(f"{ch}_hill_alpha", alpha=3, beta=1.5)
                hill_gamma = pm.Beta(f"{ch}_hill_gamma", alpha=2, beta=2)

                # Channel effect (beta)
                if ch in self._calibration_priors:
                    roas_mu, roas_sigma = self._calibration_priors[ch]
                    beta = pm.TruncatedNormal(
                        f"{ch}_beta", mu=roas_mu, sigma=roas_sigma, lower=0)
                else:
                    beta = pm.HalfNormal(f"{ch}_beta", sigma=2)

                # Apply transforms
                x_adstocked = geometric_adstock_pymc(x_data, theta, l_max=self.l_max)
                x_saturated = hill_saturation_pymc(x_adstocked, hill_alpha, hill_gamma)

                mu_contributions = mu_contributions + beta * x_saturated

            # Context effects
            if n_ctx > 0:
                X_ctx_data = pm.Data("X_context", X_context)
                ctx_betas = pm.Normal("context_betas", mu=0, sigma=1, shape=n_ctx)
                mu_contributions = mu_contributions + pm.math.dot(X_ctx_data, ctx_betas)

            # Likelihood
            sigma = pm.HalfNormal("sigma", sigma=1)
            y_obs = pm.Data("y_obs_data", y)
            pm.Normal("y_obs", mu=mu_contributions, sigma=sigma, observed=y_obs)

        return model

    def fit(self, progress_callback=None) -> BayesianMMMModel:
        """Run MCMC sampling and return fitted BayesianMMMModel."""
        import time as _time
        _t_start = _time.time()

        # Prepare data (train set)
        X_channels = self._prepare_channel_data(self.df_train)
        X_context, context_stats = self._prepare_context_data(self.df_train)
        y_train = self.dv_train_norm

        model = self._build_pymc_model(X_channels, X_context, y_train)

        with model:
            trace = pm.sample(
                draws=self.draws,
                tune=self.tune,
                chains=self.chains,
                target_accept=self.target_accept,
                return_inferencedata=True,
                progressbar=True,
                random_seed=42,
            )

        if progress_callback:
            progress_callback(0.80)

        # Extract posterior summaries
        posterior = trace.posterior
        posterior_samples = {}

        channel_params = {}
        for ch in self.channel_keys:
            theta_samples = posterior[f"{ch}_theta"].values.flatten()
            alpha_samples = posterior[f"{ch}_hill_alpha"].values.flatten()
            gamma_samples = posterior[f"{ch}_hill_gamma"].values.flatten()
            beta_samples = posterior[f"{ch}_beta"].values.flatten()

            posterior_samples[f"{ch}_theta"] = theta_samples
            posterior_samples[f"{ch}_hill_alpha"] = alpha_samples
            posterior_samples[f"{ch}_hill_gamma"] = gamma_samples
            posterior_samples[f"{ch}_beta"] = beta_samples

            beta_hdi = az.hdi(beta_samples, hdi_prob=0.94)

            channel_params[ch] = BayesianChannelParams(
                name=ch,
                adstock_type=self.adstock_type,
                theta_mean=float(theta_samples.mean()),
                alpha_mean=float(alpha_samples.mean()),
                gamma_mean=float(gamma_samples.mean()),
                beta_mean=float(beta_samples.mean()),
                beta_hdi_low=float(beta_hdi[0]),
                beta_hdi_high=float(beta_hdi[1]),
                _norm_max=self.spend_stats[ch]["max"],
            )

        # Context coefficients
        context_coefs = {}
        if self.context_keys and "context_betas" in posterior:
            ctx_samples = posterior["context_betas"].values
            # shape: (chains, draws, n_ctx)
            ctx_means = ctx_samples.mean(axis=(0, 1))
            for i, ctx in enumerate(self.context_keys):
                if i < len(ctx_means):
                    context_coefs[ctx] = float(ctx_means[i])

        # Intercept
        intercept_mean = float(posterior["intercept"].values.flatten().mean())

        if progress_callback:
            progress_callback(0.90)

        # Compute fit metrics
        fitted_model = BayesianMMMModel(
            channel_params=channel_params,
            intercept=intercept_mean,
            context_coefs=context_coefs,
            _trace=trace,
            _posterior_samples=posterior_samples,
            _df=self.df,
            _channel_keys=list(self.channel_keys),
            _context_keys=list(self.context_keys),
            _organic_keys=list(self.organic_keys),
            _dv_mean=self.dv_mean,
            _dv_std=self.dv_std,
            _use_log_dv=self.use_log_dv,
            _context_stats=context_stats,
            dv_col=self.dv_col,
            is_fitted=True,
        )

        # Train metrics
        y_pred_train = fitted_model.predict(self.df_train)
        dv_train_orig = self.df_train[self.dv_col].values.astype(float)
        ss_res_train = np.sum((dv_train_orig - y_pred_train) ** 2)
        ss_tot_train = np.sum((dv_train_orig - dv_train_orig.mean()) ** 2)
        r_squared = max(0.0, 1 - ss_res_train / (ss_tot_train + 1e-9))

        dv_train_for_nrmse = self.dv_train_norm
        y_pred_train_norm = (np.log1p(y_pred_train) - self.dv_mean) / self.dv_std if self.use_log_dv else (y_pred_train - self.dv_mean) / self.dv_std
        train_nrmse = float(np.sqrt(np.mean((dv_train_for_nrmse - y_pred_train_norm) ** 2)) / (dv_train_for_nrmse.std() + 1e-9))

        # Test metrics
        test_r_squared = 0.0
        mape_holdout = 0.0
        holdout_nrmse = train_nrmse
        if len(self.df_test) > 1:
            y_pred_test = fitted_model.predict(self.df_test)
            dv_test_orig = self.df_test[self.dv_col].values.astype(float)
            ss_res_test = np.sum((dv_test_orig - y_pred_test) ** 2)
            ss_tot_test = np.sum((dv_test_orig - dv_test_orig.mean()) ** 2)
            test_r_squared = max(0.0, 1 - ss_res_test / (ss_tot_test + 1e-9))

            nonzero = np.abs(dv_test_orig) > 1e-6
            if nonzero.any():
                mape_holdout = float(np.mean(np.abs(
                    (dv_test_orig[nonzero] - y_pred_test[nonzero]) / dv_test_orig[nonzero]
                )))

            dv_test_log = np.log1p(dv_test_orig) if self.use_log_dv else dv_test_orig
            dv_test_norm = (dv_test_log - self.dv_mean) / self.dv_std
            y_pred_test_norm = (np.log1p(y_pred_test) - self.dv_mean) / self.dv_std if self.use_log_dv else (y_pred_test - self.dv_mean) / self.dv_std
            holdout_nrmse = float(np.sqrt(np.mean((dv_test_norm - y_pred_test_norm) ** 2)) / (dv_test_norm.std() + 1e-9))

        fitted_model.r_squared = r_squared
        fitted_model.train_nrmse = train_nrmse
        fitted_model.nrmse = holdout_nrmse
        fitted_model.test_r_squared = test_r_squared
        fitted_model.mape_holdout = mape_holdout

        # Feature importance
        feature_importance = {}
        for ch, cp in channel_params.items():
            feature_importance[f"{ch}_spend"] = abs(cp.beta_mean)
        for ctx, coef in context_coefs.items():
            feature_importance[ctx] = abs(coef)
        fitted_model.feature_importance = feature_importance

        # Training metadata
        _duration = _time.time() - _t_start
        fitted_model.training_meta = {
            "engine": "bayesian",
            "dv_col": self.dv_col,
            "adstock_type": self.adstock_type,
            "draws": self.draws,
            "tune": self.tune,
            "chains": self.chains,
            "target_accept": self.target_accept,
            "n_train": self.n_train,
            "n_test": len(self.df_test),
            "n_total": len(self.df),
            "channel_keys": list(self.channel_keys),
            "context_keys": list(self.context_keys),
            "organic_keys": list(self.organic_keys),
            "use_log_dv": self.use_log_dv,
            "training_duration_sec": round(_duration, 1),
            "has_calibration": bool(self._calibration_priors),
            "calibrated_channels": list(self._calibration_priors.keys()),
        }

        if progress_callback:
            progress_callback(1.0)

        return fitted_model
