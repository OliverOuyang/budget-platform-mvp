from __future__ import annotations

import pandas as pd
from app.styles import highlight_total_row
from core.calculation_pipeline import execute_calculation_pipeline


def _build_target_preview_table(
    *,
    df_raw1: pd.DataFrame,
    df_raw2: pd.DataFrame,
    total_budget: float,
    channel_budget_shares: dict[str, float],
    channel_1_3_rate: dict[str, float],
    channel_1_8_cps: dict[str, float],
    channel_t0_cost: dict[str, float],
    non_initial_credit: float,
    rta_promotion_fee: float,
    month_total_days: int,
    days_elapsed: int,
    m0_calc_period: int,
    last_month_data: dict[str, dict],
) -> pd.DataFrame:
    try:
        _, _, table1, _ = execute_calculation_pipeline(
            df_raw1=df_raw1,
            df_raw2=df_raw2,
            total_budget=total_budget,
            channel_budget_shares=channel_budget_shares,
            channel_1_3_rate=channel_1_3_rate,
            channel_1_8_cps=channel_1_8_cps,
            channel_t0_cost=channel_t0_cost,
            non_initial_credit=non_initial_credit,
            existing_m0_expense=0.0,
            rta_promotion_fee=rta_promotion_fee,
            month_total_days=month_total_days,
            days_elapsed=days_elapsed,
            m0_calc_period=m0_calc_period,
        )
    except Exception:
        return pd.DataFrame()

    rows = []
    weighted_1_8_approval = 0.0
    total_completion = 0.0
    for ch in table1.channels:
        if ch.channel_name == "总计":
            continue
        approval_1_8 = float(last_month_data.get(ch.channel_name, {}).get("1-8t0过件率") or 0.0)
        weighted_1_8_approval += approval_1_8 * ch.t0_completion_volume
        total_completion += ch.t0_completion_volume
        rows.append(
            {
                "渠道": ch.channel_name,
                "花费结构": ch.expense_structure,
                "1-3T0过件率": ch.approval_rate_1_3,
                "1-8T0CPS": ch.cps_1_8,
                "花费": ch.expense,
                "1-8组T0交易额": ch.t0_transaction,
                "1-8T0过件率": approval_1_8,
                "T0申完成本": ch.t0_completion_cost,
                "T0申完量": ch.t0_completion_volume,
            }
        )

    total_row = next((ch for ch in table1.channels if ch.channel_name == "总计"), None)
    if total_row:
        rows.insert(
            0,
            {
                "渠道": "总计",
                "花费结构": 100.0,
                "1-3T0过件率": total_row.approval_rate_1_3,
                "1-8T0CPS": total_row.cps_1_8,
                "花费": total_row.expense,
                "1-8组T0交易额": total_row.t0_transaction,
                "1-8T0过件率": (weighted_1_8_approval / total_completion) if total_completion > 0 else 0.0,
                "T0申完成本": total_row.t0_completion_cost,
                "T0申完量": total_row.t0_completion_volume,
            },
        )

    return pd.DataFrame(rows)


def _style_target_preview_table(df: pd.DataFrame):
    if df.empty:
        return df

    return (
        df.style
        .format(
            {
                "花费结构": "{:.1f}%",
                "1-3T0过件率": "{:.1%}",
                "1-8T0CPS": "{:.1%}",
                "花费": "{:,.1f}万",
                "1-8组T0交易额": "{:,.2f}亿",
                "1-8T0过件率": "{:.1%}",
                "T0申完成本": "{:,.0f}元",
                "T0申完量": "{:,.0f}",
            }
        )
        .set_properties(subset=["渠道"], **{"font-weight": "600"})
        .set_properties(subset=["花费结构", "花费"], **{"background-color": "#eff6ff"})
        .set_properties(subset=["1-3T0过件率", "1-8T0过件率"], **{"background-color": "#f0fdf4"})
        .set_properties(subset=["1-8T0CPS", "T0申完成本"], **{"background-color": "#fff7ed"})
        .set_properties(subset=["1-8组T0交易额", "T0申完量"], **{"background-color": "#faf5ff"})
        .apply(highlight_total_row, axis=1)
    )


def _style_latest_reference_table(df: pd.DataFrame):
    if df.empty:
        return df
    return (
        df.style
        .format(
            {
                "历史过件率(%)": "{:.2f}%",
                "历史CPS(%)": "{:.2f}%",
                "历史申完成本(元)": "{:,.0f}",
                "历史花费结构(%)": "{:.2f}%",
            }
        )
        .set_properties(subset=["渠道"], **{"font-weight": "600"})
        .set_properties(subset=["历史过件率(%)"], **{"background-color": "#f0fdf4"})
        .set_properties(subset=["历史CPS(%)"], **{"background-color": "#fff7ed"})
        .set_properties(subset=["历史申完成本(元)"], **{"background-color": "#eff6ff"})
        .set_properties(subset=["历史花费结构(%)"], **{"background-color": "#faf5ff"})
    )
