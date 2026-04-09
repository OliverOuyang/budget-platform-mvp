"""Shared parameter assembly helpers for what-if and goal-scenario tabs."""
from __future__ import annotations

from typing import Optional
import streamlit as st
from app.config import DEFAULT_TOTAL_BUDGET, DEFAULT_MONTH_DAYS, DEFAULT_DAYS_ELAPSED
from core.calculation_pipeline import execute_calculation_pipeline


def get_current_pipeline_params() -> Optional[dict]:
    """Assemble pipeline parameters from session state.

    Returns None if uploaded data or channel configuration is missing.
    """
    data = st.session_state.get("uploaded_data")
    if not data:
        return None

    flow = st.session_state.get("v01_flow", {})
    inputs = flow.get("inputs", {})
    channel_budget_shares = inputs.get("channel_budget_shares", {})
    if not channel_budget_shares:
        return None

    return {
        "df_raw1": data["df_raw1"],
        "df_raw2": data["df_raw2"],
        "total_budget": inputs.get(
            "total_budget",
            st.session_state.get("result_total_budget", DEFAULT_TOTAL_BUDGET),
        ),
        "channel_budget_shares": channel_budget_shares,
        "channel_1_3_rate": inputs.get("channel_1_3_rate", {}),
        "channel_1_8_cps": inputs.get("channel_1_8_cps", {}),
        "channel_t0_cost": inputs.get("channel_t0_cost", {}),
        "non_initial_credit": inputs.get(
            "non_initial_credit",
            st.session_state.get("result_non_initial_credit", 0.0),
        ),
        "existing_m0_expense": 0.0,
        "rta_promotion_fee": inputs.get(
            "rta_promotion_fee",
            st.session_state.get("result_rta_promotion_fee", 0.0),
        ),
        "month_total_days": int(inputs.get(
            "month_total_days",
            st.session_state.get("result_month_total_days", DEFAULT_MONTH_DAYS),
        )),
        "days_elapsed": int(inputs.get(
            "days_elapsed",
            st.session_state.get("result_days_elapsed", DEFAULT_DAYS_ELAPSED),
        )),
        "m0_calc_period": int(inputs.get(
            "m0_calc_period",
            st.session_state.get("result_m0_calc_period", 3),
        )),
    }


def run_pipeline_with_params(params: dict):
    """Run execute_calculation_pipeline with a flat params dict.

    Returns (BudgetParameters, CalculationCoefficients, Table1Result, Table2Result).
    """
    scalars = {k: params[k] for k in (
        "df_raw1", "df_raw2", "non_initial_credit",
        "existing_m0_expense", "rta_promotion_fee",
        "month_total_days", "days_elapsed", "m0_calc_period",
    )}
    return execute_calculation_pipeline(
        total_budget=params["total_budget"],
        channel_budget_shares=params["channel_budget_shares"],
        channel_1_3_rate=params["channel_1_3_rate"],
        channel_1_8_cps=params["channel_1_8_cps"],
        channel_t0_cost=params["channel_t0_cost"],
        **scalars,
    )


def build_adoption_params(sim_params: dict, current: dict) -> dict:
    """Map scenario/simulation keys to the template system keys.

    Key mapping:
      channel_1_3_rate -> channel_1_3_approval_rate
      channel_t0_cost  -> channel_t0_completion_cost
    """
    return {
        "total_budget": sim_params["total_budget"],
        "channel_budget_shares": sim_params["channel_budget_shares"],
        "channel_1_3_approval_rate": sim_params["channel_1_3_rate"],
        "channel_t0_completion_cost": sim_params["channel_t0_cost"],
        "channel_1_8_cps": sim_params["channel_1_8_cps"],
        "non_initial_credit_transaction": current.get("non_initial_credit", 0.0),
        "rta_promotion_fee": current.get("rta_promotion_fee", 0.0),
        "month_total_days": current.get("month_total_days", DEFAULT_MONTH_DAYS),
        "days_elapsed": current.get("days_elapsed", DEFAULT_DAYS_ELAPSED),
        "existing_m0_calculation_months": current.get("m0_calc_period", 3),
    }
