"""Tab 0: 总览"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from app.ui_utils import normalize_channel_history


def render_tab_overview():
    """总览 Tab"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    p = st.session_state.get("parameters")
    coef = st.session_state.get("coefficients")

    st.caption("💡 核心指标说明：T0交易额 = 花费 ÷ CPS ÷ 10000（亿元）；M0交易额 = T0 × M0/T0系数；申完量 = 花费 × 10000 ÷ 申完成本（笔）")

    # 5步流程卡片
    step_cols = st.columns(5)
    steps = [
        ("① 预算分配", f"{t1.total_expense:,.0f} 万元", "按最新月渠道花费结构分配"),
        ("② 申完量", f"{t1.total_completion_volume:,.0f} 笔", "花费 × 10000 ÷ T0申完成本"),
        ("③ 授信量", f"{sum(ch.credit_volume_1_3 for ch in t1.channels if ch.channel_name != '总计'):,.0f} 笔", "申完量 × 1-3 T0过件率"),
        ("④ T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元", "花费 ÷ CPS ÷ 10000"),
        ("⑤ M0交易额", f"{t1.total_m0_transaction * 10:.2f} 千万元", f"T0 × M0/T0({coef.m0_t0_ratio:.3f})"),
    ]
    for col, (title, value, desc) in zip(step_cols, steps):
        with col.container(border=True):
            st.caption(title)
            st.markdown(f"**{value}**")
            st.caption(desc)

    if st.session_state.get("uploaded_data"):
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

        info_cols = st.columns(3)
        with info_cols[0]:
            st.metric("数据文件", upload["file_name"])
        with info_cols[1]:
            n_months = df_n["月份标签"].nunique() if "月份标签" in df_n.columns else 0
            st.metric("历史月数", n_months)
        with info_cols[2]:
            st.metric("存量首登M0 CPS", f"{coef.existing_m0_cps_avg:.2%}")

        if "月份标签" in df_n.columns and "渠道名称" in df_n.columns:
            st.subheader("📈 关键指标按月趋势")

            monthly_rate = df_n.groupby("月份标签").apply(
                lambda g: (g["1-3t0过件率"] * g["非年龄拒绝申完量"]).sum() /
                          g["非年龄拒绝申完量"].sum() if g["非年龄拒绝申完量"].sum() > 0 else np.nan
            ).reset_index()
            monthly_rate.columns = ["月份", "1-3 T0过件率"]
            monthly_rate = monthly_rate.dropna().sort_values("月份")

            monthly_exp = df_n.groupby("月份标签")["花费"].sum().reset_index()
            monthly_exp.columns = ["月份", "花费(万元)"]
            monthly_exp = monthly_exp.sort_values("月份")

            monthly_t0 = df_n.groupby("月份标签")["1-8t0首借24h借款金额"].sum().reset_index()
            monthly_t0.columns = ["月份", "T0交易额(亿元)"]
            monthly_t0["T0交易额(亿元)"] = monthly_t0["T0交易额(亿元)"] / 1e8
            monthly_t0 = monthly_t0.sort_values("月份")

            r1, r2 = st.columns(2)
            with r1:
                fig1 = px.line(monthly_rate, x="月份", y="1-3 T0过件率", markers=True)
                fig1.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig1, width='stretch')
            with r2:
                fig2 = px.line(monthly_exp, x="月份", y="花费(万元)", markers=True)
                fig2.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig2, width='stretch')

            r3, r4 = st.columns(2)
            with r3:
                fig3 = px.line(monthly_t0, x="月份", y="T0交易额(亿元)", markers=True)
                fig3.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig3, width='stretch')
            with r4:
                merged = monthly_exp.merge(monthly_t0, on="月份")
                merged["全业务CPS"] = merged["花费(万元)"] / (merged["T0交易额(亿元)"] * 1e4)
                fig4 = px.line(merged, x="月份", y="全业务CPS", markers=True)
                fig4.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig4, width='stretch')

            # 定位图
            st.subheader("📍 当前预算方案在历史趋势中的定位")
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
                fig_pos.update_layout(
                    title=f"花费趋势 + 当前方案定位（最新月: {latest_exp:,.0f}万 → 当前: {current_exp:,.0f}万）",
                    height=260, margin=dict(l=20, r=20, t=40, b=20), showlegend=True
                )
                st.plotly_chart(fig_pos, width='stretch')
                exp_vs_hist = (current_exp - latest_exp) / latest_exp * 100 if latest_exp > 0 else 0
                st.info(
                    f"📌 当前方案花费**{current_exp:,.0f}万**，较最新月历史数据"
                    f"{'**+' if exp_vs_hist > 0 else ''}{exp_vs_hist:.1f}%。"
                    f"当前值基于渠道参数配置重新分配，非历史实际值。"
                )

        # 方案对比
        _render_scenario_comparison()
        # 数据洞察
        _render_insights(df_n)


def _render_scenario_comparison():
    """方案对比（内联）"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    scenarios = st.session_state.get("comparison_scenarios")
    st.subheader("📊 方案对比")
    if scenarios:
        best_name = None
        best_score = None
        for name, s in scenarios.items():
            score = float(s["table2"].total_transaction) - float(s["table2"].total_cps) * 100
            if best_score is None or score > best_score:
                best_score = score
                best_name = name

        comp_rows = [{
            "方案": "【当前方案】",
            "总花费(万元)": f"{t1.total_expense:,.0f}",
            "T0交易额(千万元)": f"{t1.total_t0_transaction * 10:,.2f}",
            "全业务CPS": f"{t2.total_cps:.2%}",
            "1-3 T0过件率": f"{t2.approval_rate_1_3_excl_age:.2%}",
        }]
        for name, s in scenarios.items():
            t1s, t2s = s["table1"], s["table2"]
            comp_rows.append({
                "方案": name,
                "总花费(万元)": f"{t1s.total_expense:,.0f}",
                "T0交易额(千万元)": f"{t1s.total_t0_transaction * 10:,.2f}",
                "全业务CPS": f"{t2s.total_cps:.2%}",
                "1-3 T0过件率": f"{t2s.approval_rate_1_3_excl_age:.2%}",
            })
        st.dataframe(pd.DataFrame(comp_rows), width='stretch', hide_index=True)
        if best_name is not None:
            best = scenarios[best_name]
            tradeoff = "规模提升，但 CPS 压力更大"
            if t2.total_cps <= best["table2"].total_cps and t2.total_transaction >= best["table2"].total_transaction:
                tradeoff = "当前方案优于最佳已保存方案，可考虑替换。"
            elif t2.total_cps > best["table2"].total_cps and t2.total_transaction >= best["table2"].total_transaction:
                tradeoff = "当前方案规模更高，但成本压力高于最佳已保存方案。"
            elif t2.total_cps <= best["table2"].total_cps and t2.total_transaction < best["table2"].total_transaction:
                tradeoff = "当前方案成本更稳，但规模逊于最佳已保存方案。"
            st.info(f"📌 方案定位：最佳已保存方案为 **{best_name}**。{tradeoff}")

        st.markdown("**当前方案与已保存方案指标差值：**")
        delta_cols = st.columns(len(scenarios)) if len(scenarios) <= 4 else 2
        for i, (name, s) in enumerate(scenarios.items()):
            t1s, t2s = s["table1"], s["table2"]
            with (delta_cols[i % len(delta_cols)] if len(scenarios) <= 4 else delta_cols[i % 2]):
                with st.container(border=True):
                    st.caption(f"📌 {name}")
                    exp_d = t1.total_expense - t1s.total_expense
                    cps_d = t2.total_cps - t2s.total_cps
                    apr_d = t2.approval_rate_1_3_excl_age - t2s.approval_rate_1_3_excl_age
                    t0_d = t1.total_t0_transaction - t1s.total_t0_transaction
                    st.metric("总花费差", f"{exp_d:+,.0f} 万元")
                    st.metric("T0交易额差", f"{t0_d * 10:+.2f} 千万元")
                    st.caption(f"{'✅ CPS更低(更优)' if cps_d > 0 else '⚠️ CPS更高(需关注)'} {cps_d:+.2%}")
                    st.caption(f"{'✅ 过件率提升' if apr_d > 0 else '⚠️ 过件率下降'} {apr_d:+.2%}")

        st.markdown("**渠道维度拆解（与各方案对比）：**")
        ch_rows = []
        for ch_cur in t1.channels:
            if ch_cur.channel_name == "总计":
                continue
            for name, s in scenarios.items():
                t1s = s["table1"]
                ch_s = next((c for c in t1s.channels if c.channel_name == ch_cur.channel_name), None)
                if ch_s:
                    exp_diff = ch_cur.expense - ch_s.expense
                    t0_diff = ch_cur.t0_transaction - ch_s.t0_transaction
                    if abs(exp_diff) > 0.1 or abs(t0_diff) > 0.01:
                        ch_rows.append({
                            "对比方案": name, "渠道": ch_cur.channel_name,
                            "花费差(万元)": f"{exp_diff:+,.0f}",
                            "T0交易额差(千万元)": f"{t0_diff * 10:+.2f}",
                        })
        if ch_rows:
            st.dataframe(pd.DataFrame(ch_rows), width='stretch', hide_index=True)
            st.caption("💡 花费差>0表示当前方案该渠道分配更多预算；T0交易额差由渠道1-3过件率和1-8 CPS参数共同决定。")
        else:
            st.caption("各渠道参数与保存方案无显著差异。")
    else:
        st.info("暂无已保存方案，请在「方案管理」中保存方案后查看对比")


def _render_insights(df_n):
    """数据洞察（内联）"""
    st.subheader("💡 数据洞察")
    if "月份标签" in df_n.columns:
        monthly_rate = df_n.groupby("月份标签").apply(
            lambda g: (g["1-3t0过件率"] * g["非年龄拒绝申完量"]).sum() /
                      g["非年龄拒绝申完量"].sum() if g["非年龄拒绝申完量"].sum() > 0 else np.nan
        ).reset_index()
        monthly_rate.columns = ["月份", "1-3 T0过件率"]
        monthly_rate = monthly_rate.dropna()
        if len(monthly_rate) >= 2:
            first_val = monthly_rate["1-3 T0过件率"].iloc[0]
            last_val = monthly_rate["1-3 T0过件率"].iloc[-1]
            trend_pct = (last_val - first_val) / first_val * 100 if first_val else 0
            trend_word = "上升" if trend_pct > 2 else ("下降" if trend_pct < -2 else "平稳")
            top_ch = df_n.groupby("渠道名称")["花费"].sum().idxmax()
            st.info(f"📌 近{len(monthly_rate)}个月1-3 T0过件率呈**{trend_word}**趋势(整体{trend_pct:+.1f}%)，主要受**{top_ch}**渠道影响。")
        monthly_exp = df_n.groupby("月份标签")["花费"].sum().reset_index()
        monthly_exp.columns = ["月份", "花费(万元)"]
        monthly_exp = monthly_exp.sort_values("月份")
        if len(monthly_exp) >= 2:
            latest_exp = monthly_exp["花费(万元)"].iloc[-1]
            prev_exp = monthly_exp["花费(万元)"].iloc[-2]
            exp_change = (latest_exp - prev_exp) / prev_exp * 100 if prev_exp else 0
            latest_month = monthly_exp["月份"].iloc[-1]
            latest_t0 = df_n.groupby("月份标签")["1-8t0首借24h借款金额"].sum().reset_index()
            latest_t0.columns = ["月份", "T0"]
            latest_t0["T0"] = latest_t0["T0"] / 1e8
            latest_t0_val = latest_t0[latest_t0["月份"] == latest_month]["T0"].iloc[-1] if not latest_t0[latest_t0["月份"] == latest_month].empty else 0
            st.info(f"📌 {latest_month}总花费**{latest_exp:,.0f}**万元，较前一月{exp_change:+.1f}%。T0交易额**{latest_t0_val:.2f}**亿元。")
