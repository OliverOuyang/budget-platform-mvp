"""
_mmm_tab_fit.py — Tab 0: Model fit quality diagnostics.
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


def render_tab_fit(model, df, dv_col: str, ch_names: dict, data_mode: str, time_col: str, period_label: str):
    """Render Tab 0: Fit quality.

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
    st.subheader("模型拟合效果")

    # 计算测试集 R²（后20%）
    n_total = len(df)
    n_train = int(n_total * 0.8)
    df_test = df.iloc[n_train:]
    y_test_actual = df_test[dv_col].values if dv_col in df_test.columns else np.array([])
    test_r2 = 0.0
    if len(y_test_actual) > 1:
        y_test_pred = model.predict(df_test)
        ss_res = np.sum((y_test_actual - y_test_pred) ** 2)
        ss_tot = np.sum((y_test_actual - y_test_actual.mean()) ** 2)
        test_r2 = max(0.0, 1 - ss_res / ss_tot)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(
        "R²（拟合优度）", f"{model.r_squared:.4f}",
        delta="良好" if model.r_squared > 0.7 else "偏低",
        delta_color="normal" if model.r_squared > 0.7 else "inverse",
        help="越接近 1 越好，>0.7 为可接受",
    )
    m2.metric(
        "NRMSE（归一化误差）", f"{model.nrmse:.4f}",
        delta="良好" if model.nrmse < 0.5 else "偏高",
        delta_color="normal" if model.nrmse < 0.5 else "inverse",
        help="越小越好，<0.3 良好，<0.5 可接受",
    )
    _rssd = getattr(model, 'decomp_rssd', 0)
    m3.metric(
        "Decomp RSSD", f"{_rssd:.4f}",
        delta="均衡" if _rssd < 0.35 else "偏高",
        delta_color="normal" if _rssd < 0.35 else "inverse",
        help="渠道贡献分布与花费分布差异，越小越均衡",
    )
    m4.metric(
        "Test R²（测试集）", f"{test_r2:.4f}",
        delta="良好" if test_r2 > 0.6 else "偏低",
        delta_color="normal" if test_r2 > 0.6 else "inverse",
        help="后20%数据上的拟合优度，衡量泛化能力",
    )

    # 实际 vs 预测
    y_pred = model.predict(df)
    y_actual = df[dv_col].values if dv_col in df.columns else np.zeros(len(df))

    fig_fit = go.Figure()
    fig_fit.add_trace(go.Scatter(
        x=df[time_col], y=y_actual,
        mode="lines", name="实际值",
        line=dict(color="#1976D2", width=2),
    ))
    fig_fit.add_trace(go.Scatter(
        x=df[time_col], y=y_pred,
        mode="lines", name="预测值",
        line=dict(color="#FF7043", width=2, dash="dot"),
    ))
    if n_train < n_total:
        fig_fit.add_vrect(
            x0=df[time_col].iloc[n_train],
            x1=df[time_col].iloc[-1],
            fillcolor="rgba(200,200,200,0.15)",
            line_width=0,
            annotation_text="测试集",
            annotation_position="top left",
        )
    fig_fit.update_layout(
        title="实际值 vs 预测值（借款金额，万元）",
        xaxis_title="月份" if data_mode == "real" else "周次",
        yaxis_title="借款金额（万元）",
        height=380, hovermode="x unified",
    )
    st.plotly_chart(fig_fit, use_container_width=True)

    # 残差诊断
    st.subheader("残差诊断")
    residuals = y_actual - y_pred
    res_colors = ["#43A047" if r >= 0 else "#E53935" for r in residuals]

    res_col1, res_col2 = st.columns(2)
    with res_col1:
        fig_res = go.Figure()
        fig_res.add_trace(go.Bar(
            x=df[time_col], y=residuals,
            marker_color=res_colors,
            name="残差",
            hovertemplate="残差: %{y:,.0f}<extra></extra>",
        ))
        if n_train < n_total:
            fig_res.add_vrect(
                x0=df[time_col].iloc[n_train],
                x1=df[time_col].iloc[-1],
                fillcolor="rgba(200,200,200,0.15)",
                line_width=0,
                annotation_text="测试集",
                annotation_position="top left",
            )
        fig_res.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig_res.update_layout(
            title="残差时序（绿=实际>预测, 红=实际<预测）",
            xaxis_title="月份" if data_mode == "real" else "周次",
            yaxis_title="残差（万元）",
            height=280, margin=dict(t=40, b=30),
            showlegend=False,
        )
        st.plotly_chart(fig_res, use_container_width=True)

    with res_col2:
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=residuals, nbinsx=15,
            marker_color="#1976D2", opacity=0.7,
            name="残差分布",
        ))
        res_mean = float(np.mean(residuals))
        res_std = float(np.std(residuals)) + 1e-9
        x_norm = np.linspace(res_mean - 3 * res_std, res_mean + 3 * res_std, 100)
        y_norm = (1 / (res_std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_norm - res_mean) / res_std) ** 2)
        bin_width = (residuals.max() - residuals.min()) / 15 if len(residuals) > 1 else 1
        y_norm_scaled = y_norm * len(residuals) * bin_width
        fig_hist.add_trace(go.Scatter(
            x=x_norm, y=y_norm_scaled,
            mode="lines", name="正态参考",
            line=dict(color="#FF7043", width=2, dash="dash"),
        ))
        fig_hist.update_layout(
            title="残差分布（vs 正态曲线）",
            xaxis_title="残差（万元）",
            yaxis_title="频次",
            height=280, margin=dict(t=40, b=30),
            showlegend=True,
        )
        st.plotly_chart(fig_hist, use_container_width=True)

    # 残差统计
    res_stat_cols = st.columns(4)
    res_stat_cols[0].metric("残差均值", f"{res_mean:,.0f}")
    res_stat_cols[1].metric("残差标准差", f"{res_std:,.0f}")
    res_stat_cols[2].metric("最大绝对误差", f"{float(np.max(np.abs(residuals))):,.0f}")
    res_stat_cols[3].metric("MAPE", f"{float(np.mean(np.abs(residuals) / (np.abs(y_actual) + 1e-9))) * 100:.1f}%")

    if abs(res_mean) > res_std * 0.5:
        st.warning(f"残差均值 {res_mean:,.0f} 偏离零较远，模型存在系统性{'高估' if res_mean < 0 else '低估'}倾向。")

    # ── DW statistic interpretation ──────────────────────────────────────────
    _dw = getattr(model, 'dw_stat', 0) or 0
    _mape_val = float(np.mean(np.abs(residuals) / (np.abs(y_actual) + 1e-9))) * 100
    _avg_actual = float(np.mean(np.abs(y_actual)))
    _mape_abs = _mape_val / 100 * _avg_actual

    _diag_c1, _diag_c2 = st.columns(2)
    with _diag_c1:
        if _dw > 0:
            st.metric("Durbin-Watson 统计量", f"{_dw:.3f}")
            if _dw < 1.5:
                st.warning(f"DW={_dw:.3f} < 1.5，存在正自相关。模型可能遗漏了时序结构，建议增加滞后特征。")
            elif _dw > 2.5:
                st.warning(f"DW={_dw:.3f} > 2.5，存在负自相关。模型可能过度拟合了短期波动。")
            else:
                st.success(f"DW={_dw:.3f}，在 [1.5, 2.5] 范围内，残差无显著自相关。")
    with _diag_c2:
        st.metric("MAPE", f"{_mape_val:.1f}%")
        st.markdown(
            f"平均每{'月' if data_mode == 'real' else '周'}预测偏差约 **{_mape_abs:,.0f} 万元**"
            f"（实际均值 {_avg_actual:,.0f} 万元）。"
            f"{'误差可控，可用于预算分配参考。' if _mape_val < 15 else '误差偏大，建议结合业务判断使用。'}"
        )

    # ── ACF plot ──────────────────────────────────────────────────────────────
    st.subheader("自相关分析 (ACF)")
    _max_lag = min(20, len(residuals) // 3)
    if _max_lag > 2:
        _acf_vals = []
        _r_mean = float(np.mean(residuals))
        _r_var = float(np.sum((residuals - _r_mean) ** 2))
        for lag in range(_max_lag + 1):
            if _r_var > 0:
                _acf_v = float(np.sum((residuals[:len(residuals) - lag] - _r_mean) * (residuals[lag:] - _r_mean)) / _r_var)
            else:
                _acf_v = 0.0
            _acf_vals.append(_acf_v)

        _conf_bound = 1.96 / np.sqrt(len(residuals))
        fig_acf = go.Figure()
        for i, v in enumerate(_acf_vals):
            fig_acf.add_trace(go.Scatter(
                x=[i, i], y=[0, v], mode="lines",
                line=dict(color="#1976D2", width=2), showlegend=False,
            ))
        fig_acf.add_trace(go.Scatter(
            x=list(range(len(_acf_vals))), y=_acf_vals,
            mode="markers", marker=dict(color="#1976D2", size=6), name="ACF",
        ))
        fig_acf.add_hline(y=_conf_bound, line_dash="dash", line_color="red", annotation_text="95%置信上界")
        fig_acf.add_hline(y=-_conf_bound, line_dash="dash", line_color="red", annotation_text="95%置信下界")
        fig_acf.add_hline(y=0, line_color="gray", line_width=0.5)
        fig_acf.update_layout(
            title="残差自相关函数 (ACF)",
            xaxis_title="滞后期数", yaxis_title="自相关系数",
            height=280, margin=dict(t=35, b=30),
        )
        st.plotly_chart(fig_acf, use_container_width=True)

        _sig_lags = [i for i, v in enumerate(_acf_vals[1:], 1) if abs(v) > _conf_bound]
        if _sig_lags:
            st.caption(f"滞后 {_sig_lags} 处自相关显著超出95%置信区间，提示残差中可能存在未被捕捉的周期性模式。")
        else:
            st.caption("所有滞后期的自相关系数均在95%置信区间内，残差接近白噪声，模型拟合较充分。")

    # STL 分解可视化
    if "stl_trend" in df.columns and "stl_seasonal" in df.columns:
        st.subheader("STL 时序分解")
        stl_col1, stl_col2 = st.columns(2)
        with stl_col1:
            fig_stl_trend = go.Figure()
            fig_stl_trend.add_trace(go.Scatter(
                x=df[time_col], y=df[dv_col],
                mode="lines", name="实际值", line=dict(color="#90A4AE", width=1),
            ))
            fig_stl_trend.add_trace(go.Scatter(
                x=df[time_col], y=df["stl_trend"],
                mode="lines", name="STL 趋势", line=dict(color="#1565C0", width=2),
            ))
            fig_stl_trend.update_layout(
                title="趋势分量（STL LOESS）",
                height=250, margin=dict(t=35, b=30),
                legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(fig_stl_trend, use_container_width=True)
        with stl_col2:
            fig_stl_season = go.Figure()
            fig_stl_season.add_trace(go.Scatter(
                x=df[time_col], y=df["stl_seasonal"],
                mode="lines", name="季节分量", line=dict(color="#7B1FA2", width=2),
            ))
            fig_stl_season.update_layout(
                title="季节分量（年度周期）",
                height=250, margin=dict(t=35, b=30),
                yaxis_title="万元",
            )
            st.plotly_chart(fig_stl_season, use_container_width=True)
        st.caption("STL 分解将因变量拆分为趋势（长期走向）、季节（周期波动）和残差（随机噪声）三个分量，比线性趋势+Fourier更能捕捉非线性模式。")

    # 渠道参数表
    st.subheader("渠道参数详情")
    contributions_for_tab0 = model.channel_contribution(df)
    ch_total_contrib_t0 = {ch: float(v.sum()) for ch, v in contributions_for_tab0.items()}
    total_contrib_t0 = sum(ch_total_contrib_t0.values()) + 1e-9

    ch_total_spend_t0 = {
        ch: float(df[f"{ch}_spend"].sum())
        for ch in model._channel_keys
        if f"{ch}_spend" in df.columns
    }

    param_rows = []
    for ch, cp in model.channel_params.items():
        spend_sum = ch_total_spend_t0.get(ch, 0)
        contrib = ch_total_contrib_t0.get(ch, 0)
        roi = contrib / spend_sum if spend_sum > 0 else 0.0
        _theta = getattr(cp, 'theta', getattr(cp, 'theta_mean', 0))
        _alpha = getattr(cp, 'alpha', getattr(cp, 'alpha_mean', 0))
        _gamma = getattr(cp, 'gamma', getattr(cp, 'gamma_mean', 0))
        _beta = getattr(cp, 'beta', getattr(cp, 'beta_mean', 0))
        if cp.adstock_type == "geometric":
            adstock_str = f"θ={_theta:.3f}"
        else:
            _ws = getattr(cp, 'weibull_shape', 0)
            _wsc = getattr(cp, 'weibull_scale', 0)
            adstock_str = f"shape={_ws:.2f}, scale={_wsc:.2f}"
        param_rows.append({
            "渠道": ch_names.get(ch, ch),
            "类型": "付费",
            "Adstock": adstock_str,
            "Hill α": round(_alpha, 3),
            "Hill γ": round(_gamma, 3),
            "系数 β": round(_beta, 6),
            "贡献 %": f"{contrib / total_contrib_t0 * 100:.1f}%",
            "ROI": round(roi, 3),
        })
    for ch, cp in getattr(model, 'organic_params', {}).items():
        contrib = ch_total_contrib_t0.get(ch, 0)
        _theta = getattr(cp, 'theta', getattr(cp, 'theta_mean', 0))
        _beta = getattr(cp, 'beta', getattr(cp, 'beta_mean', 0))
        if cp.adstock_type == "geometric":
            adstock_str = f"θ={_theta:.3f}"
        else:
            _ws = getattr(cp, 'weibull_shape', 0)
            _wsc = getattr(cp, 'weibull_scale', 0)
            adstock_str = f"shape={_ws:.2f}, scale={_wsc:.2f}"
        param_rows.append({
            "渠道": ch_names.get(ch, ch),
            "类型": "Organic",
            "Adstock": adstock_str,
            "Hill α": "—",
            "Hill γ": "—",
            "系数 β": round(_beta, 6),
            "贡献 %": f"{contrib / total_contrib_t0 * 100:.1f}%",
            "ROI": "—",
        })
    if hasattr(model, 'impressions_params'):
        for ch, cp in model.impressions_params.items():
            _theta = getattr(cp, 'theta', getattr(cp, 'theta_mean', 0))
            _alpha = getattr(cp, 'alpha', getattr(cp, 'alpha_mean', 0))
            _gamma = getattr(cp, 'gamma', getattr(cp, 'gamma_mean', 0))
            _beta = getattr(cp, 'beta', getattr(cp, 'beta_mean', 0))
            if cp.adstock_type == "geometric":
                adstock_str = f"θ={_theta:.3f}"
            else:
                _ws = getattr(cp, 'weibull_shape', 0)
                _wsc = getattr(cp, 'weibull_scale', 0)
                adstock_str = f"shape={_ws:.2f}, scale={_wsc:.2f}"
            param_rows.append({
                "渠道": ch_names.get(ch, ch) + "(曝光)",
                "类型": "曝光",
                "Adstock": adstock_str,
                "Hill α": round(_alpha, 3),
                "Hill γ": round(_gamma, 3),
                "系数 β": round(_beta, 6),
                "贡献 %": "—",
                "ROI": "—",
            })
    st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)
