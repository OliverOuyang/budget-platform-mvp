"""
渠道维度预算计算模块
负责计算渠道维度预算表(Table 1)的所有衍生指标
"""

from typing import Dict, List
import warnings
import pandas as pd
from core.models import (
    BudgetParameters,
    ChannelData,
    Table1Result
)
from app.config import CHANNEL_NAMES, TRANSACTION_UNIT_DIVISOR


def calculate_table1(
    params: BudgetParameters,
    budget_shares: Dict[str, float],
    m0_t0_coefficient: float,
    historical_data: pd.DataFrame
) -> Table1Result:
    """
    计算渠道维度预算表(Table 1)

    Args:
        params: 预算参数对象,包含总花费和各渠道固定参数
        budget_shares: 各渠道预算占比 {渠道名称: 占比}
        m0_t0_coefficient: M0/T0 交易比值系数 (前6月均值)
        historical_data: 历史数据DataFrame (raw_达成情况),用于免费渠道外推

    Returns:
        Table1Result: 包含所有渠道数据和汇总指标的结果对象

    Logic:
        1. 根据 budget_shares 分配总花费到各渠道
        2. 对每个渠道计算衍生指标:
           - T0交易额 = 花费 / CPS / 10000 (亿元)
           - T0申完量 = 花费 / 申完成本
           - 花费结构 = 该渠道花费 / 总花费 (%)
           - 当月首登M0交易额 = T0交易额 × m0_t0_coefficient
           - 1-3 T0授信量 = 申完量 × 1-3过件率
           - 1-8 T0授信量 = 申完量 × 1-8过件率
           - 1-7 T0授信量 = 申完量 × 1-7过件率
           - 申完结构 = 该渠道申完量 / 总申完量 (%)
        3. 特殊处理免费渠道: CPS=0, 使用历史外推计算T0交易额
        4. 计算汇总指标: 总花费、总T0交易额、总M0交易额、总申完量

    Edge Cases:
        - 除零保护: CPS=0或申完成本=0时返回0
        - 缺失参数: 未在params中找到的渠道参数默认为0
        - 免费渠道: 特殊处理,使用历史数据外推
    """
    # 分配花费到各渠道
    channel_expenses = _allocate_budget_to_channels(
        params.total_budget,
        budget_shares
    )

    # 计算各渠道指标
    channels: List[ChannelData] = []

    for channel_name in CHANNEL_NAMES:
        expense = channel_expenses.get(channel_name, 0.0)

        channel_data = _calculate_channel_metrics(
            channel_name=channel_name,
            expense=expense,
            params=params,
            m0_t0_coefficient=m0_t0_coefficient,
            historical_data=historical_data
        )

        channels.append(channel_data)

    # 计算总申完量 (用于申完结构计算)
    total_completion_volume = sum(ch.t0_completion_volume for ch in channels)

    # 计算申完结构和花费结构
    total_expense = params.total_budget

    for ch in channels:
        # 花费结构 (%)
        if total_expense > 0:
            ch.expense_structure = (ch.expense / total_expense) * 100
        else:
            ch.expense_structure = 0.0

        # 申完结构 (%)
        if total_completion_volume > 0:
            ch.completion_structure = (ch.t0_completion_volume / total_completion_volume) * 100
        else:
            ch.completion_structure = 0.0

    # 计算汇总指标
    total_t0_transaction = sum(ch.t0_transaction for ch in channels)
    total_m0_transaction = sum(ch.m0_transaction for ch in channels)

    # ==================== 计算总计行 (加权平均) ====================
    # 1-3过件率总计 = sum(各渠道过件率 × 各渠道申完数) / sum(申完数)
    weighted_approval_sum = 0.0
    total_completion_for_avg = 0.0

    for ch in channels:
        if ch.t0_completion_volume > 0:
            weighted_approval_sum += ch.approval_rate_1_3 * ch.t0_completion_volume
            total_completion_for_avg += ch.t0_completion_volume

    if total_completion_for_avg > 0:
        total_approval_rate_1_3 = weighted_approval_sum / total_completion_for_avg
    else:
        total_approval_rate_1_3 = 0.0

    # CPS总计（小数） = sum(花费) / sum(交易额) / 10000
    if total_t0_transaction > 0:
        total_cps_1_8 = total_expense / total_t0_transaction / 10000
    else:
        total_cps_1_8 = 0.0

    # T0申完成本总计 (加权平均)
    weighted_cost_sum = 0.0
    total_completion_for_cost = 0.0

    for ch in channels:
        if ch.t0_completion_volume > 0:
            weighted_cost_sum += ch.t0_completion_cost * ch.t0_completion_volume
            total_completion_for_cost += ch.t0_completion_volume

    if total_completion_for_cost > 0:
        total_t0_cost = weighted_cost_sum / total_completion_for_cost
    else:
        total_t0_cost = 0.0

    # 创建总计行 ChannelData 对象
    total_channel = ChannelData(
        channel_name="总计",
        approval_rate_1_3=total_approval_rate_1_3,
        cps_1_8=total_cps_1_8,
        t0_completion_cost=total_t0_cost,
        expense=total_expense,
        t0_transaction=total_t0_transaction,
        t0_completion_volume=total_completion_volume,
        expense_structure=100.0,  # 总计占比100%
        m0_transaction=total_m0_transaction,
        credit_volume_1_3=sum(ch.credit_volume_1_3 for ch in channels),
        completion_structure=100.0,  # 总计占比100%
        historical_loan_amount_1_8=total_t0_transaction,
        non_age_reject_completion=total_completion_volume
    )

    # 将总计行添加到channels列表末尾
    channels.append(total_channel)

    return Table1Result(
        channels=channels,
        total_expense=total_expense,
        total_t0_transaction=total_t0_transaction,
        total_m0_transaction=total_m0_transaction,
        total_completion_volume=total_completion_volume
    )


def _allocate_budget_to_channels(
    total_budget: float,
    budget_shares: Dict[str, float]
) -> Dict[str, float]:
    """
    将总预算按占比分配到各渠道

    Args:
        total_budget: 总花费 (万元)
        budget_shares: 各渠道占比 {渠道名称: 占比}

    Returns:
        Dict[str, float]: {渠道名称: 分配花费(万元)}

    Note:
        - 占比总和应为1.0
        - 如果某渠道不在budget_shares中,其花费为0
    """
    channel_expenses = {}

    for channel_name in CHANNEL_NAMES:
        share = budget_shares.get(channel_name, 0.0)
        channel_expenses[channel_name] = total_budget * share

    return channel_expenses


def _calculate_channel_metrics(
    channel_name: str,
    expense: float,
    params: BudgetParameters,
    m0_t0_coefficient: float,
    historical_data: pd.DataFrame
) -> ChannelData:
    """
    计算单个渠道的所有衍生指标

    Args:
        channel_name: 渠道名称
        expense: 该渠道分配的花费 (万元)
        params: 预算参数对象
        m0_t0_coefficient: M0/T0 交易比值系数
        historical_data: 历史数据 (用于免费渠道外推)

    Returns:
        ChannelData: 包含所有计算指标的渠道数据对象

    Note:
        - 免费渠道特殊处理: CPS=0, 使用历史外推
        - 所有除法操作都有除零保护
    """
    # 提取渠道固定参数
    approval_rate_1_3 = params.channel_1_3_approval_rate.get(channel_name, 0.0)
    cps_1_8 = params.channel_1_8_cps.get(channel_name, 0.0)
    t0_completion_cost = params.channel_t0_completion_cost.get(channel_name, 0.0)

    # 计算 T0申完量
    # T0申完量 = 花费(万元) × 10000 / T0申完成本(元/笔)
    if t0_completion_cost > 0:
        t0_completion_volume = expense * 10000 / t0_completion_cost
    else:
        t0_completion_volume = 0.0

    # 计算 T0交易额（亿元）
    # 特殊处理免费渠道
    if channel_name == "免费渠道":
        # 使用历史数据外推 T0交易额
        t0_transaction = _extrapolate_free_channel_transaction(
            historical_data,
            expense,
            t0_completion_volume
        )
    else:
        # T0交易额(亿元) = 花费(万元) / CPS(小数) / 10000
        if cps_1_8 > 0:
            t0_transaction = expense / cps_1_8 / 10000
        else:
            t0_transaction = 0.0

    # 计算 当月首登M0交易额
    # 当月首登M0交易额 = T0交易额 × m0_t0_coefficient
    m0_transaction = t0_transaction * m0_t0_coefficient

    # 计算授信量
    # 1-3 T0授信量 = 申完量 × 1-3过件率
    credit_volume_1_3 = t0_completion_volume * approval_rate_1_3

    # 计算历史数据字段（1-8首借24h借款金额 和 非年龄拒绝申完量）
    # 1-8首借24h借款金额(亿元) = 花费(万元) / CPS(小数) / 10000
    if cps_1_8 > 0:
        historical_loan_amount_1_8 = expense / cps_1_8 / 10000
    else:
        historical_loan_amount_1_8 = 0.0

    # 非年龄拒绝申完量 = 花费 / T0申完成本
    non_age_reject_completion = t0_completion_volume

    # 创建 ChannelData 对象
    return ChannelData(
        channel_name=channel_name,
        approval_rate_1_3=approval_rate_1_3,
        cps_1_8=cps_1_8,
        t0_completion_cost=t0_completion_cost,
        expense=expense,
        t0_transaction=t0_transaction,
        t0_completion_volume=t0_completion_volume,
        expense_structure=0.0,  # 稍后在主函数中计算
        m0_transaction=m0_transaction,
        credit_volume_1_3=credit_volume_1_3,
        completion_structure=0.0,  # 稍后在主函数中计算
        historical_loan_amount_1_8=historical_loan_amount_1_8,
        non_age_reject_completion=non_age_reject_completion
    )


def _extrapolate_free_channel_transaction(
    historical_data: pd.DataFrame,
    expense: float,
    completion_volume: float
) -> float:
    """
    免费渠道 T0交易额外推逻辑

    Args:
        historical_data: 历史数据DataFrame (raw_达成情况)
        expense: 免费渠道花费 (万元)
        completion_volume: T0申完量

    Returns:
        float: 外推的 T0交易额 (亿元)

    Logic:
        1. 从历史数据中提取免费渠道的平均 "T0交易额/申完量" 比率
        2. 使用该比率乘以当前申完量得到 T0交易额
        3. 如果历史数据不足,返回0

    Note:
        - 这是简化的外推逻辑,实际可能需要更复杂的时间序列模型
        - 可以后续替换为 Prophet 或其他预测模型
    """
    # 处理空数据或缺失列
    if historical_data.empty:
        return 0.0

    required_cols = ['渠道类别', '1-8t0首借24h借款金额', '非年龄拒绝t0申完量']
    if not all(col in historical_data.columns for col in required_cols):
        return 0.0

    # 筛选免费渠道历史数据
    df_free = historical_data[
        historical_data['渠道类别'] == '免费渠道'
    ].copy()

    if df_free.empty:
        return 0.0

    # 提取有效的交易额和申完量
    df_free = df_free.dropna(subset=['1-8t0首借24h借款金额', '非年龄拒绝t0申完量'])

    # 过滤掉申完量为0的记录
    df_free = df_free[df_free['非年龄拒绝t0申完量'] > 0]

    if df_free.empty:
        return 0.0

    # 计算平均 "交易额/申完量" 比率
    # 注意: 1-8t0首借24h借款金额 单位已经是亿元
    df_free['1-8t0首借24h借款金额'] = pd.to_numeric(df_free['1-8t0首借24h借款金额'], errors='coerce').fillna(0)
    df_free['非年龄拒绝t0申完量'] = pd.to_numeric(df_free['非年龄拒绝t0申完量'], errors='coerce').fillna(0)
    df_free = df_free[df_free['非年龄拒绝t0申完量'] > 0]  # filter before ratio
    df_free['ratio'] = df_free['1-8t0首借24h借款金额'] / df_free['非年龄拒绝t0申完量']

    avg_ratio = df_free['ratio'].mean()

    # 外推: T0交易额 = 申完量 × 平均比率
    if completion_volume > 0 and avg_ratio > 0:
        t0_transaction = completion_volume * avg_ratio
    else:
        t0_transaction = 0.0

    return t0_transaction


def calculate_budget_shares(df: pd.DataFrame) -> Dict[str, float]:
    """
    计算各渠道的预算占比(基于最新月份花费)

    Args:
        df: raw_达成情况 DataFrame

    Returns:
        Dict[str, float]: {渠道类别: 占比}
        示例: {'腾讯': 0.45, '抖音': 0.30, ...}

    Note:
        - 占比总和为1.0
        - 如果某渠道花费为0或缺失,占比为0
        - 处理除零情况:如果总花费为0,返回空字典
    """
    if df.empty or '月份' not in df.columns or '花费' not in df.columns:
        return {}

    df_clean = df.dropna(subset=['月份'])
    if df_clean.empty:
        return {}

    latest_month = df_clean['月份'].max()
    df_latest = df_clean[df_clean['月份'] == latest_month].copy()

    channel_expenses = {}
    for _, row in df_latest.iterrows():
        channel = row.get('渠道类别')
        expense = row.get('花费', 0)

        if pd.isna(channel) or channel not in CHANNEL_NAMES:
            continue

        try:
            if isinstance(expense, str):
                expense_value = float(expense.replace("万","").strip()) if expense and not pd.isna(expense) else 0.0
            else:
                expense_value = float(expense) if not pd.isna(expense) else 0.0
            channel_expenses[channel] = max(0.0, expense_value)
        except (ValueError, TypeError):
            channel_expenses[channel] = 0.0

    total_expense = sum(channel_expenses.values())
    if total_expense == 0:
        warnings.warn("最近月份渠道总花费为零，预算分配将返回空字典", RuntimeWarning)
        return {}

    budget_shares = {
        channel: expense / total_expense
        for channel, expense in channel_expenses.items()
    }
    return budget_shares
