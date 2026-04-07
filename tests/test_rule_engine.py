import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd

from engine.rule_engine import RuleEngine, BudgetInput, PredictionResult


@pytest.fixture
def historical_engine_df():
    """Minimal DataFrame that satisfies RuleEngine._fit_coefficients."""
    n = 6
    rng = np.random.default_rng(42)
    channels = ["tencent_moments", "tencent_video", "tencent_wechat",
                "tencent_search", "douyin", "app_store", "precision_marketing"]
    data = {"month": pd.date_range("2023-01-01", periods=n, freq="MS")}
    for ch in channels:
        data[f"{ch}_spend"]       = rng.uniform(100, 500, n)
        data[f"{ch}_impressions"] = rng.uniform(500_000, 2_000_000, n)
        data[f"{ch}_clicks"]      = rng.uniform(5_000, 50_000, n)

    data["first_login_cnt"]  = rng.uniform(1000, 5000, n)
    data["apply_start_cnt"]  = rng.uniform(800, 4000, n)
    data["apply_submit_cnt"] = rng.uniform(600, 3000, n)
    data["credit_cnt"]       = rng.uniform(400, 2000, n)
    data["credit_a13_cnt"]   = rng.uniform(200, 1000, n)
    data["loan_cnt"]         = rng.uniform(300, 1500, n)
    data["loan_amt"]         = rng.uniform(500_000, 2_000_000, n)
    data["credit_amt"]       = rng.uniform(800_000, 3_000_000, n)
    data["ltv_12m"]          = rng.uniform(100_000, 500_000, n)
    data["ltv_24m"]          = rng.uniform(200_000, 800_000, n)
    data["fpd30_plus_rate"]  = rng.uniform(0.02, 0.08, n)
    data["first_loan_txn"]   = rng.uniform(200, 1000, n)
    data["first_loan_final_loss_rate"]  = rng.uniform(0.05, 0.12, n)
    data["repeat_loan_final_loss_rate"] = rng.uniform(0.02, 0.06, n)
    return pd.DataFrame(data)


@pytest.fixture
def base_budget():
    return BudgetInput(
        tencent_moments_spend=100.0,
        tencent_video_spend=80.0,
        tencent_wechat_spend=60.0,
        tencent_search_spend=40.0,
        douyin_spend=120.0,
        app_store_spend=50.0,
        precision_marketing_spend=50.0,
        goal_mode="规模优先",
    )


def test_simulate_produces_result(historical_engine_df, base_budget):
    """simulate() returns PredictionResult with positive loan_amt."""
    engine = RuleEngine(historical_engine_df)
    result = engine.simulate(base_budget, scenario_name="测试方案")
    assert isinstance(result, PredictionResult)
    assert result.loan_amt > 0


def test_generate_scenarios_produces_four(historical_engine_df, base_budget):
    """generate_scenarios returns exactly 4 scenarios."""
    engine = RuleEngine(historical_engine_df)
    scenarios = engine.generate_scenarios(base_budget)
    assert len(scenarios) == 4
    assert "基准方案" in scenarios
    assert "保守方案" in scenarios
    assert "标准方案" in scenarios
    assert "激进方案" in scenarios
