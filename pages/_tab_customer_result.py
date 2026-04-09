"""Tab 2: 客群结果（重构版：结论先行 + 计算逻辑标注 + 层级清晰）"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


# ---------------------------------------------------------------------------
# 辅助：DataFrame Styler（替代 to_html，实现层级缩进 + 条件背景色）
# ---------------------------------------------------------------------------

def _style_table2(df: pd.DataFrame):
    """对 Table2 DataFrame 应用条件格式：整体行蓝色、效率行橙色、费用行灰色。"""

    def row_style(row):
        indicator = row["指标"]
        stripped = indicator.strip()
        # 整体首借交易额行 → 蓝色加粗
        if stripped == "整体首借交易额":
            return ["background-color: #E3F2FD; font-weight: bold"] * len(row)
        # 效率指标分区标题 + 指标行 → 橙色系
        if stripped in ("─── 效率指标 ───", "全业务CPS", "1-3组T0过件率（排年龄）"):
            return ["background-color: #FFF3E0; color: #E65100"] * len(row)
        # 费用分区标题 + 费用行 → 灰色系
        if stripped in ("─── 费用汇总 ───", "投放花费", "RTA费用+促申完"):
            return ["background-color: #F5F5F5; color: #616161"] * len(row)
        return [""] * len(row)

    display_df = df.drop(columns=["层级"], errors="ignore")
    return display_df.style.apply(row_style, axis=1)


# ---------------------------------------------------------------------------
# 主渲染函数
# ---------------------------------------------------------------------------

def render_tab_customer_result():
    """客群结果 Tab"""
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    coef = st.session_state.get("coefficients")

    if t1 is None or t2 is None:
        st.info("请先在左侧完成预算推算，结果将在此处展示。")
        return

    # -----------------------------------------------------------------------
    # 1. 客群核心结论区（结论先行）
    # -----------------------------------------------------------------------
    with st.container(border=True):
        st.markdown("#### 客群核心结论")

        # 预先计算各项指标
        initial_total = t2.current_month_initial_m0 + t2.first_login_t0 + t2.existing_initial_m0
        initial_pct = initial_total / t2.total_transaction if t2.total_transaction > 0 else 0
        non_initial_pct = t2.non_initial_credit / t2.total_transaction if t2.total_transaction > 0 else 0
        m0_t0_ratio = (
            t2.current_month_initial_m0 / t2.first_login_t0 if t2.first_login_t0 > 0 else 0
        )
        existing_cps = coef.existing_m0_cps_avg if coef else 0
        # 存量CPS合理区间判断（与全业务CPS比较）
        existing_cps_label = (
            "低于全业务CPS，表现较优"
            if existing_cps < t2.total_cps
            else "高于全业务CPS，需关注"
        )

        conclusions = [
            (
                "整体规模 & 效率",
                f"整体首借 **{t2.total_transaction:.2f}亿**，全业务CPS **{t2.total_cps:.1%}**",
                f"总花费 {t1.total_expense + t2.rta_promotion_fee:,.0f} 万元 ÷ 首借 {t2.total_transaction:.2f}亿 ÷ 10000",
            ),
            (
                "初审 vs 非初审",
                f"初审占 **{initial_pct:.0%}** 为主体，非初审占 **{non_initial_pct:.0%}**",
                f"初审 {initial_total:.2f}亿 / 总交易额 {t2.total_transaction:.2f}亿",
            ),
            (
                "M0/T0 比例",
                f"M0 是 T0 的 **{m0_t0_ratio:.2f}倍**（{'M0 > T0，当月激活效果好' if m0_t0_ratio >= 1 else 'M0 < T0，激活转化待提升'}）",
                f"当月M0 {t2.current_month_initial_m0:.2f}亿 ÷ 首登T0 {t2.first_login_t0:.2f}亿",
            ),
            (
                "存量M0 CPS评估",
                f"存量CPS **{existing_cps:.1%}**，{existing_cps_label}",
                f"来源：历史均值，存量花费 {t2.calculated_existing_m0_expense:,.0f} 万元",
            ),
        ]

        cols = st.columns(4)
        for col, (title, body, caption_text) in zip(cols, conclusions):
            with col:
                st.caption(title)
                st.markdown(body)
                st.caption(caption_text)

    # -----------------------------------------------------------------------
    # 2. Table 2 客群汇总表（Styler，不用 to_html）
    # -----------------------------------------------------------------------
    st.subheader("客群汇总（Table 2）")
    st.caption(
        "层级说明：整体首借 = 初审授信户（当月M0 + 首登T0 + 存量M0）+ 非初审授信户"
    )

    t2_df = t2.to_dataframe()
    styled = _style_table2(t2_df)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # 3. 交易额构成分析（环形图 + 瀑布图 + 花费vs交易额对比图）
    # -----------------------------------------------------------------------
    st.subheader("交易额构成分析")

    chart_col1, chart_col2 = st.columns(2)

    # 3-a 环形图
    with chart_col1:
        donut_labels = ["当月首登M0", "首登T0", "存量首登M0", "非初审授信户"]
        donut_values = [
            t2.current_month_initial_m0,
            t2.first_login_t0,
            t2.existing_initial_m0,
            t2.non_initial_credit,
        ]
        fig_donut = px.pie(
            names=donut_labels,
            values=donut_values,
            title="整体首借交易额构成",
            hole=0.5,
            color_discrete_sequence=["#7C3AED", "#22C55E", "#F97316", "#E64980"],
        )
        fig_donut.update_traces(
            textposition="inside",
            textinfo="percent+value",
            hovertemplate="%{label}<br>%{percent}<br>%{value:.2f}亿<extra></extra>",
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    # 3-b 瀑布图：各客群累加到总交易额
    with chart_col2:
        wf_labels = ["当月首登M0", "首登T0", "存量首登M0", "非初审授信户", "整体首借总计"]
        wf_values = [
            t2.current_month_initial_m0,
            t2.first_login_t0,
            t2.existing_initial_m0,
            t2.non_initial_credit,
            t2.total_transaction,
        ]
        wf_measure = ["relative", "relative", "relative", "relative", "total"]
        wf_colors = ["#7C3AED", "#22C55E", "#F97316", "#E64980", "#1E88E5"]

        fig_wf = go.Figure(
            go.Waterfall(
                name="交易额",
                orientation="v",
                measure=wf_measure,
                x=wf_labels,
                y=wf_values,
                text=[f"{v:.2f}亿" for v in wf_values],
                textposition="outside",
                connector={"line": {"color": "#BDBDBD"}},
                increasing={"marker": {"color": "#7C3AED"}},
                decreasing={"marker": {"color": "#E64980"}},
                totals={"marker": {"color": "#1E88E5"}},
            )
        )
        fig_wf.update_layout(
            title="各客群交易额累加瀑布图",
            yaxis_title="交易额(亿元)",
            showlegend=False,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig_wf, use_container_width=True)

    # 3-c 花费 vs 交易额对比图
    segments = ["当月首登", "存量首登", "非初审"]
    expenses = [
        t1.total_expense + t2.rta_promotion_fee,
        t2.calculated_existing_m0_expense,
        0,
    ]
    transactions_display = [
        (t2.current_month_initial_m0 + t2.first_login_t0) * 10,
        t2.existing_initial_m0 * 10,
        t2.non_initial_credit * 10,
    ]
    fig_eff = make_subplots(specs=[[{"secondary_y": True}]])
    fig_eff.add_trace(
        go.Bar(
            x=segments,
            y=expenses,
            name="花费(万元)",
            marker_color="#4C6EF5",
            text=[f"{v:,.0f}" for v in expenses],
            textposition="outside",
        ),
        secondary_y=False,
    )
    fig_eff.add_trace(
        go.Bar(
            x=segments,
            y=transactions_display,
            name="交易额(千万元)",
            marker_color="#7C3AED",
            text=[f"{v:.1f}" for v in transactions_display],
            textposition="outside",
        ),
        secondary_y=True,
    )
    fig_eff.update_layout(
        title="各客群花费与交易额对比",
        barmode="group",
        margin=dict(l=20, r=20, t=40, b=20),
    )
    fig_eff.update_yaxes(title_text="花费(万元)", secondary_y=False)
    fig_eff.update_yaxes(title_text="交易额(千万元)", secondary_y=True)
    st.plotly_chart(fig_eff, use_container_width=True)

    # -----------------------------------------------------------------------
    # 4. CPS效率对比表（条件格式：高→绿、低→红、基准→灰）
    # -----------------------------------------------------------------------
    st.subheader("客群CPS效率对比")

    eff_data = []
    if t1.total_expense > 0 and (t2.current_month_initial_m0 + t2.first_login_t0) > 0:
        eff = (
            (t1.total_expense + t2.rta_promotion_fee)
            / (t2.current_month_initial_m0 + t2.first_login_t0)
            / 10000
        )
        eff_data.append(
            {
                "客群": "当月首登",
                "花费(万元)": f"{t1.total_expense + t2.rta_promotion_fee:,.0f}",
                "交易额(亿元)": f"{t2.current_month_initial_m0 + t2.first_login_t0:.2f}",
                "CPS": f"{eff:.2%}",
                "效率": "高" if eff < t2.total_cps else "低",
            }
        )
    if t2.calculated_existing_m0_expense > 0 and t2.existing_initial_m0 > 0:
        eff = t2.calculated_existing_m0_expense / t2.existing_initial_m0 / 10000
        eff_data.append(
            {
                "客群": "存量首登",
                "花费(万元)": f"{t2.calculated_existing_m0_expense:,.0f}",
                "交易额(亿元)": f"{t2.existing_initial_m0:.2f}",
                "CPS": f"{eff:.2%}",
                "效率": "高" if eff < t2.total_cps else "低",
            }
        )
    if t2.non_initial_credit > 0:
        eff_data.append(
            {
                "客群": "非初审授信户",
                "花费(万元)": "—(手动输入)",
                "交易额(亿元)": f"{t2.non_initial_credit:.2f}",
                "CPS": "—",
                "效率": "参考",
            }
        )
    eff_data.append(
        {
            "客群": "全业务合计",
            "花费(万元)": f"{t1.total_expense + t2.calculated_existing_m0_expense + t2.rta_promotion_fee:,.0f}",
            "交易额(亿元)": f"{t2.total_transaction:.2f}",
            "CPS": f"{t2.total_cps:.2%}",
            "效率": "基准",
        }
    )

    eff_df = pd.DataFrame(eff_data)

    _EFF_COLOR_MAP = {
        "高": "background-color: #E8F5E9; color: #2E7D32",
        "低": "background-color: #FFEBEE; color: #C62828",
        "基准": "background-color: #F5F5F5; color: #616161",
        "参考": "background-color: #FFF8E1; color: #795548",
    }

    def _style_eff_row(row):
        eff_val = row.get("效率", "")
        style = _EFF_COLOR_MAP.get(eff_val, "")
        return [style] * len(row)

    styled_eff = eff_df.style.apply(_style_eff_row, axis=1)
    st.dataframe(styled_eff, use_container_width=True, hide_index=True)

    # -----------------------------------------------------------------------
    # 5. 计算逻辑区（折叠展示）
    # -----------------------------------------------------------------------
    with st.expander("计算逻辑详解", expanded=False):
        st.markdown("#### 各客群计算公式")

        cps_pct = (coef.existing_m0_cps_avg * 100) if coef else 0
        ratio_val = coef.m0_t0_ratio if coef else 0

        logic_items = [
            (
                "当月首登M0",
                f"{t2.current_month_initial_m0:.2f} 亿元",
                f"Table1 各渠道T0交易额之和 × M0/T0系数({ratio_val:.3f})",
                f"= {t2.first_login_t0:.2f}亿 × {ratio_val:.3f} = {t2.current_month_initial_m0:.2f}亿",
            ),
            (
                "首登T0",
                f"{t2.first_login_t0:.2f} 亿元",
                "直接汇总 Table1 各渠道T0交易额（花费 ÷ CPS ÷ 10000）",
                f"= Σ(渠道花费 ÷ 渠道CPS ÷ 10000) = {t2.first_login_t0:.2f}亿",
            ),
            (
                "存量首登M0",
                f"{t2.existing_initial_m0:.2f} 亿元",
                f"存量花费 ÷ 存量CPS({cps_pct:.1f}%) ÷ 10000",
                f"= {t2.calculated_existing_m0_expense:,.0f}万 ÷ {cps_pct:.1f}% ÷ 10000 = {t2.existing_initial_m0:.2f}亿",
            ),
            (
                "非初审授信户",
                f"{t2.non_initial_credit:.2f} 亿元",
                "手动输入值，直接计入汇总，不参与CPS计算",
                "来源：页面左侧「非初审授信户首借交易额」输入框",
            ),
            (
                "全业务CPS",
                f"{t2.total_cps:.2%}",
                "（投放花费 + RTA费用 + 促申完）÷ 整体首借交易额 ÷ 10000",
                f"= ({t1.total_expense:,.0f} + {t2.rta_promotion_fee:,.0f})万 ÷ {t2.total_transaction:.2f}亿 ÷ 10000 = {t2.total_cps:.2%}",
            ),
        ]

        for name, result, formula, derivation in logic_items:
            col_name, col_result, col_formula = st.columns([1.5, 1, 4])
            with col_name:
                st.markdown(f"**{name}**")
            with col_result:
                st.markdown(f"`{result}`")
            with col_formula:
                st.caption(formula)
                st.caption(derivation)
            st.divider()

        st.markdown("#### 系数来源说明")
        coef_cols = st.columns(2)
        with coef_cols[0]:
            with st.container(border=True):
                st.caption("M0/T0 系数来源")
                if coef and coef.m0_t0_source_months:
                    months_str = "、".join(coef.m0_t0_source_months)
                    st.markdown(f"取前 **{len(coef.m0_t0_source_months)} 个月**均值")
                    st.caption(f"使用月份：{months_str}")
                    st.caption(f"历史值：{[f'{v:.3f}' for v in coef.m0_t0_ratio_history]}")
                st.markdown(f"当前系数：**{ratio_val:.3f}**")
        with coef_cols[1]:
            with st.container(border=True):
                st.caption("存量M0 CPS 来源")
                if coef and coef.existing_m0_source_months:
                    months_str = "、".join(coef.existing_m0_source_months)
                    st.markdown(f"取前 **{len(coef.existing_m0_source_months)} 个月**均值")
                    st.caption(f"使用月份：{months_str}")
                    st.caption(f"历史值：{[f'{v:.2%}' for v in coef.existing_m0_cps_history]}")
                st.markdown(f"当前CPS：**{cps_pct:.1f}%**")
