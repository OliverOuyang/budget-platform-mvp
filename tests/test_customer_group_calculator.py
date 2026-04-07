import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd

from core.customer_group_calculator import extrapolate_by_days, calculate_table2
from core.models import BudgetParameters


def test_extrapolate_by_days_normal():
    """50 value, 15 days elapsed, 30 total → 100.0."""
    result = extrapolate_by_days(50.0, 15, 30)
    assert pytest.approx(result, rel=1e-6) == 100.0


def test_extrapolate_by_days_zero_elapsed():
    """Zero days elapsed → 0.0."""
    result = extrapolate_by_days(100.0, 0, 30)
    assert result == 0.0


def test_extrapolate_by_days_full_month():
    """Days elapsed >= total_days → current_value unchanged."""
    result = extrapolate_by_days(75.0, 30, 30)
    assert result == 75.0


def test_extrapolate_by_days_exceeds_total():
    """Days elapsed > total_days → still returns current_value."""
    result = extrapolate_by_days(75.0, 35, 30)
    assert result == 75.0


def test_calculate_table2_basic(sample_table1_result, sample_df_raw2):
    """total_transaction = initial_credit_total + non_initial_credit."""
    params = BudgetParameters(
        total_budget=1000.0,
        non_initial_credit_transaction=0.8,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
        month_total_days=30,
        days_elapsed=25,
    )
    days_params = {"month_total_days": 30, "days_elapsed": 25}
    result = calculate_table2(
        table1_result=sample_table1_result,
        params=params,
        existing_m0_cps=0.30,
        customer_data=sample_df_raw2,
        days_params=days_params,
    )
    expected_total = result.initial_credit_total + result.non_initial_credit
    assert pytest.approx(result.total_transaction, rel=1e-6) == expected_total
