"""Tests for engine/mmm_bayesian.py — Bayesian MMM engine unit tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd

from engine.mmm_bayesian import (
    geometric_adstock,
    hill_saturation,
    BayesianChannelParams,
    BayesianMMMModel,
)


def _has_pymc():
    try:
        import pymc  # noqa: F401
        return True
    except ImportError:
        return False


# ─── NumPy transforms ───────────────────────────────────────────────────────

class TestGeometricAdstock:
    def test_no_decay(self):
        x = np.array([1.0, 0.0, 0.0, 0.0])
        result = geometric_adstock(x, theta=0.0)
        np.testing.assert_array_almost_equal(result, [1.0, 0.0, 0.0, 0.0])

    def test_full_carryover(self):
        x = np.array([1.0, 0.0, 0.0])
        result = geometric_adstock(x, theta=0.5)
        np.testing.assert_array_almost_equal(result, [1.0, 0.5, 0.25])

    def test_monotone_decay(self):
        x = np.array([10.0, 0.0, 0.0, 0.0, 0.0])
        result = geometric_adstock(x, theta=0.7)
        # Each subsequent value should be smaller
        for i in range(1, len(result)):
            assert result[i] <= result[i - 1]

    def test_single_element(self):
        x = np.array([5.0])
        result = geometric_adstock(x, theta=0.9)
        assert result[0] == 5.0


class TestHillSaturation:
    def test_zero_input(self):
        x = np.array([0.0])
        result = hill_saturation(x, alpha=2.0, gamma=0.5)
        # With x_safe = 1e-10, result should be ~0
        assert result[0] < 1e-5

    def test_high_input_saturates(self):
        x = np.array([1000.0])
        result = hill_saturation(x, alpha=2.0, gamma=0.5)
        # Should be close to 1
        assert result[0] > 0.99

    def test_at_gamma(self):
        """At x = gamma, output should be 0.5 (half-saturation)."""
        gamma = 0.5
        x = np.array([gamma])
        result = hill_saturation(x, alpha=2.0, gamma=gamma)
        np.testing.assert_almost_equal(result[0], 0.5, decimal=2)

    def test_monotone_increasing(self):
        x = np.array([0.1, 0.5, 1.0, 5.0, 10.0])
        result = hill_saturation(x, alpha=1.5, gamma=1.0)
        for i in range(1, len(result)):
            assert result[i] >= result[i - 1]


# ─── BayesianChannelParams ──────────────────────────────────────────────────

class TestBayesianChannelParams:
    def test_default_values(self):
        cp = BayesianChannelParams(name="test_ch")
        assert cp.name == "test_ch"
        assert cp.adstock_type == "geometric"
        assert cp.theta_mean == 0.0
        assert cp.beta_mean == 0.0

    def test_transform_output_shape(self):
        cp = BayesianChannelParams(
            name="ch", theta_mean=0.5, alpha_mean=2.0,
            gamma_mean=0.5, beta_mean=1.0, _norm_max=100.0,
        )
        spend = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
        result = cp.transform(spend)
        assert result.shape == spend.shape

    def test_transform_nonnegative(self):
        cp = BayesianChannelParams(
            name="ch", theta_mean=0.3, alpha_mean=1.5,
            gamma_mean=0.5, beta_mean=0.5, _norm_max=50.0,
        )
        spend = np.array([0.0, 10.0, 20.0])
        result = cp.transform(spend)
        assert np.all(result >= 0)

    def test_transform_handles_nan(self):
        cp = BayesianChannelParams(name="ch", _norm_max=100.0)
        spend = np.array([np.nan, 10.0, np.nan])
        result = cp.transform(spend)
        assert not np.any(np.isnan(result))


# ─── BayesianMMMModel ───────────────────────────────────────────────────────

@pytest.fixture
def fitted_model():
    """Create a minimal BayesianMMMModel with synthetic params."""
    channel_params = {
        "ch_a": BayesianChannelParams(
            name="ch_a", theta_mean=0.3, alpha_mean=2.0,
            gamma_mean=0.5, beta_mean=1.5,
            beta_hdi_low=0.8, beta_hdi_high=2.2, _norm_max=100.0,
        ),
        "ch_b": BayesianChannelParams(
            name="ch_b", theta_mean=0.5, alpha_mean=1.5,
            gamma_mean=0.4, beta_mean=0.8,
            beta_hdi_low=0.3, beta_hdi_high=1.3, _norm_max=200.0,
        ),
    }
    model = BayesianMMMModel(
        channel_params=channel_params,
        intercept=0.5,
        context_coefs={},
        r_squared=0.85,
        nrmse=0.15,
        is_fitted=True,
        _channel_keys=["ch_a", "ch_b"],
        _context_keys=[],
        _organic_keys=[],
        _dv_mean=3000.0,
        _dv_std=500.0,
        _use_log_dv=False,
        _posterior_samples={
            "ch_a_beta": np.random.normal(1.5, 0.3, 100),
            "ch_b_beta": np.random.normal(0.8, 0.2, 100),
        },
    )
    return model


@pytest.fixture
def sample_df():
    """Minimal DF for model prediction."""
    np.random.seed(0)
    n = 20
    return pd.DataFrame({
        "ch_a_spend": np.random.uniform(10, 100, n),
        "ch_b_spend": np.random.uniform(20, 200, n),
    })


class TestBayesianMMMModel:
    def test_predict_shape(self, fitted_model, sample_df):
        result = fitted_model.predict(sample_df)
        assert isinstance(result, np.ndarray)
        assert len(result) == len(sample_df)

    def test_predict_reasonable_values(self, fitted_model, sample_df):
        result = fitted_model.predict(sample_df)
        # All predictions should be positive (intercept + positive betas)
        assert np.all(result > 0)

    def test_channel_contribution_keys(self, fitted_model, sample_df):
        contribs = fitted_model.channel_contribution(sample_df)
        assert "ch_a" in contribs
        assert "ch_b" in contribs

    def test_channel_contribution_nonnegative(self, fitted_model, sample_df):
        contribs = fitted_model.channel_contribution(sample_df)
        for ch, values in contribs.items():
            assert np.all(values >= 0), f"Negative contribution for {ch}"

    def test_channel_contribution_shape(self, fitted_model, sample_df):
        contribs = fitted_model.channel_contribution(sample_df)
        for ch, values in contribs.items():
            assert len(values) == len(sample_df)

    def test_marginal_response_shape(self, fitted_model, sample_df):
        spend_range = np.linspace(0, 200, 50)
        result = fitted_model.marginal_response("ch_a", spend_range, df_last=sample_df)
        assert len(result) == 50

    def test_marginal_response_nonnegative(self, fitted_model, sample_df):
        spend_range = np.linspace(0, 200, 30)
        result = fitted_model.marginal_response("ch_a", spend_range, df_last=sample_df)
        assert np.all(result >= 0)

    def test_marginal_response_missing_channel(self, fitted_model):
        spend_range = np.linspace(0, 100, 10)
        result = fitted_model.marginal_response("nonexistent", spend_range)
        np.testing.assert_array_equal(result, np.zeros(10))

    def test_budget_optimization_returns_dict(self, fitted_model, sample_df):
        result = fitted_model.budget_optimization(
            total_budget=1000.0, df_recent=sample_df)
        assert "optimal_allocation" in result
        assert "total_budget" in result
        assert "channels" in result

    def test_budget_optimization_sums_to_total(self, fitted_model, sample_df):
        result = fitted_model.budget_optimization(
            total_budget=1000.0, df_recent=sample_df)
        alloc = result["optimal_allocation"]
        assert abs(sum(alloc.values()) - 1000.0) < 1.0  # within $1

    def test_budget_scenarios_returns_list(self, fitted_model, sample_df):
        scenarios = fitted_model.budget_scenarios(df_recent=sample_df)
        assert isinstance(scenarios, list)
        assert len(scenarios) == 5  # default 5 ratios

    def test_budget_scenarios_labels(self, fitted_model, sample_df):
        scenarios = fitted_model.budget_scenarios(df_recent=sample_df)
        labels = [s["label"] for s in scenarios]
        assert "100%" in labels

    def test_get_posterior_summary_no_trace(self, fitted_model):
        """Without trace, should return warning."""
        summary = fitted_model.get_posterior_summary()
        assert "warning" in summary

    def test_get_channel_roas_distribution(self, fitted_model):
        samples = fitted_model.get_channel_roas_distribution("ch_a")
        assert isinstance(samples, np.ndarray)
        assert len(samples) > 0

    def test_get_channel_roas_distribution_missing(self, fitted_model):
        samples = fitted_model.get_channel_roas_distribution("nonexistent")
        assert len(samples) > 0  # returns [0.0] fallback

    def test_get_contribution_with_hdi(self, fitted_model, sample_df):
        result = fitted_model.get_contribution_with_hdi(sample_df)
        assert "ch_a" in result
        assert "mean" in result["ch_a"]
        assert "hdi_low" in result["ch_a"]
        assert "hdi_high" in result["ch_a"]

    def test_get_contribution_hdi_ordering(self, fitted_model, sample_df):
        result = fitted_model.get_contribution_with_hdi(sample_df)
        for ch, vals in result.items():
            # hdi_low <= mean <= hdi_high (on average)
            assert np.mean(vals["hdi_low"]) <= np.mean(vals["mean"]) + 1e-6
            assert np.mean(vals["mean"]) <= np.mean(vals["hdi_high"]) + 1e-6


# ─── BayesianMMMTrainer (requires PyMC) ─────────────────────────────────────

@pytest.fixture
def trainer_df():
    """Dataframe suitable for BayesianMMMTrainer."""
    np.random.seed(42)
    n = 80
    df = pd.DataFrame({
        "week_start": pd.date_range("2023-01-01", periods=n, freq="W"),
        "ch_a_spend": np.random.uniform(100, 500, n),
        "ch_b_spend": np.random.uniform(50, 300, n),
    })
    df["dv_t0_loan_amt"] = (
        2000 + 1.5 * df["ch_a_spend"] + 0.8 * df["ch_b_spend"]
        + np.random.normal(0, 100, n)
    )
    return df


@pytest.mark.skipif(
    not _has_pymc(), reason="PyMC not installed"
)
class TestBayesianMMMTrainer:
    def test_trainer_init(self, trainer_df):
        from engine.mmm_bayesian import BayesianMMMTrainer
        trainer = BayesianMMMTrainer(
            trainer_df, dv_col="dv_t0_loan_amt", draws=50, tune=25, chains=1)
        assert trainer.channel_keys == ["ch_a", "ch_b"]
        assert trainer.draws == 50

    def test_set_calibration_prior(self, trainer_df):
        from engine.mmm_bayesian import BayesianMMMTrainer
        trainer = BayesianMMMTrainer(
            trainer_df, dv_col="dv_t0_loan_amt", draws=50, tune=25, chains=1)
        trainer.set_calibration_prior("ch_a", roas_mu=1.5, roas_sigma=0.3)
        assert "ch_a" in trainer._calibration_priors

    def test_set_calibration_prior_unknown_channel(self, trainer_df):
        from engine.mmm_bayesian import BayesianMMMTrainer
        trainer = BayesianMMMTrainer(
            trainer_df, dv_col="dv_t0_loan_amt", draws=50, tune=25, chains=1)
        trainer.set_calibration_prior("nonexistent", roas_mu=1.0, roas_sigma=0.5)
        assert "nonexistent" not in trainer._calibration_priors

    def test_fit_returns_model(self, trainer_df):
        from engine.mmm_bayesian import BayesianMMMTrainer
        trainer = BayesianMMMTrainer(
            trainer_df, dv_col="dv_t0_loan_amt",
            draws=50, tune=25, chains=1)
        model = trainer.fit()
        assert isinstance(model, BayesianMMMModel)
        assert model.is_fitted
        assert model.r_squared > 0
        assert len(model.channel_params) == 2
