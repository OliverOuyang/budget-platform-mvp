from __future__ import annotations

import streamlit as st
import plotly.graph_objects as go


def _build_key_findings(t1_result, t2_result, prev_t1_result, prev_t2_result) -> list[str]:
    findings = []
    # Exclude "总计" row, only look at channel-level data
    channels = [ch for ch in t1_result.channels if ch.channel_name != "总计"]

    if channels:
        # 1. Best and worst CPS channels (efficiency suggestion)
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

        # 2. Efficiency assessment for highest-spend channel
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

    # 3. CPS trend vs previous calculation
    if prev_t2_result is not None:
        cps_delta = t2_result.total_cps - prev_t2_result.total_cps
        if abs(cps_delta) >= 0.001:
            direction = "下降" if cps_delta < 0 else "上升"
            findings.append(
                f"全业务CPS较上次计算{direction} {abs(cps_delta):.2%}，"
                f"当前为 {t2_result.total_cps:.2%}。"
            )

    # 4. Budget allocation completeness
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


def render_decision_section(t1, t2, prev_t1, prev_t2, flow, decision_summary) -> None:
    """Render the full decision section: smart banner, decision card, and budget charts."""
    has_prev = prev_t1 is not None

    delta_exp = (t1.total_expense - prev_t1.total_expense) if has_prev and prev_t1 else None
    delta_tx = (t2.total_transaction - prev_t2.total_transaction) if has_prev and prev_t2 else None
    delta_cps = (t2.total_cps - prev_t2.total_cps) if has_prev and prev_t2 else None
    delta_t0 = (t1.total_t0_transaction - prev_t1.total_t0_transaction) if has_prev and prev_t1 else None
    delta_apr = (t2.approval_rate_1_3_excl_age - prev_t2.approval_rate_1_3_excl_age) if has_prev and prev_t2 else None

    key_findings = _build_key_findings(t1, t2, prev_t1, prev_t2)

    # --- V4.3c: Smart suggestion banner ---
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
        # a) Core decision conclusion (1-2 sentences)
        status_icon = {"success": "✅", "warning": "⚠️"}.get(decision_summary["status"], "ℹ️")
        st.markdown(f"### {status_icon} {decision_summary['headline']}")
        actions_text = "　".join(decision_summary["recommended_actions"])
        st.markdown(f"<span style='color:#666;font-size:0.9rem;'>{actions_text}</span>", unsafe_allow_html=True)

        st.divider()

        # b) Key status label chips
        chip_items = []
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

        # c) 5 core metric cards
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("总投放花费", f"{t1.total_expense:,.0f} 万元", f"{delta_exp:+,.0f} 万元" if delta_exp is not None else None)
        m2.metric("整体首借交易额", f"{t2.total_transaction:.2f} 亿元", f"{delta_tx:+.2f} 亿元" if delta_tx is not None else None)
        m3.metric("全业务CPS", f"{t2.total_cps:.2%}", f"{delta_cps:+.2%}" if delta_cps is not None else None, delta_color="inverse")
        m4.metric("T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元", f"{delta_t0 * 10:+.2f} 千万元" if delta_t0 is not None else None)
        m5.metric("1-3 T0过件率", f"{t2.approval_rate_1_3_excl_age:.2%}", f"{delta_apr:+.2%}" if delta_apr is not None else None)

        st.divider()

        # d) Key findings (dynamic bullets)
        st.markdown("**关键发现**")
        for finding in key_findings:
            st.markdown(f"- {finding}")

    # --- Budget structure and efficiency overview charts ---
    with st.container(border=True):
        st.markdown("#### 预算结构与效率总览")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            # Channel spend distribution pie chart
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
            # Channel transaction contribution bar chart
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
