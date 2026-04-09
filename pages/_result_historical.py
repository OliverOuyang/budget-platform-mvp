from __future__ import annotations

import streamlit as st
import pandas as pd
from app.flow_components import render_section_header
from app.styles import highlight_total_row
from app.ui_utils import normalize_channel_history, safe_num
from core.customer_group_calculator import extrapolate_by_days


def _build_latest_share_rows(last_month: dict[str, dict]) -> list[dict]:
    total_expense_raw = sum(safe_num(item.get("花费")) for item in last_month.values())
    rows = []
    for channel_name, item in last_month.items():
        expense = safe_num(item.get("花费"))
        rows.append(
            {
                "渠道": channel_name,
                "历史过件率(%)": safe_num(item.get("1-3t0过件率")) * 100,
                "历史CPS(%)": safe_num(item.get("1-8t0cps")) * 100,
                "历史申完成本(元)": safe_num(item.get("t0申完成本")),
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
        .apply(highlight_total_row, axis=1)
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
        st.caption(f'当前按 {int(days_elapsed)} / {int(month_total_days)} 天进行月内外推；\u201c截至当前\u201d是原始累计值，\u201c整月预估\u201d按比例放大。')
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
