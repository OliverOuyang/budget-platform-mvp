"""Tab 2: 客群结果"""
import streamlit as st
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go


def render_tab_customer_result():
    """客群结果 Tab"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    coef = st.session_state.get("coefficients")

    if t1 is None or t2 is None:
        st.info("请先在左侧完成预算推算，结果将在此处展示。")
        return

    st.subheader("👥 Table 2 (客群汇总)")
    st.markdown(t2.to_html(), unsafe_allow_html=True)

    st.subheader("📊 交易额构成分析")
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        fig_donut = px.pie(
            names=["当月首登M0", "首登T0", "存量首登M0", "非初审授信户"],
            values=[t2.current_month_initial_m0, t2.first_login_t0,
                    t2.existing_initial_m0, t2.non_initial_credit],
            title="整体首借交易额构成",
            hole=0.5,
            color_discrete_sequence=["#4C6EF5", "#12B886", "#F59F00", "#E64980"]
        )
        fig_donut.update_traces(
            textposition='inside', textinfo='percent+value',
            hovertemplate='%{label}<br>%{percent}<br>%{value:.2f}亿<extra></extra>'
        )
        st.plotly_chart(fig_donut, width='stretch')

    with chart_col2:
        segments = ["当月首登", "存量首登", "非初审"]
        expenses = [t1.total_expense, t2.calculated_existing_m0_expense, 0]
        transactions = [
            (t2.current_month_initial_m0 + t2.first_login_t0) * 10,
            t2.existing_initial_m0 * 10,
            t2.non_initial_credit * 10
        ]
        fig_eff = make_subplots(specs=[[{"secondary_y": True}]])
        fig_eff.add_trace(go.Bar(x=segments, y=expenses, name="花费(万元)", marker_color="#4C6EF5"), secondary_y=False)
        fig_eff.add_trace(go.Bar(x=segments, y=transactions, name="交易额(千万元)", marker_color="#12B886"), secondary_y=True)
        fig_eff.update_layout(title="各客群花费与交易额对比", barmode='group')
        fig_eff.update_yaxes(title_text="花费(万元)", secondary_y=False)
        fig_eff.update_yaxes(title_text="交易额(千万元)", secondary_y=True)
        st.plotly_chart(fig_eff, width='stretch')

    st.subheader("📋 客群CPS效率对比")
    eff_data = []
    if t1.total_expense > 0 and (t2.current_month_initial_m0 + t2.first_login_t0) > 0:
        eff = (t1.total_expense + t2.rta_promotion_fee) / (t2.current_month_initial_m0 + t2.first_login_t0) / 10000
        eff_data.append({
            "客群": "当月首登",
            "花费(万元)": f"{t1.total_expense + t2.rta_promotion_fee:,.0f}",
            "交易额(亿元)": f"{t2.current_month_initial_m0 + t2.first_login_t0:.2f}",
            "CPS": f"{eff:.2%}",
            "效率": "高" if eff < t2.total_cps else "低"
        })
    if t2.calculated_existing_m0_expense > 0 and t2.existing_initial_m0 > 0:
        eff = t2.calculated_existing_m0_expense / t2.existing_initial_m0 / 10000
        eff_data.append({
            "客群": "存量首登",
            "花费(万元)": f"{t2.calculated_existing_m0_expense:,.0f}",
            "交易额(亿元)": f"{t2.existing_initial_m0:.2f}",
            "CPS": f"{eff:.2%}",
            "效率": "高" if eff < t2.total_cps else "低"
        })
    if t2.non_initial_credit > 0:
        eff_data.append({
            "客群": "非初审授信户",
            "花费(万元)": "—(手动输入)",
            "交易额(亿元)": f"{t2.non_initial_credit:.2f}",
            "CPS": "—",
            "效率": "参考"
        })
    eff_data.append({
        "客群": "全业务合计",
        "花费(万元)": f"{t1.total_expense + t2.calculated_existing_m0_expense + t2.rta_promotion_fee:,.0f}",
        "交易额(亿元)": f"{t2.total_transaction:.2f}",
        "CPS": f"{t2.total_cps:.2%}",
        "效率": "基准"
    })
    st.dataframe(pd.DataFrame(eff_data), width='stretch', hide_index=True)

    st.subheader("💡 客群分析结论")
    st.info(
        f"**初审授信户贡献**: "
        f"当月首登({t2.current_month_initial_m0:.2f}亿) + 首登T0({t2.first_login_t0:.2f}亿) + "
        f"存量首登({t2.existing_initial_m0:.2f}亿) = **{t2.initial_credit_total:.2f}亿**，"
        f"占总交易额**{(t2.current_month_initial_m0 + t2.first_login_t0 + t2.existing_initial_m0) / t2.total_transaction:.1%}**"
    )
    ratio = t2.current_month_initial_m0 / t2.first_login_t0 if t2.first_login_t0 > 0 else 0
    st.info(
        f"**M0/T0比例**: 当前M0交易额({t2.current_month_initial_m0:.2f}亿) / T0交易额({t2.first_login_t0:.2f}亿) "
        f"= **{ratio:.2f}**，"
        f"M0略{'高于' if ratio > 1 else '低于'}T0规模"
    )
    st.info(
        f"**全业务CPS**: (总花费{t1.total_expense:,.0f}万 + RTA{t2.rta_promotion_fee:,.0f}万) "
        f"/ 总交易额{t2.total_transaction:.2f}亿 / 10000 = **{t2.total_cps:.2%}**，"
        f"即每借出**{1/t2.total_cps*10000:.0f}**元需花费1元"
    )

    st.markdown("**各客群计算逻辑:**")
    st.markdown(f"- **当月首登M0 ({t2.current_month_initial_m0:.2f}亿)**: 来源于Table1各渠道T0交易额 × M0/T0系数 = {t2.current_month_initial_m0:.2f}亿")
    st.markdown(f"- **首登T0 ({t2.first_login_t0:.2f}亿)**: Table1汇总T0交易额 = {t2.first_login_t0:.2f}亿")
    st.markdown(f"- **存量首登M0 ({t2.existing_initial_m0:.2f}亿)**: 存量花费{t2.calculated_existing_m0_expense:,.0f}万 / 存量CPS {coef.existing_m0_cps_avg:.2%} / 10000 = {t2.existing_initial_m0:.2f}亿")
    st.markdown(f"- **非初审授信户 ({t2.non_initial_credit:.2f}亿)**: 手动输入值，直接计入汇总")
