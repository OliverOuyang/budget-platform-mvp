"""
预算MMM模型 - 核心计算流水线

纯业务逻辑，无 Streamlit 依赖。可独立测试。
"""
import time
import warnings
from typing import Dict, Tuple, Optional
import pandas as pd
from core.models import BudgetParameters, CalculationCoefficients, Table1Result, Table2Result
from core.coefficient_engine import calculate_all_coefficients
from core.channel_calculator import calculate_table1, calculate_budget_shares
from core.customer_group_calculator import calculate_table2


def run_pipeline(
    df_raw1: pd.DataFrame,
    df_raw2: pd.DataFrame,
    params: BudgetParameters,
) -> Tuple[BudgetParameters, CalculationCoefficients, Table1Result, Table2Result]:
    """
    执行完整计算流水线（纯业务逻辑，无 Streamlit 依赖）。

    Parameters
    ----------
    df_raw1 : pd.DataFrame
        raw_达成情况（渠道维度）
    df_raw2 : pd.DataFrame
        raw_客群首借金额（客群维度）
    params : BudgetParameters
        完整预算参数对象

    Returns
    -------
    Tuple[BudgetParameters, CalculationCoefficients, Table1Result, Table2Result]
        (参数对象, 系数对象, Table1结果, Table2结果)
    """
    # Silent failure guard — emit warnings instead of crashing
    if df_raw1.empty:
        warnings.warn("df_raw1 (渠道维度) 数据为空，系数计算将使用默认值", RuntimeWarning)
    if df_raw2.empty:
        warnings.warn("df_raw2 (客群维度) 数据为空，客群推算结果可能不准确", RuntimeWarning)

    # Step 1: 计算系数
    coefficients = calculate_all_coefficients(
        df_channel=df_raw1,
        df_customer=df_raw2,
        existing_m0_months=params.existing_m0_calculation_months,
    )

    # Step 2: 计算预算占比
    budget_shares = params.channel_budget_shares or calculate_budget_shares(df_raw1)

    # Step 3: 计算 Table 1
    table1 = calculate_table1(
        params=params,
        budget_shares=budget_shares,
        m0_t0_coefficient=coefficients.m0_t0_ratio,
        historical_data=df_raw1,
    )

    # Step 4: 计算 Table 2
    days_params = {
        "days_elapsed": params.days_elapsed,
        "month_total_days": params.month_total_days,
    }

    table2 = calculate_table2(
        table1_result=table1,
        params=params,
        existing_m0_cps=coefficients.existing_m0_cps_avg,
        customer_data=df_raw2,
        days_params=days_params,
    )

    return params, coefficients, table1, table2


def execute_calculation_pipeline(
    df_raw1: pd.DataFrame,
    df_raw2: pd.DataFrame,
    total_budget: float,
    channel_budget_shares: Optional[Dict[str, float]],
    channel_1_3_rate: Dict[str, float],
    channel_1_8_cps: Dict[str, float],
    channel_t0_cost: Dict[str, float],
    non_initial_credit: float,
    existing_m0_expense: float,
    rta_promotion_fee: float,
    month_total_days: int,
    days_elapsed: int,
    m0_calc_period: int,
) -> Tuple[BudgetParameters, CalculationCoefficients, Table1Result, Table2Result]:
    """
    执行完整计算流水线（纯业务逻辑，无 Streamlit 依赖）。

    # Deprecated: use run_pipeline() instead

    Parameters
    ----------
    df_raw1 : pd.DataFrame
        raw_达成情况（渠道维度）
    df_raw2 : pd.DataFrame
        raw_客群首借金额（客群维度）
    total_budget : float
        总花费（万元）
    channel_1_3_rate : Dict[str, float]
        渠道 1-3 T0 过件率（小数）
    channel_1_8_cps : Dict[str, float]
        渠道 1-8 T0 CPS（小数）
    channel_t0_cost : Dict[str, float]
        渠道 T0 申完成本（元）
    non_initial_credit : float
        非初审授信户首借交易额（亿元）
    existing_m0_expense : float
        存量首登 M0 花费（万元）
    rta_promotion_fee : float
        RTA 费用 + 促申完（万元）
    month_total_days : int
        当月总天数
    days_elapsed : int
        已完成天数
    m0_calc_period : int
        存量首登 M0 计算周期（3 或 6）

    Returns
    -------
    Tuple[BudgetParameters, CalculationCoefficients, Table1Result, Table2Result]
        (参数对象, 系数对象, Table1结果, Table2结果)
    """
    params = BudgetParameters(
        total_budget=total_budget,
        channel_budget_shares=channel_budget_shares or {},
        channel_1_3_approval_rate=channel_1_3_rate,
        channel_1_8_cps=channel_1_8_cps,
        channel_t0_completion_cost=channel_t0_cost,
        non_initial_credit_transaction=non_initial_credit,
        existing_m0_expense=existing_m0_expense,
        rta_promotion_fee=rta_promotion_fee,
        month_total_days=month_total_days,
        days_elapsed=days_elapsed,
        existing_m0_calculation_months=m0_calc_period,
    )
    return run_pipeline(df_raw1, df_raw2, params)
