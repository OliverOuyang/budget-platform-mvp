import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np

from core.coefficient_engine import (
    DEFAULT_M0_T0_RATIO,
    DEFAULT_CPS_RATE,
    calculate_m0_t0_coefficient,
    calculate_existing_m0_cps,
    calculate_all_coefficients,
)
from core.models import CalculationCoefficients


def test_named_constants_exist():
    assert DEFAULT_M0_T0_RATIO == 1.5
    assert DEFAULT_CPS_RATE == 0.05


def test_calculate_m0_t0_coefficient_returns_tuple():
    """When M0/T0 columns are NaN, falls back to DEFAULT_M0_T0_RATIO."""
    df = pd.DataFrame({
        "月份": ["2024-01", "2024-02"],
        "1_8m0首登当月首借24h借款金额": [np.nan, np.nan],
        "1-8t0首借24h借款金额": [0.0, 0.0],
    })
    result = calculate_m0_t0_coefficient(df)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] == DEFAULT_M0_T0_RATIO
    assert result[1] == []


def test_calculate_m0_t0_with_valid_data():
    """Provide real ratios; verify output matches expected mean."""
    # m0 / t0 = 9 / 3 = 3.0, 8 / 2 = 4.0 → mean = 3.5
    df = pd.DataFrame({
        "月份": ["2024-01", "2024-02"],
        "1_8m0首登当月首借24h借款金额": [9.0, 8.0],
        "1-8t0首借24h借款金额": [3.0, 2.0],
    })
    coef, ratios = calculate_m0_t0_coefficient(df)
    assert len(ratios) == 2
    assert pytest.approx(ratios[0], rel=1e-6) == 3.0
    assert pytest.approx(ratios[1], rel=1e-6) == 4.0
    assert pytest.approx(coef, rel=1e-6) == 3.5


def test_calculate_existing_m0_cps_empty_customer():
    """Empty df_customer (with 月份 col) should return DEFAULT_CPS_RATE."""
    df_channel = pd.DataFrame({
        "月份": ["2024-01"],
        "渠道类别": ["腾讯"],
        "花费": [1000.0],
    })
    # Must have 月份 column so sort_values doesn't KeyError, but no rows
    df_customer = pd.DataFrame({"月份": pd.Series([], dtype=str)})
    cps, history = calculate_existing_m0_cps(df_channel, df_customer)
    assert cps == DEFAULT_CPS_RATE
    assert history == []


def test_calculate_all_coefficients_returns_correct_type(sample_df_raw1, sample_df_raw2):
    """calculate_all_coefficients returns CalculationCoefficients with expected fields."""
    result = calculate_all_coefficients(sample_df_raw1, sample_df_raw2)
    assert isinstance(result, CalculationCoefficients)
    assert isinstance(result.m0_t0_ratio, float)
    assert isinstance(result.existing_m0_cps_avg, float)
    assert isinstance(result.m0_t0_ratio_history, list)
    assert isinstance(result.existing_m0_cps_history, list)
    assert isinstance(result.m0_t0_source_months, list)
    assert isinstance(result.existing_m0_source_months, list)
