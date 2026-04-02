import pytest
import warnings
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.calculation_pipeline import execute_calculation_pipeline
import pandas as pd
import numpy as np

RAW1_COLS = [
    "月份", "渠道类别", "1-3t0过件率", "1-8t0cps", "花费",
    "1-8t0首借24h借款金额", "1-8t0过件率", "t0申完成本",
    "非年龄拒绝t0申完量", "当月首登m0_t0_24h_交易比值", "1_8m0首登当月首借24h借款金额",
]
RAW2_COLS = [
    "月份", "客群", "授信人数", "发起人数", "风险通过人数",
    "动支人数", "初始授信额度", "首贷金额", "渠道类别",
]


def make_df1(rows):
    data = {col: [np.nan] * rows for col in RAW1_COLS}
    if rows:
        data["月份"] = ["2024-01"] * rows
        data["渠道类别"] = ["腾讯"] * rows
    return pd.DataFrame(data)


def make_df2(rows):
    data = {col: [np.nan] * rows for col in RAW2_COLS}
    if rows:
        data["月份"] = ["2024-01"] * rows
        data["客群"] = ["A组"] * rows
    return pd.DataFrame(data)


def test_empty_df1_emits_warning():
    df1 = make_df1(0)
    df2 = make_df2(1)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        execute_calculation_pipeline(
            df_raw1=df1,
            df_raw2=df2,
            total_budget=100,
            channel_1_3_rate={},
            channel_1_8_cps={},
            channel_t0_cost={},
            non_initial_credit=0.0,
            existing_m0_expense=0.0,
            rta_promotion_fee=0.0,
            month_total_days=30,
            days_elapsed=15,
            m0_calc_period=3,
        )
        assert any("df_raw1" in str(w_.message) for w_ in w)


def test_empty_df2_emits_warning():
    df1 = make_df1(1)
    df2 = make_df2(0)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        execute_calculation_pipeline(
            df_raw1=df1,
            df_raw2=df2,
            total_budget=100,
            channel_1_3_rate={},
            channel_1_8_cps={},
            channel_t0_cost={},
            non_initial_credit=0.0,
            existing_m0_expense=0.0,
            rta_promotion_fee=0.0,
            month_total_days=30,
            days_elapsed=15,
            m0_calc_period=3,
        )
        assert any("df_raw2" in str(w_.message) for w_ in w)


def test_both_empty_emit_both_warnings():
    df1 = make_df1(0)
    df2 = make_df2(0)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        execute_calculation_pipeline(
            df_raw1=df1,
            df_raw2=df2,
            total_budget=100,
            channel_1_3_rate={},
            channel_1_8_cps={},
            channel_t0_cost={},
            non_initial_credit=0.0,
            existing_m0_expense=0.0,
            rta_promotion_fee=0.0,
            month_total_days=30,
            days_elapsed=15,
            m0_calc_period=3,
        )
        warning_messages = [str(w_.message) for w_ in w]
        assert any("df_raw1" in m for m in warning_messages)
        assert any("df_raw2" in m for m in warning_messages)
