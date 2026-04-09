"""Tab 0: 总览与定位"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from app.ui_utils import normalize_channel_history, get_v01_flow, build_v01_decision_summary
from pages._tab_overview_sections import (
    weighted_approval_rate as _weighted_approval_rate,
    render_scenario_comparison as _render_scenario_comparison,
    render_insights as _render_insights,
)


def _generate_key_findings(t1, t2, coef):
    """动态生成关键发现列表"""
    findings = []
    channels = [ch for ch in t1.channels if ch.channel_name != "总计"]
    if not channels:
        return findings

    # 效率最高/最低渠道
    best_ch = max(channels, key=lambda c: c.t0_transaction / c.expense if c.expense > 0 else 0)
    worst_ch = min(channels, key=lambda c: c.t0_transaction / c.expense if c.expense > 0 else float('inf'))
    best_eff = best_ch.t0_transaction / best_ch.expense * 10000 if best_ch.expense > 0 else 0
    worst_eff = worst_ch.t0_transaction / worst_ch.expense * 10000 if worst_ch.expense > 0 else 0

    findings.append(
        f"**{best_ch.channel_name}**万元效率最高({best_eff:.1f}千元/万元)，"
        f"花费占比{best_ch.expense / t1.total_expense * 100:.0f}%但交易贡献突出，建议优先保障预算"
    )

    # CPS最高渠道风险
    high_cps_ch = max(channels, key=lambda c: c.cps_1_8 or 0)
    if (high_cps_ch.cps_1_8 or 0) > 0.25:
        findings.append(
            f"**{high_cps_ch.channel_name}** CPS {high_cps_ch.cps_1_8:.1%} 偏高，"
            f"花费占比{high_cps_ch.expense / t1.total_expense * 100:.0f}%，需关注成本压力"
        )

    # 花费占比最大渠道
    top_expense_ch = max(channels, key=lambda c: c.expense)
    top_share = top_expense_ch.expense / t1.total_expense * 100
    top_eff = top_expense_ch.t0_transaction / top_expense_ch.expense * 10000 if top_expense_ch.expense > 0 else 0
    if top_share > 35:
        findings.append(
            f"**{top_expense_ch.channel_name}**花费占比{top_share:.0f}%为最大渠道，"
            f"万元效率{top_eff:.1f}千元/万元，{'效率尚可' if top_eff > best_eff * 0.7 else '效率偏低需优化'}"
        )

    # M0/T0系数
    findings.append(
        f"M0/T0系数={coef.m0_t0_ratio:.3f}，"
        f"存量M0 CPS={coef.existing_m0_cps_avg:.1%}，系数{'稳定' if coef.m0_t0_ratio < 2 else '偏高需关注'}"
    )

    return findings


def _render_conclusion_panel(t1, t2, coef):
    """核心结论面板（结论先行）"""
    with st.container(border=True):
        st.markdown("### 核心结论")

        # 一句话总结
        st.markdown(
            f"本次预算 **{t1.total_expense:,.0f}万元**，预计整体首借交易额 **{t2.total_transaction:.2f}亿元**，"
            f"全业务CPS **{t2.total_cps:.2%}**，T0交易额 **{t1.total_t0_transaction * 10:.2f}千万元**。"
        )

        # 关键发现
        findings = _generate_key_findings(t1, t2, coef)
        if findings:
            for f in findings:
                st.markdown(f"- {f}")


def _render_goal_achievement():
    """目标达成判断"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    if t1 is None or t2 is None:
        return
    flow = get_v01_flow()
    targets = flow.get("targets", {})
    if not targets:
        return
    decision_summary = build_v01_decision_summary(flow, t1, t2)

    st.subheader("目标达成判断")
    goal_cols = st.columns(3)
    check_specs = [
        ("预算目标", decision_summary["checks"]["budget"], f"{t1.total_expense:,.0f} / {float(targets.get('budget_target', 0)):,.0f} 万元"),
        ("CPS 目标", decision_summary["checks"]["cps"], f"{t2.total_cps:.2%} / {float(targets.get('cps_target', 0)):.2%}"),
        ("过件率目标", decision_summary["checks"]["approval"], f"{t2.approval_rate_1_3_excl_age:.2%} / {float(targets.get('approval_target', 0)):.2%}"),
    ]
    status_colors = {"success": "#f0fdf4", "warning": "#fff7ed", "danger": "#fef2f2"}
    for col, (label, check, value) in zip(goal_cols, check_specs):
        status_icon = {"success": "✅", "warning": "⚠️", "danger": "⛔"}.get(check["status"], "ℹ️")
        bg = status_colors.get(check["status"], "#f8f9fa")
        with col.container(border=True):
            st.markdown(
                f'<div style="background:{bg};padding:8px 12px;border-radius:6px;">'
                f'<span style="font-size:13px;">{status_icon} <b>{label}</b></span><br>'
                f'<span style="font-size:15px;font-weight:700;">{value}</span><br>'
                f'<span style="font-size:11px;color:#666;">{check["summary"]}</span></div>',
                unsafe_allow_html=True,
            )

    blocker_order = sorted(
        [
            ("预算", abs(decision_summary["checks"]["budget"]["delta"] or 0)),
            ("CPS", abs(decision_summary["checks"]["cps"]["delta"] or 0)),
            ("过件率", abs(decision_summary["checks"]["approval"]["delta"] or 0)),
        ],
        key=lambda item: item[1],
        reverse=True,
    )
    verdict = (
        "可保存当前方案。" if decision_summary["status"] == "success"
        else "建议先微调后再保存。" if decision_summary["status"] == "info"
        else "当前不建议直接保存为正式场景。"
    )
    st.caption(f"主要约束项: {blocker_order[0][0]} | {verdict}")


def render_tab_overview():
    """总览 Tab"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    p = st.session_state.get("parameters")
    coef = st.session_state.get("coefficients")

    # ── 结论先行 ──
    _render_conclusion_panel(t1, t2, coef)

    # ── 目标达成 ──
    _render_goal_achievement()

    # ── 推算逻辑链（5步流程） ──
    st.subheader("推算逻辑链")
    st.caption("每花1元 → 产生多少申请 → 通过多少 → 转化多少交易额 → 扩展到M0")
    step_cols = st.columns(5)
    steps = [
        ("① 预算分配", f"{t1.total_expense:,.0f} 万元",
         "总预算按渠道结构分配", f"总花费 × 渠道占比"),
        ("② 申完量", f"{t1.total_completion_volume:,.0f} 笔",
         "花费转化为申请完成量", f"花费×10000 ÷ 申完成本"),
        ("③ 授信量", f"{sum(ch.credit_volume_1_3 for ch in t1.channels if ch.channel_name != '总计'):,.0f} 笔",
         "申请中通过审核的数量", f"申完量 × 1-3过件率"),
        ("④ T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元",
         "首借当天产生的交易额", f"花费 ÷ CPS ÷ 10000"),
        ("⑤ M0交易额", f"{t1.total_m0_transaction * 10:.2f} 千万元",
         "首月累计交易额", f"T0 × M0/T0({coef.m0_t0_ratio:.3f})"),
    ]
    for i, (col, (title, value, desc, formula)) in enumerate(zip(step_cols, steps)):
        with col.container(border=True):
            st.caption(title)
            st.markdown(f"**{value}**")
            st.caption(desc)
            st.caption(f"`{formula}`")
    st.caption("① → ② → ③ → ④ → ⑤ 每步由上一步结果驱动")

    if not st.session_state.get("uploaded_data"):
        return

    upload = st.session_state.uploaded_data
    df_n = normalize_channel_history(upload["df_raw1"])
    df_n["花费"] = df_n["花费"].fillna(0)
    df_n["1-3t0过件率"] = df_n["1-3t0过件率"].fillna(0)
    df_n["1-8t0首借24h借款金额"] = df_n["1-8t0首借24h借款金额"].fillna(0)
    df_n["t0申完成本"] = df_n["t0申完成本"].replace(0, np.nan)
    if "非年龄拒绝t0申完量" in df_n.columns:
        df_n["非年龄拒绝申完量"] = pd.to_numeric(df_n["非年龄拒绝t0申完量"], errors="coerce").fillna(0)
    else:
        df_n["非年龄拒绝申完量"] = df_n["花费"] / df_n["t0申完成本"]

    # ── 数据概览 ──
    info_cols = st.columns(3)
    with info_cols[0]:
        st.metric("数据文件", upload["file_name"])
    with info_cols[1]:
        n_months = df_n["月份标签"].nunique() if "月份标签" in df_n.columns else 0
        st.metric("历史月数", n_months)
    with info_cols[2]:
        st.metric("存量首登M0 CPS", f"{coef.existing_m0_cps_avg:.2%}")

    if '月份标签' not in df_n.columns or '渠道名称' not in df_n.columns:
        st.warning("数据中缺少 '月份标签' 或 '渠道名称' 列，请检查数据格式")
        return

    # ── 关键指标月度趋势 ──
    st.subheader("关键指标月度趋势")
    st.caption("观察花费、过件率、交易额、CPS的月度走势，判断当前方案是否合理")

    monthly_rate = df_n.groupby("月份标签").apply(_weighted_approval_rate, include_groups=False).reset_index()
    monthly_rate.columns = ["月份", "1-3 T0过件率"]
    monthly_rate = monthly_rate.dropna().sort_values("月份")

    monthly_exp = df_n.groupby("月份标签")["花费"].sum().reset_index()
    monthly_exp.columns = ["月份", "花费(万元)"]
    monthly_exp["花费(万元)"] = monthly_exp["花费(万元)"] / 10000
    monthly_exp = monthly_exp.sort_values("月份")

    monthly_t0 = df_n.groupby("月份标签")["1-8t0首借24h借款金额"].sum().reset_index()
    monthly_t0.columns = ["月份", "T0交易额(亿元)"]
    monthly_t0["T0交易额(亿元)"] = monthly_t0["T0交易额(亿元)"] / 1e8
    monthly_t0 = monthly_t0.sort_values("月份")

    r1, r2 = st.columns(2)
    with r1:
        fig1 = px.line(monthly_rate, x="月份", y="1-3 T0过件率", markers=True,
                       title="过件率走势 | 看质量是否稳定")
        fig1.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig1, use_container_width=True)
    with r2:
        fig2 = px.line(monthly_exp, x="月份", y="花费(万元)", markers=True,
                       title="花费走势 | 看预算规模变化")
        fig2.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    r3, r4 = st.columns(2)
    with r3:
        fig3 = px.line(monthly_t0, x="月份", y="T0交易额(亿元)", markers=True,
                       title="T0交易额走势 | 看产出是否增长")
        fig3.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig3, use_container_width=True)
    with r4:
        merged = monthly_exp.merge(monthly_t0, on="月份")
        merged["全业务CPS"] = merged["花费(万元)"] / (merged["T0交易额(亿元)"] * 1e4)
        fig4 = px.line(merged, x="月份", y="全业务CPS", markers=True,
                       title="CPS走势 | 看成本是否可控")
        fig4.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig4, use_container_width=True)

    # ── 当前方案定位 ──
    st.subheader("当前预算方案在历史趋势中的定位")
    if len(monthly_exp) > 0:
        current_exp = t1.total_expense
        latest_exp = monthly_exp["花费(万元)"].iloc[-1]
        fig_pos = make_subplots(specs=[[{"secondary_y": False}]])
        fig_pos.add_trace(go.Scatter(
            x=monthly_exp["月份"], y=monthly_exp["花费(万元)"],
            mode="lines+markers", name="历史花费(万元)", line=dict(color="#4C6EF5")
        ))
        fig_pos.add_hline(
            y=current_exp, line_dash="dot", line_color="red",
            annotation_text=f"当前方案: {current_exp:,.0f}万", annotation_position="top right"
        )
        # 标注最高和最低月
        max_idx = monthly_exp["花费(万元)"].idxmax()
        min_idx = monthly_exp["花费(万元)"].idxmin()
        fig_pos.add_annotation(
            x=monthly_exp.loc[max_idx, "月份"], y=monthly_exp.loc[max_idx, "花费(万元)"],
            text=f"峰值: {monthly_exp.loc[max_idx, '花费(万元)']:,.0f}万",
            showarrow=True, arrowhead=2, font=dict(size=10, color="#e53935"),
        )
        fig_pos.add_annotation(
            x=monthly_exp.loc[min_idx, "月份"], y=monthly_exp.loc[min_idx, "花费(万元)"],
            text=f"谷值: {monthly_exp.loc[min_idx, '花费(万元)']:,.0f}万",
            showarrow=True, arrowhead=2, font=dict(size=10, color="#2e7d32"),
        )
        fig_pos.update_layout(
            title=f"花费趋势定位（最新月: {latest_exp:,.0f}万 → 当前方案: {current_exp:,.0f}万）",
            height=280, margin=dict(l=20, r=20, t=40, b=20), showlegend=True
        )
        st.plotly_chart(fig_pos, use_container_width=True)
        exp_vs_hist = (current_exp - latest_exp) / latest_exp * 100 if latest_exp > 0 else 0
        direction = "增加" if exp_vs_hist > 0 else "减少"
        st.info(
            f"当前方案花费 **{current_exp:,.0f}万**，较最新月{direction} **{abs(exp_vs_hist):.1f}%**。"
            f"当前值基于渠道参数配置重新分配，非历史实际值。"
        )

    # ── 方案对比 ──
    _render_scenario_comparison()
    # ── 数据洞察 ──
    _render_insights(df_n)
