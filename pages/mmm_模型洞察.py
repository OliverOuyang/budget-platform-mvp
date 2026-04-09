"""
MMM 模型洞察 - 合并页面
训练和管理 MMM 模型。训练完成后，模型参数自动提供给预算推算结果页使用。
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

from utils.data_loader import (
    load_mock_data, load_uploaded_data, load_real_data, load_weekly_data,
    CHANNEL_NAMES, CHANNEL_KEYS,
    REAL_CHANNEL_NAMES, REAL_CHANNEL_KEYS,
    WEEKLY_CHANNEL_NAMES, WEEKLY_CHANNEL_KEYS,
)
from engine.mmm_engine import (
    MMMTrainer, MMMModel, save_model, load_model,
    hill_saturation, geometric_adstock, weibull_adstock,
    ModelRegistry,
)

# ─── 页面标题 ───────────────────────────────────────────────────��─────────────
st.title("🧪 MMM 模型洞察")
st.markdown("训练和管理 MMM 模型。训练完成后，模型参数自动提供给预算推算结果页使用。")

# ─── 顶部配置区 ───────────────────────────────────────────────────────────────
with st.container(border=True):
    st.subheader("⚙️ 模型配置")

    cfg_col1, cfg_col2, cfg_col3 = st.columns(3)

    with cfg_col1:
        data_source = st.radio(
            "数据来源",
            ["真实数据(周度)", "真实数据(月度)", "内置Mock数据", "上传CSV"],
            horizontal=True,
            help="周度：四月数据67周×5渠道（含免费渠道）；月度：分渠道转化16月×4渠道；Mock：104周×7渠道模拟",
        )
        if data_source == "真实数据(周度)":
            st.caption("因变量：`dv_first_loan_amt`（首借交易额，万元）| 周度×5渠道（含免费渠道organic）")
            _dv_labels = {
                "dv_first_loan_amt": "首借交易额",
                "dv_total_loan_amt": "合计交易额",
                "dv_repeat_loan_amt": "复借交易额",
                "dv_t0_cps": "T0 CPS(花费加权)",
                "dv_t0_approval_rate": "T0过件率(全量,花费加权)",
                "dv_safe_t0_approval_rate": "T0过件率(安全,花费加权)",
                "dv_13_approval_count": "1-3档授信人数(sum)",
                "dv_t0_cost": "T0申完成本(花费加权)",
                "dv_t0_loan_amt": "T0借款金额",
            }
            # Load df temporarily to get available DVs (will be properly loaded below)
            try:
                _tmp_df = load_weekly_data()
                _available_dvs = [c for c in _tmp_df.columns if c.startswith("dv_")]
            except Exception:
                _available_dvs = ["dv_first_loan_amt"]
            if _available_dvs:
                _selected_dv = st.selectbox(
                    "因变量",
                    _available_dvs,
                    format_func=lambda x: _dv_labels.get(x, x),
                    key="weekly_dv_selector",
                )
                st.session_state["_weekly_dv_col"] = _selected_dv
        elif data_source == "真实数据(月度)":
            st.caption("因变量：`dv_first_loan_amt`（首借交易额，万元）| 月度×4渠道")
        else:
            st.caption("因变量：`dv_t0_loan_amt`（借款金额）")

    with cfg_col2:
        adstock_type = st.radio(
            "Adstock 类型",
            ["geometric", "weibull"],
            horizontal=True,
            format_func=lambda x: "几何衰减 (Geometric)" if x == "geometric" else "Weibull PDF",
            help="geometric：简单快速；weibull：Robyn默认，更灵活",
        )

    with cfg_col3:
        n_trials = st.number_input(
            "优化迭代次数",
            min_value=50, max_value=1000,
            value=300, step=50,
            help="越多越精准，但训练时间更长",
        )
        st.caption("训练/测试划分：80% / 20%")

    # ── R13: Advanced training config ────────────────────────────────────────
    with st.expander("⚙️ 高级训练配置", expanded=False):
        _adv_c1, _adv_c2, _adv_c3 = st.columns(3)
        with _adv_c1:
            _n_weeks = len(st.session_state["df"]) if "df" in st.session_state else 118
            train_weeks = st.slider(
                "训练窗口(周)",
                min_value=40, max_value=_n_weeks, value=_n_weeks,
                help="仅使用最近N周数据训练，可排除早期regime不同的数据",
            )
            if train_weeks >= _n_weeks:
                train_weeks = None  # Use all data
        with _adv_c2:
            use_interactions = st.checkbox(
                "启用交互特征(spend×impressions)",
                value=False,
                help="添加花费×曝光交互项。增加模型复杂度，可能加剧共线性",
            )
        with _adv_c3:
            regularization = st.radio(
                "正则化方式",
                ["ridge", "elasticnet"],
                format_func=lambda x: "Ridge (L2)" if x == "ridge" else "ElasticNet (L1+L2)",
                help="Ridge稳定性好；ElasticNet可自动特征选择",
            )

    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
    train_btn = btn_col1.button("▶️ 开始训练", type="primary", use_container_width=True)
    load_btn = btn_col2.button("📂 加载已有模型", use_container_width=True)

    # ── US-706: Model Manager ────────────────────────────────────────────────
    with st.expander("📋 模型管理", expanded=False):
        _registry = ModelRegistry()
        _registry_entries = _registry.list()
        if not _registry_entries:
            st.info("暂无已保存模型。训练完成后可保存到模型库。")
        else:
            # Show table
            _reg_rows = []
            for _e in _registry_entries:
                _reg_rows.append({
                    "ID": _e.get("id", ""),
                    "名称": _e.get("name", ""),
                    "因变量": _e.get("dv_col", ""),
                    "R²(训练)": _e.get("r_squared", 0),
                    "NRMSE": _e.get("train_nrmse", _e.get("r_squared", 0)),
                    "RSSD": _e.get("decomp_rssd", 0),
                    "创建时间": _e.get("created_at", "")[:16] if _e.get("created_at") else "",
                })
            _reg_df = pd.DataFrame(_reg_rows)
            st.dataframe(_reg_df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

            # Per-row load / delete buttons
            st.markdown("**加载 / 删除模型**")
            _compare_selected = st.session_state.get("_reg_compare_ids", [])
            for _e in _registry_entries:
                _eid = _e.get("id", "")
                _ename = _e.get("name", _eid)
                _rc1, _rc2, _rc3 = st.columns([3, 1, 1])
                _rc1.markdown(f"`{_eid}` — **{_ename}**  (R²={_e.get('r_squared',0):.4f})")
                if _rc2.button("加载", key=f"reg_load_{_eid}", use_container_width=True):
                    _loaded = _registry.load(_eid)
                    if _loaded and _loaded.is_fitted:
                        st.session_state["mmm_model"] = _loaded
                        st.success(f"已加载模型 {_ename}")
                        st.rerun()
                    else:
                        st.error("加载失败，文件可能已损坏。")
                if _rc3.button("删除", key=f"reg_del_{_eid}", use_container_width=True):
                    _registry.delete(_eid)
                    st.success(f"已删除模型 {_ename}")
                    st.rerun()

            # Compare mode: select 2 models
            st.markdown("---")
            st.markdown("**对比模式（选择2个模型）**")
            _all_ids = [_e.get("id", "") for _e in _registry_entries]
            _all_names = [f"{_e.get('id','')[:6]} — {_e.get('name','')}" for _e in _registry_entries]
            _cmp_sel = st.multiselect(
                "选择对比模型（最多2个）",
                options=_all_ids,
                format_func=lambda x: next(
                    (f"{_e.get('id','')[:6]} — {_e.get('name','')}" for _e in _registry_entries if _e.get("id") == x),
                    x
                ),
                max_selections=2,
                key="reg_compare_multiselect",
            )
            if len(_cmp_sel) == 2:
                st.session_state["_reg_compare_ids"] = _cmp_sel
                _cmp_models = [_registry.get_entry(_cmp_sel[0]), _registry.get_entry(_cmp_sel[1])]
                if _cmp_models[0] and _cmp_models[1]:
                    st.markdown("**并排指标对比**")
                    _cmp_metric_keys = ["r_squared", "train_nrmse", "decomp_rssd", "test_r_squared", "mape_holdout", "cv_mean_r2"]
                    _cmp_metric_labels = {
                        "r_squared": "R²(训练)", "train_nrmse": "NRMSE",
                        "decomp_rssd": "DecompRSSD", "test_r_squared": "R²(测试)",
                        "mape_holdout": "Holdout MAPE", "cv_mean_r2": "CV R²",
                    }
                    _cmp_rows = []
                    for _mk in _cmp_metric_keys:
                        _cmp_rows.append({
                            "指标": _cmp_metric_labels.get(_mk, _mk),
                            _cmp_models[0].get("name", "模型A"): round(_cmp_models[0].get(_mk, 0), 4),
                            _cmp_models[1].get("name", "模型B"): round(_cmp_models[1].get(_mk, 0), 4),
                        })
                    st.dataframe(pd.DataFrame(_cmp_rows), use_container_width=True, hide_index=True)

# ─── 数据加载 ─────────────────────────────────────────────────────────────────
if data_source == "上传CSV":
    uploaded = st.file_uploader("上传CSV文件（需含 week_start 及各渠道 _spend 列）", type=["csv", "xlsx"])
    if uploaded:
        try:
            df = load_uploaded_data(uploaded)
            st.session_state["df"] = df
            st.session_state["_data_mode"] = "mock"
            st.success(f"数据加载成功：{len(df)} 行，{len(df.columns)} 列")
        except Exception as e:
            st.error(f"数据加载失败：{e}")
            st.stop()
    else:
        st.info("请上传CSV文件，或切换为其他数据来源。")
        st.stop()
elif data_source == "真实数据(周度)":
    try:
        df = load_weekly_data()
        st.session_state["df"] = df
        st.session_state["_data_mode"] = "weekly"
        n_paid = len([c for c in df.columns if c.endswith('_spend') and c != 'total_spend'])
        has_organic = "free_channel_first_login" in df.columns
        st.success(f"周度数据加载成功：{len(df)} 周 × {n_paid} 付费渠道" + (" + 免费渠道(organic)" if has_organic else ""))
    except Exception as e:
        st.error(f"周度数据加载失败：{e}")
        st.stop()
elif data_source == "真实数据(月度)":
    try:
        df = load_real_data()
        st.session_state["df"] = df
        st.session_state["_data_mode"] = "real"
        st.success(f"月度数据加载成功：{len(df)} 月 × {len([c for c in df.columns if c.endswith('_spend') and c != 'total_spend'])} 付费渠道")
    except Exception as e:
        st.error(f"月度数据加载失败：{e}")
        st.stop()
else:
    if "df" not in st.session_state:
        df = load_mock_data()
        st.session_state["df"] = df
        st.session_state["_data_mode"] = "mock"
    else:
        df = st.session_state["df"]

df = st.session_state["df"]

# Resolve channel name mapping based on data mode
_data_mode = st.session_state.get("_data_mode", "mock")
if _data_mode == "weekly":
    _ch_names = WEEKLY_CHANNEL_NAMES
elif _data_mode == "real":
    _ch_names = REAL_CHANNEL_NAMES
else:
    _ch_names = CHANNEL_NAMES
_time_col = "month" if "month" in df.columns else "week_start"
_period_label = "万元/月" if _data_mode == "real" else "万元/周"

# ─── 模型训练 / 加载 ──────────────────────────────────────────────────────────
model: MMMModel = st.session_state.get("mmm_model")
if _data_mode in ("real", "weekly"):
    # Use DV selector value if available (weekly mode)
    _default_dv = "dv_first_loan_amt" if "dv_first_loan_amt" in df.columns else "dv_total_loan_amt"
    dv_col = st.session_state.get("_weekly_dv_col", _default_dv) if _data_mode == "weekly" else _default_dv
else:
    dv_col = "dv_t0_loan_amt" if "dv_t0_loan_amt" in df.columns else "loan_amt"

if load_btn:
    cached = load_model()
    if cached and cached.is_fitted:
        model = cached
        st.session_state["mmm_model"] = model
        st.success(
            f"模型已加载 | R²={model.r_squared:.4f} | "
            f"NRMSE={model.nrmse:.4f} | DecompRSSD={model.decomp_rssd:.4f}"
        )
    else:
        st.warning("未找到已有模型文件，请先训练。")

if train_btn:
    if dv_col not in df.columns:
        st.error(f"因变量列 `{dv_col}` 不存在，请检查数据。")
    else:
        for _k in ["mmm_optimal_budget", "mmm_budget_suggestion", "mmm_opt_total"]:
            st.session_state.pop(_k, None)
        progress_bar = st.progress(0.0, text="正在训练 MMM 模型...")

        def _update_progress(p):
            progress_bar.progress(min(p, 1.0), text=f"贝叶斯优化进度：{p*100:.0f}%")

        with st.spinner(f"贝叶斯优化中（{n_trials} 次迭代），请稍候..."):
            trainer = MMMTrainer(df, dv_col=dv_col, n_trials=n_trials,
                                 adstock_type=adstock_type,
                                 train_weeks=train_weeks,
                                 use_interactions=use_interactions,
                                 regularization=regularization)
            model = trainer.fit(progress_callback=_update_progress)
            save_model(model)
            st.session_state["mmm_model"] = model
            st.session_state["mmm_trainer"] = trainer
        progress_bar.progress(1.0, text="训练完成！")
        st.success(
            f"训练完成 | R²(train)={model.r_squared:.4f} | R²(test/CV)={model.test_r_squared:.4f} | "
            f"NRMSE={model.nrmse:.4f} | DecompRSSD={model.decomp_rssd:.4f}"
        )
        # Show Pareto candidates
        if model.pareto_results:
            with st.expander("Pareto 候选模型"):
                pareto_df = pd.DataFrame(model.pareto_results)
                display_cols = ["study_idx", "r_squared", "nrmse", "decomp_rssd", "test_r_squared", "cv_test_r_squared", "combined"]
                display_cols = [c for c in display_cols if c in pareto_df.columns]
                pareto_show = pareto_df[display_cols].copy()
                col_names = {"study_idx": "Study", "r_squared": "R2(train)", "nrmse": "NRMSE",
                             "decomp_rssd": "DecompRSSD", "test_r_squared": "R2(test)",
                             "cv_test_r_squared": "R2(CV)", "combined": "Combined"}
                pareto_show = pareto_show.rename(columns=col_names)
                st.dataframe(pareto_show, use_container_width=True, hide_index=True)

                # Pareto front scatter plot (NRMSE vs RSSD)
                if "nrmse" in pareto_df.columns and "decomp_rssd" in pareto_df.columns:
                    fig_pareto = go.Figure()
                    fig_pareto.add_trace(go.Scatter(
                        x=pareto_df["nrmse"], y=pareto_df["decomp_rssd"],
                        mode="markers+text",
                        marker=dict(size=10, color=pareto_df.get("cv_test_r_squared", pareto_df.get("test_r_squared", [0]*len(pareto_df))),
                                    colorscale="Viridis", showscale=True, colorbar=dict(title="CV R²")),
                        text=[f"S{r.get('study_idx','')}" for _, r in pareto_df.iterrows()],
                        textposition="top center",
                        hovertemplate="NRMSE=%{x:.4f}<br>RSSD=%{y:.4f}<br>CV R²=%{marker.color:.4f}<extra></extra>",
                    ))
                    fig_pareto.update_layout(
                        title="Pareto Front (NRMSE vs DecompRSSD)",
                        xaxis_title="NRMSE ↓", yaxis_title="DecompRSSD ↓",
                        height=300, margin=dict(t=40, b=40),
                    )
                    st.plotly_chart(fig_pareto, use_container_width=True)

                if "selection_reason" in pareto_df.columns:
                    st.caption(f"选模策略: {pareto_df['selection_reason'].iloc[0]}")

        # ── US-706: Save trained model to registry ──────────────────────────
        with st.expander("💾 保存模型到模型库", expanded=False):
            _save_name = st.text_input(
                "模型名称",
                value=f"{dv_col}_{adstock_type}_{n_trials}t",
                key="save_model_name",
            )
            if st.button("保存到模型库", key="save_to_registry", type="primary"):
                _reg = ModelRegistry()
                _mid = _reg.save(model, name=_save_name)
                st.success(f"已保存到模型库，ID: `{_mid}`。可在「模型管理」面板中加载或对比。")

if model is None:
    # 尝试自动加载
    auto = load_model()
    if auto and auto.is_fitted:
        model = auto
        st.session_state["mmm_model"] = model

if model is None:
    st.info("请先训练模型或加载已有模型。")
    st.stop()

# ─── 模型结论摘要 ─────────────────────────────────────────────────────────────
def _model_quality_grade(r2: float, nrmse: float, test_r2: float) -> tuple:
    """Return (grade, color, label) based on composite model quality."""
    score = r2 * 0.3 + max(0, test_r2) * 0.4 + max(0, 1 - nrmse) * 0.3
    if score >= 0.7:
        return "A", "#2E7D32", "良好"
    elif score >= 0.5:
        return "B", "#F57F17", "可接受"
    else:
        return "C", "#C62828", "需改进"

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

# 获取最大贡献渠道
_contributions_summary = model.channel_contribution(df)
_ch_total_summary = {ch: float(v.sum()) for ch, v in _contributions_summary.items()}
_top_ch = max(_ch_total_summary, key=_ch_total_summary.get) if _ch_total_summary else ""
_top_ch_name = _ch_names.get(_top_ch, _top_ch)
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
        st.markdown(f"- NRMSE = **{model.nrmse:.4f}** | DecompRSSD = **{model.decomp_rssd:.4f}**")
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
        if model.decomp_rssd > 0.35:
            recommendations.append("渠道贡献分布偏离花费分布较大，检查是否有渠道被高/低估。")
        if model.nrmse > 0.5:
            recommendations.append("归一化误差偏高，模型拟合精度有提升空间。")
        if not recommendations:
            recommendations.append("模型各项指标均在合理范围，可放心使用。")
        for r in recommendations:
            st.markdown(f"- {r}")

# ─── US-707: Training Transparency Panel ──────────────────────────────────────
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
                "渠道": _ch_names.get(ch, ch),
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

# ─── 4 个 Tab ─────────────────────────────────────────────────────────────────
tab0, tab1, tab2, tab3 = st.tabs([
    "📈 拟合效果",
    "🍰 渠道贡献",
    "📉 响应曲线",
    "💡 预算优化",
])

# ══════════════════════════════════════════════════════════════════════════════
# Tab 0：拟合效果
# ══════════════════════════════════════════════════════════════════════════════
with tab0:
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
        help="越��越好，<0.3 良好，<0.5 可接受",
    )
    m3.metric(
        "Decomp RSSD", f"{model.decomp_rssd:.4f}",
        delta="均衡" if model.decomp_rssd < 0.35 else "偏高",
        delta_color="normal" if model.decomp_rssd < 0.35 else "inverse",
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
        x=df[_time_col], y=y_actual,
        mode="lines", name="实际值",
        line=dict(color="#1976D2", width=2),
    ))
    fig_fit.add_trace(go.Scatter(
        x=df[_time_col], y=y_pred,
        mode="lines", name="预测值",
        line=dict(color="#FF7043", width=2, dash="dot"),
    ))
    if n_train < n_total:
        fig_fit.add_vrect(
            x0=df[_time_col].iloc[n_train],
            x1=df[_time_col].iloc[-1],
            fillcolor="rgba(200,200,200,0.15)",
            line_width=0,
            annotation_text="测试集",
            annotation_position="top left",
        )
    fig_fit.update_layout(
        title="实际值 vs 预测值（借款金额，万元）",
        xaxis_title="月份" if _data_mode == "real" else "周次",
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
            x=df[_time_col], y=residuals,
            marker_color=res_colors,
            name="残差",
            hovertemplate="残差: %{y:,.0f}<extra></extra>",
        ))
        if n_train < n_total:
            fig_res.add_vrect(
                x0=df[_time_col].iloc[n_train],
                x1=df[_time_col].iloc[-1],
                fillcolor="rgba(200,200,200,0.15)",
                line_width=0,
                annotation_text="测试集",
                annotation_position="top left",
            )
        fig_res.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig_res.update_layout(
            title="残差时序（绿=实际>预测, 红=实际<预测）",
            xaxis_title="月份" if _data_mode == "real" else "周次",
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
        # Normal curve overlay
        res_mean = float(np.mean(residuals))
        res_std = float(np.std(residuals)) + 1e-9
        x_norm = np.linspace(res_mean - 3 * res_std, res_mean + 3 * res_std, 100)
        y_norm = (1 / (res_std * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_norm - res_mean) / res_std) ** 2)
        # Scale to match histogram
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

    # ── US-708: DW statistic interpretation ─────────────────────────────────
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
                st.warning(f"DW={_dw:.3f} > 2.5，存在负自相关。模型可��过度拟合了短期波动。")
            else:
                st.success(f"DW={_dw:.3f}，在 [1.5, 2.5] 范围内，残差无显著自相关。")
    with _diag_c2:
        st.metric("MAPE", f"{_mape_val:.1f}%")
        st.markdown(
            f"平均每{'月' if _data_mode == 'real' else '周'}预测偏差约 **{_mape_abs:,.0f} 万元**"
            f"（实际均值 {_avg_actual:,.0f} 万元）。"
            f"{'误差可控，可用于预算分配参考。' if _mape_val < 15 else '误差偏大，建议结合业务判断使用。'}"
        )

    # ── US-708: ACF plot ────────────────────────────────────────────────────
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
        # Stem lines
        for i, v in enumerate(_acf_vals):
            fig_acf.add_trace(go.Scatter(
                x=[i, i], y=[0, v], mode="lines",
                line=dict(color="#1976D2", width=2), showlegend=False,
            ))
        # Markers
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
                x=df[_time_col], y=df[dv_col],
                mode="lines", name="实际值", line=dict(color="#90A4AE", width=1),
            ))
            fig_stl_trend.add_trace(go.Scatter(
                x=df[_time_col], y=df["stl_trend"],
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
                x=df[_time_col], y=df["stl_seasonal"],
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
        if cp.adstock_type == "geometric":
            adstock_str = f"θ={cp.theta:.3f}"
        else:
            adstock_str = f"shape={cp.weibull_shape:.2f}, scale={cp.weibull_scale:.2f}"
        param_rows.append({
            "渠道": _ch_names.get(ch, ch),
            "类型": "付费",
            "Adstock": adstock_str,
            "Hill α": round(cp.alpha, 3),
            "Hill γ": round(cp.gamma, 3),
            "系数 β": round(cp.beta, 6),
            "贡献 %": f"{contrib / total_contrib_t0 * 100:.1f}%",
            "ROI": round(roi, 3),
        })
    # Organic channels
    for ch, cp in model.organic_params.items():
        contrib = ch_total_contrib_t0.get(ch, 0)
        if cp.adstock_type == "geometric":
            adstock_str = f"θ={cp.theta:.3f}"
        else:
            adstock_str = f"shape={cp.weibull_shape:.2f}, scale={cp.weibull_scale:.2f}"
        param_rows.append({
            "渠道": _ch_names.get(ch, ch),
            "类型": "Organic",
            "Adstock": adstock_str,
            "Hill α": "—",
            "Hill γ": "—",
            "系数 β": round(cp.beta, 6),
            "贡献 %": f"{contrib / total_contrib_t0 * 100:.1f}%",
            "ROI": "—",
        })
    # Impressions media params (if available)
    if hasattr(model, 'impressions_params'):
        for ch, cp in model.impressions_params.items():
            if cp.adstock_type == "geometric":
                adstock_str = f"θ={cp.theta:.3f}"
            else:
                adstock_str = f"shape={cp.weibull_shape:.2f}, scale={cp.weibull_scale:.2f}"
            param_rows.append({
                "渠道": _ch_names.get(ch, ch) + "(曝光)",
                "类型": "曝光",
                "Adstock": adstock_str,
                "Hill α": round(cp.alpha, 3),
                "Hill γ": round(cp.gamma, 3),
                "系数 β": round(cp.beta, 6),
                "贡献 %": "—",
                "ROI": "—",
            })
    st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1：渠道贡献
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
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
        wf_labels.append(_ch_names.get(ch, ch))
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
        title=f"贡献分解瀑布图（周均/月均，{_period_label}）",
        yaxis_title=f"借款金额（{_period_label}）",
        height=360,
        margin=dict(t=40, b=60),
        showlegend=False,
    )
    st.plotly_chart(fig_waterfall, use_container_width=True)
    st.caption("瀑布图展示：基线（截距+宏观/季节因素） → 各渠道边际贡献 → 最终预测均值")

    # ── US-708: Business interpretation per channel ─────────────────────────
    st.markdown("**渠道效果业务解读**")
    for ch in sorted_channels:
        _ch_n = _ch_names.get(ch, ch)
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
            "渠道": _ch_names.get(ch, ch),
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
            x=df[_time_col], y=contrib_arr,
            mode="lines", name=_ch_names.get(ch, ch),
            stackgroup="one",
            line=dict(width=0.5),
            fillcolor=colors_stack[i % len(colors_stack)],
        ))
    fig_stack.update_layout(
        title="各渠道贡献（万元，堆叠面积）",
        xaxis_title="月份" if _data_mode == "real" else "周次",
        yaxis_title="贡献（万元）",
        height=380, hovermode="x unified",
    )
    st.plotly_chart(fig_stack, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2：响应曲线
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("渠道边际响应曲线（Hill 饱和效应）")

    channels_list = list(model.channel_params.keys())
    n_channels = len(channels_list)
    colors_resp = px.colors.qualitative.Plotly

    # 每行3个渠道 card
    saturation_info = []
    for row_start in range(0, n_channels, 3):
        row_channels = channels_list[row_start:row_start + 3]
        card_cols = st.columns(len(row_channels))

        for col_idx, ch in enumerate(row_channels):
            cp = model.channel_params[ch]
            ch_name = _ch_names.get(ch, ch)
            hist_mean = float(df[f"{ch}_spend"].mean()) if f"{ch}_spend" in df.columns else 100.0
            hist_max = float(df[f"{ch}_spend"].max()) if f"{ch}_spend" in df.columns else hist_mean * 2

            spend_range = np.linspace(0, hist_mean * 2, 200)

            # 使用 model.marginal_response 计算响应曲线（自动处理 log-DV 逆变换）
            response_vals = model.marginal_response(ch, spend_range, df_last=df)

            # 当前花费点饱和度（归一化空间）
            norm_current = hist_mean / (hist_max + 1e-9)
            sat_pct = float(hill_saturation(np.array([norm_current]), cp.alpha, cp.gamma)[0]) * 100

            # 边际 ROI（使用 marginal_response 保持量纲一致）
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
                    # 标记当前花费点
                    current_response = r_current
                    fig_hill.add_trace(go.Scatter(
                        x=[hist_mean], y=[current_response],
                        mode="markers",
                        marker=dict(color="red", size=10, symbol="circle"),
                        name="当前花费",
                    ))
                    fig_hill.update_layout(
                        height=200,
                        margin=dict(l=10, r=10, t=20, b=30),
                        xaxis_title=f"花费（{_period_label}）",
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

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3：预算优化
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
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
        # Scale each channel spend proportionally
        scaled_spends = {}
        for ch in model._channel_keys:
            col_name = f"{ch}_spend"
            if col_name in df.columns:
                scaled_spends[ch] = float(df[col_name].mean()) * multiplier
        # Build a scaled dataframe for prediction
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
                st.metric("总预算", f"{scenario_budget:,.0f} {_period_label}")
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
            f"优化总预算（{_period_label}）",
            min_value=100.0, max_value=10000.0,
            value=round(current_total_spend, 0),
            step=50.0,
            help=f"当前历史均值总预算约 {current_total_spend:.0f} {_period_label}",
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
            "渠道": [_ch_names.get(ch, ch) for ch in optimal],
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
        roi_by_name = {_ch_names.get(ch, ch): v for ch, v in roi_map.items()}
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

            # 状态行
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
                title=f"优化前 vs 优化后（{_period_label}）",
                barmode="group", height=320,
                yaxis_title=f"花费（{_period_label}）",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # 采纳按钮
        if st.button("✅ 采纳优化方案", type="primary"):
            recommended = {ch: v for ch, v in optimal.items()}
            st.session_state["mmm_recommended_spends"] = recommended
            st.session_state["mmm_budget_suggestion"] = recommended

            # 聚合为 V01 的 5 渠道口径供 Page 2 使用
            if _data_mode in ("real", "weekly"):
                # Real/weekly data channels are already at V01 granularity
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
                sat_vals = [st.session_state.get("mmm_channel_saturation", {}).get(_ch_names.get(k, k), 0) for k in mmm_keys]
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
            if _data_mode == "real":
                # Real data is already monthly
                st.session_state["mmm_predicted_loan_amt"] = float(predicted.mean())
            elif _data_mode == "weekly":
                # Weekly data — convert to monthly (×4.33)
                st.session_state["mmm_predicted_loan_amt"] = float(predicted.mean()) * 4.33
            else:
                # Mock data is weekly — convert to monthly
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
