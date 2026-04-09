"""V4.3c What-if 快速模拟 Tab — 一键调整参数，用真实计算管线查看结果变化。"""
from __future__ import annotations

import streamlit as st
import pandas as pd
from app.styles import render_callout
from pages._shared_params import (
    get_current_pipeline_params,
    build_adoption_params,
    run_pipeline_with_params,
)


# ==================== 预设模拟方案 ====================
WHATIF_PRESETS = {
    "预算+500万": {"type": "budget_delta", "delta": 500},
    "预算-500万": {"type": "budget_delta", "delta": -500},
    "CPS全降10%": {"type": "cps_scale", "factor": 0.9},
    "砍付费商店50%": {"type": "channel_cut", "channel": "付费商店", "factor": 0.5},
    "过件率+2pp": {"type": "approval_delta", "delta": 0.02},
}


def _apply_preset(params: dict, preset_config: dict) -> dict:
    """将 what-if 预设应用到参数副本上，返回新参数字典。"""
    p = {k: (dict(v) if isinstance(v, dict) else v) for k, v in params.items()}
    ptype = preset_config["type"]

    if ptype == "budget_delta":
        p["total_budget"] = max(p["total_budget"] + preset_config["delta"], 0)
    elif ptype == "cps_scale":
        factor = preset_config["factor"]
        p["channel_1_8_cps"] = {k: v * factor for k, v in p["channel_1_8_cps"].items()}
    elif ptype == "channel_cut":
        ch = preset_config["channel"]
        factor = preset_config["factor"]
        shares = dict(p["channel_budget_shares"])
        if ch in shares:
            freed = shares[ch] * (1 - factor)
            shares[ch] *= factor
            # 释放的预算按比例分配给其他渠道
            other_total = sum(v for k, v in shares.items() if k != ch)
            if other_total > 0:
                for k in shares:
                    if k != ch:
                        shares[k] += freed * (shares[k] / other_total)
        p["channel_budget_shares"] = shares
    elif ptype == "approval_delta":
        delta = preset_config["delta"]
        p["channel_1_3_rate"] = {
            k: min(v + delta, 1.0) for k, v in p["channel_1_3_rate"].items()
        }

    return p


def _build_comparison_df(t1_base, t2_base, t1_sim, t2_sim) -> pd.DataFrame:
    """构建基线 vs 模拟对比表。"""

    def _fmt(cur, sim, is_pct=False):
        diff = sim - cur
        if abs(diff) < 1e-6:
            return "不变"
        if is_pct:
            return f"{diff * 100:+.1f}pp"
        return f"{(diff / cur * 100):+.1f}%" if cur != 0 else f"{diff:+.2f}"

    return pd.DataFrame([
        {
            "指标": "总花费(万)",
            "当前值": f"{t1_base.total_expense:,.0f}",
            "模拟值": f"{t1_sim.total_expense:,.0f}",
            "变化": _fmt(t1_base.total_expense, t1_sim.total_expense),
        },
        {
            "指标": "全业务CPS",
            "当前值": f"{t2_base.total_cps * 100:.1f}%",
            "模拟值": f"{t2_sim.total_cps * 100:.1f}%",
            "变化": _fmt(t2_base.total_cps, t2_sim.total_cps, is_pct=True),
        },
        {
            "指标": "T0交易额(亿)",
            "当前值": f"{t1_base.total_t0_transaction:.2f}",
            "模拟值": f"{t1_sim.total_t0_transaction:.2f}",
            "变化": _fmt(t1_base.total_t0_transaction, t1_sim.total_t0_transaction),
        },
        {
            "指标": "首借交易额(亿)",
            "当前值": f"{t2_base.total_transaction:.2f}",
            "模拟值": f"{t2_sim.total_transaction:.2f}",
            "变化": _fmt(t2_base.total_transaction, t2_sim.total_transaction),
        },
    ])


def render_tab_whatif():
    """渲染 What-if 快速模拟 Tab。"""
    st.markdown("**What-if 快速模拟**")
    render_callout(
        "一键调整参数，查看结果变化。选择下方按钮快速模拟不同场景。", kind="info"
    )

    current = get_current_pipeline_params()
    t1_base = st.session_state.get("table1_result")
    t2_base = st.session_state.get("table2_result")
    if current is None or t1_base is None or t2_base is None:
        st.info("请先完成参数配置并执行计算，What-if 模拟将在此处可用。")
        return

    # 预设按钮
    if "whatif_selected" not in st.session_state:
        st.session_state.whatif_selected = "CPS全降10%"

    btn_cols = st.columns(len(WHATIF_PRESETS))
    for i, name in enumerate(WHATIF_PRESETS):
        with btn_cols[i]:
            is_selected = st.session_state.whatif_selected == name
            if st.button(
                name,
                key=f"whatif_{name}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            ):
                st.session_state.whatif_selected = name
                st.rerun()

    # 执行模拟（真实管线计算）
    selected = st.session_state.whatif_selected
    sim_params = _apply_preset(current, WHATIF_PRESETS[selected])

    with st.spinner("模拟计算中..."):
        _, _, t1_sim, t2_sim = run_pipeline_with_params(sim_params)

    st.dataframe(
        _build_comparison_df(t1_base, t2_base, t1_sim, t2_sim),
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
            st.session_state["pending_result_template_params"] = build_adoption_params(
                sim_params, current
            )
            st.rerun()
    with col_reset:
        if st.button("🔄 重置", use_container_width=True):
            st.session_state.whatif_selected = "CPS全降10%"
            st.rerun()
