"""Tests for US-701 (Rolling CV, Bootstrap) and US-703 (ModelRegistry)."""
import pytest
import numpy as np
import pandas as pd
import shutil
from pathlib import Path

from engine.mmm_engine import MMMModel, MMMTrainer, ModelRegistry, ChannelParams


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_weekly_df():
    """Generate 60-week mock DataFrame for testing."""
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2024-06-01", periods=n, freq="W-MON")
    df = pd.DataFrame({"week_start": dates})
    for ch in ["tencent", "douyin"]:
        df[f"{ch}_spend"] = np.random.uniform(50, 200, n)
        df[f"{ch}_impressions"] = np.random.uniform(1000, 5000, n)
        df[f"{ch}_first_login"] = np.random.uniform(100, 500, n)
    df["free_channel_first_login"] = np.random.uniform(200, 800, n)
    df["total_spend"] = df["tencent_spend"] + df["douyin_spend"]
    # DV with trend + noise
    t = np.linspace(0, 1, n)
    df["dv_total_loan_amt"] = 5000 + 2000 * t + np.random.normal(0, 300, n)
    # Add prophet-style features
    from core.external_data import add_prophet_features
    df = add_prophet_features(df, "week_start", n_changepoints=3)
    return df


@pytest.fixture
def fitted_model():
    """Create a minimal fitted MMMModel for registry testing."""
    return MMMModel(
        channel_params={"tencent": ChannelParams(name="tencent", beta=1.5)},
        intercept=0.5,
        r_squared=0.85,
        train_nrmse=0.35,
        nrmse=0.40,
        decomp_rssd=0.08,
        test_r_squared=0.0,
        mape_holdout=0.5,
        dw_stat=1.8,
        dv_col="dv_total_loan_amt",
        training_meta={
            "dv_col": "dv_total_loan_amt",
            "n_trials": 100,
            "adstock_type": "geometric",
            "n_train": 48,
            "n_test": 12,
            "training_duration_sec": 30.0,
        },
        cv_results={"mean_r2": 0.65, "std_r2": 0.1, "n_folds": 5, "fold_details": []},
        bootstrap_stability={"tencent": {"mean": 1.5, "std": 0.3, "cv": 0.2, "stable": True}},
        feature_importance={"tencent_spend": 1.5},
        is_fitted=True,
    )


@pytest.fixture
def registry_dir():
    """Create a temp directory for registry that avoids Windows tmp_path issues."""
    d = Path(__file__).parent / "_test_registry_tmp"
    d.mkdir(exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ─── US-701: Rolling CV ────────────────────────────────────────────────────

def test_rolling_cv_returns_valid(mock_weekly_df):
    """Rolling-origin CV should return dict with mean_r2, fold_details."""
    trainer = MMMTrainer(
        mock_weekly_df, dv_col="dv_total_loan_amt",
        n_trials=5, n_models=1,
    )
    params = {}
    for ch in trainer.channel_keys:
        params[f"{ch}_theta"] = 0.1
        params[f"{ch}_alpha"] = 2.0
        params[f"{ch}_gamma"] = 0.5

    result = trainer._evaluate_rolling_cv(params, n_origins=3)

    assert "mean_r2" in result
    assert "std_r2" in result
    assert "fold_details" in result
    assert isinstance(result["fold_details"], list)
    assert len(result["fold_details"]) > 0
    assert all(0 <= f["r2"] <= 1.0 for f in result["fold_details"])


def test_bootstrap_stability_returns_valid(mock_weekly_df):
    """Bootstrap stability should return per-channel dict with mean/std/cv."""
    trainer = MMMTrainer(
        mock_weekly_df, dv_col="dv_total_loan_amt",
        n_trials=5, n_models=1,
    )
    params = {}
    for ch in trainer.channel_keys:
        params[f"{ch}_theta"] = 0.1
        params[f"{ch}_alpha"] = 2.0
        params[f"{ch}_gamma"] = 0.5

    result = trainer._bootstrap_stability(params, n_bootstrap=10)

    assert len(result) >= len(trainer.channel_keys)
    for ch in trainer.channel_keys:
        assert ch in result
        assert "mean" in result[ch]
        assert "std" in result[ch]
        assert "cv" in result[ch]
        assert "stable" in result[ch]


# ─── US-703: Model Registry ─────────────────────────────────────────────────

def test_model_registry_crud(fitted_model, registry_dir):
    """Registry should save, list, load, and delete models."""
    registry = ModelRegistry(models_dir=registry_dir / "models")

    # Save
    model_id = registry.save(fitted_model, name="test_model_v1")
    assert model_id
    assert len(model_id) == 8

    # List
    models = registry.list()
    assert len(models) == 1
    entry = models[0]
    assert entry["id"] == model_id
    assert entry["name"] == "test_model_v1"
    assert entry["dv_col"] == "dv_total_loan_amt"
    assert entry["r_squared"] == 0.85
    assert entry["train_nrmse"] == 0.35

    # Load
    loaded = registry.load(model_id)
    assert loaded is not None
    assert loaded.r_squared == 0.85
    assert loaded.dv_col == "dv_total_loan_amt"

    # Delete
    assert registry.delete(model_id) is True
    assert len(registry.list()) == 0
    assert registry.load(model_id) is None


def test_model_registry_multiple_models(fitted_model, registry_dir):
    """Registry should handle multiple models."""
    registry = ModelRegistry(models_dir=registry_dir / "models2")

    id1 = registry.save(fitted_model, name="model_a")
    # Modify and save another
    fitted_model.r_squared = 0.90
    fitted_model.dv_col = "dv_t0_cps"
    id2 = registry.save(fitted_model, name="model_b")

    models = registry.list()
    assert len(models) == 2
    assert {m["name"] for m in models} == {"model_a", "model_b"}

    # Delete one, other persists
    registry.delete(id1)
    assert len(registry.list()) == 1
    assert registry.list()[0]["id"] == id2


def test_model_registry_get_entry(fitted_model, registry_dir):
    """get_entry should return metadata for a specific model."""
    registry = ModelRegistry(models_dir=registry_dir / "models3")
    model_id = registry.save(fitted_model, name="entry_test")

    entry = registry.get_entry(model_id)
    assert entry is not None
    assert entry["name"] == "entry_test"
    assert "config_summary" in entry
    assert entry["config_summary"]["adstock_type"] == "geometric"

    # Non-existent
    assert registry.get_entry("nonexistent") is None
