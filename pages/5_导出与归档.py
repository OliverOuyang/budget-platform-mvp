"""V4.3c 导出与归档页面 — 4 种导出选项。"""
from __future__ import annotations

import io
import streamlit as st
from app.styles import inject_custom_css


inject_custom_css()

st.markdown("## 📥 导出与归档")

# ==================== 导出选项 ====================
with st.container(border=True):
    st.markdown("#### 导出报告")

    # Option 1: Excel 完整报告
    col_icon, col_info, col_btn = st.columns([0.5, 5, 1.5])
    with col_icon:
        st.markdown("### 📊")
    with col_info:
        st.markdown("**Excel 完整报告**")
        st.caption("渠道 + 客群 + 方案 + 系数 + 护栏")
    with col_btn:
        table1 = st.session_state.get("table1_result")
        table2 = st.session_state.get("table2_result")
        if table1 is not None and table2 is not None:
            try:
                from core.exporter import export_to_excel
                buf = io.BytesIO()
                export_to_excel(table1, table2, buf)
                st.download_button(
                    "导出",
                    data=buf.getvalue(),
                    file_name="预算推算报告.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )
            except Exception:
                st.button("导出", type="primary", use_container_width=True, disabled=True)
        else:
            st.button("导出", type="primary", use_container_width=True, disabled=True,
                       help="请先在预算工作台完成计算")

    st.markdown("---")

    # Option 2: 双引擎对照表
    col_icon2, col_info2, col_btn2 = st.columns([0.5, 5, 1.5])
    with col_icon2:
        st.markdown("### 📋")
    with col_info2:
        st.markdown("**双引擎对照表**")
        st.caption("V01 vs MMM 渠道级对比")
    with col_btn2:
        st.button("导出", key="export_dual", use_container_width=True, disabled=True,
                   help="训练 MMM 模型后可用")

    st.markdown("---")

    # Option 3: 计算逻辑文档
    col_icon3, col_info3, col_btn3 = st.columns([0.5, 5, 1.5])
    with col_icon3:
        st.markdown("### 📐")
    with col_info3:
        st.markdown("**计算逻辑文档**")
        st.caption("导出计算手册，含全部公式和参数说明")
    with col_btn3:
        st.button("导出", key="export_logic", use_container_width=True, disabled=True,
                   help="功能开发中")

    st.markdown("---")

    # Option 4: MMM 模型报告
    col_icon4, col_info4, col_btn4 = st.columns([0.5, 5, 1.5])
    with col_icon4:
        st.markdown("### 🧪")
    with col_info4:
        st.markdown("**MMM 模型报告**")
        st.caption("模型参数 + 饱和曲线 + 优化建议")
    with col_btn4:
        mmm_model = st.session_state.get("mmm_model")
        st.button("导出", key="export_mmm", use_container_width=True,
                   disabled=mmm_model is None,
                   help="训练 MMM 模型后可用" if mmm_model is None else "")

# ==================== 操作日志 ====================
with st.expander("📝 操作日志", expanded=False):
    logs = st.session_state.get("operation_logs", [])
    if logs:
        for log in reversed(logs[-20:]):
            st.caption(log)
    else:
        st.caption("暂无操作记录。")

# ==================== 提示 ====================
st.markdown("---")
col_back, _ = st.columns([1, 3])
with col_back:
    if st.button("← 返回预算工作台", use_container_width=True):
        st.switch_page("pages/2_预算推算结果.py")
