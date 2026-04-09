"""
_mmm_summary.py — Model quality summary panel.
Shows grade card, core metrics, recommendations, and training transparency.
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


def _model_quality_grade(r2: float, nrmse: float, test_r2: float) -> tuple:
    """Return (grade, color, label) based on composite model quality."""
    score = r2 * 0.3 + max(0, test_r2) * 0.4 + max(0, 1 - nrmse) * 0.3
    if score >= 0.7:
        return "A", "#2E7D32", "良好"
    elif score >= 0.5:
        return "B", "#F57F17", "可接受"
    else:
        return "C", "#C62828", "需改进"


def render_model_summary(model, df, dv_col: str, ch_names: dict, data_mode: str, time_col: str):
    """Render the model conclusion summary and training transparency panel.

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
    """
    _n_total = len(df)
    _n_train = int(_n_total * 0.8)
    _df_test_summary = df.iloc[_n_train:]
    _y_test_summary = _df_test_summary[dv_col].values if dv_col in _df_test_summary.columns else np.array([])
    _test_r2_summary = 0.0
    if len(_y_test_summary) > 1:
        _y_pred_summary = model.predict(_df_test_summary)
        _ss_res = np.sum((_y_test_summary - _y_pred_summary) ** 2)
        _ss_tot = np.sum((_y_test_summary - _y_test_summary.mean()) ** 2)
        _test_r2_summary = max(0.0, 1 - _ss_res / _ss_tot) if _ss_tot > 0 else 0.0

    _grade, _grade_color, _grade_label = _model_quality_grade(model.r_squared, model.nrmse, _test_r2_summary)

    _contributions_summary = model.channel_contribution(df)
    _ch_total_summary = {ch: float(v.sum()) for ch, v in _contributions_summary.items()}
    _top_ch = max(_ch_total_summary, key=_ch_total_summary.get) if _ch_total_summary else ""
    _top_ch_name = ch_names.get(_top_ch, _top_ch)
    _top_ch_pct = _ch_total_summary.get(_top_ch, 0) / (sum(_ch_total_summary.values()) + 1e-9) * 100

    with st.container(border=True):
        st.markdown("### 模型结论摘要")
        grade_col, metrics_col, rec_col = st.columns([1, 2, 2])

        with grade_col:
            st.markdown(
                f'<div style="text-align:center;padding:12px;">'
                f'<div style="font-size:48px;font-weight:800;color:{_grade_color};">{_grade}</div>'
                f'<div style="font-size:14px;color:{_grade_color};font-weight:600;">模型质量: {_grade_label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with metrics_col:
            st.markdown("**核心指标**")
            st.markdown(f"- R²(训练) = **{model.r_squared:.4f}** | R²(测试) = **{_test_r2_summary:.4f}**")
            _rssd = getattr(model, 'decomp_rssd', None)
            st.markdown(f"- NRMSE = **{model.nrmse:.4f}**" + (f" | DecompRSSD = **{_rssd:.4f}**" if _rssd else ""))
            st.markdown(f"- 最大贡献渠道: **{_top_ch_name}** ({_top_ch_pct:.1f}%)")

        with rec_col:
            st.markdown("**建议**")
            recommendations = []
            if _test_r2_summary < 0.3:
                recommendations.append("测试集R²偏低，模型泛化能力不足。建议增加训练数据或简化特征。")
            elif _test_r2_summary < 0.5:
                recommendations.append("测试集R²尚可，可用于趋势参考，但具体数值需结合业务判断。")
            else:
                recommendations.append("测试集R²良好，模型预测可信度较高，可直接用于预算优化。")
            if getattr(model, 'decomp_rssd', 0) > 0.35:
                recommendations.append("渠道贡献分布偏离花费分布较大，检查是否有渠道被高/低估。")
            if model.nrmse > 0.5:
                recommendations.append("归一化误差偏高，模型拟合精度有提升空间。")
            if not recommendations:
                recommendations.append("模型各项指标均在合理范围，可放心使用。")
            for r in recommendations:
                st.markdown(f"- {r}")

    # ─── Training Transparency Panel ─────────────────────────────────────────
    with st.expander("🔍 训练详情（特征、过程、稳定性）", expanded=False):
        _tm = getattr(model, 'training_meta', {}) or {}
        _fi = getattr(model, 'feature_importance', {}) or {}
        _cv = getattr(model, 'cv_results', {}) or {}
        _bs = getattr(model, 'bootstrap_stability', {}) or {}

        # ── Training config table ──
        if _tm:
            st.markdown("#### 训练配置")
            _config_rows = [
                {"参数": "因变量", "值": _tm.get("dv_col", "—")},
                {"参数": "Adstock类型", "值": _tm.get("adstock_type", "—")},
                {"参数": "优化迭代次数", "值": str(_tm.get("n_trials", "—"))},
                {"参数": "训练样本数", "值": str(_tm.get("n_train", "—"))},
                {"参数": "测试样本数", "值": str(_tm.get("n_test", "—"))},
                {"参数": "特征数", "值": str(len(_tm.get("feature_names", [])))},
                {"参数": "渠道数", "值": str(len(_tm.get("channel_keys", [])))},
                {"参数": "训练耗时(秒)", "值": f"{_tm.get('training_duration_sec', 0):.1f}"},
                {"参数": "正则化", "值": _tm.get("regularization", "ridge")},
                {"参数": "最优Alpha", "值": f"{_tm.get('best_alpha', 'N/A')}"},
                {"参数": "最终Alpha", "值": f"{_tm.get('final_alpha', _tm.get('best_alpha', 'N/A'))}"},
                {"参数": "Alpha自适应提升", "值": "是" if _tm.get("alpha_boosted") else "否"},
                {"参数": "集成数量", "值": str(_tm.get("n_ensemble", 1))},
                {"参数": "交互特征", "值": "开启" if _tm.get("use_interactions") else "关闭"},
                {"参数": "剪枝曝光渠道", "值": ", ".join(_tm.get("pruned_impressions", [])) or "无"},
            ]
            st.dataframe(pd.DataFrame(_config_rows), use_container_width=True, hide_index=True)

        # ── Feature importance ──
        if _fi:
            st.markdown("#### 特征重要性排名")
            _fi_sorted = sorted(_fi.items(), key=lambda x: abs(x[1]), reverse=True)
            _fi_rows = [{"排名": i + 1, "特征": k, "重要性": round(abs(v), 4)} for i, (k, v) in enumerate(_fi_sorted)]
            _fi_top = _fi_rows[:15]

            _fi_col1, _fi_col2 = st.columns([2, 3])
            with _fi_col1:
                st.dataframe(pd.DataFrame(_fi_rows), use_container_width=True, hide_index=True)
            with _fi_col2:
                _fi_df = pd.DataFrame(_fi_top)
                fig_fi = go.Figure(go.Bar(
                    x=_fi_df["重要性"], y=_fi_df["特征"],
                    orientation='h', marker_color="#1976D2",
                ))
                fig_fi.update_layout(
                    title="Top 15 特征重要性（|β| × σ）",
                    height=max(250, len(_fi_df) * 28),
                    margin=dict(t=35, b=20, l=160),
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig_fi, use_container_width=True)

        # ── Rolling CV results ──
        if _cv:
            st.markdown("#### Rolling-Origin 交叉验证")
            _cv_c1, _cv_c2, _cv_c3 = st.columns(3)
            _cv_c1.metric("CV 均值 R²", f"{_cv.get('mean_r2', 0):.4f}")
            _cv_c2.metric("CV 标准差", f"{_cv.get('std_r2', 0):.4f}")
            _n_folds_display = _cv.get("n_folds", len(_cv.get("fold_details", [])))
            _cv_c3.metric("折数", str(_n_folds_display))

            _folds = _cv.get("fold_details", [])
            if _folds:
                _fold_df = pd.DataFrame(_folds)
                if "r2" in _fold_df.columns:
                    fig_cv = go.Figure(go.Bar(
                        x=[f"Fold {i + 1}" for i in range(len(_folds))],
                        y=_fold_df["r2"],
                        marker_color=["#43A047" if r2 > 0.5 else "#FF8F00" if r2 > 0 else "#E53935"
                                      for r2 in _fold_df["r2"]],
                    ))
                    fig_cv.update_layout(
                        title="各折 R² 分布", height=250,
                        yaxis_title="R²", margin=dict(t=35, b=20),
                    )
                    st.plotly_chart(fig_cv, use_container_width=True)
            st.caption("Rolling-Origin CV：滑动预测原点，评估模型在不同时间窗口上的泛化能力。比固定 holdout 更稳健。")

        # ── Bootstrap coefficient stability ──
        if _bs:
            st.markdown("#### 系数稳定性（Block Bootstrap）")
            _bs_rows = []
            for ch, stats in _bs.items():
                _bs_rows.append({
                    "渠道": ch_names.get(ch, ch),
                    "系数均值": round(stats.get("mean", 0), 4),
                    "标准差": round(stats.get("std", 0), 4),
                    "变异系数(CV)": round(stats.get("cv", 0), 4),
                    "稳定": "✓ 稳定" if stats.get("stable", False) else "✗ 不稳定",
                })
            _bs_df = pd.DataFrame(_bs_rows)

            _bs_col1, _bs_col2 = st.columns([2, 3])
            with _bs_col1:
                st.dataframe(_bs_df, use_container_width=True, hide_index=True)
            with _bs_col2:
                fig_bs = go.Figure()
                fig_bs.add_trace(go.Bar(
                    x=_bs_df["渠道"], y=_bs_df["系数均值"],
                    error_y=dict(type="data", array=_bs_df["标准差"].tolist()),
                    marker_color=["#43A047" if "✓" in s else "#E53935" for s in _bs_df["稳定"]],
                ))
                fig_bs.update_layout(
                    title="渠道系数 ± 标准差（绿=稳定, 红=不稳定）",
                    yaxis_title="系数 β", height=280,
                    margin=dict(t=35, b=20),
                )
                st.plotly_chart(fig_bs, use_container_width=True)
            st.caption("Block Bootstrap 通过重采样连续时间块评估系数稳定性。CV < 0.5 视为稳定，说明该渠道效果估计可靠。")

        if not _tm and not _fi and not _cv and not _bs:
            st.info("当前模型没有训练元数据。重新训练模型后可查看完整训练详情。")
