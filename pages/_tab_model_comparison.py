"""Tab: 模型对照 - V01 规则层 vs MMM 模型层"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def _get_mmm_predictions(t1) -> dict | None:
    """从 session_state 中获取 MMM 模型预测结果用于对照。"""
    model = st.session_state.get("mmm_model")
    if model is None:
        return None

    try:
        contributions = st.session_state.get("mmm_contributions", {})
        recommended = st.session_state.get("mmm_v01_recommended_spends", {})

        # 从 model 获取渠道贡献占比
        channel_contrib_pcts = {}
        total_contrib = sum(contributions.values()) if contributions else 0
        if total_contrib > 0:
            for ch, val in contributions.items():
                channel_contrib_pcts[ch] = val / total_contrib

        # 计算 MMM 预测的总借款金额和 CPS
        total_mmm_spend = sum(recommended.values()) if recommended else t1.total_expense
        mmm_predicted_loan = st.session_state.get("mmm_predicted_loan_amt", 0)
        mmm_cps = (total_mmm_spend / mmm_predicted_loan * 100) if mmm_predicted_loan > 0 else 0

        return {
            "total_spend": total_mmm_spend,
            "predicted_loan_amt": mmm_predicted_loan,
            "predicted_cps": mmm_cps,
            "channel_contributions": channel_contrib_pcts,
            "recommended_spends": recommended,
        }
    except Exception:
        return None


# Metrics where a positive difference (MMM > V01) is unfavorable (higher cost = worse)
_HIGHER_IS_WORSE_METRICS = {"预测CPS"}


def _style_diff_column(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    """Apply green/red background to the 差异 column based on metric favorability."""

    def _cell_style(row):
        styles = [""] * len(row)
        diff_idx = df.columns.get_loc("差异")
        diff_val = row["差异"]
        metric = row["指标"]

        if diff_val == "-":
            return styles

        # Determine sign of the difference
        is_positive = diff_val.startswith("+")
        is_negative = diff_val.startswith("-") and diff_val != "-"

        if not (is_positive or is_negative):
            return styles

        # For cost metrics: positive diff is bad (red), negative diff is good (green)
        # For loan/contribution metrics: positive diff is good (green), negative is bad (red)
        if metric in _HIGHER_IS_WORSE_METRICS:
            color = "#FFEBEE" if is_positive else "#E8F5E9"
        else:
            color = "#E8F5E9" if is_positive else "#FFEBEE"

        styles[diff_idx] = f"background-color: {color}"
        return styles

    return df.style.apply(_cell_style, axis=1)


def _build_comparison_table(t1, t2, mmm_data: dict) -> pd.DataFrame:
    """构建 V01 vs MMM 对照表。"""
    v01_loan = (t1.total_t0_transaction * 10000 + t2.current_month_initial_m0 * 10000) if t2 else t1.total_t0_transaction * 10000
    mmm_loan = mmm_data.get("predicted_loan_amt", 0)

    rows = [
        {
            "指标": "总花费 (万元)",
            "V01 规则层": f"{t1.total_expense:,.0f}",
            "MMM 模型层": f"{mmm_data['total_spend']:,.0f}",
            "差异": "-" if abs(t1.total_expense - mmm_data["total_spend"]) < 1 else f"{(mmm_data['total_spend'] - t1.total_expense) / t1.total_expense:+.1%}",
            "解读": "输入一致" if abs(t1.total_expense - mmm_data["total_spend"]) < 1 else "花费输入不同",
        },
        {
            "指标": "预测借款金额 (万元)",
            "V01 规则层": f"{v01_loan:,.0f}",
            "MMM 模型层": f"{mmm_loan:,.0f}",
            "差异": f"{(mmm_loan - v01_loan) / v01_loan:+.1%}" if v01_loan > 0 else "-",
            "解读": "V01线性外推可能高估" if mmm_loan < v01_loan else "MMM预测更保守" if mmm_loan > v01_loan else "预测接近",
        },
        {
            "指标": "预测CPS",
            "V01 规则层": f"{t2.total_cps:.1%}" if t2 else "-",
            "MMM 模型层": f"{mmm_data['predicted_cps']:.1f}%" if mmm_data.get("predicted_cps") else "-",
            "差异": f"{mmm_data.get('predicted_cps', 0) - (t2.total_cps * 100 if t2 else 0):+.1f}pp",
            "解读": "MMM考虑饱和效应，实际成本可能更高" if mmm_data.get("predicted_cps", 0) > (t2.total_cps * 100 if t2 else 0) else "V01口径成本更高",
        },
    ]

    # 渠道贡献对比
    channels = [ch for ch in t1.channels if ch.channel_name != "总计"]
    mmm_contribs = mmm_data.get("channel_contributions", {})
    for ch in channels:
        v01_pct = ch.expense / t1.total_expense if t1.total_expense > 0 else 0
        mmm_pct = mmm_contribs.get(ch.channel_name, 0)
        diff = mmm_pct - v01_pct
        if abs(diff) > 0.01:
            interpret = "MMM认为贡献更高" if diff > 0 else "MMM认为贡献低于线性预期"
        else:
            interpret = "贡献接近"
        rows.append({
            "指标": f"{ch.channel_name}贡献占比",
            "V01 规则层": f"{v01_pct:.1%}",
            "MMM 模型层": f"{mmm_pct:.1%}" if mmm_pct > 0 else "-",
            "差异": f"{diff:+.1%}" if mmm_pct > 0 else "-",
            "解读": interpret,
        })

    return pd.DataFrame(rows)


def _render_comparison_chart(t1, mmm_data: dict):
    """渠道贡献对比柱状图。"""
    channels = [ch for ch in t1.channels if ch.channel_name != "总计"]
    mmm_contribs = mmm_data.get("channel_contributions", {})

    ch_names = [ch.channel_name for ch in channels]
    v01_pcts = [ch.expense / t1.total_expense * 100 if t1.total_expense > 0 else 0 for ch in channels]
    mmm_pcts = [mmm_contribs.get(ch.channel_name, 0) * 100 for ch in channels]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="V01 规则层", x=ch_names, y=v01_pcts, marker_color="#2E7D32"))
    fig.add_trace(go.Bar(name="MMM 模型层", x=ch_names, y=mmm_pcts, marker_color="#7B1FA2"))
    fig.update_layout(
        title="渠道贡献对比 (V01 vs MMM)",
        yaxis_title="贡献占比 (%)",
        barmode="group",
        height=350,
        margin=dict(t=40, b=40),
        legend=dict(orientation="h", y=1.1),
    )
    return fig


def _render_range_visualization(v01_loan: float, mmm_loan: float, v01_cps: float, mmm_cps: float):
    """Show V01 and MMM predictions as annotated points on a horizontal number line."""
    lo = min(v01_loan, mmm_loan)
    hi = max(v01_loan, mmm_loan)
    mid = (v01_loan + mmm_loan) / 2
    padding = max((hi - lo) * 0.3, hi * 0.05)
    x_min = max(0.0, lo - padding)
    x_max = hi + padding

    fig = go.Figure()

    # Baseline axis line
    fig.add_shape(
        type="line",
        x0=x_min, x1=x_max, y0=0, y1=0,
        line=dict(color="#BDBDBD", width=2),
    )

    # Shaded interval between the two predictions
    fig.add_shape(
        type="rect",
        x0=lo, x1=hi, y0=-0.15, y1=0.15,
        fillcolor="rgba(100, 181, 246, 0.18)",
        line=dict(width=0),
    )

    # V01 marker
    fig.add_trace(go.Scatter(
        x=[v01_loan], y=[0],
        mode="markers+text",
        marker=dict(color="#2E7D32", size=16, symbol="diamond"),
        text=[f"V01<br>{v01_loan:,.0f}万"],
        textposition="top center",
        textfont=dict(size=12, color="#2E7D32"),
        name="V01 规则层",
        hovertemplate=f"V01 借款金额: {v01_loan:,.0f} 万元<br>CPS: {v01_cps:.1%}<extra></extra>",
    ))

    # MMM marker
    fig.add_trace(go.Scatter(
        x=[mmm_loan], y=[0],
        mode="markers+text",
        marker=dict(color="#7B1FA2", size=16, symbol="circle"),
        text=[f"MMM<br>{mmm_loan:,.0f}万"],
        textposition="bottom center",
        textfont=dict(size=12, color="#7B1FA2"),
        name="MMM 模型层",
        hovertemplate=f"MMM 借款金额: {mmm_loan:,.0f} 万元<br>CPS: {mmm_cps:.1f}%<extra></extra>",
    ))

    # Midpoint marker
    fig.add_trace(go.Scatter(
        x=[mid], y=[0],
        mode="markers+text",
        marker=dict(color="#E65100", size=10, symbol="line-ns", line=dict(width=2, color="#E65100")),
        text=[f"中值 {mid:,.0f}万"],
        textposition="top center",
        textfont=dict(size=11, color="#E65100"),
        name="区间中值",
        hovertemplate=f"区间中值: {mid:,.0f} 万元<extra></extra>",
    ))

    fig.update_layout(
        title="借款金额预测区间",
        xaxis=dict(
            title="借款金额 (万元)",
            range=[x_min, x_max],
            showgrid=True,
            gridcolor="#F5F5F5",
        ),
        yaxis=dict(
            visible=False,
            range=[-0.6, 0.6],
        ),
        height=260,
        margin=dict(t=40, b=50, l=20, r=20),
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
        plot_bgcolor="white",
    )
    return fig


def _render_conclusion_panel(v01_loan: float, mmm_loan: float, diff_pct: float, t2, mmm_data: dict):
    """Render a structured conclusion panel with Verdict, Evidence, and Recommendation."""
    mid_loan = (v01_loan + mmm_loan) / 2

    if abs(diff_pct) > 10:
        direction = "偏高" if diff_pct < 0 else "偏低"
        verdict = f"V01 预测比 MMM **{direction} {abs(diff_pct):.0f}%**，两引擎存在显著分歧，建议审查渠道饱和假设。"
    elif abs(diff_pct) > 5:
        direction = "略高" if diff_pct < 0 else "略低"
        verdict = f"V01 预测比 MMM **{direction} {abs(diff_pct):.0f}%**，差异处于中等水平，区间中值可作为规划基准。"
    else:
        verdict = f"双引擎预测差异仅 **{abs(diff_pct):.1f}%**，结果高度一致，预测置信度较高。"

    evidence = [
        f"V01 借款金额：**{v01_loan:,.0f} 万元**，MMM 借款金额：**{mmm_loan:,.0f} 万元**",
        f"区间中值：**{mid_loan:,.0f} 万元**（差异绝对值 {abs(mmm_loan - v01_loan):,.0f} 万元）",
    ]
    if t2:
        evidence.append(f"V01 CPS：**{t2.total_cps:.1%}**")
    mmm_cps = mmm_data.get("predicted_cps", 0)
    if mmm_cps > 0:
        evidence.append(f"MMM CPS：**{mmm_cps:.1f}%**（含饱和效应修正）")

    if abs(diff_pct) > 10:
        recommendation = (
            f"差异超过 10%，建议重新审查高贡献渠道的 Adstock 衰减参数，并以区间中值 **{mid_loan:,.0f} 万元** 为保守规划基准。"
        )
    elif abs(diff_pct) > 5:
        recommendation = (
            f"差异在合理范围内，建议以区间中值 **{mid_loan:,.0f} 万元** 作为目标借款金额，上浮 5% 设置弹性预算。"
        )
    else:
        recommendation = (
            f"双引擎高度吻合，可直接采用中值 **{mid_loan:,.0f} 万元** 作为正式规划目标，无需额外校验。"
        )

    with st.container(border=True):
        st.markdown("#### 对照核心结论")

        st.markdown("**判断**")
        st.markdown(verdict)

        st.markdown("**依据**")
        for item in evidence:
            st.markdown(f"- {item}")

        st.markdown("**建议**")
        st.markdown(recommendation)


def render_tab_model_comparison():
    """模型对照 Tab 主渲染函数。"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")

    if t1 is None or t2 is None:
        st.info("请先完成预算推算，结果将在此处展示。")
        return

    mmm_data = _get_mmm_predictions(t1)
    if mmm_data is None:
        st.info("MMM 模型尚未训练。请先前往 **MMM 模型洞察** 页训练模型后，此处将自动显示 V01 与 MMM 的预测对照。")
        return

    # Edge case: MMM trained but recommended_spends is empty
    has_recommendations = bool(mmm_data.get("recommended_spends"))
    if not has_recommendations:
        st.info("MMM 模型已训练，但尚未运行预算优化。以下对比使用 V01 花费作为 MMM 输入，仅供参考。前往 MMM 模型洞察页完成预算优化后可获得更精确对比。")

    v01_loan = (t1.total_t0_transaction * 10000 + t2.current_month_initial_m0 * 10000) if t2 else t1.total_t0_transaction * 10000
    mmm_loan = mmm_data.get("predicted_loan_amt", 0)
    diff_pct = (mmm_loan - v01_loan) / v01_loan * 100 if v01_loan > 0 else 0

    # Structured conclusion panel
    _render_conclusion_panel(v01_loan, mmm_loan, diff_pct, t2, mmm_data)

    # Color-coded comparison table
    st.markdown("#### V01 规则层 vs MMM 模型层")
    comparison_df = _build_comparison_table(t1, t2, mmm_data)
    styled = _style_diff_column(comparison_df)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Channel contribution chart + range visualization
    col1, col2 = st.columns(2)
    with col1:
        fig = _render_comparison_chart(t1, mmm_data)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        v01_cps = t2.total_cps if t2 else 0.0
        mmm_cps = mmm_data.get("predicted_cps", 0)
        range_fig = _render_range_visualization(v01_loan, mmm_loan, v01_cps, mmm_cps)
        st.plotly_chart(range_fig, use_container_width=True)
