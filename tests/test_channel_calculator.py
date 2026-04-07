import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd

from core.channel_calculator import (
    calculate_table1,
    _allocate_budget_to_channels,
    calculate_budget_shares,
)
from core.models import BudgetParameters, Table1Result
from app.config import CHANNEL_NAMES


@pytest.fixture
def base_params():
    return BudgetParameters(
        total_budget=5000.0,
        channel_1_3_approval_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_completion_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        non_initial_credit_transaction=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
        month_total_days=30,
        days_elapsed=25,
    )


@pytest.fixture
def historical_df(sample_df_raw1):
    return sample_df_raw1


def test_allocate_budget_proportional(base_params):
    """Budget allocation should sum to total_budget."""
    shares = {ch: 0.2 for ch in CHANNEL_NAMES}
    allocated = _allocate_budget_to_channels(base_params.total_budget, shares)
    total_allocated = sum(allocated.values())
    assert pytest.approx(total_allocated, rel=1e-6) == base_params.total_budget


def test_free_channel_zero_cps(historical_df):
    """Free channel (CPS=0) falls back to historical extrapolation."""
    params = BudgetParameters(
        total_budget=1000.0,
        channel_1_3_approval_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: (0.0 if ch == '免费渠道' else 0.30) for ch in CHANNEL_NAMES},
        channel_t0_completion_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
    )
    result = calculate_table1(
        params=params,
        budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        m0_t0_coefficient=1.5,
        historical_data=historical_df,
    )
    assert isinstance(result, Table1Result)
    free_ch = next(ch for ch in result.channels if ch.channel_name == '免费渠道')
    # CPS=0 means t0_transaction comes from historical extrapolation (≥ 0)
    assert free_ch.t0_transaction >= 0.0


def test_calculate_budget_shares_from_data(sample_df_raw1):
    """Budget shares should sum to 1.0 when data is valid."""
    shares = calculate_budget_shares(sample_df_raw1)
    assert len(shares) > 0
    assert pytest.approx(sum(shares.values()), rel=1e-6) == 1.0
