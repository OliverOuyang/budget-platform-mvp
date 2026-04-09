from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from app.flow_components import (
    render_flow_header,
    render_guidance_card,
    render_section_header,
    render_step_progress,
)
from pages._tab_channel_result import render_tab_channel_result
from pages._tab_customer_result import render_tab_customer_result
from pages._tab_coefficient_trace import render_tab_coefficient_trace
from pages._tab_scenario_manager import render_tab_scenario_manager
from pages._tab_model_comparison import render_tab_model_comparison
from pages._tab_goal_scenarios import render_tab_goal_scenarios, render_inline_goal_selector
from pages._tab_guardrail import render_tab_guardrail
from pages._tab_whatif import render_tab_whatif
from app.styles import inject_custom_css, render_impact_chain, render_callout
from app.config import CHANNEL_NAMES, DEFAULT_DAYS_ELAPSED, DEFAULT_MONTH_DAYS, DEFAULT_TOTAL_BUDGET
from app.ui_utils import (
    apply_template_to_result_widgets,
    build_channel_parameter_rows,
    ensure_flow_state,
    get_v01_flow,
    normalize_channel_history,
    parse_channel_parameter_rows,
    run_calculation,
    update_v01_flow,
    build_v01_decision_summary,
)
from core.calculation_pipeline import execute_calculation_pipeline
from core.customer_group_calculator import extrapolate_by_days
from core.data_loader import extract_last_month_data
from core.models import BudgetParameters


def _safe_num(val, default=0.0):
    """Return float(val) if val is a finite number, else default."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if pd.isna(f) else f
    except (ValueError, TypeError):
        return default


def _build_latest_share_rows(last_month: dict[str, dict]) -> list[dict]:
    total_expense_raw = sum(_safe_num(item.get("花费")) for item in last_month.values())
    rows = []
    for channel_name, item in last_month.items():
        expense = _safe_num(item.get("花费"))
        rows.append(
            {
                "渠道": channel_name,
                "历史过件率(%)": _safe_num(item.get("1-3t0过件率")) * 100,
                "历史CPS(%)": _safe_num(item.get("1-8t0cps")) * 100,
                "历史申完成本(元)": _safe_num(item.get("t0申完成本")),
                "历史花费结构(%)": (expense / total_expense_raw * 100) if total_expense_raw else 0.0,
            }
        )
    rows.sort(key=lambda item: item["历史过件率(%)"], reverse=True)
    return rows


def _build_history_baseline_rows(df_raw1: pd.DataFrame, days_elapsed: int, month_total_days: int) -> tuple[list[dict], str | None]:
    """Build actuals for prior 3 months plus current-month actual/projected rows."""
    df_n = normalize_channel_history(df_raw1)
    if df_n.empty or "月份标签" not in df_n.columns:
        return [], None

    df_n["花费"] = pd.to_numeric(df_n.get("花费"), errors="coerce").fillna(0)
    df_n["T0交易额元"] = pd.to_numeric(df_n.get("1-8t0首借24h借款金额"), errors="coerce").fillna(0)
    df_n["M0交易额元"] = pd.to_numeric(df_n.get("1_8m0首登当月首借24h借款金额"), errors="coerce").fillna(0)
    completion = pd.to_numeric(df_n.get("非年龄拒绝t0申完量"), errors="coerce")
    if completion.isna().all():
        cost_series = pd.to_numeric(df_n.get("t0申完成本"), errors="coerce").replace(0, pd.NA)
        completion = (df_n["花费"] / cost_series).fillna(0)
    else:
        completion = completion.fillna(0)
    approval_rate = pd.to_numeric(df_n.get("1-3t0过件率"), errors="coerce").fillna(0)
    df_n["申完量"] = completion
    df_n["加权过件分子"] = approval_rate * completion

    monthly = (
        df_n.groupby("月份标签", as_index=False)
        .agg(
            花费元=("花费", "sum"),
            T0交易额元=("T0交易额元", "sum"),
            M0交易额元=("M0交易额元", "sum"),
            申完量=("申完量", "sum"),
            加权过件分子=("加权过件分子", "sum"),
        )
        .sort_values("月份标签")
    )
    if monthly.empty:
        return [], None

    monthly["投放花费(万元)"] = monthly["花费元"] / 10000
    monthly["首借交易额(亿元)"] = (monthly["T0交易额元"] + monthly["M0交易额元"]) / 1e8
    monthly["投放CPS(%)"] = monthly.apply(
        lambda row: (row["投放花费(万元)"] / row["首借交易额(亿元)"] / 10000 * 100) if row["首借交易额(亿元)"] > 0 else 0.0,
        axis=1,
    )
    monthly["1-3过件率(%)"] = monthly.apply(
        lambda row: (row["加权过件分子"] / row["申完量"] * 100) if row["申完量"] > 0 else 0.0,
        axis=1,
    )

    latest = monthly.iloc[-1]
    rows = [
        {
            "阶段": "历史实际",
            "月份": row["月份标签"],
            "投放花费(万元)": row["投放花费(万元)"],
            "首借交易额(亿元)": row["首借交易额(亿元)"],
            "投放CPS(%)": row["投放CPS(%)"],
            "1-3过件率(%)": row["1-3过件率(%)"],
        }
        for _, row in monthly.iloc[-4:-1].iterrows()
    ]
    rows.append(
        {
            "阶段": "当月截至当前",
            "月份": latest["月份标签"],
            "投放花费(万元)": latest["投放花费(万元)"],
            "首借交易额(亿元)": latest["首借交易额(亿元)"],
            "投放CPS(%)": latest["投放CPS(%)"],
            "1-3过件率(%)": latest["1-3过件率(%)"],
        }
    )
    rows.append(
        {
            "阶段": "当月整月预估",
            "月份": latest["月份标签"],
            "投放花费(万元)": extrapolate_by_days(float(latest["投放花费(万元)"]), days_elapsed, month_total_days),
            "首借交易额(亿元)": extrapolate_by_days(float(latest["首借交易额(亿元)"]), days_elapsed, month_total_days),
            "投放CPS(%)": latest["投放CPS(%)"],
            "1-3过件率(%)": latest["1-3过件率(%)"],
        }
    )
    return rows, str(latest["月份标签"])


def _compute_weighted_approval(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    if "非年龄拒绝t0申完量" in df.columns:
        completion = pd.to_numeric(df["非年龄拒绝t0申完量"], errors="coerce").fillna(0)
    else:
        cost = pd.to_numeric(df.get("t0申完成本", 0), errors="coerce").replace(0, pd.NA)
        expense = pd.to_numeric(df.get("花费", 0), errors="coerce").fillna(0)
        completion = (expense / cost).fillna(0)
    rates = pd.to_numeric(df.get("1-3t0过件率", 0), errors="coerce").fillna(0)
    total_completion = float(completion.sum())
    if total_completion <= 0:
        return 0.0
    return float((rates * completion).sum() / total_completion)


def _build_baseline_panel_data(
    df_raw1: pd.DataFrame,
    *,
    month_total_days: int,
    days_elapsed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    normalized = normalize_channel_history(df_raw1)
    if normalized.empty or "月份标签" not in normalized.columns:
        return pd.DataFrame(), pd.DataFrame()

    normalized["花费"] = pd.to_numeric(normalized.get("花费", 0), errors="coerce").fillna(0)
    normalized["1-8t0首借24h借款金额"] = pd.to_numeric(normalized.get("1-8t0首借24h借款金额", 0), errors="coerce").fillna(0)
    normalized["1_8m0首登当月首借24h借款金额"] = pd.to_numeric(
        normalized.get("1_8m0首登当月首借24h借款金额", 0), errors="coerce"
    ).fillna(0)

    months = [m for m in sorted(normalized["月份标签"].dropna().unique().tolist()) if m != "-"]
    if not months:
        return pd.DataFrame(), pd.DataFrame()

    latest_month = months[-1]
    previous_months = months[-4:-1]
    rows: list[dict] = []

    def build_row(label: str, month_df: pd.DataFrame, *, extrapolate: bool = False) -> dict:
        factor = (month_total_days / days_elapsed) if extrapolate and 0 < days_elapsed < month_total_days else 1.0
        expense_wan = float(month_df["花费"].sum()) / 10000 * factor
        transaction_yi = float(
            (month_df["1-8t0首借24h借款金额"] + month_df["1_8m0首登当月首借24h借款金额"]).sum()
        ) / 100000000 * factor
        approval = _compute_weighted_approval(month_df)
        cps = (expense_wan / transaction_yi / 10000) if transaction_yi > 0 else 0.0
        return {
            "阶段": label,
            "投放花费(万元)": expense_wan,
            "首借交易额(亿元)": transaction_yi,
            "投放CPS": cps,
            "1-3组T0过件率": approval,
        }

    for month in previous_months:
        month_df = normalized[normalized["月份标签"] == month].copy()
        rows.append(build_row(f"{month} 实际", month_df))

    latest_df = normalized[normalized["月份标签"] == latest_month].copy()
    rows.append(build_row(f"{latest_month} 截至当前", latest_df))
    rows.append(build_row(f"{latest_month} 整月预估", latest_df, extrapolate=True))

    channel_rows = []
    factor = (month_total_days / days_elapsed) if 0 < days_elapsed < month_total_days else 1.0
    latest_channel = latest_df.groupby("渠道类别", as_index=False).agg(
        {
            "花费": "sum",
            "1-8t0首借24h借款金额": "sum",
        }
    )
    for _, row in latest_channel.iterrows():
        channel_rows.append(
            {
                "渠道": row["渠道类别"],
                "截至当前花费(万元)": float(row["花费"]) / 10000,
                "截至当前T0交易额(亿元)": float(row["1-8t0首借24h借款金额"]) / 100000000,
                "整月预估花费(万元)": float(row["花费"]) / 10000 * factor,
                "整月预估T0交易额(亿元)": float(row["1-8t0首借24h借款金额"]) / 100000000 * factor,
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(channel_rows)


def _build_historical_channel_detail(df_raw1: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Build per-month channel core metrics tables for historical reference."""
    df_n = normalize_channel_history(df_raw1)
    if df_n.empty or "月份标签" not in df_n.columns:
        return []

    df_n["花费"] = pd.to_numeric(df_n.get("花费", 0), errors="coerce").fillna(0)
    df_n["1-8t0首借24h借款金额"] = pd.to_numeric(
        df_n.get("1-8t0首借24h借款金额", 0), errors="coerce"
    ).fillna(0)
    df_n["1-8t0过件率"] = pd.to_numeric(df_n.get("1-8t0过件率", 0), errors="coerce").fillna(0)
    df_n["t0申完成本"] = pd.to_numeric(df_n.get("t0申完成本", 0), errors="coerce").fillna(0)
    if "非年龄拒绝t0申完量" in df_n.columns:
        df_n["申完量"] = pd.to_numeric(df_n["非年龄拒绝t0申完量"], errors="coerce").fillna(0)
    else:
        cost = df_n["t0申完成本"].replace(0, pd.NA)
        df_n["申完量"] = (df_n["花费"] / cost).fillna(0)

    months = sorted(m for m in df_n["月份标签"].dropna().unique() if m != "-")
    if len(months) < 2:
        return []

    # Include up to 3 prior months + latest (possibly partial)
    history_months = months[-4:]

    result: list[tuple[str, pd.DataFrame]] = []
    for month in history_months:
        month_df = df_n[df_n["月份标签"] == month].copy()
        if month_df.empty:
            continue

        total_expense = month_df["花费"].sum()
        rows = []
        for _, row in month_df.iterrows():
            channel = row.get("渠道类别", row.get("渠道名称", ""))
            expense = float(row["花费"])
            rows.append({
                "渠道": channel,
                "花费": expense / 10000,
                "1-8组T0交易额": float(row["1-8t0首借24h借款金额"]) / 1e8,
                "1-8T0过件率": float(row["1-8t0过件率"]),
                "T0申完成本": float(row["t0申完成本"]),
                "T0申完量": float(row["申完量"]),
                "花费结构": (expense / total_expense * 100) if total_expense > 0 else 0.0,
            })

        total_t0 = month_df["1-8t0首借24h借款金额"].sum()
        total_completion = month_df["申完量"].sum()
        weighted_approval = (
            (month_df["1-8t0过件率"] * month_df["申完量"]).sum() / total_completion
            if total_completion > 0 else 0.0
        )
        avg_cost = total_expense / total_completion if total_completion > 0 else 0.0
        rows.insert(0, {
            "渠道": "总计",
            "花费": total_expense / 10000,
            "1-8组T0交易额": total_t0 / 1e8,
            "1-8T0过件率": weighted_approval,
            "T0申完成本": avg_cost,
            "T0申完量": total_completion,
            "花费结构": 100.0,
        })

        month_num = pd.to_datetime(month + "-01").month
        label = f"{month_num}月首登T0指标"
        if month == months[-1]:
            label += "（截至当前）"
        result.append((label, pd.DataFrame(rows)))

    return result


def _style_historical_channel_detail(df: pd.DataFrame):
    """Style per-month channel detail table with color-coded columns."""
    if df.empty:
        return df

    def highlight_total(row):
        if row.get("渠道") == "总计":
            return ["background-color: #eef2ff; font-weight: 700;" for _ in row]
        return ["" for _ in row]

    return (
        df.style
        .format({
            "花费": "{:,.1f}万",
            "1-8组T0交易额": "{:.2f}亿",
            "1-8T0过件率": "{:.1%}",
            "T0申完成本": "{:,.0f}",
            "T0申完量": "{:,.0f}",
            "花费结构": "{:.1f}%",
        })
        .set_properties(subset=["渠道"], **{"font-weight": "600"})
        .set_properties(subset=["花费", "花费结构"], **{"background-color": "#eff6ff"})
        .set_properties(subset=["1-8组T0交易额", "T0申完量"], **{"background-color": "#faf5ff"})
        .set_properties(subset=["1-8T0过件率"], **{"background-color": "#f0fdf4"})
        .set_properties(subset=["T0申完成本"], **{"background-color": "#fff7ed"})
        .apply(highlight_total, axis=1)
    )


def _render_historical_baseline_panel(
    df_raw1: pd.DataFrame,
    *,
    month_total_days: int,
    days_elapsed: int,
) -> None:
    monthly_df, channel_df = _build_baseline_panel_data(
        df_raw1,
        month_total_days=month_total_days,
        days_elapsed=days_elapsed,
    )
    with st.container(border=True):
        render_section_header(
            "历史与当月预估",
            "先看近 3 个月实际、当月截至当前和按天数外推的整月预估，再进入参数配置。",
        )
        st.caption(f"当前按 {int(days_elapsed)} / {int(month_total_days)} 天进行月内外推；“截至当前”是原始累计值，“整月预估”按比例放大。")
        if not monthly_df.empty:
            st.dataframe(
                monthly_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "投放花费(万元)": st.column_config.NumberColumn(format="%.1f"),
                    "首借交易额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                    "投放CPS": st.column_config.NumberColumn(format="%.2f%%"),
                    "1-3组T0过件率": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )
        else:
            st.info("历史月份不足，暂时无法生成趋势基线面板。")

        if not channel_df.empty:
            st.caption("最新月份渠道拆解：帮助你先判断当前月结构，再决定是否调整下方参数。")
            st.dataframe(
                channel_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "截至当前花费(万元)": st.column_config.NumberColumn(format="%.1f"),
                    "截至当前T0交易额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                    "整月预估花费(万元)": st.column_config.NumberColumn(format="%.1f"),
                    "整月预估T0交易额(亿元)": st.column_config.NumberColumn(format="%.2f"),
                },
            )


def _build_historical_result_table(
    df_raw1: pd.DataFrame,
    df_raw2: pd.DataFrame,
    *,
    month_total_days: int,
    days_elapsed: int,
    rta_estimate: float,
) -> pd.DataFrame:
    df_channel = normalize_channel_history(df_raw1)
    df_customer = df_raw2.copy().replace("\\N", pd.NA)
    if df_channel.empty or df_customer.empty:
        return pd.DataFrame()

    df_customer["月份"] = pd.to_datetime(df_customer["月份"], errors="coerce")
    df_customer["月份标签"] = df_customer["月份"].dt.strftime("%Y-%m")
    df_customer["首贷金额"] = pd.to_numeric(df_customer["首贷金额"], errors="coerce").fillna(0)
    available_months = sorted(set(df_channel["月份标签"].dropna()) & set(df_customer["月份标签"].dropna()))
    if not available_months:
        return pd.DataFrame()

    latest_month = available_months[-1]
    actual_months = available_months[:-1][-2:]
    latest_month_num = pd.to_datetime(latest_month + "-01").month
    column_specs = [(m, f"{pd.to_datetime(m + '-01').month}月达成", False) for m in actual_months]
    column_specs.append((latest_month, f"{latest_month_num}月至今达成", False))
    column_specs.append((latest_month, f"{latest_month_num}月预估", True))

    def fmt_wan(v): return "—" if v is None or pd.isna(v) else f"{v:,.1f}万"
    def fmt_yi(v): return "—" if v is None or pd.isna(v) else f"{v:,.2f}亿"
    def fmt_pct(v): return "—" if v is None or pd.isna(v) else f"{v:.1%}"

    row_order = [
        "投放花费",
        "RTA费用+促申完",
        "整体首借交易额",
        "1) 初审授信户首借交易额",
        "①初审M0交易额",
        "a)当月首登初审M0交易额",
        "首登T0交易额",
        "b)存量首登初审M0交易额",
        "②初审M1+交易额",
        "2) 非初审授信户首借交易额",
        "全业务CPS（仅投放费用）",
        "1-3组T0过件率（排年龄）",
        "T0 CPS（仅投放费用）",
    ]

    def collect(month: str, *, extrapolate: bool) -> dict[str, float | None]:
        factor = (month_total_days / days_elapsed) if extrapolate and 0 < days_elapsed < month_total_days else 1.0
        month_channel = df_channel[df_channel["月份标签"] == month].copy()
        month_customer = df_customer[df_customer["月份标签"] == month].copy()
        groups = month_customer.groupby("客群")["首贷金额"].sum() / 1e8

        spend_wan = float(month_channel["花费"].sum()) / 10000 * factor
        first_login_t0_yi = float(pd.to_numeric(month_channel["1-8t0首借24h借款金额"], errors="coerce").fillna(0).sum()) / 1e8 * factor
        current_m0_yi = float(groups.get("当月首登M0", 0.0)) * factor
        existing_m0_yi = float(groups.get("存量首登M0", 0.0)) * factor
        initial_m1_yi = float(groups.get("初审M1+", 0.0)) * factor
        non_initial_yi = float(groups.get("非初审-重申", 0.0) + groups.get("非初审-重审及其他", 0.0)) * factor
        total_yi = float(month_customer["首贷金额"].sum()) / 1e8 * factor

        initial_m0_total = current_m0_yi + existing_m0_yi
        initial_credit_total = initial_m0_total + initial_m1_yi
        full_cps = (spend_wan / total_yi / 10000) if total_yi > 0 else 0.0
        t0_cps = (spend_wan / first_login_t0_yi / 10000) if first_login_t0_yi > 0 else 0.0
        approval = _compute_weighted_approval(month_channel)
        return {
            "投放花费": spend_wan,
            "RTA费用+促申完": rta_estimate if extrapolate else None,
            "整体首借交易额": total_yi,
            "1) 初审授信户首借交易额": initial_credit_total,
            "①初审M0交易额": initial_m0_total,
            "a)当月首登初审M0交易额": current_m0_yi,
            "首登T0交易额": first_login_t0_yi,
            "b)存量首登初审M0交易额": existing_m0_yi,
            "②初审M1+交易额": initial_m1_yi,
            "2) 非初审授信户首借交易额": non_initial_yi,
            "全业务CPS（仅投放费用）": full_cps,
            "1-3组T0过件率（排年龄）": approval,
            "T0 CPS（仅投放费用）": t0_cps,
        }

    month_values = {label: collect(month, extrapolate=is_est) for month, label, is_est in column_specs}
    rows = []
    for metric in row_order:
        row = {"指标": metric}
        for label, values in month_values.items():
            value = values.get(metric)
            if "花费" in metric or metric == "RTA费用+促申完":
                row[label] = fmt_wan(value)
            elif "CPS" in metric or "过件率" in metric:
                row[label] = fmt_pct(value)
            else:
                row[label] = fmt_yi(value)
        rows.append(row)
    return pd.DataFrame(rows)


def _style_historical_result_table(df: pd.DataFrame):
    if df.empty:
        return df

    def row_style(row):
        metric = str(row.get("指标", ""))
        if metric == "整体首借交易额":
            return ["background-color: #eef2ff; font-weight: 700;" for _ in row]
        if metric in {"投放花费", "RTA费用+促申完"}:
            return ["background-color: #eff6ff;" for _ in row]
        if "CPS" in metric:
            return ["background-color: #fff7ed;" for _ in row]
        if "过件率" in metric:
            return ["background-color: #f0fdf4;" for _ in row]
        if "初审" in metric or "非初审" in metric or "交易额" in metric:
            return ["background-color: #faf5ff;" for _ in row]
        return ["" for _ in row]

    return (
        df.style
        .set_properties(subset=["指标"], **{"font-weight": "600"})
        .apply(row_style, axis=1)
    )


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

    def highlight_total(row):
        if row.get("渠道") == "总计":
            return ["background-color: #eef2ff; font-weight: 700;" for _ in row]
        return ["" for _ in row]

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
        .apply(highlight_total, axis=1)
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


def _apply_template_to_result_widgets(params: dict) -> None:
    """Sync loaded template values into result-page widget state."""
    apply_template_to_result_widgets(params)


def _consume_pending_template_params() -> None:
    """Apply pending template values on a fresh rerun before widgets are created."""
    pending_params = st.session_state.pop("pending_result_template_params", None)
    pending_name = st.session_state.pop("pending_result_template_name", None)
    if pending_params:
        _apply_template_to_result_widgets(pending_params)
        if pending_name:
            st.success(f"模板 '{pending_name}' 已加载")


def _clear_active_template_selection() -> None:
    """Clear template-selection state without wiping currently visible parameter values."""
    st.session_state.pop("result_selected_template", None)
    st.session_state.pop("current_template_params", None)


def _render_template_management(
    total_budget: float,
    channel_budget_shares: dict[str, float],
    channel_1_3_rate: dict[str, float],
    channel_1_8_cps: dict[str, float],
    channel_t0_cost: dict[str, float],
    non_initial_credit: float,
    existing_m0_expense: float,
    rta_promotion_fee: float,
    month_total_days: int,
    days_elapsed: int,
    m0_calc_period: int,
) -> None:
    tm = st.session_state.get("template_manager")
    if tm is None:
        return

    templates = tm.list_templates()
    tab_save, tab_load, tab_delete = st.tabs(["保存模板", "加载模板", "删除模板"])

    with tab_save:
        save_name = st.text_input("模板名称", key="result_template_name", placeholder="例如：4月基准方案")
        save_desc = st.text_input("描述", key="result_template_desc", placeholder="例如：按最新月花费结构配置")
        overwrite_key = "result_template_overwrite_confirm"
        if st.session_state.get(overwrite_key):
            st.warning(
                f"模板 '{st.session_state[overwrite_key]}' 已存在。你可以直接覆盖，或改名后另存。"
            )
            overwrite_cols = st.columns(2)
            if overwrite_cols[0].button("覆盖现有模板", key="result_confirm_overwrite", use_container_width=True):
                save_name = st.session_state[overwrite_key]
                st.session_state["result_template_name"] = save_name
            if overwrite_cols[1].button("取消覆盖", key="result_cancel_overwrite", use_container_width=True):
                st.session_state.pop(overwrite_key, None)
                st.rerun()
        if st.button("💾 保存当前参数", key="result_save_template", use_container_width=True):
            if not save_name.strip():
                st.error("请填写模板名称")
            else:
                params = BudgetParameters(
                    total_budget=total_budget,
                    channel_budget_shares=channel_budget_shares,
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
                pending_name = st.session_state.get(overwrite_key)
                if tm.template_exists(save_name.strip()) and pending_name != save_name.strip():
                    st.session_state[overwrite_key] = save_name.strip()
                    st.rerun()
                else:
                    try:
                        tm.save_template(
                            template_name=save_name.strip(),
                            params=params,
                            channel_budget_shares=channel_budget_shares,
                            channel_1_3_rate=channel_1_3_rate,
                            channel_1_8_cps=channel_1_8_cps,
                            channel_t0_cost=channel_t0_cost,
                            non_initial_credit=non_initial_credit,
                            existing_m0_expense=existing_m0_expense,
                            rta_promotion_fee=rta_promotion_fee,
                            description=save_desc.strip(),
                            overwrite=(pending_name == save_name.strip()),
                        )
                        st.session_state.pop(overwrite_key, None)
                        st.success(f"模板 '{save_name}' 已保存")
                        st.rerun()
                    except FileExistsError:
                        st.session_state[overwrite_key] = save_name.strip()
                        st.rerun()

    with tab_load:
        if not templates:
            st.info("暂无已保存模板")
        else:
            template_names = [item["name"] for item in templates]
            selected = st.selectbox("选择模板", template_names, key="result_selected_template")
            if st.button("📂 加载此模板", key="result_load_template", use_container_width=True):
                template_data = tm.load_template(selected)
                if template_data:
                    st.session_state["pending_result_template_params"] = template_data["parameters"]
                    st.session_state["pending_result_template_name"] = selected
                    st.rerun()
                else:
                    st.error(f"加载模板 '{selected}' 失败")

    with tab_delete:
        if not templates:
            st.info("暂无可删除模板")
        else:
            delete_name = st.selectbox("选择要删除的模板", [item["name"] for item in templates], key="result_delete_template_name")
            st.caption("删除后不可恢复。")
            if st.button("🗑️ 删除模板", key="result_delete_template", use_container_width=True):
                if tm.delete_template(delete_name):
                    if st.session_state.get("result_selected_template") == delete_name:
                        _clear_active_template_selection()
                    st.success(f"模板 '{delete_name}' 已删除")
                    st.rerun()
                else:
                    st.error(f"删除模板 '{delete_name}' 失败")


def _render_parameter_panel() -> bool:
    data = st.session_state.get("uploaded_data")
    if not data:
        return False

    _consume_pending_template_params()
    template_params = st.session_state.get("current_template_params", {})
    last_month = extract_last_month_data(data["df_raw1"])
    latest_share_rows = _build_latest_share_rows(last_month)

    st.subheader("🛠️ 参数配置与计算")

    # --- 历史达成 + 预估参数（默认折叠）---
    with st.expander("📊 历史达成与当月预估", expanded=False):
        st.caption("「预估」列使用当前月累计数据按已完成天数外推；历史月份按两张 raw 的可交集月份展示。")
        param_cols = st.columns(3)
        with param_cols[0]:
            month_total_days = st.number_input(
                "当月总天数",
                28,
                31,
                int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
                key="result_month_total_days",
            )
        with param_cols[1]:
            days_elapsed = st.number_input(
                "已完成天数",
                1,
                31,
                int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
                key="result_days_elapsed",
            )
        with param_cols[2]:
            m0_calc_period = st.radio(
                "存量首登M0计算周期",
                [3, 6],
                index=0 if int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))) == 3 else 1,
                horizontal=True,
                key="result_m0_calc_period",
            )
        extra_cols = st.columns(2)
        with extra_cols[0]:
            non_initial_credit = st.number_input(
                "非初审授信户首借交易额 (亿元)",
                0.0,
                value=float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
                format="%.2f",
                key="result_non_initial_credit",
            )
        with extra_cols[1]:
            rta_promotion_fee = st.number_input(
                "RTA费用+促申完 (万元)",
                0.0,
                value=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
                format="%.2f",
                key="result_rta_promotion_fee",
            )
        historical_table = _build_historical_result_table(
            data["df_raw1"],
            data["df_raw2"],
            month_total_days=int(month_total_days),
            days_elapsed=int(days_elapsed),
            rta_estimate=rta_promotion_fee,
        )
        if not historical_table.empty:
            historical_height = min(760, 52 + (len(historical_table) + 1) * 42)
            st.dataframe(
                _style_historical_result_table(historical_table),
                use_container_width=True,
                hide_index=True,
                height=historical_height,
            )
        else:
            st.info("历史月份不足，暂时无法生成达成与预估表。")

        # 各月渠道核心指标明细
        channel_details = _build_historical_channel_detail(data["df_raw1"])
        if channel_details:
            st.markdown("---")
            st.caption("📋 各月渠道核心指标明细（蓝色=预算，绿色=质量，橙色=成本，紫色=产出）")
            detail_tabs = st.tabs([label for label, _ in channel_details])
            for tab, (_, detail_df) in zip(detail_tabs, channel_details):
                with tab:
                    detail_height = min(300, 52 + (len(detail_df) + 1) * 38)
                    st.dataframe(
                        _style_historical_channel_detail(detail_df),
                        use_container_width=True,
                        hide_index=True,
                        height=detail_height,
                    )

    hist_total_budget = sum(_safe_num(item.get("花费")) for item in last_month.values()) / 10000 if last_month else 0
    baseline_approval = (
        sum(_safe_num(item.get("1-3t0过件率")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cps = (
        sum(_safe_num(item.get("1-8t0cps")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cost = (
        sum(_safe_num(item.get("t0申完成本")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )

    # --- 模板管理（默认折叠）---
    with st.expander("💾 模板管理（可选）", expanded=False):
        _render_template_management(
            float(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
            template_params.get("channel_budget_shares", {}),
            template_params.get("channel_1_3_approval_rate", {}),
            template_params.get("channel_1_8_cps", {}),
            template_params.get("channel_t0_completion_cost", {}),
            float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
            0.0,
            float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
            int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
            int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
            int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))),
        )

    # --- 核心预算输入 ---
    with st.container(border=True):
        render_section_header("💰 核心预算输入", "确定总预算规模。")
        budget_cols = st.columns([3, 1])
        with budget_cols[0]:
            total_budget = st.slider(
                "总花费 (万元)",
                500,
                10000,
                int(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
                50,
                key="result_total_budget",
            )
        with budget_cols[1]:
            st.metric("较最新月差异", f"{total_budget - hist_total_budget:+,.0f} 万元")

    # --- Step 3.5: MMM 智能推荐（可选）---
    mmm_model = st.session_state.get("mmm_model")
    mmm_recommendations = {}  # channel_name -> {spend, roi, saturation}

    if mmm_model is not None:
        with st.container(border=True):
            st.markdown(
                '<div style="border-left:4px solid #7B1FA2; padding-left:12px;">'
                '<span style="font-size:15px;font-weight:600;">步骤 3.5 - MMM 智能推荐</span> '
                '<span style="background:#7B1FA2;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;">MMM</span> '
                '<span style="background:#1976D2;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;">可选</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"基于已训练的 MMM 模型，在 {total_budget:,.0f} 万元总预算约束下，按等边际原则计算最优渠道分配。")

            # Model status callout
            trainer = st.session_state.get("mmm_trainer")
            model_info = ""
            if trainer and hasattr(trainer, "best_score"):
                model_info = f"R²={getattr(trainer, 'best_score', 0):.2f}"
            st.info(f"**模型状态：** 已加载 | {model_info} | 训练数据来自 MMM 模型洞察页")

            # Get optimization results from MMM
            recommended_spends = st.session_state.get("mmm_v01_recommended_spends", {})
            if recommended_spends:
                rec_rows = []
                for ch_name in CHANNEL_NAMES:
                    hist_expense = _safe_num(last_month.get(ch_name, {}).get("花费")) / 10000 if last_month.get(ch_name) else 0
                    mmm_spend = recommended_spends.get(ch_name, hist_expense)
                    change_pct = ((mmm_spend - hist_expense) / hist_expense * 100) if hist_expense > 0 else 0
                    roi = st.session_state.get("mmm_v01_channel_roi", {}).get(ch_name, 0)
                    sat = st.session_state.get("mmm_v01_channel_saturation", {}).get(ch_name, 0)

                    if sat > 85:
                        advice = "接近饱和，建议减投"
                    elif sat < 50 and roi > 2:
                        advice = "ROI高，加大投入"
                    elif change_pct > 10:
                        advice = "适度增投"
                    elif change_pct < -10:
                        advice = "建议控量"
                    else:
                        advice = "维持现状"

                    mmm_recommendations[ch_name] = {"spend": mmm_spend, "roi": roi, "saturation": sat}
                    rec_rows.append({
                        "渠道": ch_name,
                        "上月花费(万)": f"{hist_expense:,.0f}",
                        "MMM推荐(万)": f"{mmm_spend:,.0f}",
                        "变化": f"{change_pct:+.1f}%",
                        "ROI": f"{roi:.1f}x" if roi > 0 else "-",
                        "饱和度": f"{sat:.0f}%" if sat > 0 else "-",
                        "操作建议": advice,
                    })

                st.dataframe(pd.DataFrame(rec_rows), use_container_width=True, hide_index=True)

                # 一键采纳 button
                adopt_cols = st.columns([1, 1])
                with adopt_cols[0]:
                    if st.button("🤖 一键采纳 → 填入下方参数矩阵", type="primary", use_container_width=True):
                        for ch_name, rec in mmm_recommendations.items():
                            # Update template params to use MMM recommended spends
                            if total_budget > 0:
                                template_params.setdefault("channel_budget_shares", {})[ch_name] = rec["spend"] / total_budget
                        st.session_state.pop("result_channel_editor", None)
                        st.rerun()
                with adopt_cols[1]:
                    st.button("跳过，手动配置", use_container_width=True)
                st.caption("采纳后仍可在下方参数矩阵中微调。MMM 推荐基于等边际原则优化，不保证与所有业务约束一致。")
            else:
                st.warning("MMM 模型已训练但尚无预算优化结果。请前往 MMM 模型洞察页的「预算优化」Tab 运行优化。")

    # --- 渠道参数矩阵（合并了最新月参考 + MMM参考 + 均值校验）---
    with st.container(border=True):
        render_section_header("📋 渠道参数矩阵", "蓝色=可编辑，紫色=MMM参考，灰色=历史参考。")
        editor_rows = build_channel_parameter_rows(last_month, template_params, total_budget=total_budget, mmm_recommendations=mmm_recommendations)
        editor_height = min(300, 52 + (len(editor_rows) + 1) * 38)

        # Column config with color coding
        col_config = {
            "渠道": st.column_config.TextColumn("渠道", width="medium"),
            "目标花费(万元)": st.column_config.NumberColumn("🔵目标花费(万元)", format="%.0f"),
            "目标1-3过件率(%)": st.column_config.NumberColumn("🔵目标过件率(%)", format="%.2f"),
            "目标CPS(%)": st.column_config.NumberColumn("🔵目标CPS(%)", format="%.2f"),
            "MMM建议(万)": st.column_config.NumberColumn("🟣MMM建议(万)", format="%.0f"),
            "MMM·ROI": st.column_config.NumberColumn("🟣ROI", format="%.1f"),
            "MMM·饱和度(%)": st.column_config.NumberColumn("🟣饱和度(%)", format="%.0f"),
            "参考·花费结构(%)": st.column_config.NumberColumn("参考·花费结构(%)", format="%.2f"),
            "参考·CPS(%)": st.column_config.NumberColumn("参考·CPS(%)", format="%.2f"),
            "T0申完成本(元)": st.column_config.NumberColumn("T0申完成本(元)", format="%.0f"),
        }
        disabled_cols = ["渠道", "MMM建议(万)", "MMM·ROI", "MMM·饱和度(%)", "参考·花费结构(%)", "参考·CPS(%)", "T0申完成本(元)"]
        editor_df = st.data_editor(
            editor_rows,
            use_container_width=True,
            height=editor_height,
            hide_index=True,
            disabled=disabled_cols,
            column_config=col_config,
            key="result_channel_editor",
        )

        # 合计行：预算分配汇总
        channel_budget_shares, channel_1_3_rate, channel_1_8_cps, channel_t0_cost = parse_channel_parameter_rows(editor_df)
        allocated_total = sum(max(float(row.get("目标花费(万元)") or 0), 0) for row in editor_df.to_dict("records"))
        budget_diff = allocated_total - total_budget
        alloc_cols = st.columns([2, 1])
        with alloc_cols[0]:
            if abs(budget_diff) < 1:
                st.success(f"合计: {allocated_total:,.0f} / {total_budget:,.0f} 万元 ✅ 预算已分配完毕")
            else:
                st.warning(f"合计: {allocated_total:,.0f} / {total_budget:,.0f} 万元（差额 {budget_diff:+,.0f} 万元）")
        with alloc_cols[1]:
            st.caption("各渠道花费之和可以不等于总预算，差额仅作提示。")

        # MMM 饱和度提示
        if mmm_recommendations:
            high_sat_channels = [(ch, rec["saturation"]) for ch, rec in mmm_recommendations.items() if rec.get("saturation", 0) > 80]
            if high_sat_channels:
                sat_texts = [f"{ch} 饱和度 {sat:.0f}%" for ch, sat in high_sat_channels]
                st.warning(f"**MMM 提示：** {', '.join(sat_texts)}，继续增投的边际回报递减。建议将预算向低饱和度渠道倾斜。")

        # 内联均值校验（原步骤 5）
        existing_m0_expense = 0.0
        current_approval_avg = sum(channel_1_3_rate.values()) / len(channel_1_3_rate) if channel_1_3_rate else 0.0
        current_cps_avg = sum(channel_1_8_cps.values()) / len(channel_1_8_cps) if channel_1_8_cps else 0.0
        current_cost_avg = sum(channel_t0_cost.values()) / len(channel_t0_cost) if channel_t0_cost else 0.0
        compare_cols = st.columns(3)
        compare_cols[0].metric("当前均值 vs 最新月过件率", f"{current_approval_avg:.2%}", f"{current_approval_avg - baseline_approval:+.2%}")
        compare_cols[1].metric("当前均值 vs 最新月CPS", f"{current_cps_avg:.2%}", f"{current_cps_avg - baseline_cps:+.2%}", delta_color="inverse")
        compare_cols[2].metric("当前均值 vs 最新月申完成本", f"{current_cost_avg:,.0f} 元", f"{current_cost_avg - baseline_cost:+,.0f} 元", delta_color="inverse")

    # --- 目标拆解预览 ---
    with st.container(border=True):
        render_section_header("📎 目标拆解预览", "检查目标拆解表是否接近预期。")

        target_preview_df = _build_target_preview_table(
            df_raw1=data["df_raw1"],
            df_raw2=data["df_raw2"],
            total_budget=total_budget,
            channel_budget_shares=channel_budget_shares,
            channel_1_3_rate=channel_1_3_rate,
            channel_1_8_cps=channel_1_8_cps,
            channel_t0_cost=channel_t0_cost,
            non_initial_credit=non_initial_credit,
            rta_promotion_fee=rta_promotion_fee,
            month_total_days=month_total_days,
            days_elapsed=days_elapsed,
            m0_calc_period=m0_calc_period,
            last_month_data=last_month,
        )
        target_month_label = f"{days_elapsed} / {month_total_days} 天口径"
        if 'df_raw1' not in data or '月份' not in data['df_raw1'].columns:
            st.warning("数据不完整，无法推算结果")
            return
        st.caption(f"{pd.to_datetime(max(data['df_raw1']['月份'])).month}月首登T0目标 · {total_budget:,.0f}万预算 · {target_month_label}")
        st.caption("蓝色看预算与结构，绿色看质量，橙色看成本，紫色看产出量。总计行会单独高亮。")
        target_preview_height = min(340, 52 + (len(target_preview_df) + 1) * 40) if not target_preview_df.empty else 220
        st.dataframe(
            _style_target_preview_table(target_preview_df),
            use_container_width=True,
            hide_index=True,
            height=target_preview_height,
        )

    # --- 计算按钮 ---
    with st.container(border=True):
        confirm_cols = st.columns(3)
        confirm_cols[0].metric("本次预算", f"{total_budget:,.0f} 万元")
        confirm_cols[1].metric("M0周期", f"{m0_calc_period} 个月")
        confirm_cols[2].metric("已完成天数", f"{int(days_elapsed)} / {int(month_total_days)} 天")
        if days_elapsed > month_total_days:
            st.warning("已完成天数大于当月总天数，请先修正后再计算。")
        if st.button("🚀 计算预算", type="primary", use_container_width=True, disabled=days_elapsed > month_total_days):
            run_calculation(
                data["df_raw1"],
                data["df_raw2"],
                total_budget,
                channel_budget_shares,
                channel_1_3_rate,
                channel_1_8_cps,
                channel_t0_cost,
                non_initial_credit,
                existing_m0_expense,
                rta_promotion_fee,
                int(month_total_days),
                int(days_elapsed),
                int(m0_calc_period),
            )
            st.session_state.pop("goal_scenarios", None)  # Clear stale scenario data
            st.rerun()

    update_v01_flow(
        current_step=2,
        inputs={
            "total_budget": total_budget,
            "channel_budget_shares": channel_budget_shares,
            "channel_1_3_rate": channel_1_3_rate,
            "channel_1_8_cps": channel_1_8_cps,
            "channel_t0_cost": channel_t0_cost,
            "non_initial_credit": non_initial_credit,
            "existing_m0_expense": existing_m0_expense,
            "rta_promotion_fee": rta_promotion_fee,
            "month_total_days": int(month_total_days),
            "days_elapsed": int(days_elapsed),
            "m0_calc_period": int(m0_calc_period),
        },
        targets={
            "budget_target": float(total_budget),
            "cps_target": float(current_cps_avg or baseline_cps),
            "approval_target": float(current_approval_avg or baseline_approval),
        },
        next_step="点击计算后查看下方结果和分析 tabs",
    )
    return True


ensure_flow_state()
inject_custom_css()
flow = get_v01_flow()
steps = ["数据上传", "历史基线", "总预算", "MMM推荐", "渠道参数", "补充参数", "计算结果"]

render_flow_header(
    title="📈 预算推算结果",
    purpose="配置总预算 → 参考 MMM 推荐 → 调整渠道参数 → 运行双引擎计算 → 查看结果对比",
    chain="数据上传与检查 → **预算推算结果**",
    current_label="预算推算结果",
)
render_step_progress(steps, 3)
update_v01_flow(current_step=2, next_step="在本页完成参数配置、计算并查看结果")

t1 = st.session_state.get("table1_result")
t2 = st.session_state.get("table2_result")

if st.session_state.get("uploaded_data") is None:
    render_guidance_card(
        "缺少输入数据",
        "请先前往数据上传与检查页上传 Excel 并完成基础检查，再回到当前页配置参数和执行计算。",
        kind="warning",
    )
    if st.button("⬅️ 前往数据上传与检查页", use_container_width=True):
        st.switch_page("pages/1_预算输入与配置.py")
    st.stop()

_render_parameter_panel()

# --- Goal-driven scenario quick entry (pre-calculation accessible) ---
render_inline_goal_selector()

if t1 is None:
    render_guidance_card(
        "尚无计算结果",
        "请先在上方参数区完成配置并点击“计算预算”。计算后，结果与分析 tabs 会在当前页下方出现。",
        kind="info",
    )
    st.stop()
decision_summary = build_v01_decision_summary(flow, t1, t2)

# --- 前置数据：与上次对比 ---
has_prev = st.session_state.get("previous_table1_result") is not None
prev_t1 = st.session_state.get("previous_table1_result")
prev_t2 = st.session_state.get("previous_table2_result")

delta_exp = (t1.total_expense - prev_t1.total_expense) if has_prev and prev_t1 else None
delta_tx = (t2.total_transaction - prev_t2.total_transaction) if has_prev and prev_t2 else None
delta_cps = (t2.total_cps - prev_t2.total_cps) if has_prev and prev_t2 else None
delta_t0 = (t1.total_t0_transaction - prev_t1.total_t0_transaction) if has_prev and prev_t1 else None
delta_apr = (t2.approval_rate_1_3_excl_age - prev_t2.approval_rate_1_3_excl_age) if has_prev and prev_t2 else None

# --- 关键发现自动生成 ---
def _build_key_findings(t1_result, t2_result, prev_t1_result, prev_t2_result) -> list[str]:
    findings = []
    # 排除"总计"行，只看渠道级别数据
    channels = [ch for ch in t1_result.channels if ch.channel_name != "总计"]

    if channels:
        # 1. CPS最低与最高渠道（效率建议）
        valid_cps_channels = [ch for ch in channels if ch.cps_1_8 and ch.cps_1_8 > 0]
        if valid_cps_channels:
            best_ch = min(valid_cps_channels, key=lambda c: c.cps_1_8)
            worst_ch = max(valid_cps_channels, key=lambda c: c.cps_1_8)
            if best_ch.channel_name != worst_ch.channel_name:
                findings.append(
                    f"效率最优渠道：{best_ch.channel_name}（CPS {best_ch.cps_1_8:.2%}）；"
                    f"效率最低渠道：{worst_ch.channel_name}（CPS {worst_ch.cps_1_8:.2%}），"
                    f"可考虑向效率较优渠道倾斜预算。"
                )

        # 2. 花费占比最高渠道效率评估
        max_exp_ch = max(channels, key=lambda c: c.expense)
        avg_cps = t2_result.total_cps if t2_result.total_cps else 0.0
        if avg_cps > 0 and max_exp_ch.cps_1_8 > 0:
            diff_pct = (max_exp_ch.cps_1_8 - avg_cps) / avg_cps
            if diff_pct > 0.05:
                findings.append(
                    f"花费占比最高渠道 {max_exp_ch.channel_name}（占比 {max_exp_ch.expense_structure:.1f}%）"
                    f"的 CPS 高于全业务均值 {diff_pct:.1%}，拖高了整体成本。"
                )
            elif diff_pct < -0.05:
                findings.append(
                    f"花费占比最高渠道 {max_exp_ch.channel_name}（占比 {max_exp_ch.expense_structure:.1f}%）"
                    f"的 CPS 低于全业务均值 {abs(diff_pct):.1%}，对整体降本有正向贡献。"
                )

    # 3. CPS 与上次对比趋势
    if prev_t2_result is not None:
        cps_delta = t2_result.total_cps - prev_t2_result.total_cps
        if abs(cps_delta) >= 0.001:
            direction = "下降" if cps_delta < 0 else "上升"
            findings.append(
                f"全业务CPS较上次计算{direction} {abs(cps_delta):.2%}，"
                f"当前为 {t2_result.total_cps:.2%}。"
            )

    # 4. 预算分配完整性
    targets = st.session_state.get("v01_flow", {}).get("targets", {})
    budget_target = float(targets.get("budget_target", 0) or 0)
    if budget_target > 0:
        utilization = t1_result.total_expense / budget_target
        if abs(utilization - 1.0) < 0.001:
            findings.append(f"预算已按 {t1_result.total_expense:,.0f} 万元完整分配。")
        elif utilization < 1.0:
            findings.append(
                f"当前花费 {t1_result.total_expense:,.0f} 万元，"
                f"距目标预算尚余 {budget_target - t1_result.total_expense:,.0f} 万元未分配。"
            )

    return findings if findings else ["当前方案各渠道参数正常，可进入方案评审阶段。"]


key_findings = _build_key_findings(t1, t2, prev_t1, prev_t2)

# --- V4.3c: 智能建议 Banner ---
mmm_model = st.session_state.get("mmm_model")
if mmm_model is not None:
    st.markdown("""<div class="smart-banner">
        <div style="font-size:18px;flex-shrink:0">🤖</div>
        <div style="flex:1">
            <div style="font-size:13px;font-weight:700;margin-bottom:2px">智能建议</div>
            <div style="font-size:12px;color:#666;line-height:1.5">基于 MMM 模型饱和度分析，可参考 MMM 模型洞察页的优化建议进行渠道调整。</div>
        </div>
    </div>""", unsafe_allow_html=True)

# --- V4.3c: Decision Card ---
with st.container(border=True):
    # a) 核心决策结论（1-2句话）
    status_icon = {"success": "✅", "warning": "⚠️"}.get(decision_summary["status"], "ℹ️")
    st.markdown(f"### {status_icon} {decision_summary['headline']}")
    actions_text = "　".join(decision_summary["recommended_actions"])
    st.markdown(f"<span style='color:#666;font-size:0.9rem;'>{actions_text}</span>", unsafe_allow_html=True)

    st.divider()

    # b) 关键状态标签 chips
    chip_items = []
    # 预算分配状态
    budget_check = decision_summary["checks"]["budget"]
    cps_check = decision_summary["checks"]["cps"]
    approval_check = decision_summary["checks"]["approval"]
    chip_map = {"success": "✅", "warning": "⚠️", "danger": "❌", "info": "ℹ️"}
    chip_items.append(f"{chip_map.get(budget_check['status'], 'ℹ️')} 预算分配 {budget_check['label']}")
    chip_items.append(f"{chip_map.get(cps_check['status'], 'ℹ️')} CPS {cps_check['label']}")
    chip_items.append(f"{chip_map.get(approval_check['status'], 'ℹ️')} 过件率 {approval_check['label']}")
    if has_prev:
        cps_vs_prev = "低于上次" if (delta_cps is not None and delta_cps < 0) else ("高于上次" if (delta_cps is not None and delta_cps > 0) else "与上次持平")
        chip_items.append(f"📊 CPS {cps_vs_prev}")
    st.markdown("　".join(f"`{chip}`" for chip in chip_items))

    st.divider()

    # c) 5个核心指标 metric 卡片
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("总投放花费", f"{t1.total_expense:,.0f} 万元", f"{delta_exp:+,.0f} 万元" if delta_exp is not None else None)
    m2.metric("整体首借交易额", f"{t2.total_transaction:.2f} 亿元", f"{delta_tx:+.2f} 亿元" if delta_tx is not None else None)
    m3.metric("全业务CPS", f"{t2.total_cps:.2%}", f"{delta_cps:+.2%}" if delta_cps is not None else None, delta_color="inverse")
    m4.metric("T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元", f"{delta_t0 * 10:+.2f} 千万元" if delta_t0 is not None else None)
    m5.metric("1-3 T0过件率", f"{t2.approval_rate_1_3_excl_age:.2%}", f"{delta_apr:+.2%}" if delta_apr is not None else None)

    st.divider()

    # d) 关键发现（动态 bullets）
    st.markdown("**关键发现**")
    for finding in key_findings:
        st.markdown(f"- {finding}")

# --- 预算结构与效率总览图表 ---
with st.container(border=True):
    st.markdown("#### 预算结构与效率总览")
    chart_cols = st.columns(2)
    with chart_cols[0]:
        # 渠道花费分布饼图
        channels = [ch for ch in t1.channels if ch.channel_name != "总计"]
        if channels:
            fig_pie = go.Figure(data=[go.Pie(
                labels=[ch.channel_name for ch in channels],
                values=[ch.expense for ch in channels],
                hole=0.4,
                textinfo="label+percent",
                marker=dict(colors=["#2E7D32", "#E53935", "#1976D2", "#FF9800", "#9E9E9E"]),
            )])
            fig_pie.update_layout(title="渠道花费分布", height=320, margin=dict(t=40, b=20))
            st.plotly_chart(fig_pie, use_container_width=True)

    with chart_cols[1]:
        # 渠道交易额贡献柱状图
        if channels:
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                name="T0交易额",
                x=[ch.channel_name for ch in channels],
                y=[ch.t0_transaction for ch in channels],
                marker_color="#1976D2",
            ))
            fig_bar.add_trace(go.Bar(
                name="M0交易额",
                x=[ch.channel_name for ch in channels],
                y=[ch.m0_transaction for ch in channels],
                marker_color="#90CAF9",
            ))
            fig_bar.update_layout(
                title="渠道交易额贡献",
                yaxis_title="交易额 (亿元)",
                barmode="stack",
                height=320,
                margin=dict(t=40, b=20),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

# --- 历史达成与当月预估（折叠）---
data = st.session_state.get("uploaded_data")
if data is not None:
    with st.expander("📊 历史达成与当月预估 (点击展开)", expanded=False):
        flow_state = get_v01_flow()
        inputs = flow_state.get("inputs", {})
        _days = int(inputs.get("days_elapsed", DEFAULT_DAYS_ELAPSED))
        _month_days = int(inputs.get("month_total_days", DEFAULT_MONTH_DAYS))
        _render_historical_baseline_panel(
            data["df_raw1"],
            month_total_days=_month_days,
            days_elapsed=_days,
        )

# --- 分项详情 Tabs (V4.3c: 6 tabs) ---
st.markdown("---")
st.caption("**分项详情**")

tabs = st.tabs(["📊 渠道", "👥 客群", "🛡️ 护栏", "🎯 方案", "🤖 双引擎", "📈 What-if"])
with tabs[0]:
    render_tab_channel_result()
with tabs[1]:
    render_tab_customer_result()
with tabs[2]:
    render_tab_guardrail()
with tabs[3]:
    render_tab_goal_scenarios()
with tabs[4]:
    render_tab_model_comparison()
with tabs[5]:
    render_tab_whatif()
