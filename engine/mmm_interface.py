"""
engine/mmm_interface.py

Unified interface layer for MMM engines.
Supports switching between Legacy (Optuna + Ridge) and Bayesian (PyMC) engines
via a factory function and shared Protocol definitions.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

import numpy as np
import pandas as pd


# ─── UI 标签 ─────────────────────────────────────────────────────────────────

ENGINE_TYPES: Dict[str, str] = {
    "legacy": "Optuna + Ridge (传统)",
    "bayesian": "PyMC 贝叶斯",
}


# ─── Protocols ───────────────────────────────────────────────────────────────

@runtime_checkable
class IMMModel(Protocol):
    """Structural protocol that both MMMModel and BayesianMMMModel must satisfy."""

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict DV given input dataframe."""
        ...

    def channel_contribution(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Decompose per-channel contribution."""
        ...

    def marginal_response(
        self,
        ch: str,
        spend_range: np.ndarray,
        df_last: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        """Compute marginal response curve for a single channel."""
        ...

    def budget_optimization(
        self,
        total_budget: float,
        df_recent: pd.DataFrame,
        channel_constr_low: float = 0.3,
        channel_constr_up: float = 5.0,
    ) -> Dict[str, float]:
        """Optimal budget allocation under total budget constraint."""
        ...

    def budget_scenarios(
        self,
        df_recent: pd.DataFrame,
        multipliers: Optional[List[float]] = None,
        channel_constr_low: float = 0.3,
        channel_constr_up: float = 5.0,
    ) -> Dict[str, Dict[str, float]]:
        """Multi-scenario budget allocation."""
        ...


@runtime_checkable
class IMMTrainer(Protocol):
    """Structural protocol for MMM trainers."""

    def fit(self, progress_callback: Optional[Callable[..., Any]] = None) -> IMMModel:
        """Train the model and return a fitted IMMModel."""
        ...


# ─── Factory ─────────────────────────────────────────────────────────────────

def create_trainer(engine_type: str, df: pd.DataFrame, dv_col: str, **kwargs: Any) -> IMMTrainer:
    """
    Factory function that returns a trainer for the requested engine.

    Parameters
    ----------
    engine_type : str
        One of "legacy" or "bayesian".
    df : pd.DataFrame
        Training data.
    dv_col : str
        Name of the dependent-variable column.
    **kwargs
        Extra keyword arguments forwarded to the trainer constructor.

    Returns
    -------
    IMMTrainer
        A trainer whose fit() returns an IMMModel.

    Raises
    ------
    ValueError
        If engine_type is not recognised.
    """
    if engine_type == "legacy":
        # Lazy import — keeps PyMC optional
        from engine.mmm_engine import MMMTrainer  # noqa: PLC0415
        return MMMTrainer(df=df, dv_col=dv_col, **kwargs)

    if engine_type == "bayesian":
        # Lazy import — only attempted when PyMC is actually installed
        from engine.mmm_bayesian import BayesianMMMTrainer  # noqa: PLC0415
        return BayesianMMMTrainer(df=df, dv_col=dv_col, **kwargs)

    raise ValueError(
        f"Unknown engine_type '{engine_type}'. "
        f"Valid options: {list(ENGINE_TYPES.keys())}"
    )
