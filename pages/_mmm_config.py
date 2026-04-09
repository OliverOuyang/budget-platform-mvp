"""
_mmm_config.py — Model configuration, training, and registry panel.
Returns (model, df, dv_col, data_mode, ch_names, time_col, period_label).
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd

from utils.data_loader import (
    load_mock_data, load_uploaded_data, load_real_data, load_weekly_data,
    CHANNEL_NAMES,
    REAL_CHANNEL_NAMES,
    WEEKLY_CHANNEL_NAMES,
)
from engine.mmm_engine import (
    MMMTrainer, MMMModel, save_model, load_model,
    ModelRegistry,
)
from engine.mmm_interface import create_trainer, ENGINE_TYPES


def render_mmm_config(df_container: dict):
    """Render the configuration, training, and data-loading panel.

    Parameters
    ----------
    df_container : dict
        Mutable dict used to pass ``df`` back to the caller (avoids a
        second session-state lookup at the call site).  Key ``"df"`` is
        set inside this function.

    Returns
    -------
    tuple
        (model, df, dv_col, data_mode, ch_names, time_col, period_label)
        where ``model`` may be ``None`` if nothing has been trained/loaded yet
        (the caller must handle that case).
    """

    # ─── 顶部配置区 ───────────────────────────────────────────────────────────
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
            engine_type = st.radio(
                "建模引擎",
                list(ENGINE_TYPES.keys()),
                format_func=lambda x: ENGINE_TYPES[x],
                horizontal=True,
                help="传统：Optuna+Ridge 点估计；贝叶斯：PyMC MCMC 后验分布",
            )
            adstock_type = st.radio(
                "Adstock 类型",
                ["geometric", "weibull"],
                horizontal=True,
                format_func=lambda x: "几何衰减 (Geometric)" if x == "geometric" else "Weibull PDF",
                help="geometric：简单快速；weibull：Robyn默认，更灵活",
            )

        with cfg_col3:
            if engine_type == "bayesian":
                n_draws = st.number_input(
                    "MCMC 采样次数 (draws)", min_value=500, max_value=5000,
                    value=2000, step=500,
                    help="后验分布采样数，越多越精确但越慢",
                )
                n_tune = st.number_input(
                    "预热迭代 (tune)", min_value=200, max_value=3000,
                    value=1000, step=200,
                    help="采样前的预热步数",
                )
                n_trials = 300  # unused default
            else:
                n_trials = st.number_input(
                    "优化迭代次数", min_value=50, max_value=1000,
                    value=300, step=50,
                    help="越多越精准，但训练时间更长",
                )
                n_draws = 2000  # unused default
                n_tune = 1000
            st.caption("训练/测试划分：80% / 20%")

        # ── Advanced training config ──────────────────────────────────────────
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
                    train_weeks = None
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

        # ── Model Manager ─────────────────────────────────────────────────────
        with st.expander("📋 模型管理", expanded=False):
            _registry = ModelRegistry()
            _registry_entries = _registry.list()
            if not _registry_entries:
                st.info("暂无已保存模型。训练完成后可保存到模型库。")
            else:
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

                st.markdown("---")
                st.markdown("**对比模式（选择2个模型）**")
                _all_ids = [_e.get("id", "") for _e in _registry_entries]
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

    # ─── 数据加载 ─────────────────────────────────────────────────────────────
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
    df_container["df"] = df

    # Resolve channel name mapping based on data mode
    data_mode = st.session_state.get("_data_mode", "mock")
    if data_mode == "weekly":
        ch_names = WEEKLY_CHANNEL_NAMES
    elif data_mode == "real":
        ch_names = REAL_CHANNEL_NAMES
    else:
        ch_names = CHANNEL_NAMES
    time_col = "month" if "month" in df.columns else "week_start"
    period_label = "万元/月" if data_mode == "real" else "万元/周"

    # ─── 模型训练 / 加载 ──────────────────────────────────────────────────────
    model: MMMModel = st.session_state.get("mmm_model")
    if data_mode in ("real", "weekly"):
        _default_dv = "dv_first_loan_amt" if "dv_first_loan_amt" in df.columns else "dv_total_loan_amt"
        dv_col = st.session_state.get("_weekly_dv_col", _default_dv) if data_mode == "weekly" else _default_dv
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
                _label = "MCMC 采样" if engine_type == "bayesian" else "Optuna 优化"
                progress_bar.progress(min(p, 1.0), text=f"{_label}进度：{p*100:.0f}%")

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

                    import plotly.graph_objects as go
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

            # Save trained model to registry
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
        auto = load_model()
        if auto and auto.is_fitted:
            model = auto
            st.session_state["mmm_model"] = model

    return model, df, dv_col, data_mode, ch_names, time_col, period_label
