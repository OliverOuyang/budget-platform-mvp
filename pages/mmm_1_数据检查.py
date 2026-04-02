"""
数据检查页 (Phase C)
展示：时间范围、缺失值、分布、统计特征、趋势图、异常点
"""
import sys
sys.path.insert(0, "/home/ubuntu/budget_combined")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from utils.data_loader import (
    load_mock_data, load_uploaded_data, validate_data,
    CHANNEL_NAMES, CHANNEL_KEYS, METRIC_LABELS
)

st.title("🔍 数据检查")
st.caption("上传业务数据或使用 Mock 数据，检查数据质量后再进行预算推演。")

# ─── 数据加载 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 数据来源")
    data_source = st.radio("选择数据来源", ["使用 Mock 数据", "上传 Excel/CSV"])
    if data_source == "上传 Excel/CSV":
        uploaded = st.file_uploader("上传文件", type=["csv", "xlsx"])
        if uploaded:
            try:
                df = load_uploaded_data(uploaded)
                st.success(f"✅ 上传成功：{len(df)} 行")
            except Exception as e:
                st.error(f"读取失败：{e}")
                df = load_mock_data()
        else:
            st.info("暂未上传，使用 Mock 数据")
            df = load_mock_data()
    else:
        df = load_mock_data()
        st.success("✅ 已加载 Mock 数据")

# 存入 session_state 供其他页面使用
st.session_state["df"] = df

# ─── 基础信息 ──────────────────────────────────────────────────────────────────
val = validate_data(df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("数据行数（周）", val["row_count"])
col2.metric("字段数", val["col_count"])
if val["time_range"]:
    col3.metric("起始周", str(val["time_range"][0])[:10])
    col4.metric("截止周", str(val["time_range"][1])[:10])

if not val["ok"]:
    for issue in val["issues"]:
        st.error(f"⚠️ {issue}")
else:
    st.success("✅ 数据结构校验通过")

st.divider()

# ─── Tab 布局 ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📋 缺失值", "📊 统计特征", "📈 趋势图", "🔔 异常点", "🌐 宏观环境"]
)

# ── Tab1：缺失值 ───────────────────────────────────────────────────────────────
with tab1:
    st.subheader("缺失值分析")
    null_df = df.isnull().sum().reset_index()
    null_df.columns = ["字段", "缺失数"]
    null_df["缺失率"] = (null_df["缺失数"] / len(df) * 100).round(2)
    null_df = null_df[null_df["缺失数"] > 0]
    if null_df.empty:
        st.success("✅ 所有字段均无缺失值")
    else:
        st.warning(f"⚠️ 共 {len(null_df)} 个字段存在缺失值")
        st.dataframe(null_df, use_container_width=True)

    # 热力图
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()[:20]
    fig_null = px.imshow(
        df[numeric_cols].isnull().astype(int).T,
        color_continuous_scale=["#e8f5e9", "#e53935"],
        labels=dict(color="缺失"),
        title="缺失值热力图（红色=缺失）",
        height=400,
    )
    fig_null.update_layout(xaxis_title="周次", yaxis_title="字段")
    st.plotly_chart(fig_null, use_container_width=True)

# ── Tab2：统计特征 ─────────────────────────────────────────────────────────────
with tab2:
    st.subheader("核心指标统计特征")
    key_cols = [
        "total_spend", "loan_amt", "first_login_cnt", "apply_submit_cnt",
        "credit_cnt", "loan_cnt", "quality_a13_rate", "cps_amt",
        "fpd30_plus_rate", "ltv_12m",
    ]
    key_cols = [c for c in key_cols if c in df.columns]
    stats = df[key_cols].describe().T
    stats.index = [METRIC_LABELS.get(c, c) for c in stats.index]
    st.dataframe(stats.round(4), use_container_width=True)

    st.subheader("渠道花费分布（箱线图）")
    spend_cols = [f"{ch}_spend" for ch in CHANNEL_KEYS if f"{ch}_spend" in df.columns]
    fig_box = go.Figure()
    for col in spend_cols:
        ch_key = col.replace("_spend", "")
        fig_box.add_trace(go.Box(
            y=df[col], name=CHANNEL_NAMES.get(ch_key, ch_key),
            boxmean=True,
        ))
    fig_box.update_layout(
        title="各渠道周度花费分布（万元）",
        yaxis_title="花费（万元）",
        height=420,
        showlegend=False,
    )
    st.plotly_chart(fig_box, use_container_width=True)

# ── Tab3：趋势图 ───────────────────────────────────────────────────────────────
with tab3:
    st.subheader("核心指标趋势")
    metric_choice = st.selectbox(
        "选择指标",
        options=list(METRIC_LABELS.keys()),
        format_func=lambda x: METRIC_LABELS[x],
        index=0,
    )

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=df["week_start"], y=df[metric_choice],
        mode="lines+markers", name=METRIC_LABELS[metric_choice],
        line=dict(color="#1976D2", width=2),
        marker=dict(size=4),
    ))
    # 添加 MA4 均线
    ma4 = df[metric_choice].rolling(4).mean()
    fig_trend.add_trace(go.Scatter(
        x=df["week_start"], y=ma4,
        mode="lines", name="4周均线",
        line=dict(color="#FF7043", width=2, dash="dot"),
    ))
    fig_trend.update_layout(
        title=f"{METRIC_LABELS[metric_choice]} 周度趋势",
        xaxis_title="周次",
        yaxis_title=METRIC_LABELS[metric_choice],
        height=420,
        hovermode="x unified",
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    st.subheader("渠道花费趋势（堆叠面积图）")
    spend_cols = [f"{ch}_spend" for ch in CHANNEL_KEYS if f"{ch}_spend" in df.columns]
    fig_area = go.Figure()
    colors = px.colors.qualitative.Set2
    for i, col in enumerate(spend_cols):
        ch_key = col.replace("_spend", "")
        fig_area.add_trace(go.Scatter(
            x=df["week_start"], y=df[col],
            mode="lines", name=CHANNEL_NAMES.get(ch_key, ch_key),
            stackgroup="one",
            line=dict(width=0.5),
            fillcolor=colors[i % len(colors)],
        ))
    fig_area.update_layout(
        title="各渠道周度花费趋势（万元，堆叠）",
        xaxis_title="周次",
        yaxis_title="花费（万元）",
        height=420,
        hovermode="x unified",
    )
    st.plotly_chart(fig_area, use_container_width=True)

# ── Tab4：异常点检测 ───────────────────────────────────────────────────────────
with tab4:
    st.subheader("异常点检测（IQR 方法）")
    detect_col = st.selectbox(
        "选择检测字段",
        options=[c for c in METRIC_LABELS if c in df.columns],
        format_func=lambda x: METRIC_LABELS[x],
        index=0,
    )

    series = df[detect_col]
    Q1, Q3 = series.quantile(0.25), series.quantile(0.75)
    IQR = Q3 - Q1
    lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
    outliers = df[(series < lower) | (series > upper)]

    col_a, col_b = st.columns(2)
    col_a.metric("IQR 下界", f"{lower:.2f}")
    col_b.metric("IQR 上界", f"{upper:.2f}")
    st.metric("异常点数量", len(outliers))

    fig_out = go.Figure()
    fig_out.add_trace(go.Scatter(
        x=df["week_start"], y=series,
        mode="lines+markers", name="原始值",
        line=dict(color="#1976D2"), marker=dict(size=4),
    ))
    if not outliers.empty:
        fig_out.add_trace(go.Scatter(
            x=outliers["week_start"], y=outliers[detect_col],
            mode="markers", name="异常点",
            marker=dict(color="#e53935", size=10, symbol="x"),
        ))
    fig_out.add_hline(y=upper, line_dash="dash", line_color="#FF7043",
                      annotation_text="上界")
    fig_out.add_hline(y=lower, line_dash="dash", line_color="#FF7043",
                      annotation_text="下界")
    fig_out.update_layout(
        title=f"{METRIC_LABELS[detect_col]} 异常点检测",
        height=420, hovermode="x unified",
    )
    st.plotly_chart(fig_out, use_container_width=True)

    if not outliers.empty:
        st.dataframe(
            outliers[["week_start", detect_col]].rename(
                columns={"week_start": "周次", detect_col: METRIC_LABELS[detect_col]}
            ),
            use_container_width=True,
        )

# ── Tab5：宏观环境 ─────────────────────────────────────────────────────────────
with tab5:
    st.subheader("宏观经济环境指标")
    macro_cols = {
        "cpi_yoy":              "CPI 同比（%）",
        "ppi_yoy":              "PPI 同比（%）",
        "social_retail_yoy":    "社零同比（%）",
        "unemployment_rate":    "城镇调查失业率（%）",
        "m2_yoy":               "M2 同比（%）",
        "social_financing_yoy": "社融同比（%）",
        "lpr_1y":               "LPR 1Y（%）",
        "lpr_5y":               "LPR 5Y（%）",
        "shibor_1w":            "SHIBOR 1W（%）",
    }
    available = {k: v for k, v in macro_cols.items() if k in df.columns}

    if available:
        selected_macro = st.multiselect(
            "选择展示指标",
            options=list(available.keys()),
            default=["cpi_yoy", "lpr_1y", "m2_yoy"],
            format_func=lambda x: available[x],
        )
        if selected_macro:
            fig_macro = go.Figure()
            colors_m = px.colors.qualitative.Plotly
            for i, col in enumerate(selected_macro):
                fig_macro.add_trace(go.Scatter(
                    x=df["week_start"], y=df[col],
                    mode="lines", name=available[col],
                    line=dict(color=colors_m[i % len(colors_m)], width=2),
                ))
            fig_macro.update_layout(
                title="宏观环境指标趋势",
                xaxis_title="周次",
                yaxis_title="值（%）",
                height=420,
                hovermode="x unified",
            )
            st.plotly_chart(fig_macro, use_container_width=True)

        # 最新值展示
        latest = df.iloc[-1]
        st.subheader("最新一周宏观指标")
        macro_display = {v: latest.get(k, "N/A") for k, v in available.items()}
        cols = st.columns(3)
        for i, (label, val_m) in enumerate(macro_display.items()):
            cols[i % 3].metric(label, f"{val_m:.2f}" if isinstance(val_m, float) else val_m)
    else:
        st.info("当前数据中未包含宏观指标字段")
