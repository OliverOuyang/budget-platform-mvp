"""Tab 3: 系数追溯"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go


def render_tab_coefficient_trace():
    """系数追溯 Tab"""
    coef = st.session_state.get("coefficients")
    if coef is None:
        st.info("暂无系数数据，请先完成预算推算。")
        return

    _render_coefficient_conclusions(coef)
    st.markdown("---")
    _render_coefficient_tables(coef)
    _render_coefficient_charts(coef)
    st.markdown("---")
    _render_impact_analysis()
    st.markdown("---")
    _render_formula_explanation()


def _render_coefficient_conclusions(coef):
    """系数结论区（顶部摘要）"""
    m0t0_history = coef.m0_t0_ratio_history or []
    cps_history = coef.existing_m0_cps_history or []

    # 计算M0/T0近月稳定性
    m0t0_stability_text = ""
    if len(m0t0_history) >= 2:
        mean_val = sum(m0t0_history) / len(m0t0_history)
        max_dev = max(abs(v - mean_val) / mean_val for v in m0t0_history if mean_val > 0) * 100
        stability = "近月稳定，波动小于3%，可信度高" if max_dev < 3 else f"近月波动约 {max_dev:.1f}%，请注意"
        m0t0_stability_text = stability
    else:
        m0t0_stability_text = "历史数据不足，置信度待验证"

    # 计算CPS趋势
    cps_trend_text = ""
    if len(cps_history) >= 2:
        first_val = cps_history[0]
        last_val = cps_history[-1]
        change_pct = (last_val - first_val) / first_val * 100 if first_val > 0 else 0
        if abs(change_pct) < 3:
            cps_trend_text = "近月趋势平稳"
        elif change_pct > 0:
            cps_trend_text = f"近月呈上升趋势（+{change_pct:.1f}%），投放成本有所增加"
        else:
            cps_trend_text = f"近月呈下降趋势（{change_pct:.1f}%），投放效率改善"
    else:
        cps_trend_text = "历史数据不足，趋势待观察"

    st.subheader("🔍 系数可信度评估")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.caption("M0/T0 系数")
            st.markdown(f"**{coef.m0_t0_ratio:.3f}**（6月均值）")
            st.caption(m0t0_stability_text)
    with c2:
        with st.container(border=True):
            st.caption("存量M0 CPS")
            st.markdown(f"**{coef.existing_m0_cps_avg:.2%}**（3月均值）")
            st.caption(cps_trend_text)


def _highlight_outliers_m0t0(df, mean_val):
    """M0/T0系数表条件格式：偏离均值>10%标红，均值行加粗灰底"""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for i, row in df.iterrows():
        if row["月份"] == "均值":
            styles.loc[i] = "font-weight: bold; background-color: #f0f0f0;"
        else:
            try:
                val = float(row["M0/T0系数"])
                if mean_val > 0 and abs(val - mean_val) / mean_val > 0.10:
                    styles.loc[i, "M0/T0系数"] = "color: #d32f2f; font-weight: bold;"
            except (ValueError, TypeError):
                pass
    return styles


def _highlight_outliers_cps(df, mean_val):
    """CPS表条件格式：偏离均值>10%标红，均值行加粗灰底"""
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for i, row in df.iterrows():
        if row["月份"] == "均值":
            styles.loc[i] = "font-weight: bold; background-color: #f0f0f0;"
        else:
            try:
                raw = str(row["CPS"]).replace("%", "")
                val = float(raw) / 100
                if mean_val > 0 and abs(val - mean_val) / mean_val > 0.10:
                    styles.loc[i, "CPS"] = "color: #d32f2f; font-weight: bold;"
            except (ValueError, TypeError):
                pass
    return styles


def _render_coefficient_tables(coef):
    """系数表（带条件格式）"""
    tr1, tr2 = st.columns(2)

    with tr1:
        st.markdown("**M0/T0 系数追溯**")
        if coef.m0_t0_source_months and coef.m0_t0_ratio_history:
            mean_m0t0 = coef.m0_t0_ratio
            rows = list(zip(coef.m0_t0_source_months, coef.m0_t0_ratio_history))
            rows.append(("均值", mean_m0t0))
            df_m0t0 = pd.DataFrame(rows, columns=["月份", "M0/T0系数"])
            # 格式化显示列（保留3位小数）
            df_display = df_m0t0.copy()
            df_display["M0/T0系数"] = df_display["M0/T0系数"].apply(lambda x: f"{x:.3f}")
            styled = df_display.style.apply(
                lambda _: _highlight_outliers_m0t0(df_display, mean_m0t0),
                axis=None
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("暂无M0/T0系数历史数据")

    with tr2:
        st.markdown("**存量首登M0 CPS追溯**")
        if coef.existing_m0_source_months and coef.existing_m0_cps_history:
            mean_cps = coef.existing_m0_cps_avg
            rows = list(zip(coef.existing_m0_source_months, coef.existing_m0_cps_history))
            rows.append(("均值", mean_cps))
            df_cps = pd.DataFrame(rows, columns=["月份", "CPS"])
            # 格式化显示列（百分比）
            df_display = df_cps.copy()
            df_display["CPS"] = df_display["CPS"].apply(lambda x: f"{x:.2%}")
            styled = df_display.style.apply(
                lambda _: _highlight_outliers_cps(df_display, mean_cps),
                axis=None
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.info("暂无存量CPS历史数据")


def _render_coefficient_charts(coef):
    """系数趋势折线图（M0/T0 + CPS）"""
    has_m0t0 = bool(coef.m0_t0_source_months and coef.m0_t0_ratio_history)
    has_cps = bool(coef.existing_m0_source_months and coef.existing_m0_cps_history)
    if not has_m0t0 and not has_cps:
        return

    c1, c2 = st.columns(2)

    with c1:
        if has_m0t0:
            months = coef.m0_t0_source_months
            values = coef.m0_t0_ratio_history
            mean_val = coef.m0_t0_ratio
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=values,
                mode="lines+markers",
                name="M0/T0系数",
                line=dict(color="#4C6EF5", width=2),
                marker=dict(size=7)
            ))
            fig.add_hline(
                y=mean_val,
                line_dash="dash",
                line_color="#FF6B6B",
                annotation_text=f"均值 {mean_val:.3f}",
                annotation_position="top right"
            )
            fig.update_layout(
                title="M0/T0系数月度走势",
                height=260,
                margin=dict(l=20, r=20, t=40, b=20),
                yaxis_title="系数值",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        if has_cps:
            months = coef.existing_m0_source_months
            values = coef.existing_m0_cps_history
            mean_val = coef.existing_m0_cps_avg
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=months, y=[v * 100 for v in values],
                mode="lines+markers",
                name="存量M0 CPS",
                line=dict(color="#20C997", width=2),
                marker=dict(size=7)
            ))
            fig.add_hline(
                y=mean_val * 100,
                line_dash="dash",
                line_color="#FF6B6B",
                annotation_text=f"均值 {mean_val:.2%}",
                annotation_position="top right"
            )
            fig.update_layout(
                title="存量M0 CPS月度走势",
                height=260,
                margin=dict(l=20, r=20, t=40, b=20),
                yaxis_title="CPS (%)",
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)


def _render_formula_explanation():
    """计算公式说明（折叠展示）"""
    with st.expander("📖 计算公式说明", expanded=False):
        st.markdown("#### M0/T0 系数")
        st.markdown("""
| 项目 | 说明 |
|------|------|
| **公式** | 前6个月各月（当月首登M0交易额 ÷ 首登T0交易额）的均值 |
| **含义** | M0与T0的换算关系，反映M0用户在整体首借中的占比趋势 |
| **计算窗口** | 前6个月均值 |
| **异常判定** | 当月值偏离均值 >10% 时标红提示 |
        """)
        st.markdown("#### 存量首登M0 CPS")
        st.markdown("""
| 项目 | 说明 |
|------|------|
| **公式** | 前3个月各月（存量花费 ÷ 存量首登M0交易额）的均值 |
| **含义** | 存量用户中M0渠道的投放效率 |
| **计算窗口** | 前3个月均值（可在「预算输入」页切换为6个月） |
| **异常判定** | 当月值偏离均值 >10% 时标红提示 |
        """)


def _render_impact_analysis():
    """参数实时影响分析面板"""
    prev_p = st.session_state.get("previous_parameters")
    prev_t1 = st.session_state.get("previous_table1_result")
    prev_t2 = st.session_state.get("previous_table2_result")
    curr_t1 = st.session_state.get("table1_result")
    curr_t2 = st.session_state.get("table2_result")
    if not all([prev_p, prev_t1, prev_t2]):
        return

    with st.expander("📊 参数影响分析", expanded=True):
        col1, col2, col3 = st.columns(3)

        exp_delta = curr_t1.total_expense - prev_t1.total_expense
        txn_delta = curr_t2.total_transaction - prev_t2.total_transaction
        cps_delta = curr_t2.total_cps - prev_t2.total_cps

        # 变化幅度条件着色：通过 delta_color 参数控制
        col1.metric(
            "总花费",
            f"{curr_t1.total_expense:,.0f} 万元",
            f"{exp_delta:+.0f} 万元"
        )
        col2.metric(
            "总交易额",
            f"{curr_t2.total_transaction:.2f} 亿元",
            f"{txn_delta:+.2f} 亿元"
        )
        col3.metric(
            "全业务CPS",
            f"{curr_t2.total_cps:.2%}",
            f"{cps_delta:+.2%}",
            delta_color="inverse"
        )

        # 变化幅度着色说明
        change_notes = []
        if abs(exp_delta) / max(prev_t1.total_expense, 1) > 0.10:
            change_notes.append(f"花费变动超过10%（{exp_delta:+.0f}万），请确认预算调整意图。")
        if abs(cps_delta) / max(prev_t2.total_cps, 0.001) > 0.10:
            direction = "恶化" if cps_delta > 0 else "改善"
            change_notes.append(f"CPS {direction}超过10%（{cps_delta:+.2%}），建议检查渠道参数。")

        for note in change_notes:
            st.warning(note)
