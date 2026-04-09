"""Overview tab extracted sections: scenario comparison & data insights."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np


def weighted_approval_rate(g):
    """加权过件率：按非年龄拒绝申完量加权。供 overview 各处 groupby.apply 使用。"""
    total_weight = g["非年龄拒绝申完量"].sum()
    if total_weight > 0:
        return (g["1-3t0过件率"] * g["非年龄拒绝申完量"]).sum() / total_weight
    return np.nan


def render_scenario_comparison():
    """方案对比"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    scenarios = st.session_state.get("comparison_scenarios")
    st.subheader("方案对比")
    if not scenarios:
        st.info("暂无已保存方案，请在「方案与导出」中保存方案后查看对比")
        return

    best_name = None
    best_score = None
    for name, s in scenarios.items():
        score = float(s["table2"].total_transaction) - float(s["table2"].total_cps) * 100
        if best_score is None or score > best_score:
            best_score = score
            best_name = name

    # 结论先行
    if best_name:
        best = scenarios[best_name]
        if t2.total_cps <= best["table2"].total_cps and t2.total_transaction >= best["table2"].total_transaction:
            st.success(f"当前方案优于最佳已保存方案 **{best_name}**（CPS更低且交易额更高），建议保存。")
        elif t2.total_cps > best["table2"].total_cps:
            st.warning(f"当前方案CPS高于 **{best_name}**，成本压力较大，建议继续优化。")
        else:
            st.info(f"当前方案与 **{best_name}** 互有优劣，需综合判断。")

    comp_rows = [{
        "方案": "【当前方案】",
        "总花费(万元)": f"{t1.total_expense:,.0f}",
        "T0交易额(千万元)": f"{t1.total_t0_transaction * 10:,.2f}",
        "全业务CPS": f"{t2.total_cps:.2%}",
        "1-3 T0过件率": f"{t2.approval_rate_1_3_excl_age:.2%}",
    }]
    for name, s in scenarios.items():
        t1s, t2s = s["table1"], s["table2"]
        label = f"{name} {'(推荐)' if name == best_name else ''}"
        comp_rows.append({
            "方案": label,
            "总花费(万元)": f"{t1s.total_expense:,.0f}",
            "T0交易额(千万元)": f"{t1s.total_t0_transaction * 10:,.2f}",
            "全业务CPS": f"{t2s.total_cps:.2%}",
            "1-3 T0过件率": f"{t2s.approval_rate_1_3_excl_age:.2%}",
        })
    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

    st.markdown("**指标差值明细：**")
    delta_cols = st.columns(min(len(scenarios), 4))
    for i, (name, s) in enumerate(scenarios.items()):
        t1s, t2s = s["table1"], s["table2"]
        with delta_cols[i % len(delta_cols)]:
            with st.container(border=True):
                st.caption(f"vs {name}")
                exp_d = t1.total_expense - t1s.total_expense
                cps_d = t2.total_cps - t2s.total_cps
                apr_d = t2.approval_rate_1_3_excl_age - t2s.approval_rate_1_3_excl_age
                t0_d = t1.total_t0_transaction - t1s.total_t0_transaction
                st.metric("总花费差", f"{exp_d:+,.0f} 万元")
                st.metric("T0交易额差", f"{t0_d * 10:+.2f} 千万元")
                st.caption(f"{'✅ CPS更低' if cps_d < 0 else '⚠️ CPS更高'} {cps_d:+.2%}")
                st.caption(f"{'✅ 过件率提升' if apr_d > 0 else '⚠️ 过件率下降'} {apr_d:+.2%}")

    # 渠道维度拆解
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
        with st.expander("渠道维度拆解", expanded=False):
            st.dataframe(pd.DataFrame(ch_rows), use_container_width=True, hide_index=True)
            st.caption("花费差>0表示当前方案该渠道分配更多预算；T0交易额差由渠道过件率和CPS参数共同决定。")


def render_insights(df_n):
    """数据洞察"""
    st.subheader("数据洞察")
    if "月份标签" not in df_n.columns:
        return

    insights = []

    monthly_rate = df_n.groupby("月份标签").apply(weighted_approval_rate, include_groups=False).reset_index()
    monthly_rate.columns = ["月份", "1-3 T0过件率"]
    monthly_rate = monthly_rate.dropna()
    if len(monthly_rate) >= 2:
        first_val = monthly_rate["1-3 T0过件率"].iloc[0]
        last_val = monthly_rate["1-3 T0过件率"].iloc[-1]
        trend_pct = (last_val - first_val) / first_val * 100 if first_val else 0
        trend_word = "上升" if trend_pct > 2 else ("下降" if trend_pct < -2 else "平稳")
        top_ch = df_n.groupby("渠道名称")["花费"].sum().idxmax()
        insights.append(
            f"**过件率趋势{trend_word}**：近{len(monthly_rate)}个月整体变动{trend_pct:+.1f}%，"
            f"主要受 **{top_ch}** 渠道影响"
        )

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
        t0_val = latest_t0[latest_t0["月份"] == latest_month]["T0"].iloc[-1] if not latest_t0[latest_t0["月份"] == latest_month].empty else 0
        insights.append(
            f"**{latest_month}花费{latest_exp:,.0f}万元**，环比{exp_change:+.1f}%，"
            f"T0交易额 {t0_val:.2f}亿元"
        )

    for insight in insights:
        st.info(f"{insight}")
