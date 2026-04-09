"""Tab: 目标方案 — 目标驱动多方案生成与对比"""
import streamlit as st
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

from core.calculation_pipeline import execute_calculation_pipeline
from core.scenario_generator import (
    generate_goal_scenarios,
    VALID_DIRECTIONS,
    GRADIENT_LABELS,
)
from core.data_loader import DEFAULT_GUARDRAIL_THRESHOLDS, load_guardrail_data
from app.config import DEFAULT_TOTAL_BUDGET, DEFAULT_MONTH_DAYS, DEFAULT_DAYS_ELAPSED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_current_params_from_session() -> Optional[dict]:
    """Assemble the 13 pipeline parameters from session state.

    Returns None if uploaded data is missing (cannot run pipeline).
    """
    data = st.session_state.get("uploaded_data")
    if not data:
        return None

    flow = st.session_state.get("v01_flow", {})
    inputs = flow.get("inputs", {})

    # Channel dicts: prefer last-computed inputs, fall back to defaults
    channel_budget_shares = inputs.get("channel_budget_shares", {})
    channel_1_3_rate = inputs.get("channel_1_3_rate", {})
    channel_1_8_cps = inputs.get("channel_1_8_cps", {})
    channel_t0_cost = inputs.get("channel_t0_cost", {})

    if not channel_budget_shares:
        return None

    return {
        "df_raw1": data["df_raw1"],
        "df_raw2": data["df_raw2"],
        "total_budget": inputs.get("total_budget", st.session_state.get("result_total_budget", DEFAULT_TOTAL_BUDGET)),
        "channel_budget_shares": channel_budget_shares,
        "channel_1_3_rate": channel_1_3_rate,
        "channel_1_8_cps": channel_1_8_cps,
        "channel_t0_cost": channel_t0_cost,
        "non_initial_credit": inputs.get("non_initial_credit", st.session_state.get("result_non_initial_credit", 0.0)),
        "existing_m0_expense": 0.0,  # Matches page 2 line 1027 hardcoded value
        "rta_promotion_fee": inputs.get("rta_promotion_fee", st.session_state.get("result_rta_promotion_fee", 0.0)),
        "month_total_days": int(inputs.get("month_total_days", st.session_state.get("result_month_total_days", DEFAULT_MONTH_DAYS))),
        "days_elapsed": int(inputs.get("days_elapsed", st.session_state.get("result_days_elapsed", DEFAULT_DAYS_ELAPSED))),
        "m0_calc_period": int(inputs.get("m0_calc_period", st.session_state.get("result_m0_calc_period", 3))),
    }


def _run_scenarios(current: dict, goal_direction: str, gradients: List[float]):
    """Generate scenarios and run pipeline for baseline + 3 gradients.

    Stores results in st.session_state["goal_scenarios"].
    """
    scenarios = generate_goal_scenarios(
        channel_budget_shares=current["channel_budget_shares"],
        channel_1_3_rate=current["channel_1_3_rate"],
        channel_1_8_cps=current["channel_1_8_cps"],
        channel_t0_cost=current["channel_t0_cost"],
        total_budget=current["total_budget"],
        goal_direction=goal_direction,
        gradients=gradients,
    )

    # Shared scalar params (unchanged across scenarios)
    scalars = {k: current[k] for k in (
        "df_raw1", "df_raw2", "non_initial_credit",
        "existing_m0_expense", "rta_promotion_fee",
        "month_total_days", "days_elapsed", "m0_calc_period",
    )}

    results = []

    # Baseline
    _, _, t1_base, t2_base = execute_calculation_pipeline(
        total_budget=current["total_budget"],
        channel_budget_shares=current["channel_budget_shares"],
        channel_1_3_rate=current["channel_1_3_rate"],
        channel_1_8_cps=current["channel_1_8_cps"],
        channel_t0_cost=current["channel_t0_cost"],
        **scalars,
    )
    results.append({"label": "基线", "t1": t1_base, "t2": t2_base, "params": None})

    # 3 gradient scenarios
    for sc in scenarios:
        _, _, t1_sc, t2_sc = execute_calculation_pipeline(
            total_budget=sc["total_budget"],
            channel_budget_shares=sc["channel_budget_shares"],
            channel_1_3_rate=sc["channel_1_3_rate"],
            channel_1_8_cps=sc["channel_1_8_cps"],
            channel_t0_cost=sc["channel_t0_cost"],
            **scalars,
        )
        results.append({"label": sc["label"], "t1": t1_sc, "t2": t2_sc, "params": sc})

    st.session_state["goal_scenarios"] = {
        "direction": goal_direction,
        "gradients": gradients,
        "results": results,
    }


def _build_adoption_params(scenario_params: dict, current: dict) -> dict:
    """Map generator keys to template system keys for _apply_template_to_result_widgets().

    Key mapping (generator -> template):
      channel_1_3_rate -> channel_1_3_approval_rate
      channel_t0_cost  -> channel_t0_completion_cost
      channel_1_8_cps  -> channel_1_8_cps (same)
      channel_budget_shares -> channel_budget_shares (same)
    """
    return {
        "total_budget": scenario_params["total_budget"],
        "channel_budget_shares": scenario_params["channel_budget_shares"],
        "channel_1_3_approval_rate": scenario_params["channel_1_3_rate"],
        "channel_t0_completion_cost": scenario_params["channel_t0_cost"],
        "channel_1_8_cps": scenario_params["channel_1_8_cps"],
        "non_initial_credit_transaction": current.get("non_initial_credit", 0.0),
        "rta_promotion_fee": current.get("rta_promotion_fee", 0.0),
        "month_total_days": current.get("month_total_days", DEFAULT_MONTH_DAYS),
        "days_elapsed": current.get("days_elapsed", DEFAULT_DAYS_ELAPSED),
        "existing_m0_calculation_months": current.get("m0_calc_period", 3),
    }


def _color_best_worst(val, best, worst):
    """Return CSS style for best (green) and worst (red) values."""
    if val == best:
        return "color: #16a34a; font-weight: bold"
    if val == worst:
        return "color: #dc2626"
    return ""


# ---------------------------------------------------------------------------
# Comparison Table
# ---------------------------------------------------------------------------

def _render_comparison_table(results: list):
    """Render the multi-scenario comparison table with color coding."""
    labels = [r["label"] for r in results]

    # -- Summary metrics --
    rows = []

    def _add_row(name, values, lower_is_better=False):
        best = min(values) if lower_is_better else max(values)
        worst = max(values) if lower_is_better else min(values)
        row = {"指标": name}
        for lbl, val in zip(labels, values):
            row[lbl] = val
        row["_best"] = best
        row["_worst"] = worst
        rows.append(row)

    budgets = [r["t1"].total_expense for r in results]
    _add_row("总预算 (万���)", budgets, lower_is_better=True)

    month_days = int(st.session_state.get("result_month_total_days", 30))
    daily = [b / month_days for b in budgets]
    _add_row("日均花费 (万元)", daily, lower_is_better=True)

    cps_vals = [r["t2"].total_cps for r in results]
    _add_row("全业务CPS", cps_vals, lower_is_better=True)

    t0_vals = [r["t1"].total_t0_transaction for r in results]
    _add_row("首借T0交易额 (亿元)", t0_vals)

    # Weighted average 1-3 approval rate
    def _weighted_avg_rate(r):
        channels = [ch for ch in r["t1"].channels if ch.channel_name != "总计"]
        total_exp = sum(ch.expense for ch in channels)
        if total_exp == 0:
            return 0
        return sum(ch.approval_rate_1_3 * ch.expense for ch in channels) / total_exp

    rates = [_weighted_avg_rate(r) for r in results]
    _add_row("加权1-3过件率", rates)

    # Build DataFrame
    df = pd.DataFrame(rows)
    display_cols = ["指标"] + labels

    def _style_row(row):
        styles = [""] * len(row)
        best = row.get("_best")
        worst = row.get("_worst")
        for i, lbl in enumerate(labels, start=1):
            val = row.get(lbl)
            if val is not None and best is not None:
                if val == best and best != worst:
                    styles[i] = "color: #16a34a; font-weight: bold"
                elif val == worst and best != worst:
                    styles[i] = "color: #dc2626"
        return styles[:len(display_cols)]

    styled = df[display_cols].style.apply(
        lambda row: _style_row(df.iloc[row.name]),
        axis=1,
    ).format({
        lbl: lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) and abs(v) > 10 else
             f"{v:.2%}" if isinstance(v, float) and abs(v) < 1 else f"{v}"
        for lbl in labels
    })

    st.dataframe(styled, use_container_width=True, hide_index=True)


def _render_channel_drilldown(results: list):
    """Expandable per-channel detail."""
    labels = [r["label"] for r in results]
    with st.expander("渠道明细 (点击展开)", expanded=False):
        for r in results[0]["t1"].channels:
            if r.channel_name == "总计":
                continue
            ch_name = r.channel_name
            row = {"渠道": ch_name}
            for res in results:
                ch = next((c for c in res["t1"].channels if c.channel_name == ch_name), None)
                if ch:
                    row[f"{res['label']}_花费"] = f"{ch.expense:,.0f}"
                    row[f"{res['label']}_CPS"] = f"{ch.cps_1_8:.2%}" if ch.cps_1_8 else "-"
                    row[f"{res['label']}_T0"] = f"{ch.t0_transaction:.4f}"
            st.markdown(f"**{ch_name}**")
            cols = st.columns(len(results))
            for i, res in enumerate(results):
                ch = next((c for c in res["t1"].channels if c.channel_name == ch_name), None)
                if ch:
                    cols[i].metric(
                        res["label"],
                        f"{ch.expense:,.0f}万",
                        f"CPS {ch.cps_1_8:.1%}" if ch.cps_1_8 else None,
                    )


def _render_guardrail_section():
    """Display guardrail indicators if data is uploaded."""
    guardrail_df = st.session_state.get("guardrail_data")
    if guardrail_df is None or (isinstance(guardrail_df, pd.DataFrame) and guardrail_df.empty):
        st.caption("护栏指标: 暂无数据。请在「数据上传与配置」页上传护栏指标文件。")
        return

    st.markdown("**护栏指标 (Phase 1 — 仅展示)**")
    thresholds = st.session_state.get("guardrail_thresholds", DEFAULT_GUARDRAIL_THRESHOLDS)

    def _highlight_threshold(val, col_name):
        if col_name in thresholds and isinstance(val, (int, float)) and not np.isnan(val):
            if val > thresholds[col_name]:
                return "background-color: #fecaca; color: #991b1b"
        return ""

    display_df = guardrail_df.copy()
    # Show latest month only
    if "月份" in display_df.columns:
        latest = display_df["月份"].max()
        display_df = display_df[display_df["月份"] == latest]

    metric_cols = ["FPD30", "首借终损率", "复借终损率", "复借交易额", "渠道LTV"]
    styled = display_df.style
    if "FPD30" in display_df.columns:
        styled = styled.map(
            lambda v: _highlight_threshold(v, "FPD30"),
            subset=["FPD30"],
        )
    for col in ["首借终损率", "复借终损率"]:
        if col in display_df.columns:
            styled = styled.map(
                lambda v, c=col: _highlight_threshold(v, c),
                subset=[col],
            )

    st.dataframe(styled, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Goal selector (shared UI for inline + tab)
# ---------------------------------------------------------------------------

def _render_goal_selector(key_prefix: str = "goal") -> Tuple[str, List[float]]:
    """Render the goal direction radio + gradient inputs. Returns (direction, gradients)."""
    direction = st.radio(
        "优化方向",
        VALID_DIRECTIONS,
        horizontal=True,
        key=f"{key_prefix}_direction",
        help="降成本: 降低各渠道CPS | 提质量: 提升1-3过件率 | 提规模: 增加总预算",
    )
    gcols = st.columns(3)
    defaults = [5, 10, 15]
    gradients = []
    for i, (col, label, default) in enumerate(zip(gcols, GRADIENT_LABELS, defaults)):
        with col:
            val = st.number_input(
                f"{label}幅度 (%)",
                min_value=1,
                max_value=50,
                value=default,
                key=f"{key_prefix}_grad_{i}",
            )
            gradients.append(val / 100.0)
    return direction, gradients


def _render_adopt_buttons(results: list, current: dict, key_prefix: str = "adopt"):
    """Render adopt buttons for each scenario (skip baseline).

    Uses the 'pending' pattern: stores params in session state for the next rerun,
    where _consume_pending_template_params() applies them before widgets are created.
    This avoids StreamlitAPIException when widget keys are already instantiated.
    """
    st.caption("**采纳将覆盖当前参数配置，未保存的修改将丢失。**")
    cols = st.columns(len(results) - 1)
    for i, (col, res) in enumerate(zip(cols, results[1:])):
        with col:
            if res["params"] and st.button(
                f"采纳: {res['label']}",
                key=f"{key_prefix}_{i}",
                use_container_width=True,
            ):
                adoption = _build_adoption_params(res["params"], current)
                # Use pending pattern to avoid widget key conflict
                st.session_state["pending_result_template_params"] = adoption
                st.session_state.pop("goal_scenarios", None)
                st.rerun()


# ---------------------------------------------------------------------------
# Public renderers
# ---------------------------------------------------------------------------

def render_inline_goal_selector():
    """Compact pre-calculation goal selector (inline expander in parameter panel area)."""
    current = _get_current_params_from_session()
    if current is None:
        return

    with st.expander("🎯 目标方案快捷配置", expanded=False):
        direction, gradients = _render_goal_selector(key_prefix="inline_goal")

        if st.button("生成对比方案", key="inline_goal_generate", use_container_width=True):
            with st.spinner("⏳ 正在生成对比方案..."):
                _run_scenarios(current, direction, gradients)
            st.rerun()

        # Show compact results if available
        gs = st.session_state.get("goal_scenarios")
        if gs:
            results = gs["results"]
            st.markdown(f"**方向: {gs['direction']}** — 基线 + {len(results)-1} 个梯度方案")
            metric_cols = st.columns(len(results))
            for col, r in zip(metric_cols, results):
                with col:
                    st.metric(r["label"], f"{r['t1'].total_expense:,.0f}万")
                    st.caption(f"CPS {r['t2'].total_cps:.2%}")
                    st.caption(f"T0 {r['t1'].total_t0_transaction:.4f}亿")

            _render_adopt_buttons(results, current, key_prefix="inline_adopt")


def render_tab_goal_scenarios():
    """Full goal scenarios tab: selector + comparison table + drill-down + guardrails."""
    current = _get_current_params_from_session()
    if current is None:
        st.info("请先完成参数配置，目标方案功能将在此处可用。")
        return

    st.markdown("### 目标驱动方案生成")
    st.caption("选择优化方向和梯度幅度，自动生成对比方案。基于当前参数重新计算。")

    direction, gradients = _render_goal_selector(key_prefix="tab_goal")

    if st.button("🚀 生成对比方案", key="tab_goal_generate", type="primary", use_container_width=True):
        with st.spinner("⏳ 正在生成对比方案 (基线 + 3个梯度)..."):
            _run_scenarios(current, direction, gradients)
        st.rerun()

    # Display results
    gs = st.session_state.get("goal_scenarios")
    if not gs:
        st.info("点击上方按钮生成对比方案。")
        return

    results = gs["results"]
    st.markdown(f"**优化方向: {gs['direction']}** | 梯度: {', '.join(f'{g:.0%}' for g in gs['gradients'])}")
    st.markdown("---")

    # Comparison table
    st.markdown("#### 方案对比")
    _render_comparison_table(results)

    # Channel drill-down
    _render_channel_drilldown(results)

    # Guardrail section
    _render_guardrail_section()

    # MMM reference (if available)
    mmm_model = st.session_state.get("mmm_model")
    if mmm_model is not None:
        st.markdown("---")
        st.markdown("**MMM 参考**")
        mmm_spend = st.session_state.get("mmm_v01_recommended_spends", {})
        mmm_loan = st.session_state.get("mmm_predicted_loan_amt", 0)
        if mmm_spend:
            mcols = st.columns(3)
            mcols[0].metric("MMM推荐总花费", f"{sum(mmm_spend.values()):,.0f}万")
            mcols[1].metric("MMM预测借款", f"{mmm_loan:,.0f}万")
            if mmm_loan > 0:
                mcols[2].metric("MMM预测CPS", f"{sum(mmm_spend.values()) / mmm_loan:.2%}")

    # Adoption
    st.markdown("---")
    _render_adopt_buttons(results, current, key_prefix="tab_adopt")
