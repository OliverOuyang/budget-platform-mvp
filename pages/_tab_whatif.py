"""V4.3c What-if 快速模拟 Tab — 一键调整参数查看结果变化。"""
from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
from app.config import CHANNEL_NAMES, DEFAULT_TOTAL_BUDGET
from app.styles import render_callout


# ==================== 预设模拟方案 ====================
WHATIF_PRESETS = {
    "预算+500万": {"type": "budget_delta", "delta": 500},
    "预算-500万": {"type": "budget_delta", "delta": -500},
    "CPS全降10%": {"type": "cps_scale", "factor": 0.9},
    "砍付费商店50%": {"type": "channel_cut", "channel": "付费商店", "factor": 0.5},
    "过件率+2pp": {"type": "approval_delta", "delta": 0.02},
}


def _simulate_whatif(preset_name: str, preset_config: dict) -> pd.DataFrame:
    """运行 what-if 模拟，返回对比 DataFrame。"""
    table1 = st.session_state.get("table1_result")
    table2 = st.session_state.get("table2_result")
    params = st.session_state.get("parameters")

    if table1 is None or table2 is None or params is None:
        return _mock_simulation(preset_name, preset_config)

    # 当前值
    current_budget = getattr(params, "total_budget", DEFAULT_TOTAL_BUDGET)
    current_cps = getattr(table2, "total_cps", 0.353)
    current_t0 = getattr(table1, "total_t0_transaction", 0.85)
    total_transaction = getattr(table2, "total_transaction", 2.35)

    sim_budget = current_budget
    sim_cps = current_cps
    sim_t0 = current_t0
    sim_total = total_transaction

    preset_type = preset_config["type"]

    if preset_type == "budget_delta":
        delta = preset_config["delta"]
        sim_budget = current_budget + delta
        scale = sim_budget / current_budget if current_budget > 0 else 1
        sim_t0 = current_t0 * scale
        sim_total = total_transaction * scale
        # CPS stays roughly same with budget scale
    elif preset_type == "cps_scale":
        factor = preset_config["factor"]
        sim_cps = current_cps * factor
        # Lower CPS → more T0 per unit spend
        cps_effect = current_cps / sim_cps if sim_cps > 0 else 1
        sim_t0 = current_t0 * cps_effect
        sim_total = total_transaction + (sim_t0 - current_t0) * 1.49  # M0/T0 ratio effect
    elif preset_type == "channel_cut":
        factor = preset_config["factor"]
        # Rough: channel is ~16% of budget, cut reduces total proportionally
        sim_t0 = current_t0 * (1 - 0.16 * (1 - factor))
        sim_total = total_transaction * (1 - 0.16 * (1 - factor))
        sim_budget = current_budget * (1 - 0.16 * (1 - factor))
    elif preset_type == "approval_delta":
        delta = preset_config["delta"]
        # Approval doesn't directly affect T0, but affects authorization volume
        sim_t0 = current_t0  # unchanged
        sim_total = total_transaction  # unchanged

    def _fmt_change(current, simulated, is_pct=False):
        diff = simulated - current
        if abs(diff) < 1e-6:
            return "不变"
        if is_pct:
            return f"{diff:+.1f}pp"
        pct = (diff / current * 100) if current != 0 else 0
        return f"{pct:+.1f}%"

    rows = [
        {
            "指标": "总花费(万)",
            "当前值": f"{current_budget:,.0f}",
            "模拟值": f"{sim_budget:,.0f}",
            "变化": _fmt_change(current_budget, sim_budget),
        },
        {
            "指标": "全业务CPS",
            "当前值": f"{current_cps*100:.1f}%",
            "模拟值": f"{sim_cps*100:.1f}%",
            "变化": _fmt_change(current_cps*100, sim_cps*100, is_pct=True),
        },
        {
            "指标": "T0交易额(亿)",
            "当前值": f"{current_t0:.2f}",
            "模拟值": f"{sim_t0:.2f}",
            "变化": _fmt_change(current_t0, sim_t0),
        },
        {
            "指标": "首借交易额(亿)",
            "当前值": f"{total_transaction:.2f}",
            "模拟值": f"{sim_total:.2f}",
            "变化": _fmt_change(total_transaction, sim_total),
        },
    ]
    return pd.DataFrame(rows)


def _mock_simulation(preset_name: str, preset_config: dict) -> pd.DataFrame:
    """无计算结果时用 mock 数据。"""
    base = {"总花费(万)": 3000, "全业务CPS": 35.3, "T0交易额(亿)": 0.85, "首借交易额(亿)": 2.35}

    if preset_config["type"] == "cps_scale":
        sim = {"总花费(万)": 3000, "全业务CPS": 31.8, "T0交易额(亿)": 0.94, "首借交易额(亿)": 2.52}
    elif preset_config["type"] == "budget_delta" and preset_config["delta"] > 0:
        sim = {"总花费(万)": 3500, "全业务CPS": 35.3, "T0交易额(亿)": 0.99, "首借交易额(亿)": 2.74}
    elif preset_config["type"] == "budget_delta" and preset_config["delta"] < 0:
        sim = {"总花费(万)": 2500, "全业务CPS": 35.3, "T0交易额(亿)": 0.71, "首借交易额(亿)": 1.96}
    elif preset_config["type"] == "channel_cut":
        sim = {"总花费(万)": 2760, "全业务CPS": 34.1, "T0交易额(亿)": 0.78, "首借交易额(亿)": 2.16}
    else:
        sim = {"总花费(万)": 3000, "全业务CPS": 35.3, "T0交易额(亿)": 0.85, "首借交易额(亿)": 2.35}

    rows = []
    for key in base:
        b, s = base[key], sim[key]
        if abs(b - s) < 0.01:
            change = "不变"
        elif "CPS" in key:
            change = f"{s - b:+.1f}pp"
        else:
            change = f"{(s - b) / b * 100:+.1f}%"

        if "CPS" in key:
            rows.append({"指标": key, "当前值": f"{b:.1f}%", "模拟值": f"{s:.1f}%", "变化": change})
        elif "亿" in key:
            rows.append({"指标": key, "当前值": f"{b:.2f}", "模拟值": f"{s:.2f}", "变化": change})
        else:
            rows.append({"指标": key, "当前值": f"{b:,.0f}", "模拟值": f"{s:,.0f}", "变化": change})

    return pd.DataFrame(rows)


def render_tab_whatif():
    """渲染 What-if 快速模拟 Tab。"""
    st.markdown("**What-if 快速模拟**")
    render_callout("一键调整参数，查看结果变化。选择下方按钮快速模拟不同场景。", kind="info")

    # 预设按钮
    if "whatif_selected" not in st.session_state:
        st.session_state.whatif_selected = "CPS全降10%"

    btn_cols = st.columns(len(WHATIF_PRESETS))
    for i, (name, config) in enumerate(WHATIF_PRESETS.items()):
        with btn_cols[i]:
            is_selected = st.session_state.whatif_selected == name
            btn_type = "primary" if is_selected else "secondary"
            if st.button(name, key=f"whatif_{name}", type=btn_type, use_container_width=True):
                st.session_state.whatif_selected = name
                st.rerun()

    # 模拟结果
    selected = st.session_state.whatif_selected
    config = WHATIF_PRESETS[selected]
    result_df = _simulate_whatif(selected, config)

    st.markdown("")
    st.dataframe(
        result_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "模拟值": st.column_config.Column(width="medium"),
            "变化": st.column_config.Column(width="small"),
        },
    )

    # 操作按钮
    col_adopt, col_reset = st.columns(2)
    with col_adopt:
        if st.button("✅ 采纳此模拟", type="primary", use_container_width=True):
            st.info("功能开发中：采纳后将自动回填参数并重新计算。")
    with col_reset:
        if st.button("🔄 重置", use_container_width=True):
            st.session_state.whatif_selected = "CPS全降10%"
            st.rerun()
