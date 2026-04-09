"""Tab 4: 方案管理"""
import streamlit as st
import pandas as pd
import tempfile
from core.exporter import export_to_excel


def render_tab_scenario_manager():
    """方案管理 Tab"""
    _render_management_conclusions()
    _render_scenario_comparison()
    _render_download_button()


def _render_management_conclusions():
    """方案管理结论区（顶部动态建议）"""
    scenarios = st.session_state.get("comparison_scenarios") or {}
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    if t1 is None or t2 is None:
        return

    count = len(scenarios)
    if count == 0:
        st.info("📌 当前没有已保存方案。建议将本次结果保存为首个对比基线，以便后续方案优劣比较。")
        return

    # 找出已保存方案中的最优（交易额最高且CPS最低得分）
    best_name, best_score = None, None
    for name, s in scenarios.items():
        score = float(s["table2"].total_transaction) - float(s["table2"].total_cps) * 100
        if best_score is None or score > best_score:
            best_name, best_score = name, score

    current_score = float(t2.total_transaction) - float(t2.total_cps) * 100
    efficiency = t2.total_transaction / (t1.total_expense / 10000) if t1.total_expense > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.caption("已保存方案数")
            st.markdown(f"**{count} 个**")
    with c2:
        with st.container(border=True):
            st.caption("当前方案效率")
            st.markdown(f"**{efficiency:.3f}** 亿元/亿元花费")
    with c3:
        with st.container(border=True):
            st.caption("与最优方案对比")
            if best_name and best_score is not None:
                if current_score > best_score:
                    st.markdown(f"**优于 {best_name}**")
                    st.caption("可考虑替换现有最优基线")
                else:
                    st.markdown(f"**未超过 {best_name}**")
                    st.caption("建议继续微调后保存")

    if current_score > (best_score or 0):
        st.success(f"📌 当前方案综合得分优于已保存的最优方案 **{best_name}**，建议保存为新的主基线。")
    else:
        st.warning(f"📌 已有 {count} 个保存方案，当前方案尚未超过 **{best_name}**，更适合作为试算结果继续微调。")


def _render_scenario_comparison():
    """场景保存与对比"""
    st.subheader("📊 场景保存与对比")
    scenarios = st.session_state.get("comparison_scenarios") or {}
    p = st.session_state.get("parameters")
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")

    tab1, tab2 = st.tabs(["保存当前场景", "对比已保存场景"])

    with tab1:
        _render_save_panel(scenarios, p, t1, t2)

    with tab2:
        _render_compare_panel(scenarios, t1, t2)


def _render_save_panel(scenarios, p, t1, t2):
    """保存场景面板（含方案质量评估卡片）"""
    if t1 is not None and t2 is not None:
        _render_quality_assessment(t1, t2)

    name = st.text_input("场景名称", key="sc_name")
    desc = st.text_input("描述", key="sc_desc")
    decision_note = st.text_area(
        "保存说明", key="sc_decision_note",
        placeholder="记录为什么保存该场景，例如：质量达标，可作为保守基线。"
    )
    if st.button("💾 保存场景"):
        if name and decision_note.strip():
            scenarios[name] = {
                "params": p, "table1": t1, "table2": t2,
                "description": desc,
                "decision_note": decision_note.strip(),
                "saved_at": pd.Timestamp.now().isoformat()
            }
            st.session_state.comparison_scenarios = scenarios
            st.success(f"场景 '{name}' 已保存")
        elif name and not decision_note.strip():
            st.warning("请填写保存说明，记录当前场景为什么值得保留。")


def _render_quality_assessment(t1, t2):
    """保存前方案质量评估卡片"""
    efficiency = t2.total_transaction / (t1.total_expense / 10000) if t1.total_expense > 0 else 0

    # 质量判断逻辑
    issues = []
    positives = []

    if t2.total_cps > 0.50:
        issues.append(f"CPS {t2.total_cps:.2%} 偏高（>50%）")
    else:
        positives.append(f"CPS {t2.total_cps:.2%} 在合理区间")

    if t2.approval_rate_1_3_excl_age < 0.10:
        issues.append(f"1-3过件率 {t2.approval_rate_1_3_excl_age:.2%} 偏低（<10%）")
    else:
        positives.append(f"过件率 {t2.approval_rate_1_3_excl_age:.2%} 正常")

    if efficiency < 0.5:
        issues.append(f"交易效率 {efficiency:.3f} 偏低")
    else:
        positives.append(f"交易效率 {efficiency:.3f} 较好")

    quality_label = "可保存" if len(issues) == 0 else ("谨慎保存" if len(issues) == 1 else "建议继续优化")
    border_color = "#28a745" if len(issues) == 0 else ("#ffc107" if len(issues) == 1 else "#dc3545")

    st.markdown(
        f"""<div style="border-left: 4px solid {border_color}; padding: 10px 14px;
            background: #fafafa; border-radius: 4px; margin-bottom: 12px;">
            <strong>方案质量评估：{quality_label}</strong><br/>
            {"".join(f'<span style="color:#dc3545;">⚠ {i}</span><br/>' for i in issues)}
            {"".join(f'<span style="color:#28a745;">✓ {p}</span><br/>' for p in positives)}
        </div>""",
        unsafe_allow_html=True
    )


def _render_compare_panel(scenarios, curr_t1, curr_t2):
    """对比已保存场景（带条件格式 + 效率列 + 当前方案高亮）"""
    if not scenarios:
        st.info("暂无保存场景")
        return

    selected = st.multiselect("选择对比场景", list(scenarios.keys()))
    if len(selected) < 2:
        st.caption("请至少选择 2 个场景进行对比")
        return

    comp_data = []

    # 当前方案行
    if curr_t1 and curr_t2:
        eff = curr_t2.total_transaction / (curr_t1.total_expense / 10000) if curr_t1.total_expense > 0 else 0
        comp_data.append({
            "场景": "【当前方案】",
            "总花费(万元)": curr_t1.total_expense,
            "总交易额(亿元)": curr_t2.total_transaction,
            "全业务CPS(%)": curr_t2.total_cps * 100,
            "交易额/花费效率": eff,
            "保存说明": "当前未保存",
            "_is_current": True,
        })

    for sname in selected:
        s = scenarios[sname]
        t1s, t2s = s["table1"], s["table2"]
        eff = t2s.total_transaction / (t1s.total_expense / 10000) if t1s.total_expense > 0 else 0
        comp_data.append({
            "场景": sname,
            "总花费(万元)": t1s.total_expense,
            "总交易额(亿元)": t2s.total_transaction,
            "全业务CPS(%)": t2s.total_cps * 100,
            "交易额/花费效率": eff,
            "保存说明": s.get("decision_note", s.get("description", "")),
            "_is_current": False,
        })

    df_comp = pd.DataFrame(comp_data)
    display_cols = ["场景", "总花费(万元)", "总交易额(亿元)", "全业务CPS(%)", "交易额/花费效率", "保存说明"]
    df_display = df_comp[display_cols].copy()

    # 找最优/最差（排除当前方案行）
    saved_df = df_comp[~df_comp["_is_current"]]
    best_txn_idx = saved_df["总交易额(亿元)"].idxmax() if not saved_df.empty else None
    worst_txn_idx = saved_df["总交易额(亿元)"].idxmin() if not saved_df.empty else None
    best_cps_idx = saved_df["全业务CPS(%)"].idxmin() if not saved_df.empty else None
    worst_cps_idx = saved_df["全业务CPS(%)"].idxmax() if not saved_df.empty else None
    best_eff_idx = saved_df["交易额/花费效率"].idxmax() if not saved_df.empty else None

    def _style_comparison(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i in df.index:
            is_current = comp_data[i]["_is_current"]
            if is_current:
                styles.loc[i] = "background-color: #E3F2FD;"
            # 最优值标绿加粗
            if i == best_txn_idx:
                styles.loc[i, "总交易额(亿元)"] = "color: #1b5e20; font-weight: bold; background-color: #e8f5e9;"
            if i == worst_txn_idx:
                styles.loc[i, "总交易额(亿元)"] = "color: #b71c1c; background-color: #ffebee;"
            if i == best_cps_idx:
                styles.loc[i, "全业务CPS(%)"] = "color: #1b5e20; font-weight: bold; background-color: #e8f5e9;"
            if i == worst_cps_idx:
                styles.loc[i, "全业务CPS(%)"] = "color: #b71c1c; background-color: #ffebee;"
            if i == best_eff_idx:
                styles.loc[i, "交易额/花费效率"] = "color: #1b5e20; font-weight: bold; background-color: #e8f5e9;"
        return styles

    # 格式化数值列
    df_fmt = df_display.copy()
    df_fmt["总花费(万元)"] = df_fmt["总花费(万元)"].apply(lambda x: f"{x:,.0f}")
    df_fmt["总交易额(亿元)"] = df_fmt["总交易额(亿元)"].apply(lambda x: f"{x:.2f}")
    df_fmt["全业务CPS(%)"] = df_fmt["全业务CPS(%)"].apply(lambda x: f"{x:.2f}%")
    df_fmt["交易额/花费效率"] = df_fmt["交易额/花费效率"].apply(lambda x: f"{x:.3f}")

    styled = df_fmt.style.apply(
        lambda _: _style_comparison(df_display),
        axis=None
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.caption("💡 蓝底 = 当前方案；绿色加粗 = 该列最优；红色 = 该列最差（仅在已保存方案中比较）")


def _render_download_button():
    """渲染Excel导出下载按钮"""
    table1 = st.session_state.get("table1_result")
    table2 = st.session_state.get("table2_result")
    if table1 is None or table2 is None:
        return
    try:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            output_path = export_to_excel(table1, table2, output_path=tmp.name)
            with open(output_path, "rb") as f:
                excel_bytes = f.read()
        st.download_button(
            "📥 下载Excel报表", excel_bytes, "预算推算结果.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, type="primary"
        )
    except Exception as e:
        st.error(f"❌ 导出失败: {e}")
