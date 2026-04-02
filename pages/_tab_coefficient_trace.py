"""Tab 3: 系数追溯"""
import streamlit as st
import pandas as pd


def render_tab_coefficient_trace():
    """系数追溯 Tab"""
    coef = st.session_state.get("coefficients")
    tr1, tr2 = st.columns(2)
    with tr1:
        st.markdown("**M0/T0 系数追溯**")
        if coef.m0_t0_source_months and coef.m0_t0_ratio_history:
            df_m0t0 = pd.DataFrame({
                "月份": coef.m0_t0_source_months,
                "M0/T0系数": coef.m0_t0_ratio_history
            })
            st.dataframe(df_m0t0, width='stretch', hide_index=True)
        else:
            st.info("暂无M0/T0系数历史数据")
    with tr2:
        st.markdown("**存量首登M0 CPS追溯**")
        if coef.existing_m0_source_months and coef.existing_m0_cps_history:
            df_cps = pd.DataFrame({
                "月份": coef.existing_m0_source_months,
                "CPS": coef.existing_m0_cps_history
            })
            st.dataframe(df_cps, width='stretch', hide_index=True)
        else:
            st.info("暂无存量CPS历史数据")
    _render_impact_analysis()
    st.markdown("---")
    st.markdown("**📖 计算公式说明**")
    st.markdown("""
    **M0/T0系数** = 前6个月各月(当月首登M0交易额 / 首登T0交易额)的均值
    - 含义：M0与T0的换算关系，反映M0用户在整体首借中的占比趋势
    - 计算窗口：前6个月均值
    """)
    st.markdown("""
    **存量首登M0 CPS** = 前3个月各月(存量花费 / 存量首登M0交易额)的均值
    - 含义：存量用户中M0渠道的投放效率
    - 计算窗口：前3个月均值（可在「预算输入」页切换为6个月）
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
        col1.metric("总花费", f"{curr_t1.total_expense:,.0f} 万元",
                    f"{curr_t1.total_expense - prev_t1.total_expense:+.0f} 万元")
        col2.metric("总交易额", f"{curr_t2.total_transaction:.2f} 亿元",
                    f"{curr_t2.total_transaction - prev_t2.total_transaction:+.2f} 亿元")
        col3.metric("全业务CPS", f"{curr_t2.total_cps:.2%}",
                    f"{curr_t2.total_cps - prev_t2.total_cps:+.2%}", delta_color="inverse")
