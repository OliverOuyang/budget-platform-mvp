"""
_mmm_tab_response.py — Tab 2: Hill saturation response curves per channel.
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
import plotly.express as px

from engine.mmm_engine import hill_saturation


def render_tab_response(model, df, ch_names: dict, data_mode: str, period_label: str):
    """Render Tab 2: Response curves (Hill saturation).

    Parameters
    ----------
    model : MMMModel
        Fitted model object.
    df : pd.DataFrame
        Full dataset.
    ch_names : dict
        Mapping from channel key to display name.
    data_mode : str
        One of "mock", "real", "weekly".
    period_label : str
        Unit label e.g. "万元/月" or "万元/周".
    """
    st.subheader("渠道边际响应曲线（Hill 饱和效应）")

    channels_list = list(model.channel_params.keys())
    n_channels = len(channels_list)
    colors_resp = px.colors.qualitative.Plotly

    saturation_info = []
    for row_start in range(0, n_channels, 3):
        row_channels = channels_list[row_start:row_start + 3]
        card_cols = st.columns(len(row_channels))

        for col_idx, ch in enumerate(row_channels):
            cp = model.channel_params[ch]
            ch_name = ch_names.get(ch, ch)
            hist_mean = float(df[f"{ch}_spend"].mean()) if f"{ch}_spend" in df.columns else 100.0
            hist_max = float(df[f"{ch}_spend"].max()) if f"{ch}_spend" in df.columns else hist_mean * 2

            spend_range = np.linspace(0, hist_mean * 2, 200)

            response_vals = model.marginal_response(ch, spend_range, df_last=df)

            norm_current = hist_mean / (hist_max + 1e-9)
            sat_pct = float(hill_saturation(np.array([norm_current]), cp.alpha, cp.gamma)[0]) * 100

            delta_spend = hist_mean * 0.01
            r_current = float(model.marginal_response(ch, np.array([hist_mean]), df_last=df)[0])
            r_delta = float(model.marginal_response(ch, np.array([hist_mean + delta_spend]), df_last=df)[0])
            marginal_roi = (r_delta - r_current) / (delta_spend + 1e-9)

            saturation_info.append({
                "渠道": ch_name,
                "当前饱和度": sat_pct,
                "边际ROI": round(marginal_roi, 4),
            })

            with card_cols[col_idx]:
                with st.container(border=True):
                    st.markdown(f"**{ch_name}**")

                    fig_hill = go.Figure()
                    fig_hill.add_trace(go.Scatter(
                        x=spend_range, y=response_vals,
                        mode="lines",
                        line=dict(color=colors_resp[(row_start + col_idx) % len(colors_resp)], width=2),
                        name="响应曲线",
                    ))
                    fig_hill.add_trace(go.Scatter(
                        x=[hist_mean], y=[r_current],
                        mode="markers",
                        marker=dict(color="red", size=10, symbol="circle"),
                        name="当前花费",
                    ))
                    fig_hill.update_layout(
                        height=200,
                        margin=dict(l=10, r=10, t=20, b=30),
                        xaxis_title=f"花费（{period_label}）",
                        yaxis_title="贡献",
                        showlegend=False,
                    )
                    st.plotly_chart(fig_hill, use_container_width=True)
                    st.caption(f"饱和度：{sat_pct:.1f}%  |  边际ROI：{marginal_roi:.4f}")

    # 饱和度排名汇总
    sat_df = pd.DataFrame(saturation_info).sort_values("当前饱和度", ascending=False)
    top_sat = sat_df.iloc[0]["渠道"] if len(sat_df) > 0 else ""
    bottom_sat = sat_df.iloc[-1]["渠道"] if len(sat_df) > 0 else ""

    st.info(
        f"饱和度最高渠道：**{top_sat}**（已较饱和，建议控制加投）  |  "
        f"饱和度最低渠道：**{bottom_sat}**（空间较大，可优先加投）"
    )
    st.dataframe(sat_df, use_container_width=True, hide_index=True)

    # 保存饱和度数据到 session_state 供 Page 2 Step 3.5 使用
    sat_dict = {}
    for _, row in sat_df.iterrows():
        sat_dict[row["渠道"]] = row["当前饱和度"]
    st.session_state["mmm_channel_saturation"] = sat_dict
