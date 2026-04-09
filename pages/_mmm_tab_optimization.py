"""
_mmm_tab_optimization.py — Tab 3: Budget optimization with equal-marginal principle.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def render_tab_optimization(model, df, dv_col: str, ch_names: dict, data_mode: str, time_col: str, period_label: str):
    """Render Tab 3: Budget optimization.

    Parameters
    ----------
    model : MMMModel
        Fitted model object.
    df : pd.DataFrame
        Full dataset.
    dv_col : str
        Dependent variable column name.
    ch_names : dict
        Mapping from channel key to display name.
    data_mode : str
        One of "mock", "real", "weekly".
    time_col : str
        Time column name ("month" or "week_start").
    period_label : str
        Unit label e.g. "万元/月" or "万元/周".
    """
    st.subheader("预算再分配建议（等边际原则）")

    current_total_spend = float(
        sum(
            df[f"{ch}_spend"].mean()
            for ch in model._channel_keys
            if f"{ch}_spend" in df.columns
        )
    )

    # 快速场景对比卡片
    st.markdown("**快速场景预览**")
    _scenario_levels = [
        ("保守 (-15%)", 0.85, "#43A047"),
        ("基准 (当前)", 1.0, "#1976D2"),
        ("激进 (+15%)", 1.15, "#E53935"),
    ]
    scenario_cols = st.columns(3)
    _current_outcome = float(model.predict(df).mean())
    for col, (label, multiplier, color) in zip(scenario_cols, _scenario_levels):
        scenario_budget = current_total_spend * multiplier
        scaled_spends = {}
        for ch in model._channel_keys:
            col_name = f"{ch}_spend"
            if col_name in df.columns:
                scaled_spends[ch] = float(df[col_name].mean()) * multiplier
        df_scaled = df.copy()
        for ch, val in scaled_spends.items():
            col_name = f"{ch}_spend"
            if col_name in df_scaled.columns:
                df_scaled[col_name] = val
        predicted_outcome = float(model.predict(df_scaled).mean())
        outcome_change = (predicted_outcome - _current_outcome) / (_current_outcome + 1e-9) * 100
        roi_est = predicted_outcome / (scenario_budget + 1e-9)

        with col:
            with st.container(border=True):
                st.markdown(
                    f'<div style="border-left:4px solid {color};padding-left:8px;">'
                    f'<span style="font-weight:700;">{label}</span></div>',
                    unsafe_allow_html=True,
                )
                st.metric("总预算", f"{scenario_budget:,.0f} {period_label}")
                st.metric("预测产出", f"{predicted_outcome:,.0f}", f"{outcome_change:+.1f}%")
                st.metric("预估ROI", f"{roi_est:.2f}x")
                if st.button(f"以 {scenario_budget:,.0f} 优化", key=f"scenario_{multiplier}", use_container_width=True):
                    st.session_state["_opt_total_preset"] = scenario_budget
                    st.rerun()

    st.caption("场景预览基于等比例缩放所有渠道花费，实际优化结果可能因边际效应不同而有差异。")
    st.markdown("---")

    opt_input_col, opt_preset_col = st.columns([2, 3])
    with opt_input_col:
        opt_total = st.number_input(
            f"优化总预算（{period_label}）",
            min_value=100.0, max_value=10000.0,
            value=round(current_total_spend, 0),
            step=50.0,
            help=f"当前历史均值总预算约 {current_total_spend:.0f} {period_label}",
        )

    with opt_preset_col:
        st.markdown("**快速预设**")
        preset_cols = st.columns(4)
        presets = [2500, 3000, 3500, 4000]
        for i, preset in enumerate(presets):
            if preset_cols[i].button(f"{preset}万", key=f"preset_{preset}"):
                st.session_state["_opt_total_preset"] = float(preset)
                st.rerun()

    if "_opt_total_preset" in st.session_state:
        opt_total = st.session_state.pop("_opt_total_preset")

    opt_btn = st.button("🔍 运行预算优化（约 20 秒）", type="primary")

    if opt_btn:
        with st.spinner("正在运行等边际优化（Optuna 200次迭代）..."):
            optimal = model.budget_optimization(opt_total, df, n_points=50)
            st.session_state["mmm_optimal_budget"] = optimal
            st.session_state["mmm_opt_total"] = opt_total
            st.success("优化完成！以下为建议分配方案。")

    if "mmm_optimal_budget" in st.session_state:
        if st.session_state.get("mmm_opt_total") != opt_total:
            st.info("当前展示的是上一次预算优化结果；如已修改总预算，请重新点击「运行预算优化」。")

        optimal = st.session_state["mmm_optimal_budget"]
        current_spends = {
            ch: round(df[f"{ch}_spend"].mean(), 1)
            for ch in model._channel_keys
            if f"{ch}_spend" in df.columns
        }

        opt_df = pd.DataFrame({
            "渠道": [ch_names.get(ch, ch) for ch in optimal],
            "当前均值（万元）": [current_spends.get(ch, 0) for ch in optimal],
            "优化建议（万元）": [round(v, 1) for v in optimal.values()],
        })
        opt_df["变化（万元）"] = (opt_df["优化建议（万元）"] - opt_df["当前均值（万元）"]).round(1)
        opt_df["变化率（%）"] = (
            opt_df["变化（万元）"] / opt_df["当前均值（万元）"].replace(0, np.nan) * 100
        ).round(1)

        # 计算各渠道 ROI
        contributions_opt = model.channel_contribution(df)
        roi_map = {}
        for ch in model._channel_keys:
            spend_sum = float(df[f"{ch}_spend"].sum()) if f"{ch}_spend" in df.columns else 0
            contrib_sum = float(contributions_opt.get(ch, np.zeros(len(df))).sum())
            roi_map[ch] = round(contrib_sum / spend_sum, 3) if spend_sum > 0 else 0.0
        opt_df["ROI"] = [roi_map.get(ch, 0) for ch in optimal]

        # 保存 ROI 数据供 Page 2 Step 3.5 使用
        roi_by_name = {ch_names.get(ch, ch): v for ch, v in roi_map.items()}
        st.session_state["mmm_channel_roi"] = roi_by_name

        result_col, chart_col = st.columns(2)

        with result_col:
            st.dataframe(
                opt_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "变化率（%）": st.column_config.NumberColumn("变化率（%）", format="%.1f%%"),
                },
            )

            pre_total = sum(current_spends.values())
            post_total = sum(optimal.values())
            weighted_roi = sum(
                opt_df["优化建议（万元）"].iloc[i] * opt_df["ROI"].iloc[i]
                for i in range(len(opt_df))
            ) / (post_total + 1e-9)

            status_c1, status_c2, status_c3 = st.columns(3)
            status_c1.metric("优化前总量", f"{pre_total:.0f} 万元")
            status_c2.metric("优化后总量", f"{post_total:.0f} 万元")
            status_c3.metric("加权 ROI", f"{weighted_roi:.3f}")

        with chart_col:
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=opt_df["渠道"], y=opt_df["当前均值（万元）"],
                name="当前均值", marker_color="#90CAF9",
            ))
            fig_bar.add_trace(go.Bar(
                x=opt_df["渠道"], y=opt_df["优化建议（万元）"],
                name="优化建议", marker_color="#1976D2",
            ))
            fig_bar.update_layout(
                title=f"优化前 vs 优化后（{period_label}）",
                barmode="group", height=320,
                yaxis_title=f"花费（{period_label}）",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # 采纳按钮
        if st.button("✅ 采纳优化方案", type="primary"):
            recommended = {ch: v for ch, v in optimal.items()}
            st.session_state["mmm_recommended_spends"] = recommended
            st.session_state["mmm_budget_suggestion"] = recommended

            # 聚合为 V01 的 5 渠道口径供 Page 2 使用
            if data_mode in ("real", "weekly"):
                v01_mapping = {
                    "腾讯": ["tencent"],
                    "抖音": ["douyin"],
                    "精准营销": ["precision_marketing"],
                    "付费商店": ["app_store"],
                    "免费渠道": [],
                }
            else:
                v01_mapping = {
                    "腾讯": ["tencent_moments", "tencent_video", "tencent_wechat", "tencent_search"],
                    "抖音": ["douyin"],
                    "精准营销": ["precision_marketing"],
                    "付费商店": ["app_store"],
                    "免费渠道": [],
                }
            v01_spends = {}
            v01_roi = {}
            v01_sat = {}
            for v01_name, mmm_keys in v01_mapping.items():
                v01_spends[v01_name] = sum(optimal.get(k, 0) for k in mmm_keys)
                roi_vals = [roi_map.get(k, 0) for k in mmm_keys if roi_map.get(k, 0) > 0]
                v01_roi[v01_name] = sum(roi_vals) / len(roi_vals) if roi_vals else 0
                sat_vals = [st.session_state.get("mmm_channel_saturation", {}).get(ch_names.get(k, k), 0) for k in mmm_keys]
                sat_vals = [s for s in sat_vals if s > 0]
                v01_sat[v01_name] = sum(sat_vals) / len(sat_vals) if sat_vals else 0

            st.session_state["mmm_v01_recommended_spends"] = v01_spends
            st.session_state["mmm_v01_channel_roi"] = v01_roi
            st.session_state["mmm_v01_channel_saturation"] = v01_sat

            # V01-aggregated contribution percentages for model comparison tab
            total_mmm_contrib = sum(float(contributions_opt.get(ch, np.zeros(1)).sum()) for ch in model._channel_keys)
            v01_contrib_pcts = {}
            for v01_name, mmm_keys in v01_mapping.items():
                ch_contrib = sum(float(contributions_opt.get(k, np.zeros(1)).sum()) for k in mmm_keys)
                v01_contrib_pcts[v01_name] = ch_contrib / total_mmm_contrib if total_mmm_contrib > 0 else 0
            st.session_state["mmm_contributions"] = v01_contrib_pcts

            # Predicted monthly loan amount
            predicted = model.predict(df)
            if data_mode == "real":
                st.session_state["mmm_predicted_loan_amt"] = float(predicted.mean())
            elif data_mode == "weekly":
                st.session_state["mmm_predicted_loan_amt"] = float(predicted.mean()) * 4.33
            else:
                st.session_state["mmm_predicted_loan_amt"] = float(predicted.mean()) * 4.33

            st.success(
                "优化方案已采纳！已写入 `mmm_recommended_spends`。"
                "切换到预算推算结果页时，步骤3.5将自动加载MMM参考数据。"
            )

        st.info(
            "模型训练完成后，参数自动保存。"
            "切换到预算推算结果页时，步骤3.5将自动加载MMM参考数据。"
        )

    else:
        st.info("点击「运行预算优化」按钮获取 MMM 最优分配建议。")
