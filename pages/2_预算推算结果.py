from __future__ import annotations

import streamlit as st
import pandas as pd
from app.flow_components import (
    render_bullet_summary,
    render_flow_header,
    render_guidance_card,
    render_next_step_card,
    render_section_header,
    render_status_card,
    render_step_progress,
)
from pages._tab_overview import render_tab_overview
from pages._tab_channel_result import render_tab_channel_result
from pages._tab_customer_result import render_tab_customer_result
from pages._tab_coefficient_trace import render_tab_coefficient_trace
from pages._tab_scenario_manager import render_tab_scenario_manager
from app.config import CHANNEL_NAMES, DEFAULT_DAYS_ELAPSED, DEFAULT_MONTH_DAYS, DEFAULT_TOTAL_BUDGET
from app.ui_utils import (
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
    st.session_state.current_template_params = params
    st.session_state["result_total_budget"] = float(params.get("total_budget", DEFAULT_TOTAL_BUDGET))
    st.session_state["result_m0_calc_period"] = int(params.get("existing_m0_calculation_months", 3))
    st.session_state["result_non_initial_credit"] = float(params.get("non_initial_credit_transaction", 0.0))
    st.session_state["result_rta_promotion_fee"] = float(params.get("rta_promotion_fee", 0.0))
    st.session_state["result_month_total_days"] = int(params.get("month_total_days", DEFAULT_MONTH_DAYS))
    st.session_state["result_days_elapsed"] = int(params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))
    st.session_state.pop("result_channel_editor", None)


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
    render_guidance_card(
        "在本页完成参数配置",
        "参考最新月历史过件率、CPS、申完成本和花费结构设置参数，点击计算后结果会在当前页下方刷新。",
    )
    with st.container(border=True):
        render_section_header("历史达成与当月预估", "先设定已完成天数和当月总天数，再看历史完整月份、当月至今达成和当月整月预估。")
        st.caption("“预估”列使用当前月累计数据按已完成天数外推；历史月份按两张 raw 的可交集月份展示。RTA费用在历史 raw 中缺字段时留空，仅在预估列展示当前输入值。")
        day_cols = st.columns(2)
        with day_cols[0]:
            month_total_days = st.number_input(
                "当月总天数",
                28,
                31,
                int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
                key="result_month_total_days",
            )
        with day_cols[1]:
            days_elapsed = st.number_input(
                "已完成天数",
                1,
                31,
                int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
                key="result_days_elapsed",
            )
        historical_table = _build_historical_result_table(
            data["df_raw1"],
            data["df_raw2"],
            month_total_days=int(month_total_days),
            days_elapsed=int(days_elapsed),
            rta_estimate=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
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
    with st.container(border=True):
        render_section_header("推荐操作顺序", "按这个顺序往下走，改完参数后只需要继续往下看“当前目标拆解表”和“计算确认”即可。")
        st.markdown(
            """
1. 先看上面的“历史达成与当月预估”，判断最近趋势和当前月外推是否合理。
2. 如果有历史模板，先在“模板管理”里直接加载，再继续下面的预算输入。
3. 先改“核心预算输入”，确定总预算规模和 M0 计算周期。
4. 再看“最新月参考摘要”，确认渠道历史过件率、CPS、申完成本和花费结构基线。
5. 接着修改“渠道参数矩阵”，这里改动后会直接影响下面的“当前目标拆解表”。
6. 再补“补充业务参数”，确认无误后点击“计算预算”。
7. 计算完成后，继续往下看结果总览、方案判断和 tabs，不需要再回到上面重新找入口。
            """
        )

    with st.container(border=True):
        render_section_header("步骤 1 · 模板管理（可选）", "如果你已有类似方案，先在这里加载；没有就跳过，继续手动配置。")
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

    with st.container(border=True):
        render_section_header("步骤 2 · 核心预算输入", "先改总预算和计算周期。这会影响下方所有预览表和最终结果。")
        total_budget = st.slider(
            "总花费 (万元)",
            500,
            10000,
            int(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
            50,
            key="result_total_budget",
        )
        top_cols = st.columns(2)
        with top_cols[0]:
            m0_calc_period = st.radio(
                "存量首登M0计算周期",
                [3, 6],
                index=0 if int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))) == 3 else 1,
                horizontal=True,
                key="result_m0_calc_period",
            )
        with top_cols[1]:
            st.metric("相对最新月预算差异", f"{total_budget - hist_total_budget:+,.0f} 万元")

    with st.container(border=True):
        render_section_header("步骤 3 · 最新月参考摘要", "先看历史基线，再决定下面哪些渠道参数需要调整。")
        metric_cols = st.columns(4)
        metric_cols[0].metric("最新月预算基线", f"{hist_total_budget:,.0f} 万元")
        metric_cols[1].metric("最新月1-3过件率", f"{baseline_approval:.2%}")
        metric_cols[2].metric("最新月CPS", f"{baseline_cps:.2%}")
        metric_cols[3].metric("最新月申完成本", f"{baseline_cost:,.0f} 元")
        st.caption("如果你不确定参数怎么填，优先让下面的目标值贴近这里的最新月基线，再逐步微调。绿色看质量，橙色看成本，蓝色看申完成本，紫色看花费结构。")
        if latest_share_rows:
            latest_reference_df = pd.DataFrame(latest_share_rows)
            latest_reference_height = min(340, 52 + (len(latest_reference_df) + 1) * 40)
            st.dataframe(
                _style_latest_reference_table(latest_reference_df),
                use_container_width=True,
                hide_index=True,
                height=latest_reference_height,
            )
        else:
            st.info("暂无足够的最新月数据用于生成渠道参考。")

    with st.container(border=True):
        render_section_header("步骤 4 · 渠道参数矩阵", "这里是主编辑区。你改花费结构、过件率和 CPS，下面“当前目标拆解表”会立即跟着变化。")
        st.caption("带色块前缀的 3 列是你要填的目标列：`🟪` 花费结构，`🟩` 质量，`🟧` 成本率；参考列不可编辑，申完成本直接沿用上月。")
        editor_rows = build_channel_parameter_rows(last_month, template_params)
        editor_height = min(300, 52 + (len(editor_rows) + 1) * 38)
        editor_df = st.data_editor(
            editor_rows,
            use_container_width=True,
            height=editor_height,
            hide_index=True,
            disabled=["渠道", "历史花费结构(%)", "历史1-3 T0过件率(%)", "历史1-8 T0CPS(%)", "历史T0申完成本(元)"],
            column_config={
                "渠道": st.column_config.TextColumn("渠道", width="medium"),
                "目标花费结构(%)": st.column_config.NumberColumn("🟪目标花费结构(%)", format="%.2f"),
                "目标1-3过件率(%)": st.column_config.NumberColumn("🟩目标过件率(%)", format="%.2f"),
                "目标CPS(%)": st.column_config.NumberColumn("🟧目标CPS(%)", format="%.2f"),
                "历史花费结构(%)": st.column_config.NumberColumn("参考·最新月花费结构(%)", format="%.2f"),
                "历史1-3 T0过件率(%)": st.column_config.NumberColumn("参考·最新月过件率(%)", format="%.2f"),
                "历史1-8 T0CPS(%)": st.column_config.NumberColumn("参考·最新月CPS(%)", format="%.2f"),
                "历史T0申完成本(元)": st.column_config.NumberColumn("参考·最新月申完成本(元)", format="%.0f"),
            },
            key="result_channel_editor",
        )
        st.caption("建议先把目标值调到接近最新月基线，再根据业务判断逐项拉高或压低。")

    channel_budget_shares, channel_1_3_rate, channel_1_8_cps, channel_t0_cost = parse_channel_parameter_rows(editor_df)
    existing_m0_expense = 0.0
    current_approval_avg = sum(channel_1_3_rate.values()) / len(channel_1_3_rate) if channel_1_3_rate else 0.0
    current_cps_avg = sum(channel_1_8_cps.values()) / len(channel_1_8_cps) if channel_1_8_cps else 0.0
    current_cost_avg = sum(channel_t0_cost.values()) / len(channel_t0_cost) if channel_t0_cost else 0.0
    current_budget_share_avg = (sum(channel_budget_shares.values()) / len(channel_budget_shares) * 100) if channel_budget_shares else 0.0
    baseline_budget_share_avg = (sum(item["历史花费结构(%)"] for item in latest_share_rows) / len(latest_share_rows)) if latest_share_rows else 0.0

    with st.container(border=True):
        render_section_header("步骤 5 · 当前目标均值对照", "这里是矩阵编辑后的第一道检查，先看你改出来的整体均值是否偏离最新月太多。")
        compare_cols = st.columns(4)
        compare_cols[0].metric("当前均值 vs 最新月过件率", f"{current_approval_avg:.2%}", f"{current_approval_avg - baseline_approval:+.2%}")
        compare_cols[1].metric("当前均值 vs 最新月CPS", f"{current_cps_avg:.2%}", f"{current_cps_avg - baseline_cps:+.2%}", delta_color="inverse")
        compare_cols[2].metric("当前均值 vs 最新月申完成本", f"{current_cost_avg:,.0f} 元", f"{current_cost_avg - baseline_cost:+,.0f} 元", delta_color="inverse")
        compare_cols[3].metric("当前均值 vs 最新月花费结构", f"{current_budget_share_avg:.2f}%", f"{current_budget_share_avg - baseline_budget_share_avg:+.2f}%")

    with st.container(border=True):
        render_section_header("步骤 6 · 补充业务参数", "这里补全总表约束。你改这里，会影响历史预估对照和下面的目标拆解表。")
        summary_cols = st.columns(2)
        with summary_cols[0]:
            non_initial_credit = st.number_input(
                "非初审授信户首借交易额 (亿元)",
                0.0,
                value=float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
                format="%.2f",
                key="result_non_initial_credit",
            )
        with summary_cols[1]:
            rta_promotion_fee = st.number_input(
                "RTA费用+促申完 (万元)",
                0.0,
                value=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
                format="%.2f",
                key="result_rta_promotion_fee",
            )

    with st.container(border=True):
        render_section_header("步骤 7 · 当前目标拆解表", "先看这张表是否已经接近你想提交的目标版预算表；如果不对，继续回到上面改参数。")
        target_preview_df = _build_target_preview_table(
            df_raw1=data["df_raw1"],
            df_raw2=data["df_raw2"],
            total_budget=total_budget,
            channel_budget_shares=channel_budget_shares,
            channel_1_3_rate=channel_1_3_rate,
            channel_1_8_cps=channel_1_8_cps,
            channel_t0_cost=channel_t0_cost,
            non_initial_credit=float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
            rta_promotion_fee=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
            month_total_days=month_total_days,
            days_elapsed=days_elapsed,
            m0_calc_period=int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))),
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
        st.caption("如果这张表已经接近你的业务目标，就直接进入下一步计算；如果还差得远，返回上面继续调预算、渠道目标或补充参数。")

    with st.container(border=True):
        render_section_header("步骤 7 · 计算并查看结果", "点击后，下方结果总览和分析 tabs 会一起刷新。你不用回到上面重新找结果入口。")
        confirm_cols = st.columns(3)
        confirm_cols[0].metric("本次预算", f"{total_budget:,.0f} 万元")
        confirm_cols[1].metric("M0周期", f"{m0_calc_period} 个月")
        confirm_cols[2].metric("已完成天数", f"{int(days_elapsed)} / {int(month_total_days)} 天")
        if days_elapsed > month_total_days:
            st.warning("已完成天数大于当月总天数，请先修正后再计算。")
        else:
            st.info("如果上面的历史参考、参数矩阵和目标拆解表都已经看过，现在就可以计算。")
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
flow = get_v01_flow()
steps = ["数据上传与检查", "预算推算结果"]

render_flow_header(
    title="📈 V01 · 预算推算结果分析",
    purpose="基于已上传的数据，在本页完成参数配置、预算计算和结果分析，并决定是否保存方案或继续微调。",
    chain="数据上传与检查 → 预算推算结果",
    current_label="预算推算结果",
)
render_step_progress(steps, 2)
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

if t1 is None:
    render_guidance_card(
        "尚无计算结果",
        "请先在上方参数区完成配置并点击“计算预算”。计算后，结果与分析 tabs 会在当前页下方出现。",
        kind="info",
    )
    st.stop()
decision_summary = build_v01_decision_summary(flow, t1, t2)

render_guidance_card(
    decision_summary["headline"],
    "结果页会基于预算、CPS 和质量目标给出拍板建议。先看下方决策结论，再决定保存、比较或回调参数。",
    kind="success" if decision_summary["status"] == "success" else "warning" if decision_summary["status"] == "warning" else "info",
)
render_bullet_summary("当前建议动作", decision_summary["recommended_actions"])

# 核心指标
st.subheader("🎯 核心指标")
has_prev = st.session_state.get("previous_table1_result") is not None
prev_t1 = st.session_state.get("previous_table1_result")
prev_t2 = st.session_state.get("previous_table2_result")

delta_exp = (t1.total_expense - prev_t1.total_expense) if has_prev and prev_t1 else None
delta_tx = (t2.total_transaction - prev_t2.total_transaction) if has_prev and prev_t2 else None
delta_cps = (t2.total_cps - prev_t2.total_cps) if has_prev and prev_t2 else None
delta_t0 = (t1.total_t0_transaction - prev_t1.total_t0_transaction) if has_prev and prev_t1 else None
delta_apr = (t2.approval_rate_1_3_excl_age - prev_t2.approval_rate_1_3_excl_age) if has_prev and prev_t2 else None

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("总投放花费", f"{t1.total_expense:,.0f} 万元", f"{delta_exp:+,.0f} 万元" if delta_exp is not None else None)
m2.metric("整体首借交易额", f"{t2.total_transaction:.2f} 亿元", f"{delta_tx:+.2f} 亿元" if delta_tx is not None else None)
m3.metric("全业务CPS", f"{t2.total_cps:.2%}", f"{delta_cps:+.2%}" if delta_cps is not None else None, delta_color="inverse")
m4.metric("T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元", f"{delta_t0 * 10:+.2f} 千万元" if delta_t0 is not None else None)
m5.metric("1-3 T0过件率", f"{t2.approval_rate_1_3_excl_age:.2%}", f"{delta_apr:+.2%}" if delta_apr is not None else None)

action_left, action_mid, action_right = st.columns(3)
if action_left.button("⬅️ 返回数据检查页", use_container_width=True):
    st.switch_page("pages/1_预算输入与配置.py")
if action_mid.button("📌 聚焦总览与方案", use_container_width=True):
    st.toast("继续查看下方总览、方案对比与数据洞察。")
if action_right.button("💾 前往方案管理", use_container_width=True):
    st.toast("请在页面底部的「方案管理」Tab 中保存或比较方案。")

render_next_step_card(
    "按状态执行下一步",
    "若主要目标已达成，优先保存或对比方案；若仍有未达成指标，先根据下方短板回看本页上方参数区或返回数据检查页。",
)

targets = flow.get("targets", {})
if targets:
    st.subheader("🎯 目标达成判断")
    goal_cols = st.columns(3)
    check_specs = [
        ("预算目标", decision_summary["checks"]["budget"], f"{t1.total_expense:,.0f} / {float(targets.get('budget_target', 0)):,.0f} 万元"),
        ("CPS 目标", decision_summary["checks"]["cps"], f"{t2.total_cps:.2%} / {float(targets.get('cps_target', 0)):.2%}"),
        ("过件率目标", decision_summary["checks"]["approval"], f"{t2.approval_rate_1_3_excl_age:.2%} / {float(targets.get('approval_target', 0)):.2%}"),
    ]
    for col, (label, check, value) in zip(goal_cols, check_specs):
        with col:
            render_status_card(label, f"{check['label']} · {value}", check["summary"], status=check["status"])

    blocker_order = sorted(
        [
            ("预算", abs(decision_summary["checks"]["budget"]["delta"] or 0)),
            ("CPS", abs(decision_summary["checks"]["cps"]["delta"] or 0)),
            ("过件率", abs(decision_summary["checks"]["approval"]["delta"] or 0)),
        ],
        key=lambda item: item[1],
        reverse=True,
    )
    render_bullet_summary(
        "当前最关键的决策判断",
        [
            f"当前最主要的约束项是 {blocker_order[0][0]}。",
            "可保存当前方案。" if decision_summary["status"] == "success" else "建议先微调后再保存。" if decision_summary["status"] == "info" else "当前不建议直接保存为正式场景。",
        ],
    )

    if decision_summary["status"] == "success":
        render_guidance_card("推荐动作：保存或进入方案对比", "主要目标已经达成，建议优先把当前方案保存下来，再和历史方案做拍板对比。", kind="success")
    elif decision_summary["status"] == "info":
        render_guidance_card("推荐动作：优先做小幅调参", "当前更像接近达成而非完全失败，建议先使用快速调参或只回调一类关键参数。")
    else:
        render_guidance_card("推荐动作：回看上方参数区", "当前存在明显未达成目标，建议按建议动作的优先级重新设置预算、CPS 或过件率假设。", kind="warning")

# 5个Tab
tabs = st.tabs(["🏠 总览", "📊 渠道结果", "👥 客群结果", "🔢 系数追溯", "💾 方案管理"])
with tabs[0]:
    render_tab_overview()
with tabs[1]:
    render_tab_channel_result()
with tabs[2]:
    render_tab_customer_result()
with tabs[3]:
    render_tab_coefficient_trace()
with tabs[4]:
    render_tab_scenario_manager()
