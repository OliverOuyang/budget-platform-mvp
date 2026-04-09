"""Tab 1: 渠道结果"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


# ─────────────────────────────────────────────
# 内部辅助
# ─────────────────────────────────────────────

def _efficiency(ch) -> float:
    """万元效率：每万元花费产生的T0交易额（千元）"""
    return ch.t0_transaction / ch.expense * 10000 if ch.expense > 0 else 0.0


def _build_conclusions(channels, t1) -> list[str]:
    """动态生成3-4条结论，返回 (icon, text) 列表"""
    if not channels:
        return []

    total_exp = t1.total_expense or 1
    effs = {ch.channel_name: _efficiency(ch) for ch in channels}
    cps_vals = {ch.channel_name: (ch.cps_1_8 or 0) for ch in channels}
    shares = {ch.channel_name: ch.expense / total_exp for ch in channels}

    best_eff_name = max(effs, key=effs.get)
    best_eff_val = effs[best_eff_name]

    best_cps_name = min(cps_vals, key=lambda k: cps_vals[k] if cps_vals[k] > 0 else float("inf"))
    best_cps_val = cps_vals[best_cps_name] * 100

    largest_share_name = max(shares, key=shares.get)
    largest_share_pct = shares[largest_share_name] * 100
    largest_eff = effs[largest_share_name]
    avg_eff = sum(effs.values()) / len(effs)

    lines = []
    # 结论 a：效率最高
    lines.append(("✅", f"效率最高渠道：**{best_eff_name}**，万元效率 {best_eff_val:.2f} 千元/万元，显著优于其他渠道。"))

    # 结论 b：CPS最低
    lines.append(("✅", f"成本最优渠道：**{best_cps_name}**，CPS 仅 {best_cps_val:.1f}%，获客成本最低。"))

    # 结论 c：花费占比最大渠道效率评估
    eff_tag = "高于" if largest_eff >= avg_eff else "低于"
    icon_c = "✅" if largest_eff >= avg_eff else "⚠️"
    lines.append((icon_c,
        f"花费占比最大渠道：**{largest_share_name}**（占 {largest_share_pct:.1f}%），"
        f"万元效率 {largest_eff:.2f} 千元/万元，{eff_tag}平均水平 {avg_eff:.2f}。"))

    # 结论 d：风险渠道
    risk_channels = []
    for ch in channels:
        cps_pct = (ch.cps_1_8 or 0) * 100
        share_pct = ch.expense / total_exp * 100
        avg_cps = sum(cps_vals.values()) / len(cps_vals) * 100
        if cps_pct > avg_cps * 1.3 or share_pct > 40:
            risk_channels.append(ch.channel_name)
    if risk_channels:
        lines.append(("⚠️", f"需关注风险渠道：**{'、'.join(risk_channels)}**，CPS偏高或花费占比过高，建议优化投放结构。"))
    else:
        lines.append(("✅", "各渠道CPS和花费占比分布均衡，整体投放结构健康。"))

    return lines


def _style_table(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """对Table1 DataFrame应用条件格式"""
    styled = df.style

    # 总计行加粗灰底
    total_row_idx = df[df["渠道名称"] == "总计"].index.tolist()

    def highlight_total(row):
        if row.name in total_row_idx:
            return ["background-color: #f0f0f0; font-weight: bold"] * len(row)
        return [""] * len(row)

    styled = styled.apply(highlight_total, axis=1)

    # CPS列渐变色：值越低越绿，越高越红
    if "1-8 T0CPS" in df.columns:
        cps_col = df["1-8 T0CPS"].copy()
        # 排除总计行做归一化
        non_total = cps_col.drop(index=total_row_idx, errors="ignore")
        if len(non_total) > 0 and non_total.max() > non_total.min():
            def cps_color(val):
                if pd.isna(val):
                    return ""
                # 排除总计行不上色
                row_mask = df["1-8 T0CPS"] == val
                if any(df.loc[row_mask, "渠道名称"] == "总计"):
                    return ""
                mn, mx = non_total.min(), non_total.max()
                norm = (val - mn) / (mx - mn) if mx > mn else 0
                # 绿 -> 黄 -> 红
                r = int(norm * 220)
                g = int((1 - norm) * 180 + 40)
                return f"background-color: rgb({r},{g},60); color: white;"
            styled = styled.map(cps_color, subset=["1-8 T0CPS"])

    # 花费结构列：占比>30%标橙色提醒
    if "花费结构" in df.columns:
        def expense_share_color(val):
            if pd.isna(val) or val == "":
                return ""
            try:
                v = float(val)
                if v > 30:
                    return "background-color: #FFF3CD; color: #856404; font-weight: bold;"
            except (ValueError, TypeError):
                pass
            return ""
        styled = styled.map(expense_share_color, subset=["花费结构"])

    return styled


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def render_tab_channel_result():
    """渠道结果 Tab"""
    t1 = st.session_state.get("table1_result")

    if t1 is None:
        st.info("请先在左侧完成预算推算，结果将在此处展示。")
        return

    channels = [ch for ch in t1.channels if ch.channel_name != "总计"]

    # ══════════════════════════════════════════
    # 1. 渠道核心结论区
    # ══════════════════════════════════════════
    with st.container(border=True):
        st.markdown("#### 渠道核心结论")
        conclusions = _build_conclusions(channels, t1)
        for icon, text in conclusions:
            st.markdown(f"{icon} {text}")

    st.markdown("")

    # ══════════════════════════════════════════
    # 2. Table 1 渠道结果表
    # ══════════════════════════════════════════
    st.subheader("📋 Table 1 渠道预测")

    # 表头颜色图例说明
    legend_cols = st.columns(4)
    with legend_cols[0]:
        st.markdown('<span style="background:#DBEAFE;padding:2px 8px;border-radius:4px;font-size:12px;">蓝=预算/花费</span>', unsafe_allow_html=True)
    with legend_cols[1]:
        st.markdown('<span style="background:#DCFCE7;padding:2px 8px;border-radius:4px;font-size:12px;">绿=质量/过件</span>', unsafe_allow_html=True)
    with legend_cols[2]:
        st.markdown('<span style="background:#FEF9C3;padding:2px 8px;border-radius:4px;font-size:12px;">橙=成本/CPS</span>', unsafe_allow_html=True)
    with legend_cols[3]:
        st.markdown('<span style="background:#EDE9FE;padding:2px 8px;border-radius:4px;font-size:12px;">紫=产出/交易</span>', unsafe_allow_html=True)

    st.markdown("")

    df = t1.to_dataframe()

    # 格式化百分比列用于展示
    df_display = df.copy()
    if "1-3 T0过件率" in df_display.columns:
        df_display["1-3 T0过件率"] = df_display["1-3 T0过件率"].apply(
            lambda v: f"{v:.2%}" if pd.notna(v) and v != "" else ""
        )
    if "1-8 T0CPS" in df_display.columns:
        df_display["1-8 T0CPS"] = df_display["1-8 T0CPS"].apply(
            lambda v: f"{float(v)*100:.2f}%" if pd.notna(v) and v not in ("", None) else ""
        )
    if "花费结构" in df_display.columns:
        df_display["花费结构"] = df_display["花费结构"].apply(
            lambda v: f"{v:.1f}%" if pd.notna(v) else ""
        )
    if "申完结构" in df_display.columns:
        df_display["申完结构"] = df_display["申完结构"].apply(
            lambda v: f"{v:.1f}%" if pd.notna(v) else ""
        )

    # 条件格式：总计行加粗灰底 + 花费结构>30%橙色
    total_row_idx = df_display[df_display["渠道名称"] == "总计"].index.tolist()

    def highlight_total(row):
        if row.name in total_row_idx:
            return ["background-color:#f0f0f0; font-weight:bold"] * len(row)
        return [""] * len(row)

    def highlight_expense_share(val):
        try:
            v = float(str(val).replace("%", ""))
            if v > 30:
                return "background-color:#FFF3CD; color:#856404; font-weight:bold"
        except (ValueError, TypeError):
            pass
        return ""

    styled = df_display.style.apply(highlight_total, axis=1)
    if "花费结构" in df_display.columns:
        styled = styled.map(highlight_expense_share, subset=["花费结构"])

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "渠道名称":          st.column_config.TextColumn("渠道", width="small"),
            "花费(千万元)":      st.column_config.NumberColumn("花费(千万元)", format="%.2f", width="small"),
            "花费结构":          st.column_config.TextColumn("花费结构", width="small"),
            "T0交易额(千万元)":  st.column_config.NumberColumn("T0交易额(千万元)", format="%.2f", width="small"),
            "当月首登M0交易额(千万元)": st.column_config.NumberColumn("M0交易额(千万元)", format="%.2f", width="small"),
            "T0申完成本(元)":    st.column_config.NumberColumn("T0申完成本(元)", format="%.0f", width="small"),
            "T0申完量":          st.column_config.NumberColumn("T0申完量", format="%,.0f", width="small"),
            "1-3 T0授信量":      st.column_config.NumberColumn("1-3授信量", format="%,.0f", width="small"),
        }
    )

    st.markdown("---")

    # ══════════════════════════════════════════
    # 3. 可视化图表
    # ══════════════════════════════════════════
    st.subheader("📊 渠道可视化分析")

    CHART_H = 280
    COLORS = ["#4C6EF5", "#7C3AED", "#22C55E", "#F97316", "#E64980", "#06B6D4", "#8B5CF6"]
    ch_names = [ch.channel_name for ch in channels]
    ch_expenses = [ch.expense for ch in channels]
    ch_tx = [ch.t0_transaction * 10 for ch in channels]

    col_a, col_b = st.columns(2)

    with col_a:
        fig_pie = px.pie(
            names=ch_names,
            values=ch_expenses,
            title="各渠道花费占比",
            hole=0.4,
            color_discrete_sequence=COLORS,
        )
        fig_pie.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>花费: %{value:,.0f}万<br>占比: %{percent}<extra></extra>",
        )
        fig_pie.update_layout(height=CHART_H, margin=dict(t=40, b=10, l=10, r=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_b:
        fig_bar = px.bar(
            x=ch_names,
            y=ch_tx,
            title="T0交易额(千万元)",
            color_discrete_sequence=["#7C3AED"],
            text=[f"{v:.1f}" for v in ch_tx],
        )
        fig_bar.update_traces(
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>T0交易额: %{y:.2f}千万元<extra></extra>",
        )
        fig_bar.update_layout(height=CHART_H, margin=dict(t=40, b=10, l=10, r=10),
                               uniformtext_minsize=10, uniformtext_mode="show")
        st.plotly_chart(fig_bar, use_container_width=True)

    # 花费结构 vs 交易额贡献对比条形图
    total_tx = sum(ch_tx) or 1
    total_exp_sum = sum(ch_expenses) or 1
    exp_shares = [e / total_exp_sum * 100 for e in ch_expenses]
    tx_shares = [t / total_tx * 100 for t in ch_tx]

    fig_compare = go.Figure()
    fig_compare.add_trace(go.Bar(
        name="花费占比 %",
        x=ch_names,
        y=exp_shares,
        marker_color="#4C6EF5",
        text=[f"{v:.1f}%" for v in exp_shares],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>花费占比: %{y:.1f}%<extra></extra>",
    ))
    fig_compare.add_trace(go.Bar(
        name="交易额贡献 %",
        x=ch_names,
        y=tx_shares,
        marker_color="#22C55E",
        text=[f"{v:.1f}%" for v in tx_shares],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>交易额贡献: %{y:.1f}%<extra></extra>",
    ))
    fig_compare.update_layout(
        title="花费结构 vs 交易额贡献对比（高交易占比/低花费占比 = 高效渠道）",
        barmode="group",
        height=CHART_H,
        margin=dict(t=50, b=10, l=10, r=10),
        legend=dict(orientation="h", y=-0.15),
        uniformtext_minsize=9,
        uniformtext_mode="show",
        yaxis_title="%",
    )
    st.plotly_chart(fig_compare, use_container_width=True)

    st.markdown("---")

    # ══════════════════════════════════════════
    # 4. 渠道明细卡片
    # ══════════════════════════════════════════
    st.subheader("💡 渠道指标明细")

    best_ch = max(channels, key=_efficiency)
    worst_ch = min(channels, key=_efficiency)
    best_eff_val = _efficiency(best_ch)
    worst_eff_val = _efficiency(worst_ch)

    for ch in channels:
        exp_share = ch.expense / t1.total_expense * 100 if t1.total_expense > 0 else 0
        cps_disp = (ch.cps_1_8 or 0) * 100
        eff = _efficiency(ch)

        # 效率标记
        if ch.channel_name == best_ch.channel_name:
            eff_badge = "🏆"
        elif ch.channel_name == worst_ch.channel_name:
            eff_badge = "⚠️"
        else:
            eff_badge = ""

        row1_cols = st.columns(5)
        with row1_cols[0]:
            st.metric("渠道", f"{eff_badge} {ch.channel_name}".strip())
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
            st.caption(
                f"{ch.expense:,.0f}万 ÷ {cps_disp:.1f}% ÷ 10000"
                f" → T0={ch.t0_transaction:.4f}亿"
            )
        with row2_cols[4]:
            flags = []
            if exp_share > 40:
                flags.append("⚠️ 花费占比过高")
            if cps_disp > 0:
                all_cps = [(c.cps_1_8 or 0) * 100 for c in channels if (c.cps_1_8 or 0) > 0]
                avg_cps = sum(all_cps) / len(all_cps) if all_cps else 0
                if cps_disp > avg_cps * 1.3:
                    flags.append("⚠️ CPS偏高")
            if ch.approval_rate_1_3 > 0.5:
                flags.append("✅ 过件率良好")
            for f in flags:
                st.caption(f)
        st.divider()

    # ══════════════════════════════════════════
    # 5. 万元效率排名图
    # ══════════════════════════════════════════
    st.subheader("📊 各渠道万元效率排名")

    eff_data = [
        {"渠道": ch.channel_name, "万元效率(千元/万元)": _efficiency(ch)}
        for ch in channels
    ]
    eff_df = pd.DataFrame(eff_data).sort_values("万元效率(千元/万元)", ascending=False).reset_index(drop=True)

    max_eff = eff_df["万元效率(千元/万元)"].max()
    min_eff = eff_df["万元效率(千元/万元)"].min()

    bar_colors = []
    for v in eff_df["万元效率(千元/万元)"]:
        if v == max_eff:
            bar_colors.append("#22C55E")
        elif v == min_eff:
            bar_colors.append("#EF4444")
        else:
            bar_colors.append("#4C6EF5")

    fig_rank = go.Figure(go.Bar(
        x=eff_df["渠道"],
        y=eff_df["万元效率(千元/万元)"],
        marker_color=bar_colors,
        text=[f"{v:.2f}" for v in eff_df["万元效率(千元/万元)"]],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>万元效率: %{y:.2f} 千元/万元<extra></extra>",
    ))
    fig_rank.update_layout(
        title="各渠道万元效率排名（越高越好 | 绿=最高 红=最低）",
        height=CHART_H,
        margin=dict(t=50, b=10, l=10, r=10),
        yaxis_title="千元/万元",
        uniformtext_minsize=10,
        uniformtext_mode="show",
    )
    st.plotly_chart(fig_rank, use_container_width=True)

    st.success(
        f"🏆 效率冠军: {best_ch.channel_name} — 每万元花费产生T0交易额 {best_eff_val:.2f} 千元，"
        f"优于最差渠道 {worst_eff_val:.2f} 千元"
    )
