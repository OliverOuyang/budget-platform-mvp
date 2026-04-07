from __future__ import annotations

import pandas as pd
import numpy as np
import streamlit as st
import time
from typing import Any, Dict, Optional, Tuple
from app.config import (
    CHANNEL_NAMES,
    DEFAULT_1_3_RATES,
    DEFAULT_1_8_CPS,
)
from core.calculation_pipeline import execute_calculation_pipeline


def ensure_flow_state() -> None:
    """Initialize shared workflow state used by V01 and MMM experiences."""
    st.session_state.setdefault(
        "v01_flow",
        {
            "current_step": 1,
            "data": {},
            "diagnostics": {},
            "inputs": {},
            "targets": {},
            "results": {},
            "previous_results": {},
            "scenarios": {},
            "next_step": "上传数据文件",
        },
    )
    st.session_state.setdefault(
        "mmm_flow",
        {
            "current_step": 1,
            "data": {},
            "inputs": {},
            "results": {},
            "next_step": "完成数据检查",
        },
    )


def get_v01_flow() -> Dict[str, Any]:
    ensure_flow_state()
    return st.session_state["v01_flow"]


def update_v01_flow(**patch: Any) -> None:
    flow = get_v01_flow()
    flow.update(patch)
    st.session_state["v01_flow"] = flow


def reset_v01_flow_for_new_upload() -> None:
    """Clear downstream V01 state when the source data changes."""
    stale_keys = [
        "parameters",
        "coefficients",
        "table1_result",
        "table2_result",
        "previous_parameters",
        "previous_table1_result",
        "previous_table2_result",
        "current_template_params",
        "pending_result_template_params",
        "pending_result_template_name",
        "result_selected_template",
        "result_delete_template_name",
        "result_template_name",
        "result_template_desc",
        "result_template_overwrite_confirm",
        "result_total_budget",
        "result_m0_calc_period",
        "result_non_initial_credit",
        "result_rta_promotion_fee",
        "result_month_total_days",
        "result_days_elapsed",
        "result_channel_editor",
    ]
    for key in stale_keys:
        st.session_state.pop(key, None)

    update_v01_flow(
        current_step=1,
        data={},
        diagnostics={},
        inputs={},
        targets={},
        results={},
        previous_results={},
        scenarios={},
        next_step="重新上传并完成数据检查",
    )


def build_v01_result_snapshot(table1: Any, table2: Any, params: Any) -> Dict[str, Any]:
    """Build a normalized summary object for V01 decision pages."""
    return {
        "summary": {
            "total_expense": getattr(table1, "total_expense", None),
            "total_transaction": getattr(table2, "total_transaction", None),
            "total_cps": getattr(table2, "total_cps", None),
            "approval_rate_1_3": getattr(table2, "approval_rate_1_3_excl_age", None),
            "total_t0_transaction": getattr(table1, "total_t0_transaction", None),
        },
        "inputs": {
            "total_budget": getattr(params, "total_budget", None),
            "month_total_days": getattr(params, "month_total_days", None),
            "days_elapsed": getattr(params, "days_elapsed", None),
            "existing_m0_calculation_months": getattr(params, "existing_m0_calculation_months", None),
        },
    }


def classify_target_progress(actual: float, target: float, *, higher_is_better: bool) -> Dict[str, Any]:
    """Classify progress against a target with a small tolerance band."""
    if target <= 0:
        return {
            "status": "info",
            "label": "未设置",
            "delta": None,
            "summary": "当前未配置该项目标。",
        }

    delta = actual - target
    ratio = actual / target if target else 0.0

    if higher_is_better:
        if ratio >= 1.0:
            status, label = "success", "达成"
        elif ratio >= 0.95:
            status, label = "warning", "接近达成"
        else:
            status, label = "danger", "未达成"
    else:
        if ratio <= 1.0:
            status, label = "success", "达成"
        elif ratio <= 1.05:
            status, label = "warning", "接近达成"
        else:
            status, label = "danger", "未达成"

    return {
        "status": status,
        "label": label,
        "delta": delta,
        "summary": f"当前值 {actual:.4f}，目标 {target:.4f}",
    }


def build_v01_decision_summary(
    flow: Dict[str, Any],
    table1: Optional[Any] = None,
    table2: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build consistent decision framing for both input and result stages."""
    targets = flow.get("targets", {})
    inputs = flow.get("inputs", {})

    budget_target = float(targets.get("budget_target", 0) or 0)
    cps_target = float(targets.get("cps_target", 0) or 0)
    approval_target = float(targets.get("approval_target", 0) or 0)

    budget_actual = float(
        getattr(table1, "total_expense", None)
        or flow.get("results", {}).get("summary", {}).get("total_expense")
        or inputs.get("total_budget", 0)
        or 0
    )
    cps_actual = float(
        getattr(table2, "total_cps", None)
        or flow.get("results", {}).get("summary", {}).get("total_cps")
        or 0
    )
    approval_actual = float(
        getattr(table2, "approval_rate_1_3_excl_age", None)
        or flow.get("results", {}).get("summary", {}).get("approval_rate_1_3")
        or 0
    )

    checks = {
        "budget": classify_target_progress(budget_actual, budget_target, higher_is_better=True),
        "cps": classify_target_progress(cps_actual, cps_target, higher_is_better=False),
        "approval": classify_target_progress(approval_actual, approval_target, higher_is_better=True),
    }
    statuses = [check["status"] for check in checks.values()]
    if all(status == "success" or status == "info" for status in statuses):
        headline = "当前方案已满足主要目标"
        status = "success"
    elif "danger" in statuses:
        headline = "当前方案仍有关键目标未达成"
        status = "warning"
    else:
        headline = "当前方案接近目标，建议继续微调"
        status = "info"

    recommended_actions = []
    if checks["budget"]["status"] == "danger":
        recommended_actions.append("优先检查总预算规模和渠道分配，确认是否需要提升投放上限。")
    if checks["cps"]["status"] == "danger":
        recommended_actions.append("优先回看高 CPS 渠道，降低成本假设过高或转移预算。")
    if checks["approval"]["status"] == "danger":
        recommended_actions.append("优先检查 1-3 过件率假设是否过于激进，必要时回归历史基线。")
    if not recommended_actions:
        recommended_actions.append("可以进入方案对比和保存阶段，判断是否拍板当前方案。")

    return {
        "headline": headline,
        "status": status,
        "checks": checks,
        "recommended_actions": recommended_actions,
    }

def format_month(value) -> str:
    """统一月份展示。"""
    if pd.isna(value):
        return "-"
    try:
        return pd.to_datetime(value).strftime("%Y-%m")
    except Exception:
        return str(value)

def normalize_channel_history(df: pd.DataFrame) -> pd.DataFrame:
    """将渠道历史数据整理成可分析的数值表。"""
    normalized = df.copy().replace("\\N", np.nan)
    numeric_cols = [
        "花费",
        "1-3t0过件率",
        "1-8t0cps",
        "t0申完成本",
        "1-8t0首借24h借款金额",
        "1_8m0首登当月首借24h借款金额",
    ]
    for col in numeric_cols:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
    if "月份" in normalized.columns:
        normalized["月份标签"] = normalized["月份"].apply(format_month)
    if "渠道类别" in normalized.columns:
        normalized["渠道名称"] = normalized["渠道类别"]
    return normalized

def build_channel_parameter_rows(
    last_month_data: Dict,
    template_params: Dict | None = None,
) -> pd.DataFrame:
    """构建渠道参数编辑表。"""
    rows = []
    template_params = template_params or {}
    total_expense = sum((item.get("花费") or 0) for item in last_month_data.values())

    for ch_name in CHANNEL_NAMES:
        defaults = last_month_data.get(ch_name, {})
        historical_share = ((defaults.get("花费") or 0) / total_expense * 100) if total_expense else 0.0
        target_share = (
            template_params.get("channel_budget_shares", {}).get(
                ch_name,
                historical_share / 100,
            )
            * 100
        )
        approval_rate = (
            template_params.get("channel_1_3_approval_rate", {}).get(
                ch_name,
                defaults.get("1-3t0过件率", DEFAULT_1_3_RATES.get(ch_name, 0.0)),
            )
        )
        cps_ratio = (
            template_params.get("channel_1_8_cps", {}).get(
                ch_name,
                defaults.get("1-8t0cps", DEFAULT_1_8_CPS.get(ch_name, 0.0)),
            )
        )
        completion_cost = (
            template_params.get("channel_t0_completion_cost", {}).get(
                ch_name,
                defaults.get("t0申完成本", 0.0),
            )
        )

        rows.append(
            {
                "渠道": ch_name,
                "目标花费结构(%)": target_share,
                "目标1-3过件率(%)": approval_rate * 100,
                "目标CPS(%)": cps_ratio * 100,
                "历史花费结构(%)": historical_share,
                "历史1-3 T0过件率(%)": defaults.get("1-3t0过件率", np.nan) * 100
                if defaults.get("1-3t0过件率") is not None
                else np.nan,
                "历史1-8 T0CPS(%)": defaults.get("1-8t0cps", np.nan) * 100
                if defaults.get("1-8t0cps") is not None
                else np.nan,
                "历史T0申完成本(元)": defaults.get("t0申完成本", np.nan),
            }
        )

    return pd.DataFrame(rows)

def parse_channel_parameter_rows(df: pd.DataFrame) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float], Dict[str, float]]:
    """从编辑表中回收渠道参数。"""
    channel_1_3_rate: Dict[str, float] = {}
    channel_1_8_cps: Dict[str, float] = {}
    channel_t0_cost: Dict[str, float] = {}
    channel_budget_shares: Dict[str, float] = {}

    def _safe(val, default=0.0):
        if val is None:
            return default
        try:
            f = float(val)
            return default if pd.isna(f) else f
        except (ValueError, TypeError):
            return default

    for row in df.to_dict("records"):
        channel_name = row["渠道"]
        channel_budget_shares[channel_name] = max(_safe(row["目标花费结构(%)"]), 0.0) / 100
        channel_1_3_rate[channel_name] = max(_safe(row["目标1-3过件率(%)"]), 0.0) / 100
        channel_1_8_cps[channel_name] = max(_safe(row["目标CPS(%)"]), 0.0) / 100
        channel_t0_cost[channel_name] = max(_safe(row["历史T0申完成本(元)"]), 0.0)

    total_share = sum(channel_budget_shares.values())
    if total_share > 0:
        channel_budget_shares = {k: v / total_share for k, v in channel_budget_shares.items()}

    return channel_budget_shares, channel_1_3_rate, channel_1_8_cps, channel_t0_cost

def run_calculation(
    df_raw1: pd.DataFrame,
    df_raw2: pd.DataFrame,
    total_budget: float,
    channel_budget_shares: Dict[str, float],
    channel_1_3_rate: Dict[str, float],
    channel_1_8_cps: Dict[str, float],
    channel_t0_cost: Dict[str, float],
    non_initial_credit: float,
    existing_m0_expense: float,
    rta_promotion_fee: float,
    month_total_days: int,
    days_elapsed: int,
    m0_calc_period: int,
    show_success: bool = True,
):
    """执行完整计算流水线（Streamlit UI 包装层）。"""
    try:
        ensure_flow_state()
        start_time = time.time()
        with st.spinner("⏳ 正在计算..."):
            # 保存上一次的结果用于对比
            if st.session_state.get("table1_result") is not None:
                st.session_state.previous_parameters = st.session_state.get("parameters")
                st.session_state.previous_table1_result = st.session_state.get("table1_result")
                st.session_state.previous_table2_result = st.session_state.get("table2_result")

            params, coefficients, table1, table2 = execute_calculation_pipeline(
                df_raw1=df_raw1,
                df_raw2=df_raw2,
                total_budget=total_budget,
                channel_budget_shares=channel_budget_shares,
                channel_1_3_rate=channel_1_3_rate,
                channel_1_8_cps=channel_1_8_cps,
                channel_t0_cost=channel_t0_cost,
                non_initial_credit=non_initial_credit,
                existing_m0_expense=existing_m0_expense,
                rta_promotion_fee=rta_promotion_fee,
                month_total_days=month_total_days,
                days_elapsed=days_elapsed,
                m0_calc_period=m0_calc_period,
            )

            st.session_state.parameters = params
            st.session_state.coefficients = coefficients
            st.session_state.table1_result = table1
            st.session_state.table2_result = table2
            flow = get_v01_flow()
            flow["previous_results"] = flow.get("results", {}).copy()
            flow["results"] = build_v01_result_snapshot(table1, table2, params)
            flow["inputs"] = {
                "total_budget": total_budget,
                "channel_budget_shares": channel_budget_shares,
                "channel_1_3_rate": channel_1_3_rate,
                "channel_1_8_cps": channel_1_8_cps,
                "channel_t0_cost": channel_t0_cost,
                "non_initial_credit": non_initial_credit,
                "existing_m0_expense": existing_m0_expense,
                "rta_promotion_fee": rta_promotion_fee,
                "month_total_days": month_total_days,
                "days_elapsed": days_elapsed,
                "m0_calc_period": m0_calc_period,
            }
            flow["current_step"] = 2
            flow["next_step"] = "查看结果概览、对比方案并决定是否保存模板"
            st.session_state["v01_flow"] = flow

        calc_time = time.time() - start_time
        if show_success:
            st.success("✅ 计算完成。计算时间: {:.2f}秒".format(calc_time))

    except Exception as e:
        st.error(f"❌ 计算失败: {e}")

def render_common_sidebar():
    """渲染通用的侧边栏信息"""
    with st.sidebar:
        st.title("💼 预算推算平台")
        st.markdown("---")
        
        # 参数说明
        with st.expander("ℹ️ 参数说明", expanded=False):
            st.markdown("""
            **总花费**: 月度营销预算总额（万元）
            **1-3 T0过件率**: 1-3年龄段通过率
            **1-8 T0CPS**: 花费 / 借款额 的比率，界面统一按百分比展示
            **T0申完成本**: 每笔申请完成所需花费（元）
            """)
        
        # 使用说明
        with st.expander("📖 使用说明", expanded=False):
            st.markdown("""
            ### 业务目标
            本平台用于信贷获客预算推算，支持：
            - 基于历史数据预测未来交易额
            - 多渠道预算分配优化
            - 关键指标联动分析
            ### 数据流向
            1. **数据上传与检查** → 上传Excel文件并查看质量检查、统计特征、趋势分布
            2. **预算推算结果** → 在结果页顶部配置参数、加载模板并执行计算
            3. **方案判断** → 查看结果概览、渠道拆解与方案对比，决定是否保存模板
            """)
        
        st.markdown("---")
        st.caption("© 2026 预算管理平台")
