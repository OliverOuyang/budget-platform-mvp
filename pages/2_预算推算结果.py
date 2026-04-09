from __future__ import annotations

import streamlit as st
import pandas as pd
from app.flow_components import (
    render_flow_header,
    render_guidance_card,
    render_section_header,
    render_step_progress,
)
from pages._tab_channel_result import render_tab_channel_result
from pages._tab_customer_result import render_tab_customer_result
from pages._tab_coefficient_trace import render_tab_coefficient_trace
from pages._tab_scenario_manager import render_tab_scenario_manager
from pages._tab_model_comparison import render_tab_model_comparison
from pages._tab_goal_scenarios import render_tab_goal_scenarios, render_inline_goal_selector
from pages._tab_guardrail import render_tab_guardrail
from pages._tab_whatif import render_tab_whatif
from app.styles import inject_custom_css, render_impact_chain, render_callout
from app.config import CHANNEL_NAMES, DEFAULT_DAYS_ELAPSED, DEFAULT_MONTH_DAYS, DEFAULT_TOTAL_BUDGET
from app.ui_utils import (
    apply_template_to_result_widgets,
    build_channel_parameter_rows,
    ensure_flow_state,
    get_v01_flow,
    normalize_channel_history,
    parse_channel_parameter_rows,
    run_calculation,
    safe_num,
    update_v01_flow,
    build_v01_decision_summary,
)
from core.calculation_pipeline import execute_calculation_pipeline
from core.customer_group_calculator import extrapolate_by_days
from core.data_loader import extract_last_month_data
from core.models import BudgetParameters

from pages._result_historical import (
    _build_latest_share_rows,
    _build_history_baseline_rows,
    _compute_weighted_approval,
    _build_baseline_panel_data,
    _build_historical_channel_detail,
    _style_historical_channel_detail,
    _render_historical_baseline_panel,
    _build_historical_result_table,
    _style_historical_result_table,
)
from pages._result_target_preview import (
    _build_target_preview_table,
    _style_target_preview_table,
    _style_latest_reference_table,
)
from pages._result_template import (
    _apply_template_to_result_widgets,
    _consume_pending_template_params,
    _clear_active_template_selection,
    _render_template_management,
)
from pages._result_decision import render_decision_section


def _render_parameter_panel() -> bool:
    data = st.session_state.get("uploaded_data")
    if not data:
        return False

    _consume_pending_template_params()
    template_params = st.session_state.get("current_template_params", {})
    last_month = extract_last_month_data(data["df_raw1"])
    latest_share_rows = _build_latest_share_rows(last_month)

    st.subheader("🛠️ 参数配置与计算")

    # --- 历史达成 + 预估参数（默认折叠）---
    with st.expander("📊 历史达成与当月预估", expanded=False):
        st.caption("「预估」列使用当前月累计数据按已完成天数外推；历史月份按两张 raw 的可交集月份展示。")
        param_cols = st.columns(3)
        with param_cols[0]:
            month_total_days = st.number_input(
                "当月总天数",
                28,
                31,
                int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
                key="result_month_total_days",
            )
        with param_cols[1]:
            days_elapsed = st.number_input(
                "已完成天数",
                1,
                31,
                int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
                key="result_days_elapsed",
            )
        with param_cols[2]:
            m0_calc_period = st.radio(
                "存量首登M0计算周期",
                [3, 6],
                index=0 if int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))) == 3 else 1,
                horizontal=True,
                key="result_m0_calc_period",
            )
        extra_cols = st.columns(2)
        with extra_cols[0]:
            non_initial_credit = st.number_input(
                "非初审授信户首借交易额 (亿元)",
                0.0,
                value=float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
                format="%.2f",
                key="result_non_initial_credit",
            )
        with extra_cols[1]:
            rta_promotion_fee = st.number_input(
                "RTA费用+促申完 (万元)",
                0.0,
                value=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
                format="%.2f",
                key="result_rta_promotion_fee",
            )
        historical_table = _build_historical_result_table(
            data["df_raw1"],
            data["df_raw2"],
            month_total_days=int(month_total_days),
            days_elapsed=int(days_elapsed),
            rta_estimate=rta_promotion_fee,
        )
        if not historical_table.empty:
            historical_height = min(760, 52 + (len(historical_table) + 1) * 42)
            st.dataframe(
                _style_historical_result_table(historical_table),
                use_container_width=True,
                hide_index=True,
                height=historical_height,
            )
        else:
            st.info("历史月份不足，暂时无法生成达成与预估表。")

        # 各月渠道核心指标明细
        channel_details = _build_historical_channel_detail(data["df_raw1"])
        if channel_details:
            st.markdown("---")
            st.caption("📋 各月渠道核心指标明细（蓝色=预算，绿色=质量，橙色=成本，紫色=产出）")
            detail_tabs = st.tabs([label for label, _ in channel_details])
            for tab, (_, detail_df) in zip(detail_tabs, channel_details):
                with tab:
                    detail_height = min(300, 52 + (len(detail_df) + 1) * 38)
                    st.dataframe(
                        _style_historical_channel_detail(detail_df),
                        use_container_width=True,
                        hide_index=True,
                        height=detail_height,
                    )

    hist_total_budget = sum(safe_num(item.get("花费")) for item in last_month.values()) / 10000 if last_month else 0
    baseline_approval = (
        sum(safe_num(item.get("1-3t0过件率")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cps = (
        sum(safe_num(item.get("1-8t0cps")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cost = (
        sum(safe_num(item.get("t0申完成本")) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )

    # --- 模板管理（默认折叠）---
    with st.expander("💾 模板管理（可选）", expanded=False):
        _render_template_management(
            float(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
            template_params.get("channel_budget_shares", {}),
            template_params.get("channel_1_3_approval_rate", {}),
            template_params.get("channel_1_8_cps", {}),
            template_params.get("channel_t0_completion_cost", {}),
            float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
            0.0,
            float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
            int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
            int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
            int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))),
        )

    # --- 核心预算输入 ---
    with st.container(border=True):
        render_section_header("💰 核心预算输入", "确定总预算规模。")
        budget_cols = st.columns([3, 1])
        with budget_cols[0]:
            total_budget = st.slider(
                "总花费 (万元)",
                500,
                10000,
                int(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
                50,
                key="result_total_budget",
            )
        with budget_cols[1]:
            st.metric("较最新月差异", f"{total_budget - hist_total_budget:+,.0f} 万元")

    # --- Step 3.5: MMM 智能推荐（可选）---
    mmm_model = st.session_state.get("mmm_model")
    mmm_recommendations = {}  # channel_name -> {spend, roi, saturation}

    if mmm_model is not None:
        with st.container(border=True):
            st.markdown(
                '<div style="border-left:4px solid #7B1FA2; padding-left:12px;">'
                '<span style="font-size:15px;font-weight:600;">步骤 3.5 - MMM 智能推荐</span> '
                '<span style="background:#7B1FA2;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;">MMM</span> '
                '<span style="background:#1976D2;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:700;">可选</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"基于已训练的 MMM 模型，在 {total_budget:,.0f} 万元总预算约束下，按等边际原则计算最优渠道分配。")

            # Model status callout
            trainer = st.session_state.get("mmm_trainer")
            model_info = ""
            if trainer and hasattr(trainer, "best_score"):
                model_info = f"R²={getattr(trainer, 'best_score', 0):.2f}"
            st.info(f"**模型状态：** 已加载 | {model_info} | 训练数据来自 MMM 模型洞察页")

            # Get optimization results from MMM
            recommended_spends = st.session_state.get("mmm_v01_recommended_spends", {})
            if recommended_spends:
                rec_rows = []
                for ch_name in CHANNEL_NAMES:
                    hist_expense = safe_num(last_month.get(ch_name, {}).get("花费")) / 10000 if last_month.get(ch_name) else 0
                    mmm_spend = recommended_spends.get(ch_name, hist_expense)
                    change_pct = ((mmm_spend - hist_expense) / hist_expense * 100) if hist_expense > 0 else 0
                    roi = st.session_state.get("mmm_v01_channel_roi", {}).get(ch_name, 0)
                    sat = st.session_state.get("mmm_v01_channel_saturation", {}).get(ch_name, 0)

                    if sat > 85:
                        advice = "接近饱和，建议减投"
                    elif sat < 50 and roi > 2:
                        advice = "ROI高，加大投入"
                    elif change_pct > 10:
                        advice = "适度增投"
                    elif change_pct < -10:
                        advice = "建议控量"
                    else:
                        advice = "维持现状"

                    mmm_recommendations[ch_name] = {"spend": mmm_spend, "roi": roi, "saturation": sat}
                    rec_rows.append({
                        "渠道": ch_name,
                        "上月花费(万)": f"{hist_expense:,.0f}",
                        "MMM推荐(万)": f"{mmm_spend:,.0f}",
                        "变化": f"{change_pct:+.1f}%",
                        "ROI": f"{roi:.1f}x" if roi > 0 else "-",
                        "饱和度": f"{sat:.0f}%" if sat > 0 else "-",
                        "操作建议": advice,
                    })

                st.dataframe(pd.DataFrame(rec_rows), use_container_width=True, hide_index=True)

                # 一键采纳 button
                adopt_cols = st.columns([1, 1])
                with adopt_cols[0]:
                    if st.button("🤖 一键采纳 → 填入下方参数矩阵", type="primary", use_container_width=True):
                        for ch_name, rec in mmm_recommendations.items():
                            # Update template params to use MMM recommended spends
                            if total_budget > 0:
                                template_params.setdefault("channel_budget_shares", {})[ch_name] = rec["spend"] / total_budget
                        st.session_state.pop("result_channel_editor", None)
                        st.rerun()
                with adopt_cols[1]:
                    st.button("跳过，手动配置", use_container_width=True)
                st.caption("采纳后仍可在下方参数矩阵中微调。MMM 推荐基于等边际原则优化，不保证与所有业务约束一致。")
            else:
                st.warning("MMM 模型已训练但尚无预算优化结果。请前往 MMM 模型洞察页的「预算优化」Tab 运行优化。")

    # --- 渠道参数矩阵（合并了最新月参考 + MMM参考 + 均值校验）---
    with st.container(border=True):
        render_section_header("📋 渠道参数矩阵", "蓝色=可编辑，紫色=MMM参考，灰色=历史参考。")
        editor_rows = build_channel_parameter_rows(last_month, template_params, total_budget=total_budget, mmm_recommendations=mmm_recommendations)
        editor_height = min(300, 52 + (len(editor_rows) + 1) * 38)

        # Column config with color coding
        col_config = {
            "渠道": st.column_config.TextColumn("渠道", width="medium"),
            "目标花费(万元)": st.column_config.NumberColumn("🔵目标花费(万元)", format="%.0f"),
            "目标1-3过件率(%)": st.column_config.NumberColumn("🔵目标过件率(%)", format="%.2f"),
            "目标CPS(%)": st.column_config.NumberColumn("🔵目标CPS(%)", format="%.2f"),
            "MMM建议(万)": st.column_config.NumberColumn("🟣MMM建议(万)", format="%.0f"),
            "MMM·ROI": st.column_config.NumberColumn("🟣ROI", format="%.1f"),
            "MMM·饱和度(%)": st.column_config.NumberColumn("🟣饱和度(%)", format="%.0f"),
            "参考·花费结构(%)": st.column_config.NumberColumn("参考·花费结构(%)", format="%.2f"),
            "参考·CPS(%)": st.column_config.NumberColumn("参考·CPS(%)", format="%.2f"),
            "T0申完成本(元)": st.column_config.NumberColumn("T0申完成本(元)", format="%.0f"),
        }
        disabled_cols = ["渠道", "MMM建议(万)", "MMM·ROI", "MMM·饱和度(%)", "参考·花费结构(%)", "参考·CPS(%)", "T0申完成本(元)"]
        editor_df = st.data_editor(
            editor_rows,
            use_container_width=True,
            height=editor_height,
            hide_index=True,
            disabled=disabled_cols,
            column_config=col_config,
            key="result_channel_editor",
        )

        # 合计行：预算分配汇总
        channel_budget_shares, channel_1_3_rate, channel_1_8_cps, channel_t0_cost = parse_channel_parameter_rows(editor_df)
        allocated_total = sum(max(float(row.get("目标花费(万元)") or 0), 0) for row in editor_df.to_dict("records"))
        budget_diff = allocated_total - total_budget
        alloc_cols = st.columns([2, 1])
        with alloc_cols[0]:
            if abs(budget_diff) < 1:
                st.success(f"合计: {allocated_total:,.0f} / {total_budget:,.0f} 万元 ✅ 预算已分配完毕")
            else:
                st.warning(f"合计: {allocated_total:,.0f} / {total_budget:,.0f} 万元（差额 {budget_diff:+,.0f} 万元）")
        with alloc_cols[1]:
            st.caption("各渠道花费之和可以不等于总预算，差额仅作提示。")

        # MMM 饱和度提示
        if mmm_recommendations:
            high_sat_channels = [(ch, rec["saturation"]) for ch, rec in mmm_recommendations.items() if rec.get("saturation", 0) > 80]
            if high_sat_channels:
                sat_texts = [f"{ch} 饱和度 {sat:.0f}%" for ch, sat in high_sat_channels]
                st.warning(f"**MMM 提示：** {', '.join(sat_texts)}，继续增投的边际回报递减。建议将预算向低饱和度渠道倾斜。")

        # 内联均值校验（原步骤 5）
        existing_m0_expense = 0.0
        current_approval_avg = sum(channel_1_3_rate.values()) / len(channel_1_3_rate) if channel_1_3_rate else 0.0
        current_cps_avg = sum(channel_1_8_cps.values()) / len(channel_1_8_cps) if channel_1_8_cps else 0.0
        current_cost_avg = sum(channel_t0_cost.values()) / len(channel_t0_cost) if channel_t0_cost else 0.0
        compare_cols = st.columns(3)
        compare_cols[0].metric("当前均值 vs 最新月过件率", f"{current_approval_avg:.2%}", f"{current_approval_avg - baseline_approval:+.2%}")
        compare_cols[1].metric("当前均值 vs 最新月CPS", f"{current_cps_avg:.2%}", f"{current_cps_avg - baseline_cps:+.2%}", delta_color="inverse")
        compare_cols[2].metric("当前均值 vs 最新月申完成本", f"{current_cost_avg:,.0f} 元", f"{current_cost_avg - baseline_cost:+,.0f} 元", delta_color="inverse")

        # 参数异常值校验
        _param_warnings = []
        for ch, cps_val in channel_1_8_cps.items():
            if cps_val <= 0:
                _param_warnings.append(f"**{ch}** CPS 为 0，将导致交易额计算异常")
            elif cps_val > 1:
                _param_warnings.append(f"**{ch}** CPS={cps_val:.0%} 超过100%，请确认是否正确")
        for ch, rate_val in channel_1_3_rate.items():
            if rate_val > 0.9:
                _param_warnings.append(f"**{ch}** 过件率={rate_val:.0%} 偏高，请确认是否合理")
        for ch, cost_val in channel_t0_cost.items():
            if cost_val <= 0:
                _param_warnings.append(f"**{ch}** 申完成本为 0，将导致申完量计算异常")
        if _param_warnings:
            st.warning("参数异常提示：" + "；".join(_param_warnings))

    # --- 目标拆解预览 ---
    with st.container(border=True):
        render_section_header("📎 目标拆解预览", "检查目标拆解表是否接近预期。")

        target_preview_df = _build_target_preview_table(
            df_raw1=data["df_raw1"],
            df_raw2=data["df_raw2"],
            total_budget=total_budget,
            channel_budget_shares=channel_budget_shares,
            channel_1_3_rate=channel_1_3_rate,
            channel_1_8_cps=channel_1_8_cps,
            channel_t0_cost=channel_t0_cost,
            non_initial_credit=non_initial_credit,
            rta_promotion_fee=rta_promotion_fee,
            month_total_days=month_total_days,
            days_elapsed=days_elapsed,
            m0_calc_period=m0_calc_period,
            last_month_data=last_month,
        )
        target_month_label = f"{days_elapsed} / {month_total_days} 天口径"
        if 'df_raw1' not in data or '月份' not in data['df_raw1'].columns:
            st.warning("数据不完整，无法推算结果")
            return
        st.caption(f"{pd.to_datetime(max(data['df_raw1']['月份'])).month}月首登T0目标 · {total_budget:,.0f}万预算 · {target_month_label}")
        st.caption("蓝色看预算与结构，绿色看质量，橙色看成本，紫色看产出量。总计行会单独高亮。")
        target_preview_height = min(340, 52 + (len(target_preview_df) + 1) * 40) if not target_preview_df.empty else 220
        st.dataframe(
            _style_target_preview_table(target_preview_df),
            use_container_width=True,
            hide_index=True,
            height=target_preview_height,
        )

    # --- 计算按钮 ---
    with st.container(border=True):
        confirm_cols = st.columns(3)
        confirm_cols[0].metric("本次预算", f"{total_budget:,.0f} 万元")
        confirm_cols[1].metric("M0周期", f"{m0_calc_period} 个月")
        confirm_cols[2].metric("已完成天数", f"{int(days_elapsed)} / {int(month_total_days)} 天")
        if days_elapsed > month_total_days:
            st.warning("已完成天数大于当月总天数，请先修正后再计算。")
        if st.button("🚀 计算预算", type="primary", use_container_width=True, disabled=days_elapsed > month_total_days):
            run_calculation(
                data["df_raw1"],
                data["df_raw2"],
                total_budget,
                channel_budget_shares,
                channel_1_3_rate,
                channel_1_8_cps,
                channel_t0_cost,
                non_initial_credit,
                existing_m0_expense,
                rta_promotion_fee,
                int(month_total_days),
                int(days_elapsed),
                int(m0_calc_period),
            )
            st.session_state.pop("goal_scenarios", None)  # Clear stale scenario data
            st.rerun()

    update_v01_flow(
        current_step=2,
        inputs={
            "total_budget": total_budget,
            "channel_budget_shares": channel_budget_shares,
            "channel_1_3_rate": channel_1_3_rate,
            "channel_1_8_cps": channel_1_8_cps,
            "channel_t0_cost": channel_t0_cost,
            "non_initial_credit": non_initial_credit,
            "existing_m0_expense": existing_m0_expense,
            "rta_promotion_fee": rta_promotion_fee,
            "month_total_days": int(month_total_days),
            "days_elapsed": int(days_elapsed),
            "m0_calc_period": int(m0_calc_period),
        },
        targets={
            "budget_target": float(total_budget),
            "cps_target": float(current_cps_avg or baseline_cps),
            "approval_target": float(current_approval_avg or baseline_approval),
        },
        next_step="点击计算后查看下方结果和分析 tabs",
    )
    return True


ensure_flow_state()
inject_custom_css()
flow = get_v01_flow()
steps = ["数据上传", "历史基线", "总预算", "MMM推荐", "渠道参数", "补充参数", "计算结果"]

render_flow_header(
    title="📈 预算推算结果",
    purpose="配置总预算 → 参考 MMM 推荐 → 调整渠道参数 → 运行双引擎计算 → 查看结果对比",
    chain="数据上传与检查 → **预算推算结果**",
    current_label="预算推算结果",
)
render_step_progress(steps, 3)
update_v01_flow(current_step=2, next_step="在本页完成参数配置、计算并查看结果")

t1 = st.session_state.get("table1_result")
t2 = st.session_state.get("table2_result")

if st.session_state.get("uploaded_data") is None:
    render_guidance_card(
        "缺少输入数据",
        "请先前往数据上传与检查页上传 Excel 并完成基础检查，再回到当前页配置参数和执行计算。",
        kind="warning",
    )
    if st.button("⬅️ 前往数据上传与检查页", use_container_width=True):
        st.switch_page("pages/1_预算输入与配置.py")
    st.stop()

_render_parameter_panel()

# --- Goal-driven scenario quick entry (pre-calculation accessible) ---
render_inline_goal_selector()

if t1 is None:
    render_guidance_card(
        "尚无计算结果",
        '请先在上方参数区完成配置并点击\u201c计算预算\u201d。计算后，结果与分析 tabs 会在当前页下方出现。',
        kind="info",
    )
    st.stop()
decision_summary = build_v01_decision_summary(flow, t1, t2)

# --- 前置数据：与上次对比 ---
prev_t1 = st.session_state.get("previous_table1_result")
prev_t2 = st.session_state.get("previous_table2_result")

render_decision_section(t1, t2, prev_t1, prev_t2, flow, decision_summary)

# --- 历史达成与当月预估（折叠）---
data = st.session_state.get("uploaded_data")
if data is not None:
    with st.expander("📊 历史达成与当月预估 (点击展开)", expanded=False):
        flow_state = get_v01_flow()
        inputs = flow_state.get("inputs", {})
        _days = int(inputs.get("days_elapsed", DEFAULT_DAYS_ELAPSED))
        _month_days = int(inputs.get("month_total_days", DEFAULT_MONTH_DAYS))
        _render_historical_baseline_panel(
            data["df_raw1"],
            month_total_days=_month_days,
            days_elapsed=_days,
        )

# --- 分项详情 Tabs (V4.3c: 6 tabs) ---
st.markdown("---")
st.caption("**分项详情**")

tabs = st.tabs(["📊 渠道", "👥 客群", "🛡️ 护栏", "🎯 方案", "🤖 双引擎", "📈 What-if"])
with tabs[0]:
    render_tab_channel_result()
with tabs[1]:
    render_tab_customer_result()
with tabs[2]:
    render_tab_guardrail()
with tabs[3]:
    render_tab_goal_scenarios()
with tabs[4]:
    render_tab_model_comparison()
with tabs[5]:
    render_tab_whatif()
