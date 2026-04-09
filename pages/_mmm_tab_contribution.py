"""
_mmm_tab_contribution.py — Tab 1: Channel contribution decomposition.
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


def render_tab_contribution(model, df, ch_names: dict, data_mode: str, time_col: str, period_label: str):
    """Render Tab 1: Channel contribution decomposition.

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
    time_col : str
        Time column name ("month" or "week_start").
    period_label : str
        Unit label e.g. "万元/月" or "万元/周".
    """
    st.subheader("渠道贡献分解")

    contributions = model.channel_contribution(df)
    ch_total_contrib = {ch: float(v.sum()) for ch, v in contributions.items()}
    ch_total_spend = {
        ch: float(df[f"{ch}_spend"].sum())
        for ch in model._channel_keys
        if f"{ch}_spend" in df.columns
    }
    total_contrib = sum(ch_total_contrib.values()) + 1e-9
    total_spend_val = sum(ch_total_spend.values()) + 1e-9

    # 瀑布图：基线 → 各渠道贡献 → 总预测
    y_pred_total = float(model.predict(df).mean())
    base_val = y_pred_total - sum(ch_total_contrib.values()) / len(df)
    wf_labels = ["基线(截距+外部)"]
    wf_values = [base_val]
    wf_measures = ["absolute"]
    wf_colors = ["#78909C"]
    channel_colors = px.colors.qualitative.Set2
    sorted_channels = sorted(ch_total_contrib.keys(), key=lambda k: ch_total_contrib[k], reverse=True)
    for i, ch in enumerate(sorted_channels):
        avg_contrib = ch_total_contrib[ch] / len(df)
        wf_labels.append(ch_names.get(ch, ch))
        wf_values.append(avg_contrib)
        wf_measures.append("relative")
        wf_colors.append(channel_colors[i % len(channel_colors)])
    wf_labels.append("总预测均值")
    wf_values.append(y_pred_total)
    wf_measures.append("total")
    wf_colors.append("#1976D2")

    fig_waterfall = go.Figure(go.Waterfall(
        x=wf_labels,
        y=wf_values,
        measure=wf_measures,
        textposition="outside",
        text=[f"{v:,.0f}" for v in wf_values],
        connector=dict(line=dict(color="rgba(0,0,0,0.2)", width=1)),
        increasing=dict(marker=dict(color="#43A047")),
        decreasing=dict(marker=dict(color="#E53935")),
        totals=dict(marker=dict(color="#1976D2")),
    ))
    fig_waterfall.update_layout(
        title=f"贡献分解瀑布图（周均/月均，{period_label}）",
        yaxis_title=f"借款金额（{period_label}）",
        height=360,
        margin=dict(t=40, b=60),
        showlegend=False,
    )
    st.plotly_chart(fig_waterfall, use_container_width=True)
    st.caption("瀑布图展示：基线（截距+宏观/季节因素） → 各渠道边际贡献 → 最终预测均值")

    # ── Business interpretation per channel ──────────────────────────────────
    st.markdown("**渠道效果业务解读**")
    for ch in sorted_channels:
        _ch_n = ch_names.get(ch, ch)
        _ch_s = ch_total_spend.get(ch, 0)
        _ch_c = ch_total_contrib[ch]
        _ch_pct = _ch_c / total_contrib * 100
        if _ch_s > 0:
            _ch_roi = _ch_c / _ch_s
            _interp = f"每增加 1 万元花费，预计带来约 **{_ch_roi:.2f} 万元** 交易额贡献（ROI={_ch_roi:.2f}）"
        else:
            _interp = "无花费数据（Organic渠道），贡献来自自然流量"
        st.markdown(f"- **{_ch_n}**：总贡献 {_ch_c:,.0f} 万元（{_ch_pct:.1f}%）。{_interp}")

    contrib_rows = []
    for ch in ch_total_contrib:
        is_organic = ch in model._organic_keys
        spend = ch_total_spend.get(ch, 0)
        contrib_val = ch_total_contrib[ch]
        contrib_rows.append({
            "渠道": ch_names.get(ch, ch),
            "类型": "Organic" if is_organic else "付费",
            "贡献量（万元）": round(contrib_val, 1),
            "贡献占比（%）": round(contrib_val / total_contrib * 100, 1),
            "花费（万元）": round(spend, 1) if not is_organic else 0,
            "花费占比（%）": round(spend / total_spend_val * 100, 1) if not is_organic else 0,
        })
    contrib_df = pd.DataFrame(contrib_rows)
    contrib_df["效率比"] = np.where(
        contrib_df["花费占比（%）"] > 0,
        (contrib_df["贡献占比（%）"] / contrib_df["花费占比（%）"]).round(3),
        np.nan,
    )
    contrib_df["ROI"] = np.where(
        contrib_df["花费（万元）"] > 0,
        (contrib_df["贡献量（万元）"] / contrib_df["花费（万元）"]).round(3),
        np.nan,
    )

    left_col, right_col = st.columns([3, 2])

    with left_col:
        st.dataframe(
            contrib_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "贡献占比（%）": st.column_config.ProgressColumn("贡献占比（%）", min_value=0, max_value=100),
            },
        )

    with right_col:
        st.markdown("""
        **解读逻辑**：比较「贡献占比」和「花费占比」的差距

        | 情况 | 含义 | 建议 |
        |---|---|---|
        | 贡献% **>** 花费% | 效率高，花少得多 | 考虑加大投入 |
        | 贡献% **<** 花费% | 效率低，花多得少 | 考虑减少投入 |
        | 贡献% = 0 | 未识别到显著贡献 | 检查数据质量 |

        效率比 > 1 表示该渠道投入产出高于平均水平。
        """)

    # 堆叠面积图
    st.subheader("渠道贡献趋势")
    fig_stack = go.Figure()
    colors_stack = px.colors.qualitative.Set2
    for i, (ch, contrib_arr) in enumerate(contributions.items()):
        fig_stack.add_trace(go.Scatter(
            x=df[time_col], y=contrib_arr,
            mode="lines", name=ch_names.get(ch, ch),
            stackgroup="one",
            line=dict(width=0.5),
            fillcolor=colors_stack[i % len(colors_stack)],
        ))
    fig_stack.update_layout(
        title="各渠道贡献（万元，堆叠面积）",
        xaxis_title="月份" if data_mode == "real" else "周次",
        yaxis_title="贡献（万元）",
        height=380, hovermode="x unified",
    )
    st.plotly_chart(fig_stack, use_container_width=True)
