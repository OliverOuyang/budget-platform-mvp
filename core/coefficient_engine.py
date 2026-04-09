"""
系数计算引擎
"""
from typing import Tuple, List
import pandas as pd
import numpy as np

from core.constants import M0_T0_COEFFICIENT_MONTHS, EXISTING_M0_CPS_MONTHS, TRANSACTION_UNIT_DIVISOR, EXPENSE_UNIT_DIVISOR
from core.models import CalculationCoefficients

DEFAULT_M0_T0_RATIO = 1.5
DEFAULT_CPS_RATE = 0.05


def calculate_m0_t0_coefficient(df: pd.DataFrame, months: int = M0_T0_COEFFICIENT_MONTHS) -> Tuple[float, List[float]]:
    """
    计算 M0/T0 交易比值系数 (前N个月均值)

    Args:
        df: raw_达成情况 DataFrame
        months: 计算窗口月数 (默认6个月)

    Returns:
        (系数均值, 历史比值列表)
    """
    # 按月份排序,取最新N个月
    df_sorted = df.sort_values('月份', ascending=False)

    # 按月份聚合 (一个月可能有多个渠道)
    df_monthly = df_sorted.groupby('月份').agg({
        '1_8m0首登当月首借24h借款金额': 'sum',
        '1-8t0首借24h借款金额': 'sum'
    }).reset_index()

    # 取最近N个月
    df_recent = df_monthly.head(months)

    # 计算每月比值 (vectorized)
    m0 = df_recent['1_8m0首登当月首借24h借款金额']
    t0 = df_recent['1-8t0首借24h借款金额']
    valid = pd.notna(t0) & pd.notna(m0) & (t0 > 0)
    ratios = (m0[valid] / t0[valid]).tolist()

    # 计算均值
    if len(ratios) == 0:
        return DEFAULT_M0_T0_RATIO, []  # 默认值

    coefficient = np.mean(ratios)

    return coefficient, ratios


def calculate_existing_m0_cps(
    df_channel: pd.DataFrame,
    df_customer: pd.DataFrame,
    months: int = EXISTING_M0_CPS_MONTHS
) -> Tuple[float, List[float]]:
    """
    计算存量首登M0 CPS均值（前N个月，返回小数）
    口径：历史每个月总花费 / 历史每个月存量首登M0借款

    Args:
        df_channel: raw_达成情况 DataFrame
        df_customer: raw_客群首借金额 DataFrame
        months: 计算窗口月数 (默认3个月)

    Returns:
        (CPS均值, 历史CPS列表)
    """
    # 按月份排序
    df_channel_sorted = df_channel.sort_values('月份', ascending=False)
    df_customer_sorted = df_customer.sort_values('月份', ascending=False)

    # Guard: 如果客群表为空，直接返回默认值避免 str.contains 崩溃
    if df_customer_sorted.empty:
        return DEFAULT_CPS_RATE, []

    # 获取最近N个月的月份列表
    recent_months = df_channel_sorted['月份'].unique()[:months]

    cps_list = []

    for month in recent_months:
        # 从渠道表获取该月总花费
        month_channel_data = df_channel_sorted[df_channel_sorted['月份'] == month].copy()
        month_channel_data['花费'] = pd.to_numeric(month_channel_data['花费'], errors='coerce').fillna(0)
        total_expense = month_channel_data['花费'].sum()  # 单位: 元

        # 从客群表获取该月存量首登M0交易额
        month_customer_data = df_customer_sorted[
            (df_customer_sorted['月份'] == month) &
            (df_customer_sorted['客群'].str.contains('存量首登M0', na=False))
        ]

        # 首贷金额 (单位: 元)
        existing_m0_transaction = pd.to_numeric(month_customer_data['首贷金额'], errors='coerce').fillna(0).sum()

        # 计算 CPS（小数）= 历史每个月总花费 / 历史每个月存量首登M0借款
        if existing_m0_transaction > 0:
            cps = total_expense / existing_m0_transaction
            cps_list.append(cps)

    # 计算均值
    if len(cps_list) == 0:
        return DEFAULT_CPS_RATE, []  # 默认值: 5%

    cps_avg = np.mean(cps_list)

    return cps_avg, cps_list


def calculate_all_coefficients(
    df_channel: pd.DataFrame,
    df_customer: pd.DataFrame,
    existing_m0_months: int = EXISTING_M0_CPS_MONTHS
) -> CalculationCoefficients:
    """
    计算所有系数 (便捷函数)

    Args:
        df_channel: raw_达成情况 DataFrame
        df_customer: raw_客群首借金额 DataFrame
        existing_m0_months: 存量首登M0 CPS计算月数 (默认3个月，可选6个月)

    Returns:
        CalculationCoefficients 对象
    """
    m0_t0_ratio, m0_t0_history = calculate_m0_t0_coefficient(df_channel)
    existing_cps, existing_cps_history = calculate_existing_m0_cps(
        df_channel, df_customer, months=existing_m0_months
    )

    # 提取来源月份标签（用于可解释性展示）
    df_sorted = df_channel.sort_values('月份', ascending=False)
    m0_source_months = [str(m) for m in df_sorted['月份'].unique()[:M0_T0_COEFFICIENT_MONTHS]]
    existing_source_months = [str(m) for m in df_sorted['月份'].unique()[:existing_m0_months]]

    return CalculationCoefficients(
        m0_t0_ratio=m0_t0_ratio,
        existing_m0_cps_avg=existing_cps,
        m0_t0_ratio_history=m0_t0_history,
        existing_m0_cps_history=existing_cps_history,
        m0_t0_source_months=m0_source_months,
        existing_m0_source_months=existing_source_months,
    )
