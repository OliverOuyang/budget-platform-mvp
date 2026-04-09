"""V4.3c 护栏监控 Tab — 风险指标卡片 + 渠道护栏表。"""
from __future__ import annotations

import pandas as pd
import numpy as np
import streamlit as st
from app.styles import render_callout, render_risk_card


# ==================== 护栏阈值定义 ====================
GUARDRAIL_THRESHOLDS = {
    "FPD30": {"threshold": 0.05, "label": "<5%", "higher_is_worse": True},
    "首借终损率": {"threshold": 0.10, "label": "<10%", "higher_is_worse": True},
    "复借终损率": {"threshold": 0.08, "label": "<8%", "higher_is_worse": True},
}


def _classify_risk(value: float, threshold: float, higher_is_worse: bool) -> str:
    """返回 ok / warn / bad。"""
    if pd.isna(value):
        return "ok"
    if higher_is_worse:
        if value < threshold * 0.8:
            return "ok"
        elif value < threshold:
            return "warn"
        else:
            return "bad"
    else:
        if value > threshold * 1.2:
            return "ok"
        elif value > threshold:
            return "warn"
        else:
            return "bad"


def _get_channel_risk_level(row: dict) -> tuple[str, str]:
    """综合评估渠道风险等级。返回 (status, label)。"""
    statuses = []
    for metric, config in GUARDRAIL_THRESHOLDS.items():
        val = row.get(metric)
        if val is not None and not pd.isna(val):
            statuses.append(_classify_risk(val, config["threshold"], config["higher_is_worse"]))

    if not statuses:
        return "ok", "—"
    if "bad" in statuses:
        return "bad", "高"
    if "warn" in statuses:
        return "warn", "中"
    return "ok", "低"


def render_tab_guardrail():
    """渲染护栏监控 Tab。"""
    guardrail_data = st.session_state.get("guardrail_data")

    # 数据来源提示
    detected_metrics = st.session_state.get("detected_guardrail_metrics", [])
    missing_metrics = st.session_state.get("missing_guardrail_metrics", [])

    if missing_metrics:
        missing_str = "、".join(missing_metrics)
        render_callout(
            f"<b>数据来源：</b>从已上传 Excel 自动检测。"
            f'<span style="color:#F57C00"> {missing_str} 列缺失（标记为 —）</span>',
            kind="info",
        )
    else:
        render_callout(
            "<b>数据来源：</b>从已上传 Excel 自动检测，所有护栏指标均已就绪。",
            kind="info",
        )

    # 风险概览卡片
    if guardrail_data is not None and not guardrail_data.empty:
        _render_with_data(guardrail_data)
    else:
        _render_mock_data()


def _render_with_data(gdf: pd.DataFrame):
    """用真实护栏数据渲染。"""
    # 汇总行
    summary = {}
    for metric in GUARDRAIL_THRESHOLDS:
        col_candidates = [c for c in gdf.columns if metric in c]
        if col_candidates:
            vals = pd.to_numeric(gdf[col_candidates[0]], errors="coerce").dropna()
            if not vals.empty:
                summary[metric] = vals.mean()

    # 风险卡片
    cols = st.columns(len(GUARDRAIL_THRESHOLDS))
    for i, (metric, config) in enumerate(GUARDRAIL_THRESHOLDS.items()):
        val = summary.get(metric)
        if val is not None:
            status = _classify_risk(val, config["threshold"], config["higher_is_worse"])
            display_val = f"{val*100:.1f}%"
        else:
            status = "ok"
            display_val = "—"
        with cols[i]:
            st.markdown(
                render_risk_card(metric, display_val, config["label"], status),
                unsafe_allow_html=True,
            )

    st.markdown("")
    st.dataframe(gdf, use_container_width=True, hide_index=True)


def _render_mock_data():
    """无护栏数据时展示 mock 示例。"""
    from app.config import CHANNEL_NAMES

    # Mock 风险卡片
    mock_summary = [
        ("FPD30", "3.5%", "<5.0%", "ok"),
        ("首借终损率", "8.2%", "<10.0%", "ok"),
        ("复借终损率", "7.5%", "<8.0%", "warn"),
    ]

    cols = st.columns(3)
    for i, (title, value, threshold, status) in enumerate(mock_summary):
        with cols[i]:
            st.markdown(
                render_risk_card(title, value, threshold, status),
                unsafe_allow_html=True,
            )

    st.markdown("")

    # Mock 渠道表
    mock_rows = []
    channel_data = {
        "腾讯": {"FPD30": "3.2%", "首借终损": "7.8%", "复借终损": "6.5%", "LTV": "—", "风险": "低"},
        "抖音": {"FPD30": "4.1%", "首借终损": "9.0%", "复借终损": "7.8%", "LTV": "—", "风险": "中"},
        "精准营销": {"FPD30": "2.8%", "首借终损": "6.5%", "复借终损": "5.2%", "LTV": "—", "风险": "低"},
        "付费商店": {"FPD30": "4.5%", "首借终损": "9.5%", "复借终损": "8.2%", "LTV": "—", "风险": "高"},
        "免费渠道": {"FPD30": "2.5%", "首借终损": "5.8%", "复借终损": "4.5%", "LTV": "—", "风险": "低"},
    }
    for ch, vals in channel_data.items():
        mock_rows.append({"渠道": ch, **vals})

    st.dataframe(pd.DataFrame(mock_rows), use_container_width=True, hide_index=True)
    st.caption("⚠️ 上方为示例数据。上传包含护栏指标列的 Excel 后将显示真实数据。")
