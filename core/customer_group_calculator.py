"""
客群维度汇总表计算模块 (Table 2)
负责计算初审授信户、非初审授信户、总业务交易额等指标

业务逻辑（对应截图第二张表）：
  整体首借交易额
    1) 初审授信户首借交易额
       ① 初审M0交易额
          a) 当月首登初审M0交易额   = Table1.总M0交易额
          首登T0交易额              = Table1.总T0交易额  （含在初审总计中）
       ② 存量首登初审M0交易额      = 存量首登花费 / 存量首登M0_CPS
    2) 非初审授信户首借交易额       = 手动输入

  初审授信户首借交易额 = 当月首登M0 + 首登T0 + 存量首登M0
  整体首借交易额 = 初审授信户首借交易额 + 非初审授信户首借交易额
  全业务CPS = (投放花费 + RTA) / 整体首借交易额
"""

from typing import Dict
import pandas as pd
from core.models import Table1Result, Table2Result, BudgetParameters
from app.config import EXCLUDED_CUSTOMER_GROUPS, TRANSACTION_UNIT_DIVISOR


def extrapolate_by_days(
    current_value: float,
    days_elapsed: int,
    month_total_days: int
) -> float:
    """
    按天数外推当月预估值

    Args:
        current_value: 已完成天数的累计值
        days_elapsed: 已完成天数
        month_total_days: 当月总天数

    Returns:
        float: 外推后的当月预估值
    """
    if days_elapsed == 0:
        return 0.0
    if days_elapsed >= month_total_days:
        return current_value
    return current_value * (month_total_days / days_elapsed)


def calculate_table2(
    table1_result: Table1Result,
    params: BudgetParameters,
    existing_m0_cps: float,
    customer_data: pd.DataFrame,
    days_params: Dict,
) -> Table2Result:
    """
    计算第二张表：客群维度汇总表

    业务逻辑：
        a) 当月首登初审M0交易额 = Table1.总M0交易额
           首登T0交易额         = Table1.总T0交易额
        b) 存量首登初审M0交易额 = 存量首登花费(万元) / CPS / 10000

        1) 初审授信户首借交易额 = a_M0 + T0 + b_M0
        2) 非初审授信户首借交易额 = params.non_initial_credit_transaction

        整体首借交易额 = 1) + 2)
        投放花费(万元) = Table1.总花费 + 存量首登花费
        全业务CPS = (投放花费 + RTA) / 整体首借交易额 / 10000
    """
    # ==================== 1. 提取 Table1 汇总数据 ====================
    current_month_initial_m0 = table1_result.total_m0_transaction   # a) M0
    first_login_t0 = table1_result.total_t0_transaction              # a) T0

    # ==================== 2. 根据手动输入花费计算存量首登M0交易额 ====================
    if params.existing_m0_expense > 0 and existing_m0_cps > 0:
        calculated_existing_m0_expense = params.existing_m0_expense
        existing_initial_m0 = params.existing_m0_expense / existing_m0_cps / 10000
    else:
        calculated_existing_m0_expense = 0.0
        existing_initial_m0 = 0.0

    # ==================== 3. 初审授信户首借交易额（含T0）====================
    # 业务定义：当月首登M0 + 首登T0 + 存量首登M0
    initial_credit_total = current_month_initial_m0 + first_login_t0 + existing_initial_m0

    # ==================== 4. 非初审授信户首借交易额 ====================
    non_initial_credit = params.non_initial_credit_transaction

    # ==================== 5. 整体首借交易额 ====================
    total_transaction = initial_credit_total + non_initial_credit

    # ==================== 6. 投放花费（不含RTA，用于CPS分母）====================
    # 投放花费 = 渠道花费 + 存量首登花费
    total_expense = table1_result.total_expense + calculated_existing_m0_expense

    # ==================== 7. 全业务CPS ====================
    if total_transaction > 0:
        total_cps = (total_expense + params.rta_promotion_fee) / total_transaction / 10000
    else:
        total_cps = 0.0

    # ==================== 8. 1-3组T0过件率(排年龄，加权平均) ====================
    total_completion = 0.0
    weighted_approval_rate = 0.0

    for channel in table1_result.channels:
        if channel.channel_name == "总计":
            continue
        completion_volume = channel.t0_completion_volume
        approval_rate = channel.approval_rate_1_3
        if completion_volume > 0 and not pd.isna(approval_rate):
            total_completion += completion_volume
            weighted_approval_rate += approval_rate * completion_volume

    if total_completion > 0:
        approval_rate_1_3_excl_age = weighted_approval_rate / total_completion
    else:
        approval_rate_1_3_excl_age = 0.0

    # ==================== 9. 构建返回结果 ====================
    result = Table2Result(
        initial_credit_total=initial_credit_total,
        current_month_initial_m0=current_month_initial_m0,
        first_login_t0=first_login_t0,
        existing_initial_m0=existing_initial_m0,
        non_initial_credit=non_initial_credit,
        total_transaction=total_transaction,
        total_expense=total_expense,
        rta_promotion_fee=params.rta_promotion_fee,
        total_cps=total_cps,
        approval_rate_1_3_excl_age=approval_rate_1_3_excl_age,
        calculated_existing_m0_expense=calculated_existing_m0_expense,
    )

    return result


