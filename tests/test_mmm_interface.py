"""Tests for engine/mmm_interface.py — factory routing and protocol definitions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np

from engine.mmm_interface import ENGINE_TYPES, IMMModel, IMMTrainer, create_trainer


# ─── ENGINE_TYPES ────────────────────────────────────────────────────────────

def test_engine_types_contains_legacy_and_bayesian():
    assert "legacy" in ENGINE_TYPES
    assert "bayesian" in ENGINE_TYPES
    assert len(ENGINE_TYPES) == 2


def test_engine_types_values_are_strings():
    for key, val in ENGINE_TYPES.items():
        assert isinstance(key, str)
        assert isinstance(val, str)


# ─── create_trainer factory ──────────────────────────────────────────────────

@pytest.fixture
def mock_df():
    """Minimal dataframe with required columns for MMMTrainer."""
    np.random.seed(42)
    n = 60
    df = pd.DataFrame({
        "week_start": pd.date_range("2023-01-01", periods=n, freq="W"),
        "tencent_moments_spend": np.random.uniform(100, 500, n),
        "douyin_spend": np.random.uniform(50, 300, n),
        "dv_t0_loan_amt": np.random.uniform(1000, 5000, n),
    })
    return df


def test_create_trainer_legacy(mock_df):
    trainer = create_trainer("legacy", mock_df, dv_col="dv_t0_loan_amt", n_trials=10)
    assert trainer is not None
    # Should be a MMMTrainer from engine.mmm_engine
    assert hasattr(trainer, "fit")


def test_create_trainer_invalid_engine(mock_df):
    with pytest.raises(ValueError, match="Unknown engine_type"):
        create_trainer("nonexistent", mock_df, dv_col="dv_t0_loan_amt")


def test_create_trainer_bayesian_import(mock_df):
    """Test bayesian trainer creation — skips if PyMC not installed."""
    try:
        import pymc  # noqa: F401
    except ImportError:
        pytest.skip("PyMC not installed")

    trainer = create_trainer("bayesian", mock_df, dv_col="dv_t0_loan_amt",
                             draws=100, tune=50)
    assert trainer is not None
    assert hasattr(trainer, "fit")


# ─── Protocol checks ────────────────────────────────────────────────────────

def test_legacy_model_satisfies_protocol(mock_df):
    """MMMModel from legacy engine satisfies IMMModel protocol."""
    from engine.mmm_engine import MMMModel
    assert isinstance(MMMModel, type)
    # runtime_checkable protocol — verify structural conformance
    # We check the class has the required methods
    required_methods = ["predict", "channel_contribution", "marginal_response",
                        "budget_optimization", "budget_scenarios"]
    model = MMMModel.__new__(MMMModel)
    for method in required_methods:
        assert hasattr(model, method), f"MMMModel missing {method}"


def test_bayesian_model_satisfies_protocol():
    """BayesianMMMModel satisfies IMMModel protocol."""
    from engine.mmm_bayesian import BayesianMMMModel
    required_methods = ["predict", "channel_contribution", "marginal_response",
                        "budget_optimization", "budget_scenarios"]
    model = BayesianMMMModel()
    for method in required_methods:
        assert hasattr(model, method), f"BayesianMMMModel missing {method}"


def test_legacy_trainer_satisfies_protocol(mock_df):
    """MMMTrainer satisfies IMMTrainer protocol."""
    from engine.mmm_engine import MMMTrainer
    trainer = MMMTrainer(mock_df, dv_col="dv_t0_loan_amt", n_trials=5)
    assert hasattr(trainer, "fit")


def test_bayesian_trainer_satisfies_protocol():
    """BayesianMMMTrainer has fit method (skip if PyMC not installed)."""
    try:
        import pymc  # noqa: F401
    except ImportError:
        pytest.skip("PyMC not installed")

    from engine.mmm_bayesian import BayesianMMMTrainer
    assert hasattr(BayesianMMMTrainer, "fit")
