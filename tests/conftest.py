import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
from core.models import (
    BudgetParameters, CalculationCoefficients,
    ChannelData, Table1Result, Table2Result,
)

CHANNEL_NAMES = ['腾讯', '抖音', '精准营销', '付费商店', '免费渠道']
MONTHS = ['2024-01', '2024-02', '2024-03']


@pytest.fixture
def sample_df_raw1():
    """raw_达成情况 DataFrame — 3 months × 5 channels."""
    rows = []
    for month in MONTHS:
        for ch in CHANNEL_NAMES:
            rows.append({
                '月份': month,
                '渠道类别': ch,
                '1-3t0过件率': 0.45,
                '1-8t0cps': 0.30,
                '花费': 1000000.0,
                '1-8t0首借24h借款金额': 5000000.0,
                '1-8t0过件率': 0.38,
                't0申完成本': 150.0,
                '非年龄拒绝t0申完量': 6000.0,
                '当月首登m0_t0_24h_交易比值': 1.5,
                '1_8m0首登当月首借24h借款金额': 7500000.0,
            })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_df_raw2():
    """raw_客群首借金额 DataFrame — 3 months × 5 channels."""
    rows = []
    customer_groups = ['当月首登M0', '存量首登M0', '非初审-重申']
    for month in MONTHS:
        for ch in CHANNEL_NAMES:
            for cg in customer_groups:
                rows.append({
                    '月份': month,
                    '客群': cg,
                    '授信人数': 100,
                    '发起人数': 120,
                    '风险通过人数': 80,
                    '动支人数': 60,
                    '初始授信额度': 50000.0,
                    '首贷金额': 30000.0,
                    '渠道类别': ch,
                })
    return pd.DataFrame(rows)


@pytest.fixture
def sample_table1_result():
    """Pre-built Table1Result with one channel + total."""
    ch = ChannelData(
        channel_name='腾讯',
        approval_rate_1_3=0.45,
        cps_1_8=0.30,
        t0_completion_cost=150.0,
        expense=1000.0,
        t0_transaction=0.333,
        t0_completion_volume=6667.0,
        expense_structure=100.0,
        m0_transaction=0.5,
        credit_volume_1_3=3000.0,
        completion_structure=100.0,
    )
    total_ch = ChannelData(
        channel_name='总计',
        approval_rate_1_3=0.45,
        cps_1_8=0.30,
        t0_completion_cost=150.0,
        expense=1000.0,
        t0_transaction=0.333,
        t0_completion_volume=6667.0,
        expense_structure=100.0,
        m0_transaction=0.5,
        credit_volume_1_3=3000.0,
        completion_structure=100.0,
    )
    return Table1Result(
        channels=[ch, total_ch],
        total_expense=1000.0,
        total_t0_transaction=0.333,
        total_m0_transaction=0.5,
        total_completion_volume=6667.0,
    )


@pytest.fixture
def sample_table2_result():
    """Pre-built Table2Result."""
    return Table2Result(
        initial_credit_total=1.2,
        current_month_initial_m0=0.5,
        first_login_t0=0.3,
        existing_initial_m0=0.4,
        non_initial_credit=0.8,
        total_transaction=2.0,
        total_expense=5000.0,
        rta_promotion_fee=200.0,
        calculated_existing_m0_expense=1000.0,
        total_cps=0.25,
        approval_rate_1_3_excl_age=0.45,
    )
