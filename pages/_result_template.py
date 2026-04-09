from __future__ import annotations

import streamlit as st
from app.ui_utils import apply_template_to_result_widgets
from core.models import BudgetParameters


def _apply_template_to_result_widgets(params: dict) -> None:
    """Sync loaded template values into result-page widget state."""
    apply_template_to_result_widgets(params)


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
    channel_budget_shares: dict[str, float],
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
            if overwrite_cols[1].button("取消覆盖", key="result_cancel_overwrite", use_container_width=True):
                st.session_state.pop(overwrite_key, None)
                st.rerun()
        if st.button("💾 保存当前参数", key="result_save_template", use_container_width=True):
            if not save_name.strip():
                st.error("请填写模板名称")
            else:
                params = BudgetParameters(
                    total_budget=total_budget,
                    channel_budget_shares=channel_budget_shares,
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
                            channel_budget_shares=channel_budget_shares,
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
