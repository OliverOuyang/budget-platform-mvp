"""Tab 1: 渠道结果"""
import streamlit as st
import pandas as pd
import plotly.express as px


def render_tab_channel_result():
    """渠道结果 Tab"""
    t1 = st.session_state.get("table1_result")

    st.subheader("📊 Table 1 (渠道预测)")
    st.dataframe(
        t1.to_dataframe(),
        width='stretch',
        hide_index=True,
        column_config={
            "渠道名称": st.column_config.TextColumn("渠道", width="small"),
            "1-3 T0过件率": st.column_config.NumberColumn("1-3 T0过件率", format="%.2f%%", width="small"),
            "1-8 T0CPS": st.column_config.NumberColumn("1-8 T0 CPS", format="%.2f%%", width="small"),
            "花费(千万元)": st.column_config.NumberColumn("花费(千万元)", format="%.2f", width="small"),
            "T0申完成本(元)": st.column_config.NumberColumn("T0申完成本(元)", format="%.0f", width="small"),
            "T0交易额(千万元)": st.column_config.NumberColumn("T0交易额(千万元)", format="%.2f", width="small"),
            "当月首登M0交易额(千万元)": st.column_config.NumberColumn("M0交易额(千万元)", format="%.2f", width="small"),
            "1-3 T0授信量": st.column_config.NumberColumn("1-3授信量", format="%,.0f", width="small"),
        }
    )

    st.markdown("---")
    st.subheader("📊 渠道可视化分析")

    channels = [ch for ch in t1.channels if ch.channel_name != "总计"]

    col_a, col_b = st.columns(2)
    with col_a:
        fig_expense = px.pie(
            names=[ch.channel_name for ch in channels],
            values=[ch.expense for ch in channels],
            title="各渠道花费占比", hole=0.4
        )
        fig_expense.update_traces(
            textposition='inside', textinfo='percent+label',
            hovertemplate='<b>%{label}</b><br>花费: %{value:,.0f}万<br>占比: %{percent}<extra></extra>'
        )
        st.plotly_chart(fig_expense, width='stretch')

    with col_b:
        fig_tx = px.bar(
            x=[ch.channel_name for ch in channels],
            y=[ch.t0_transaction * 10 for ch in channels],
            title="T0交易额(千万元)", color_discrete_sequence=['#2E86AB']
        )
        fig_tx.update_traces(
            textposition='outside',
            text=[f"{ch.t0_transaction * 10:.1f}" for ch in channels],
            hovertemplate='<b>%{x}</b><br>T0交易额: %{y:.2f}千万元<extra></extra>'
        )
        fig_tx.update_layout(uniformtext_minsize=10, uniformtext_mode='show')
        st.plotly_chart(fig_tx, width='stretch')

    col_c, col_d = st.columns(2)
    with col_c:
        fig_comp = px.bar(
            x=[ch.channel_name for ch in channels],
            y=[ch.t0_completion_volume for ch in channels],
            title="T0申完量", color_discrete_sequence=['#A23B72']
        )
        fig_comp.update_traces(
            textposition='outside',
            text=[f"{ch.t0_completion_volume:,.0f}" for ch in channels],
            hovertemplate='<b>%{x}</b><br>申完量: %{y:,.0f}笔<extra></extra>'
        )
        fig_comp.update_layout(uniformtext_minsize=10, uniformtext_mode='show')
        st.plotly_chart(fig_comp, width='stretch')

    with col_d:
        fig_appr = px.bar(
            x=[ch.channel_name for ch in channels],
            y=[ch.approval_rate_1_3 * 100 for ch in channels],
            title="1-3 T0过件率(%)", color_discrete_sequence=['#F18F01']
        )
        fig_appr.update_traces(
            textposition='outside',
            text=[f"{ch.approval_rate_1_3 * 100:.1f}" for ch in channels],
            hovertemplate='<b>%{x}</b><br>过件率: %{y:.1f}%<extra></extra>'
        )
        fig_appr.update_layout(uniformtext_minsize=10, uniformtext_mode='show')
        st.plotly_chart(fig_appr, width='stretch')

    st.markdown("---")
    st.subheader("💡 渠道指标明细")
    best_ch = max(channels, key=lambda c: c.t0_transaction / c.expense if c.expense > 0 else 0)
    worst_ch = min(channels, key=lambda c: c.t0_transaction / c.expense if c.expense > 0 else float('inf'))
    best_eff = best_ch.t0_transaction / best_ch.expense * 10000
    worst_eff = worst_ch.t0_transaction / worst_ch.expense * 10000

    for ch in channels:
        exp_share = ch.expense / t1.total_expense * 100 if t1.total_expense > 0 else 0
        cps_disp = (ch.cps_1_8 or 0) * 100
        eff = ch.t0_transaction / ch.expense * 10000 if ch.expense > 0 else 0

        row1_cols = st.columns(5)
        with row1_cols[0]:
            st.metric("渠道", ch.channel_name)
        with row1_cols[1]:
            st.metric("花费", f"{ch.expense:,.0f} 万元", f"{exp_share:.1f}% 占比" if exp_share > 0 else None)
        with row1_cols[2]:
            st.metric("T0交易额", f"{ch.t0_transaction * 10:,.2f} 千万元")
        with row1_cols[3]:
            st.metric("M0交易额", f"{ch.m0_transaction * 10:,.2f} 千万元")
        with row1_cols[4]:
            st.metric("万元效率", f"{eff:.2f} 千元/万元")

        row2_cols = st.columns(5)
        with row2_cols[0]:
            st.caption("1-3 T0过件率")
            st.markdown(f"**{ch.approval_rate_1_3:.2%}**")
        with row2_cols[1]:
            st.caption("T0申完量")
            st.markdown(f"**{ch.t0_completion_volume:,.0f}** 笔")
        with row2_cols[2]:
            st.caption("1-8 T0 CPS")
            st.markdown(f"**{cps_disp:.1f}%**")
        with row2_cols[3]:
            st.caption("计算推导")
            st.caption(f"{ch.expense:,.0f}万÷{cps_disp:.1f}%÷10000→{ch.t0_transaction:.2f}亿")
        with row2_cols[4]:
            flag = ""
            if ch.expense > t1.total_expense * 0.4:
                flag = "⚠️ 占比过高"
            elif ch.approval_rate_1_3 > 0.5:
                flag = "✅ 过件率良好"
            if flag:
                st.caption(flag)
        st.divider()

    # 万元效率排名
    st.subheader("📊 各渠道万元效率排名")
    eff_data = []
    for ch in channels:
        eff = ch.t0_transaction / ch.expense * 10000 if ch.expense > 0 else 0
        eff_data.append({"渠道": ch.channel_name, "万元效率(千元/万元)": eff})
    eff_df = pd.DataFrame(eff_data).sort_values("万元效率(千元/万元)", ascending=False)
    fig_rank = px.bar(eff_df, x="渠道", y="万元效率(千元/万元)", color="万元效率(千元/万元)",
                      title="各渠道万元效率（越高越好）", color_continuous_scale="Greens")
    fig_rank.update_layout(showlegend=False)
    st.plotly_chart(fig_rank, width='stretch')

    st.success(f"🏆 效率冠军: {best_ch.channel_name} — 每万元花费产生T0交易额 {best_eff:.2f}千元，优于最差渠道 {worst_eff:.2f}千元")
