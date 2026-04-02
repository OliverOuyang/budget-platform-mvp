import streamlit as st
import pandas as pd
from app.flow_components import (
    render_bullet_summary,
    render_flow_header,
    render_guidance_card,
    render_next_step_card,
    render_section_header,
    render_status_card,
    render_step_progress,
)
from pages._tab_overview import render_tab_overview
from pages._tab_channel_result import render_tab_channel_result
from pages._tab_customer_result import render_tab_customer_result
from pages._tab_coefficient_trace import render_tab_coefficient_trace
from pages._tab_scenario_manager import render_tab_scenario_manager
from app.config import CHANNEL_NAMES, DEFAULT_DAYS_ELAPSED, DEFAULT_MONTH_DAYS, DEFAULT_TOTAL_BUDGET
from app.ui_utils import (
    build_channel_parameter_rows,
    ensure_flow_state,
    get_v01_flow,
    parse_channel_parameter_rows,
    run_calculation,
    update_v01_flow,
    build_v01_decision_summary,
)
from core.data_loader import extract_last_month_data
from core.models import BudgetParameters


def _build_latest_share_rows(last_month: dict[str, dict]) -> list[dict]:
    total_expense_raw = sum((item.get("花费") or 0) for item in last_month.values())
    rows = []
    for channel_name, item in last_month.items():
        expense = float(item.get("花费") or 0)
        rows.append(
            {
                "渠道": channel_name,
                "历史过件率(%)": float(item.get("1-3t0过件率") or 0) * 100,
                "历史CPS(%)": float(item.get("1-8t0cps") or 0) * 100,
                "历史申完成本(元)": float(item.get("t0申完成本") or 0),
                "历史花费结构(%)": (expense / total_expense_raw * 100) if total_expense_raw else 0.0,
            }
        )
    return rows


def _apply_template_to_result_widgets(params: dict) -> None:
    """Sync loaded template values into result-page widget state."""
    st.session_state.current_template_params = params
    st.session_state["result_total_budget"] = float(params.get("total_budget", DEFAULT_TOTAL_BUDGET))
    st.session_state["result_m0_calc_period"] = int(params.get("existing_m0_calculation_months", 3))
    st.session_state["result_non_initial_credit"] = float(params.get("non_initial_credit_transaction", 0.0))
    st.session_state["result_rta_promotion_fee"] = float(params.get("rta_promotion_fee", 0.0))
    st.session_state["result_month_total_days"] = int(params.get("month_total_days", DEFAULT_MONTH_DAYS))
    st.session_state["result_days_elapsed"] = int(params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))
    st.session_state.pop("result_channel_editor", None)


def _consume_pending_template_params() -> None:
    """Apply pending template values on a fresh rerun before widgets are created."""
    pending_params = st.session_state.pop("pending_result_template_params", None)
    pending_name = st.session_state.pop("pending_result_template_name", None)
    if pending_params:
        _apply_template_to_result_widgets(pending_params)
        if pending_name:
            st.success(f"模板 '{pending_name}' 已加载")


def _clear_active_template_selection() -> None:
    """Clear template-selection state without wiping currently visible parameter values."""
    st.session_state.pop("result_selected_template", None)
    st.session_state.pop("current_template_params", None)


def _render_template_management(
    total_budget: float,
    channel_1_3_rate: dict[str, float],
    channel_1_8_cps: dict[str, float],
    channel_t0_cost: dict[str, float],
    non_initial_credit: float,
    existing_m0_expense: float,
    rta_promotion_fee: float,
    month_total_days: int,
    days_elapsed: int,
    m0_calc_period: int,
) -> None:
    tm = st.session_state.get("template_manager")
    if tm is None:
        return

    templates = tm.list_templates()
    tab_save, tab_load, tab_delete = st.tabs(["保存模板", "加载模板", "删除模板"])

    with tab_save:
        save_name = st.text_input("模板名称", key="result_template_name", placeholder="例如：4月基准方案")
        save_desc = st.text_input("描述", key="result_template_desc", placeholder="例如：按最新月花费结构配置")
        overwrite_key = "result_template_overwrite_confirm"
        if st.session_state.get(overwrite_key):
            st.warning(
                f"模板 '{st.session_state[overwrite_key]}' 已存在。你可以直接覆盖，或改名后另存。"
            )
            overwrite_cols = st.columns(2)
            if overwrite_cols[0].button("覆盖现有模板", key="result_confirm_overwrite", use_container_width=True):
                save_name = st.session_state[overwrite_key]
                st.session_state["result_template_name"] = save_name
            if overwrite_cols[1].button("取消覆盖", key="result_cancel_overwrite", use_container_width=True):
                st.session_state.pop(overwrite_key, None)
                st.rerun()
        if st.button("💾 保存当前参数", key="result_save_template", use_container_width=True):
            if not save_name.strip():
                st.error("请填写模板名称")
            else:
                params = BudgetParameters(
                    total_budget=total_budget,
                    channel_1_3_approval_rate=channel_1_3_rate,
                    channel_1_8_cps=channel_1_8_cps,
                    channel_t0_completion_cost=channel_t0_cost,
                    non_initial_credit_transaction=non_initial_credit,
                    existing_m0_expense=existing_m0_expense,
                    rta_promotion_fee=rta_promotion_fee,
                    month_total_days=month_total_days,
                    days_elapsed=days_elapsed,
                    existing_m0_calculation_months=m0_calc_period,
                )
                pending_name = st.session_state.get(overwrite_key)
                if tm.template_exists(save_name.strip()) and pending_name != save_name.strip():
                    st.session_state[overwrite_key] = save_name.strip()
                    st.rerun()
                else:
                    try:
                        tm.save_template(
                            template_name=save_name.strip(),
                            params=params,
                            channel_1_3_rate=channel_1_3_rate,
                            channel_1_8_cps=channel_1_8_cps,
                            channel_t0_cost=channel_t0_cost,
                            non_initial_credit=non_initial_credit,
                            existing_m0_expense=existing_m0_expense,
                            rta_promotion_fee=rta_promotion_fee,
                            description=save_desc.strip(),
                            overwrite=(pending_name == save_name.strip()),
                        )
                        st.session_state.pop(overwrite_key, None)
                        st.success(f"模板 '{save_name}' 已保存")
                        st.rerun()
                    except FileExistsError:
                        st.session_state[overwrite_key] = save_name.strip()
                        st.rerun()

    with tab_load:
        if not templates:
            st.info("暂无已保存模板")
        else:
            template_names = [item["name"] for item in templates]
            selected = st.selectbox("选择模板", template_names, key="result_selected_template")
            if st.button("📂 加载此模板", key="result_load_template", use_container_width=True):
                template_data = tm.load_template(selected)
                if template_data:
                    st.session_state["pending_result_template_params"] = template_data["parameters"]
                    st.session_state["pending_result_template_name"] = selected
                    st.rerun()
                else:
                    st.error(f"加载模板 '{selected}' 失败")

    with tab_delete:
        if not templates:
            st.info("暂无可删除模板")
        else:
            delete_name = st.selectbox("选择要删除的模板", [item["name"] for item in templates], key="result_delete_template_name")
            st.caption("删除后不可恢复。")
            if st.button("🗑️ 删除模板", key="result_delete_template", use_container_width=True):
                if tm.delete_template(delete_name):
                    if st.session_state.get("result_selected_template") == delete_name:
                        _clear_active_template_selection()
                    st.success(f"模板 '{delete_name}' 已删除")
                    st.rerun()
                else:
                    st.error(f"删除模板 '{delete_name}' 失败")


def _render_parameter_panel() -> bool:
    data = st.session_state.get("uploaded_data")
    if not data:
        return False

    _consume_pending_template_params()
    template_params = st.session_state.get("current_template_params", {})
    last_month = extract_last_month_data(data["df_raw1"])
    latest_share_rows = _build_latest_share_rows(last_month)

    st.subheader("🛠️ 参数配置与计算")
    render_guidance_card(
        "在本页完成参数配置",
        "参考最新月历史过件率、CPS、申完成本和花费结构设置参数，点击计算后结果会在当前页下方刷新。",
    )
    hist_total_budget = sum(item.get("花费", 0) for item in last_month.values()) / 10000 if last_month else 0
    baseline_approval = (
        sum((item.get("1-3t0过件率") or 0) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cps = (
        sum((item.get("1-8t0cps") or 0) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )
    baseline_cost = (
        sum((item.get("t0申完成本") or 0) for item in last_month.values()) / len(last_month) if last_month else 0.0
    )

    layout_left, layout_right = st.columns([1.7, 1.1], gap="large")

    with layout_left:
        with st.container(border=True):
            render_section_header("核心预算输入", "先确认预算总量和计算周期，再编辑渠道参数。")
            total_budget = st.slider(
                "总花费 (万元)",
                500,
                10000,
                int(st.session_state.get("result_total_budget", template_params.get("total_budget", DEFAULT_TOTAL_BUDGET))),
                50,
                key="result_total_budget",
            )
            top_cols = st.columns(2)
            with top_cols[0]:
                m0_calc_period = st.radio(
                    "存量首登M0计算周期",
                    [3, 6],
                    index=0 if int(st.session_state.get("result_m0_calc_period", template_params.get("existing_m0_calculation_months", 3))) == 3 else 1,
                    horizontal=True,
                    key="result_m0_calc_period",
                )
            with top_cols[1]:
                st.metric("最新月总花费基线", f"{hist_total_budget:,.0f} 万元")

        with st.container(border=True):
            render_section_header("渠道参数矩阵", "左侧三列是本次计算使用的配置值，右侧三列是最新月历史参考值，便于直接判断偏离程度。")
            editor_df = st.data_editor(
                build_channel_parameter_rows(last_month, template_params),
                use_container_width=True,
                height=255,
                hide_index=True,
                disabled=["渠道", "历史1-3 T0过件率(%)", "历史1-8 T0CPS(%)", "历史T0申完成本(元)"],
                column_config={
                    "渠道": st.column_config.TextColumn("渠道", width="medium"),
                    "目标1-3过件率(%)": st.column_config.NumberColumn("目标过件率(%)", format="%.2f"),
                    "目标CPS(%)": st.column_config.NumberColumn("目标CPS(%)", format="%.2f"),
                    "上月申完成本(元)": st.column_config.NumberColumn("上月申完成本(元)", format="%.0f"),
                    "历史1-3 T0过件率(%)": st.column_config.NumberColumn("最新月过件率(%)", format="%.2f"),
                    "历史1-8 T0CPS(%)": st.column_config.NumberColumn("最新月CPS(%)", format="%.2f"),
                    "历史T0申完成本(元)": st.column_config.NumberColumn("最新月申完成本(元)", format="%.0f"),
                },
                key="result_channel_editor",
            )

        channel_1_3_rate, channel_1_8_cps, channel_t0_cost = parse_channel_parameter_rows(editor_df)
        existing_m0_expense = 0.0

        with st.container(border=True):
            render_section_header("补充业务参数", "补全非初审、RTA 和天数外推参数后再计算。")
            summary_cols = st.columns(2)
            with summary_cols[0]:
                non_initial_credit = st.number_input(
                    "非初审授信户首借交易额 (亿元)",
                    0.0,
                    value=float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
                    format="%.2f",
                    key="result_non_initial_credit",
                )
            with summary_cols[1]:
                rta_promotion_fee = st.number_input(
                    "RTA费用+促申完 (万元)",
                    0.0,
                    value=float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
                    format="%.2f",
                    key="result_rta_promotion_fee",
                )

            day_cols = st.columns(2)
            with day_cols[0]:
                month_total_days = st.number_input(
                    "当月总天数",
                    28,
                    31,
                    int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
                    key="result_month_total_days",
                )
            with day_cols[1]:
                days_elapsed = st.number_input(
                    "已完成天数",
                    1,
                    31,
                    int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
                    key="result_days_elapsed",
                )

    current_approval_avg = sum(channel_1_3_rate.values()) / len(channel_1_3_rate) if channel_1_3_rate else 0.0
    current_cps_avg = sum(channel_1_8_cps.values()) / len(channel_1_8_cps) if channel_1_8_cps else 0.0
    current_cost_avg = sum(channel_t0_cost.values()) / len(channel_t0_cost) if channel_t0_cost else 0.0

    with layout_right:
        with st.container(border=True):
            render_section_header("最新月参考", "先看当前设置与最新月平均水平的偏差，再决定是否计算。")
            history_cols = st.columns(2)
            history_cols[0].metric("1-3 过件率", f"{baseline_approval:.2%}", f"{current_approval_avg - baseline_approval:+.2%}")
            history_cols[1].metric("CPS", f"{baseline_cps:.2%}", f"{current_cps_avg - baseline_cps:+.2%}", delta_color="inverse")
            history_cols = st.columns(2)
            history_cols[0].metric("申完成本", f"{baseline_cost:,.0f} 元", f"{current_cost_avg - baseline_cost:+,.0f} 元", delta_color="inverse")
            history_cols[1].metric("花费基线", f"{hist_total_budget:,.0f} 万元", f"{total_budget - hist_total_budget:+,.0f} 万元")
            if latest_share_rows:
                st.dataframe(
                    pd.DataFrame(latest_share_rows),
                    use_container_width=True,
                    hide_index=True,
                    height=240,
                    column_config={
                        "历史过件率(%)": st.column_config.NumberColumn(format="%.2f"),
                        "历史CPS(%)": st.column_config.NumberColumn(format="%.2f"),
                        "历史申完成本(元)": st.column_config.NumberColumn(format="%.0f"),
                        "历史花费结构(%)": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            else:
                st.info("暂无足够的最新月数据用于生成渠道参考。")

        with st.container(border=True):
            render_section_header("模板管理", "模板不打断主计算流程，按需保存、加载或删除即可。")
            _render_template_management(
                total_budget,
                channel_1_3_rate,
                channel_1_8_cps,
                channel_t0_cost,
                float(st.session_state.get("result_non_initial_credit", template_params.get("non_initial_credit_transaction", 0.0))),
                0.0,
                float(st.session_state.get("result_rta_promotion_fee", template_params.get("rta_promotion_fee", 0.0))),
                int(st.session_state.get("result_month_total_days", template_params.get("month_total_days", DEFAULT_MONTH_DAYS))),
                int(st.session_state.get("result_days_elapsed", template_params.get("days_elapsed", DEFAULT_DAYS_ELAPSED))),
                m0_calc_period,
            )

        with st.container(border=True):
            render_section_header("本次计算确认", "确认关键约束无误后，再刷新下方结果区和分析 tabs。")
            st.metric("本次预算", f"{total_budget:,.0f} 万元")
            st.caption(f"计算周期：M0 {m0_calc_period} 个月")
            st.caption(f"已完成 {int(days_elapsed)} / {int(month_total_days)} 天")
            if days_elapsed > month_total_days:
                st.warning("已完成天数大于当月总天数，请先修正后再计算。")
            else:
                st.info("当前输入已通过基础校验，可以直接触发预算计算。")
            if st.button("🚀 计算预算", type="primary", use_container_width=True, disabled=days_elapsed > month_total_days):
                run_calculation(
                    data["df_raw1"],
                    data["df_raw2"],
                    total_budget,
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
                st.rerun()

    update_v01_flow(
        current_step=2,
        inputs={
            "total_budget": total_budget,
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
flow = get_v01_flow()
steps = ["数据上传与检查", "预算推算结果"]

render_flow_header(
    title="📈 V01 · 预算推算结果分析",
    purpose="基于已上传的数据，在本页完成参数配置、预算计算和结果分析，并决定是否保存方案或继续微调。",
    chain="数据上传与检查 → 预算推算结果",
    current_label="预算推算结果",
)
render_step_progress(steps, 2)
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

if t1 is None:
    render_guidance_card(
        "尚无计算结果",
        "请先在上方参数区完成配置并点击“计算预算”。计算后，结果与分析 tabs 会在当前页下方出现。",
        kind="info",
    )
    st.stop()
decision_summary = build_v01_decision_summary(flow, t1, t2)

render_guidance_card(
    decision_summary["headline"],
    "结果页会基于预算、CPS 和质量目标给出拍板建议。先看下方决策结论，再决定保存、比较或回调参数。",
    kind="success" if decision_summary["status"] == "success" else "warning" if decision_summary["status"] == "warning" else "info",
)
render_bullet_summary("当前建议动作", decision_summary["recommended_actions"])

# 核心指标
st.subheader("🎯 核心指标")
has_prev = st.session_state.get("previous_table1_result") is not None
prev_t1 = st.session_state.get("previous_table1_result")
prev_t2 = st.session_state.get("previous_table2_result")

delta_exp = (t1.total_expense - prev_t1.total_expense) if has_prev and prev_t1 else None
delta_tx = (t2.total_transaction - prev_t2.total_transaction) if has_prev and prev_t2 else None
delta_cps = (t2.total_cps - prev_t2.total_cps) if has_prev and prev_t2 else None
delta_t0 = (t1.total_t0_transaction - prev_t1.total_t0_transaction) if has_prev and prev_t1 else None
delta_apr = (t2.approval_rate_1_3_excl_age - prev_t2.approval_rate_1_3_excl_age) if has_prev and prev_t2 else None

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("总投放花费", f"{t1.total_expense:,.0f} 万元", f"{delta_exp:+,.0f} 万元" if delta_exp is not None else None)
m2.metric("整体首借交易额", f"{t2.total_transaction:.2f} 亿元", f"{delta_tx:+.2f} 亿元" if delta_tx is not None else None)
m3.metric("全业务CPS", f"{t2.total_cps:.2%}", f"{delta_cps:+.2%}" if delta_cps is not None else None, delta_color="inverse")
m4.metric("T0交易额", f"{t1.total_t0_transaction * 10:.2f} 千万元", f"{delta_t0 * 10:+.2f} 千万元" if delta_t0 is not None else None)
m5.metric("1-3 T0过件率", f"{t2.approval_rate_1_3_excl_age:.2%}", f"{delta_apr:+.2%}" if delta_apr is not None else None)

action_left, action_mid, action_right = st.columns(3)
if action_left.button("⬅️ 返回数据检查页", use_container_width=True):
    st.switch_page("pages/1_预算输入与配置.py")
if action_mid.button("📌 聚焦总览与方案", use_container_width=True):
    st.toast("继续查看下方总览、方案对比与数据洞察。")
if action_right.button("💾 前往方案管理", use_container_width=True):
    st.toast("请在页面底部的「方案管理」Tab 中保存或比较方案。")

render_next_step_card(
    "按状态执行下一步",
    "若主要目标已达成，优先保存或对比方案；若仍有未达成指标，先根据下方短板回看本页上方参数区或返回数据检查页。",
)

targets = flow.get("targets", {})
if targets:
    st.subheader("🎯 目标达成判断")
    goal_cols = st.columns(3)
    check_specs = [
        ("预算目标", decision_summary["checks"]["budget"], f"{t1.total_expense:,.0f} / {float(targets.get('budget_target', 0)):,.0f} 万元"),
        ("CPS 目标", decision_summary["checks"]["cps"], f"{t2.total_cps:.2%} / {float(targets.get('cps_target', 0)):.2%}"),
        ("过件率目标", decision_summary["checks"]["approval"], f"{t2.approval_rate_1_3_excl_age:.2%} / {float(targets.get('approval_target', 0)):.2%}"),
    ]
    for col, (label, check, value) in zip(goal_cols, check_specs):
        with col:
            render_status_card(label, f"{check['label']} · {value}", check["summary"], status=check["status"])

    blocker_order = sorted(
        [
            ("预算", abs(decision_summary["checks"]["budget"]["delta"] or 0)),
            ("CPS", abs(decision_summary["checks"]["cps"]["delta"] or 0)),
            ("过件率", abs(decision_summary["checks"]["approval"]["delta"] or 0)),
        ],
        key=lambda item: item[1],
        reverse=True,
    )
    render_bullet_summary(
        "当前最关键的决策判断",
        [
            f"当前最主要的约束项是 {blocker_order[0][0]}。",
            "可保存当前方案。" if decision_summary["status"] == "success" else "建议先微调后再保存。" if decision_summary["status"] == "info" else "当前不建议直接保存为正式场景。",
        ],
    )

    if decision_summary["status"] == "success":
        render_guidance_card("推荐动作：保存或进入方案对比", "主要目标已经达成，建议优先把当前方案保存下来，再和历史方案做拍板对比。", kind="success")
    elif decision_summary["status"] == "info":
        render_guidance_card("推荐动作：优先做小幅调参", "当前更像接近达成而非完全失败，建议先使用快速调参或只回调一类关键参数。")
    else:
        render_guidance_card("推荐动作：回看上方参数区", "当前存在明显未达成目标，建议按建议动作的优先级重新设置预算、CPS 或过件率假设。", kind="warning")

# 5个Tab
tabs = st.tabs(["🏠 总览", "📊 渠道结果", "👥 客群结果", "🔢 系数追溯", "💾 方案管理"])
with tabs[0]:
    render_tab_overview()
with tabs[1]:
    render_tab_channel_result()
with tabs[2]:
    render_tab_customer_result()
with tabs[3]:
    render_tab_coefficient_trace()
with tabs[4]:
    render_tab_scenario_manager()
