"""Tab 4: 方案管理"""
import streamlit as st
import pandas as pd
import tempfile
from core.exporter import export_to_excel


def render_tab_scenario_manager():
    """方案管理 Tab"""
    _render_scenario_comparison()
    _render_download_button()


def _render_scenario_comparison():
    """场景保存与对比"""
    st.subheader("📊 场景保存与对比")
    scenarios = st.session_state.get("comparison_scenarios") or {}
    p = st.session_state.get("parameters")
    t1 = st.session_state.get("table1_result")
    t2 = st.session_state.get("table2_result")
    current_score = float(t2.total_transaction) - float(t2.total_cps) * 100 if t1 and t2 else None
    best_existing_name = None
    best_existing_score = None
    for name, scenario in scenarios.items():
        score = float(scenario["table2"].total_transaction) - float(scenario["table2"].total_cps) * 100
        if best_existing_score is None or score > best_existing_score:
            best_existing_name = name
            best_existing_score = score

    if current_score is not None:
        if best_existing_score is None:
            st.info("📌 当前没有已保存方案，建议将本次结果保存为首个对比基线。")
        elif current_score > best_existing_score:
            st.success(f"📌 当前方案优于已保存方案中的 **{best_existing_name}**，建议保存为新场景或作为新的主基线。")
        else:
            st.warning(f"📌 当前方案尚未超过 **{best_existing_name}**，更适合作为试算结果继续微调。")

    tab1, tab2 = st.tabs(["保存当前场景", "对比已保存场景"])
    with tab1:
        name = st.text_input("场景名称", key="sc_name")
        desc = st.text_input("描述", key="sc_desc")
        decision_note = st.text_area("保存说明", key="sc_decision_note", placeholder="记录为什么保存该场景，例如：质量达标，可作为保守基线。")
        if st.button("💾 保存场景"):
            if name and decision_note.strip():
                scenarios[name] = {
                    "params": p, "table1": t1, "table2": t2,
                    "description": desc, "decision_note": decision_note.strip(), "saved_at": pd.Timestamp.now().isoformat()
                }
                st.session_state.comparison_scenarios = scenarios
                st.success(f"场景 '{name}' 已保存")
            elif name and not decision_note.strip():
                st.warning("请填写保存说明，记录当前场景为什么值得保留。")
    with tab2:
        if scenarios:
            selected = st.multiselect("选择对比场景", list(scenarios.keys()))
            if len(selected) >= 2:
                comp_data = []
                for sname in selected:
                    s = scenarios[sname]
                    comp_data.append({
                        "场景": sname,
                        "总花费(万元)": s["table1"].total_expense,
                        "总交易额(亿元)": s["table2"].total_transaction,
                        "全业务CPS(%)": s["table2"].total_cps,
                        "保存说明": s.get("decision_note", s.get("description", "")),
                    })
                st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)
        else:
            st.info("暂无保存场景")


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
