"""
MMM 洞察页（Robyn 风格 Python 实现）
重构版：增加推导逻辑说明、数据来源、结果解读折叠模块、引导下一步
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

from utils.data_loader import load_mock_data, CHANNEL_NAMES, CHANNEL_KEYS
from engine.mmm_engine import MMMTrainer, MMMModel, save_model, load_model, hill_saturation, geometric_adstock, weibull_adstock


# ─── 样式 ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.guide-card {
    background: #eff6ff;
    border-left: 4px solid #3b82f6;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 8px 0;
}
.insight-highlight {
    background: #f0fdf4;
    border: 1px solid #86efac;
    border-radius: 6px;
    padding: 10px 14px;
    margin: 4px 0;
    font-size: 0.9em;
}
.warn-highlight {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 6px;
    padding: 10px 14px;
    margin: 4px 0;
    font-size: 0.9em;
}
</style>
""", unsafe_allow_html=True)

# ─── 页面标题与定位说明 ────────────────────────────────────────────────────────
st.title("🧪 MMM 洞察（Robyn 风格）")
st.markdown("""
> **本页面的作用**：量化每个渠道的真实效率，输出预算优化建议，为「预算调整」提供数据支撑。
> 
> **在决策链路中的位置**：数据检查 → **MMM 洞察（当前）** → 预算调整 → 方案对比 → 结果联动
""")

# 模型原理说明（折叠）
with st.expander("📖 MMM 是什么？本页面如何计算？（推导逻辑详解，点击展开）", expanded=False):
    st.markdown("""
    #### MMM（Marketing Mix Modeling，营销组合模型）原理

    MMM 的核心问题：**在多渠道同时投放时，如何区分每个渠道对业务结果的独立贡献？**

    ##### Step 1：Adstock 衰减变换（解决"滞后效应"）
    广告投放的效果不会在当周立即消失，而是会延续到未来几周（"余热效应"）。
    
    - **几何衰减（Geometric）**：`x_t' = x_t + θ × x_{t-1}'`
      - θ 越大（接近1），滞后效应越强（广告效果持续更久）
      - θ 越小（接近0），效果几乎只在当周体现
    - **Weibull PDF（Robyn 默认）**：使用 Weibull 分布权重对历史花费加权求和，更灵活

    ##### Step 2：Hill 饱和曲线变换（解决"边际递减"）
    花费越多，单位花费带来的效果越低（投放饱和）。
    
    `f(x) = x^α / (x^α + γ^α)`
    - α > 1：S 形曲线（低花费时效果慢，中等花费时快速增长，高花费时趋于饱和）
    - α < 1：凹形曲线（一开始效果好，但很快递减）
    - γ：半饱和点，当 x = γ 时响应值 = 0.5（归一化后）

    ##### Step 3：Ridge 回归拟合（估计各渠道贡献权重）
    `借款金额 = β₀ + β₁×变换后花费₁ + β₂×变换后花费₂ + ... + 控制变量`
    - 非负约束：媒体渠道的 β 系数强制 ≥ 0（花越多不可能带来负效果）
    - Ridge 正则化：防止多重共线性导致系数不稳定

    ##### Step 4：Optuna 贝叶斯超参数优化（找最优 Adstock 和饱和参数）
    对每个渠道的 θ、α、γ 参数进行搜索，目标函数：
    `最小化：NRMSE（预测误差）+ 0.3 × DecompRSSD（贡献分布合理性）`
    - NRMSE：归一化均方根误差，衡量预测准确度
    - DecompRSSD：渠道贡献分布 vs 花费分布的差异，防止模型把所有贡献归到一个渠道

    ##### 数据来源
    | 数据 | 来源 | 用途 |
    |---|---|---|
    | 各渠道周度花费 | Mock 数据（2024-01-01 ~ 2025-12-22，104周） | 自变量（媒体变量） |
    | 借款金额（loan_amt / dv_t0_loan_amt） | Mock 数据 | 因变量（业务结果） |
    | 节假日天数（holiday_days） | Mock 数据 | 控制变量 |
    | LPR 一年期（lpr_1y） | Mock 数据（模拟央行数据） | 宏观控制变量 |
    | CPI 同比（cpi_yoy） | Mock 数据（模拟国家统计局数据） | 宏观控制变量 |

    ##### 模型评估指标说明
    | 指标 | 含义 | 参考标准 |
    |---|---|---|
    | **R²** | 拟合优度，模型解释了多少因变量的方差 | >0.7 可接受，>0.85 良好 |
    | **NRMSE** | 归一化均方根误差，预测误差相对大小 | <0.3 良好，<0.5 可接受 |
    | **DecompRSSD** | 贡献分布 vs 花费分布差异 | 越小越均衡，<0.3 较好 |
    """)

# ─── 加载数据 ──────────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    df = load_mock_data()
    st.session_state["df"] = df
else:
    df = st.session_state["df"]

# ─── 侧边栏：训练配置 ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 模型配置")
    adstock_type = st.selectbox(
        "Adstock 类型",
        ["geometric", "weibull"],
        help="geometric：几何衰减（简单快速）\nweibull：Weibull PDF（Robyn 默认，更灵活）",
    )
    n_trials = st.slider("优化迭代次数", 100, 500, 200, step=50,
                         help="越多越精准，但训练时间更长。建议首次用200，正式使用300+")
    dv_col = st.selectbox(
        "因变量",
        ["dv_t0_loan_amt", "loan_amt", "loan_cnt"],
        help="建议使用 dv_t0_loan_amt（T0 借款金额，即当周直接产生的借款）",
    )

    st.divider()
    st.header("📅 训练数据范围")
    all_weeks = df["week_start"].dt.strftime("%Y-%m-%d").tolist()
    train_start = st.selectbox("起始周", all_weeks, index=0)
    train_end   = st.selectbox("截止周", all_weeks, index=len(all_weeks) - 1)

    st.divider()
    use_cached = st.checkbox("使用已缓存模型", value=True,
                             help="若已有训练好的模型，直接加载跳过训练")
    if st.button("🗑️ 清除缓存模型", help="清除后下次运行将重新训练模型"):
        for _k in ["mmm_model", "mmm_optimal_budget", "mmm_budget_suggestion", "mmm_opt_total"]:
            st.session_state.pop(_k, None)
        st.success("缓存已清除，下次运行将重新训练模型。")

    st.divider()
    st.markdown("""
    **💡 训练建议**
    - 首次使用：点击「加载已有模型」（已预训练）
    - 调整参数后：点击「开始训练」重新拟合
    - 迭代次数 ≥ 300 时结果更稳定
    """)

# ─── 数据过滤 ──────────────────────────────────────────────────────────────────
mask = (df["week_start"].dt.strftime("%Y-%m-%d") >= train_start) & \
       (df["week_start"].dt.strftime("%Y-%m-%d") <= train_end)
df_train = df[mask].copy()

if pd.to_datetime(train_start) > pd.to_datetime(train_end):
    st.error("训练起始周不能晚于截止周，请先修正训练范围。")
    st.stop()

if df_train.empty:
    st.error("当前训练范围没有可用数据，请重新选择训练起止周。")
    st.stop()

st.info(f"📅 训练数据：**{len(df_train)} 周**（{train_start} ~ {train_end}）| 因变量：`{dv_col}` | Adstock：`{adstock_type}`")

with st.expander("📖 为什么要选择训练数据范围？", expanded=False):
    st.markdown("""
    - **排除异常周次**：大促节假日（如双11、春节）会导致花费和效果异常，影响模型参数估计
    - **数据检查页已标记**：建议先在「数据检查」页确认异常周次，再回来调整训练范围
    - **当前使用全量数据**：104周（2024-01-01 ~ 2025-12-22），已包含节假日控制变量
    """)

# ─── 模型训练 ──────────────────────────────────────────────────────────────────
st.subheader("🚀 模型训练")

col_btn1, col_btn2 = st.columns([1, 3])
train_btn = col_btn1.button("▶️ 开始训练", type="primary", use_container_width=True)
load_btn  = col_btn2.button("📂 加载已有模型", use_container_width=True)

model: MMMModel = st.session_state.get("mmm_model")

if load_btn or (use_cached and model is None):
    cached = st.session_state.get("mmm_model") or load_model()
    if cached and cached.is_fitted:
        model = cached
        st.session_state["mmm_model"] = model
        st.success(f"✅ 模型已加载 | R²={model.r_squared:.4f} | NRMSE={model.nrmse:.4f} | DecompRSSD={model.decomp_rssd:.4f}")
    else:
        st.warning("未找到已有模型，请先训练。")

if train_btn:
    if dv_col not in df_train.columns:
        st.error(f"因变量列 `{dv_col}` 不存在，请检查数据。")
    else:
        st.session_state.pop("mmm_optimal_budget", None)
        st.session_state.pop("mmm_budget_suggestion", None)
        st.session_state.pop("mmm_opt_total", None)
        progress_bar = st.progress(0.0, text="正在训练 MMM 模型...")
        def update_progress(p):
            progress_bar.progress(min(p, 1.0), text=f"贝叶斯优化进度：{p*100:.0f}%")
        with st.spinner(f"贝叶斯优化中（{n_trials} 次迭代），请稍候..."):
            trainer = MMMTrainer(df_train, dv_col=dv_col,
                                 n_trials=n_trials, adstock_type=adstock_type)
            model = trainer.fit(progress_callback=update_progress)
            save_model(model)
            st.session_state["mmm_model"] = model
        progress_bar.progress(1.0, text="训练完成！")
        st.success(f"✅ 训练完成 | R²={model.r_squared:.4f} | NRMSE={model.nrmse:.4f} | DecompRSSD={model.decomp_rssd:.4f}")

if model is None:
    st.info("请先训练模型或加载已有模型。")
    st.markdown("""
    <div class="guide-card">
        <b>→ 建议操作</b>：点击上方「📂 加载已有模型」直接使用预训练结果，或点击「▶️ 开始训练」重新拟合。
    </div>
    """, unsafe_allow_html=True)
    st.stop()

st.divider()

# ─── Tab 布局 ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 拟合效果", "🍰 渠道贡献", "📉 响应曲线", "💡 预算优化建议", "🔗 与规则层对比"
])

# ══════════════════════════════════════════════════════════════════════════════
# Tab1：拟合效果
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("模型拟合效果")

    with st.expander("📖 如何解读这三个指标？", expanded=False):
        st.markdown("""
        | 指标 | 含义 | 参考标准 | 本模型 |
        |---|---|---|---|
        | **R²（拟合优度）** | 模型解释了因变量多少比例的变化（0~1） | >0.7 可接受，>0.85 良好 | {r2:.4f} |
        | **NRMSE（归一化误差）** | 预测误差相对大小（越小越好） | <0.3 良好，<0.5 可接受 | {nrmse:.4f} |
        | **Decomp RSSD** | 渠道贡献分布 vs 花费分布的差异（越小越均衡） | <0.3 较好 | {rssd:.4f} |
        
        > **注意**：R² 较低（如 0.6~0.8）在 MMM 中是正常的，因为业务结果受大量不可观测因素影响（竞争对手、产品变化等）。
        > 重要的是**参数方向和量级是否合理**，而非追求极高的 R²。
        """.format(r2=model.r_squared, nrmse=model.nrmse, rssd=model.decomp_rssd))

    m1, m2, m3 = st.columns(3)
    m1.metric("R²（拟合优度）", f"{model.r_squared:.4f}",
              delta="良好" if model.r_squared > 0.7 else "偏低",
              delta_color="normal" if model.r_squared > 0.7 else "inverse",
              help="越接近 1 越好，>0.7 为可接受")
    m2.metric("NRMSE（归一化误差）", f"{model.nrmse:.4f}",
              delta="良好" if model.nrmse < 0.5 else "偏高",
              delta_color="normal" if model.nrmse < 0.5 else "inverse",
              help="越小越好，<0.3 为良好，<0.5 为可接受")
    m3.metric("Decomp RSSD", f"{model.decomp_rssd:.4f}",
              delta="均衡" if model.decomp_rssd < 0.35 else "偏高",
              delta_color="normal" if model.decomp_rssd < 0.35 else "inverse",
              help="渠道贡献分布与花费分布的差异，越小越均衡")

    # 实际 vs 预测
    y_pred   = model.predict(df_train)
    y_actual = df_train[dv_col].values

    fig_fit = go.Figure()
    fig_fit.add_trace(go.Scatter(
        x=df_train["week_start"], y=y_actual,
        mode="lines", name="实际值",
        line=dict(color="#1976D2", width=2),
    ))
    fig_fit.add_trace(go.Scatter(
        x=df_train["week_start"], y=y_pred,
        mode="lines", name="预测值",
        line=dict(color="#FF7043", width=2, dash="dot"),
    ))
    fig_fit.update_layout(
        title="实际值 vs 预测值（借款金额，万元）",
        xaxis_title="周次", yaxis_title="借款金额（万元）",
        height=380, hovermode="x unified",
    )
    st.plotly_chart(fig_fit, use_container_width=True)

    with st.expander("📖 如何解读实际 vs 预测图？", expanded=False):
        st.markdown("""
        - **两条线越接近**：模型拟合越好，预测越准确
        - **系统性偏差**（预测值持续高于或低于实际值）：可能存在未纳入的结构性因素（如产品策略调整）
        - **局部大偏差**：通常对应大促、节假日等异常周次，可在数据检查页标记后排除
        - **预测值用途**：主要用于反事实分析（"如果不投这个渠道，会怎样"），而非精确预测
        """)

    # 残差图
    residuals = y_actual - y_pred
    fig_resid = go.Figure()
    fig_resid.add_trace(go.Scatter(
        x=df_train["week_start"], y=residuals,
        mode="lines+markers", name="残差",
        line=dict(color="#9C27B0", width=1.5),
        marker=dict(size=4),
    ))
    fig_resid.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_resid.update_layout(
        title="残差图（实际 - 预测）",
        xaxis_title="周次", yaxis_title="残差（万元）",
        height=280,
    )
    st.plotly_chart(fig_resid, use_container_width=True)

    with st.expander("📖 如何解读残差图？", expanded=False):
        st.markdown("""
        - **残差随机分布在0附近**：模型无系统性偏差，拟合良好
        - **残差有明显规律**（如周期性波动）：说明存在未被捕捉的季节性因素
        - **某些周残差特别大**：对应异常周次（大促、数据质量问题），可考虑排除
        """)

    # 渠道参数表
    st.subheader("📋 渠道参数详情")
    param_rows = []
    for ch, cp in model.channel_params.items():
        param_rows.append({
            "渠道": CHANNEL_NAMES.get(ch, ch),
            "Adstock 类型": cp.adstock_type,
            "衰减参数": f"θ={cp.theta:.3f}" if cp.adstock_type == "geometric"
                        else f"shape={cp.weibull_shape:.2f}, scale={cp.weibull_scale:.2f}",
            "Hill α": round(cp.alpha, 3),
            "Hill γ（半饱和点）": round(cp.gamma, 3),
            "β（贡献系数）": round(cp.beta, 6),
        })
    st.dataframe(pd.DataFrame(param_rows), use_container_width=True, hide_index=True)

    with st.expander("📖 如何解读渠道参数表？", expanded=False):
        st.markdown("""
        | 参数 | 含义 | 解读 |
        |---|---|---|
        | **θ（衰减率）** | 几何 Adstock 的衰减速度 | θ=0.5 表示上周效果本周还剩 50%；θ 越大，广告"余热"越持久 |
        | **Hill α** | 饱和曲线斜率 | α>2：S 形曲线，中等花费时效果增速最快；α<1：一开始效果好但很快递减 |
        | **Hill γ** | 半饱和点（归一化后） | γ=0.5 表示当花费达到历史最大值的 50% 时，效果已达到最大值的 50% |
        | **β（贡献系数）** | 该渠道对因变量的贡献权重 | β 越大，该渠道贡献越大；β=0 表示模型认为该渠道无显著贡献 |
        
        > **注意**：β=0 的渠道（如腾讯视频号）不一定真的没效果，可能是因为与其他渠道高度相关（多重共线性），
        > 或历史数据中该渠道花费变化不够大，导致模型无法识别其独立贡献。
        """)

    st.markdown("""
    <div class="guide-card">
        <b>→ 下一步</b>：查看「🍰 渠道贡献」Tab，了解各渠道对总借款金额的贡献比例和 ROI。
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab2：渠道贡献分解
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("渠道贡献分解")

    with st.expander("📖 渠道贡献是怎么算出来的？", expanded=False):
        st.markdown("""
        **计算方法（反事实分析）**：
        
        对于每个渠道 i，其贡献 = 模型预测值（含该渠道）- 模型预测值（该渠道花费=0）
        
        即：**"如果这个渠道不投放，会少多少借款金额"**
        
        这是 MMM 的核心输出，也是预算决策的主要依据。
        
        **数据来源**：基于训练数据（{n}周），使用已训练的 MMM 模型参数计算。
        
        **ROI 计算**：ROI = 渠道贡献量（万元）/ 渠道花费（万元）
        - ROI > 1：每投1万元，带来超过1万元的借款金额增量（正向贡献）
        - ROI < 1：效率偏低，但注意这是借款金额口径，不是利润口径
        """.format(n=len(df_train)))

    contributions = model.channel_contribution(df_train)
    ch_total_contrib = {ch: float(v.sum()) for ch, v in contributions.items()}
    ch_total_spend   = {ch: float(df_train[f"{ch}_spend"].sum())
                        for ch in model._channel_keys if f"{ch}_spend" in df_train.columns}

    total_contrib = sum(ch_total_contrib.values())
    total_spend   = sum(ch_total_spend.values())

    contrib_df = pd.DataFrame({
        "渠道": [CHANNEL_NAMES.get(ch, ch) for ch in ch_total_contrib],
        "贡献量（万元）": [round(v, 1) for v in ch_total_contrib.values()],
        "贡献占比（%）": [round(v / total_contrib * 100, 1) if total_contrib > 0 else 0
                         for v in ch_total_contrib.values()],
        "花费（万元）": [round(ch_total_spend.get(ch, 0), 1) for ch in ch_total_contrib],
        "花费占比（%）": [round(ch_total_spend.get(ch, 0) / total_spend * 100, 1) if total_spend > 0 else 0
                         for ch in ch_total_contrib],
    })
    contrib_df["ROI（贡献/花费）"] = (
        contrib_df["贡献量（万元）"] / contrib_df["花费（万元）"].replace(0, np.nan)
    ).round(3)
    contrib_df["效率评级"] = contrib_df["ROI（贡献/花费）"].apply(
        lambda x: "🔥 高效" if x > 2 else ("✅ 正常" if x > 0.5 else ("⚠️ 偏低" if x > 0 else "❓ 无贡献"))
    )

    st.dataframe(contrib_df, use_container_width=True, hide_index=True,
                 column_config={
                     "贡献占比（%）": st.column_config.ProgressColumn("贡献占比（%）", min_value=0, max_value=100),
                     "花费占比（%）": st.column_config.ProgressColumn("花费占比（%）", min_value=0, max_value=100),
                 })

    with st.expander("📖 如何解读这张渠道贡献表？", expanded=False):
        st.markdown("""
        **核心解读逻辑**：比较「贡献占比」和「花费占比」的差距
        
        | 情况 | 含义 | 建议 |
        |---|---|---|
        | 贡献占比 **>** 花费占比 | 该渠道效率高，花少得多 | 考虑**加大投入** |
        | 贡献占比 **<** 花费占比 | 该渠道效率低，花多得少 | 考虑**减少投入**或优化素材/定向 |
        | 贡献占比 **≈** 花费占比 | 效率与投入基本匹配 | 维持现状，关注饱和度 |
        | 贡献占比 = 0 | 模型未识别到显著贡献 | 检查数据质量，或该渠道与其他渠道高度相关 |
        
        **ROI 效率评级标准**（借款金额口径）：
        - 🔥 高效（ROI > 2）：每万元花费带来超过2万元借款增量
        - ✅ 正常（0.5 < ROI ≤ 2）：效率在合理范围内
        - ⚠️ 偏低（0 < ROI ≤ 0.5）：效率偏低，需关注
        - ❓ 无贡献（ROI = 0）：模型未识别到贡献，需进一步分析
        """)

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        fig_contrib_pie = px.pie(
            contrib_df, values="贡献占比（%）", names="渠道",
            title="渠道贡献占比（MMM 分解）",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.35,
        )
        fig_contrib_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_contrib_pie.update_layout(height=380, showlegend=False)
        st.plotly_chart(fig_contrib_pie, use_container_width=True)

    with col_c2:
        fig_contrib_vs = go.Figure()
        fig_contrib_vs.add_trace(go.Bar(
            x=contrib_df["渠道"], y=contrib_df["贡献占比（%）"],
            name="贡献占比", marker_color="#1976D2",
        ))
        fig_contrib_vs.add_trace(go.Bar(
            x=contrib_df["渠道"], y=contrib_df["花费占比（%）"],
            name="花费占比", marker_color="#FF7043",
        ))
        fig_contrib_vs.update_layout(
            title="贡献占比 vs 花费占比（差距=效率信号）",
            barmode="group", height=380,
            yaxis_title="%",
        )
        st.plotly_chart(fig_contrib_vs, use_container_width=True)

    # 周度贡献堆叠图
    st.subheader("周度渠道贡献趋势")
    fig_contrib_stack = go.Figure()
    colors = px.colors.qualitative.Set2
    for i, (ch, contrib_arr) in enumerate(contributions.items()):
        fig_contrib_stack.add_trace(go.Scatter(
            x=df_train["week_start"], y=contrib_arr,
            mode="lines", name=CHANNEL_NAMES.get(ch, ch),
            stackgroup="one",
            line=dict(width=0.5),
            fillcolor=colors[i % len(colors)],
        ))
    fig_contrib_stack.update_layout(
        title="各渠道周度贡献（万元，堆叠）",
        xaxis_title="周次", yaxis_title="贡献（万元）",
        height=380, hovermode="x unified",
    )
    st.plotly_chart(fig_contrib_stack, use_container_width=True)

    with st.expander("📖 如何解读周度贡献趋势图？", expanded=False):
        st.markdown("""
        - **堆叠面积**：代表该周所有渠道的总贡献量（≈ 模型预测的借款金额）
        - **各色块高度**：该渠道在该周的贡献量
        - **季节性波动**：可观察哪些渠道在特定时期贡献更大（如节假日前后）
        - **注意**：总贡献量可能低于实际借款金额，差值为截距项（基础量，不依赖媒体投放的自然流量）
        """)

    st.markdown("""
    <div class="guide-card">
        <b>→ 下一步</b>：查看「📉 响应曲线」Tab，了解各渠道的饱和度和边际效益，
        判断哪些渠道还有加投空间，哪些已经接近饱和。
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab3：边际响应曲线
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("渠道边际响应曲线（饱和效应）")

    with st.expander("📖 响应曲线是什么？如何计算？", expanded=False):
        st.markdown("""
        **响应曲线（Response Curve）** 展示：当某渠道花费从 0 增加到 X 万元时，
        预测带来的借款金额增量是多少。
        
        **计算方法**：
        1. 固定其他渠道花费为历史均值
        2. 对目标渠道的花费从 0 到 3倍历史均值进行扫描
        3. 对每个花费值，通过 MMM 模型（Adstock + Hill + β）计算预测贡献
        
        **饱和点估计**：当边际响应（曲线斜率）下降到初始斜率的 20% 时，认为接近饱和。
        
        **Adstock 衰减曲线**：展示单次投放（冲激）的效果如何随时间衰减，
        衰减越慢（θ 越大）说明广告"余热"越持久。
        """)

    df_last = df_train.tail(4)
    fig_response = go.Figure()
    colors_resp = px.colors.qualitative.Plotly

    saturation_points = {}
    for i, ch in enumerate(model._channel_keys):
        hist_mean = df_train[f"{ch}_spend"].mean()
        spend_range = np.linspace(0, hist_mean * 3, 100)
        response = model.marginal_response(ch, spend_range, df_last.mean())

        if len(response) > 1:
            marginal = np.gradient(response, spend_range)
            max_marginal = marginal[1] if marginal[1] > 0 else 1e-9
            sat_idx = np.argmax(marginal < max_marginal * 0.2)
            sat_spend = spend_range[sat_idx] if sat_idx > 0 else spend_range[-1]
            saturation_points[ch] = sat_spend
        else:
            saturation_points[ch] = hist_mean

        fig_response.add_trace(go.Scatter(
            x=spend_range, y=response,
            mode="lines", name=CHANNEL_NAMES.get(ch, ch),
            line=dict(color=colors_resp[i % len(colors_resp)], width=2),
        ))
        fig_response.add_vline(
            x=hist_mean, line_dash="dot",
            line_color=colors_resp[i % len(colors_resp)],
            opacity=0.4,
            annotation_text=f"{CHANNEL_NAMES.get(ch, ch)[:4]}均值",
            annotation_position="top",
        )

    fig_response.update_layout(
        title="各渠道响应曲线（花费 vs 预测借款金额增量）| 虚线=当前均值花费",
        xaxis_title="渠道花费（万元/周）",
        yaxis_title="预测借款金额增量（万元）",
        height=450, hovermode="x unified",
    )
    st.plotly_chart(fig_response, use_container_width=True)

    with st.expander("📖 如何解读响应曲线？", expanded=False):
        st.markdown("""
        - **曲线越陡**：该渠道当前花费水平下边际效益越高，值得加投
        - **曲线趋于平缓**：接近饱和，继续加投边际效益递减
        - **虚线位置**：当前历史均值花费所在位置
          - 虚线在曲线陡峭段：还有加投空间
          - 虚线在曲线平缓段：已接近饱和，建议控制增量
        - **曲线形状**：
          - S 形（先慢后快再慢）：低花费时效果慢，中等花费时快速增长，高花费时趋于饱和
          - 凹形（一开始快，越来越慢）：边际效益从一开始就递减
        """)

    # 饱和点汇总
    st.subheader("📍 渠道饱和度分析")
    sat_df = pd.DataFrame({
        "渠道": [CHANNEL_NAMES.get(ch, ch) for ch in saturation_points],
        "估计饱和点（万元/周）": [round(v, 1) for v in saturation_points.values()],
        "当前均值花费（万元/周）": [round(df_train[f"{ch}_spend"].mean(), 1)
                                    for ch in saturation_points],
    })
    sat_df["距饱和点空间（万元）"] = (sat_df["估计饱和点（万元/周）"] -
                                       sat_df["当前均值花费（万元/周）"]).round(1)
    sat_df["饱和度状态"] = sat_df["距饱和点空间（万元）"].apply(
        lambda x: "⚠️ 接近饱和（建议控制增量）" if x < 50
        else ("✅ 有较大增长空间" if x > 150 else "🔶 适中（可小幅加投）")
    )
    st.dataframe(sat_df, use_container_width=True, hide_index=True)

    with st.expander("📖 如何解读饱和度分析表？", expanded=False):
        st.markdown("""
        - **估计饱和点**：基于响应曲线，当边际效益下降到初始值 20% 时对应的花费水平
        - **距饱和点空间**：= 饱和点 - 当前均值花费
          - 正值：还有加投空间
          - 负值：已超过饱和点，继续加投边际效益极低
        - **使用建议**：
          - 接近饱和的渠道：不建议大幅加投，可将预算转移到有空间的渠道
          - 有增长空间的渠道：可考虑加投，但需结合 ROI 综合判断
        
        > **注意**：饱和点估计基于历史数据和模型参数，实际饱和点可能因素材质量、定向策略等因素而变化。
        """)

    # Adstock 衰减可视化
    st.subheader("⏱️ Adstock 滞后效应（各渠道衰减曲线）")
    fig_adstock = go.Figure()
    impulse = np.zeros(12)
    impulse[0] = 1.0

    for i, (ch, cp) in enumerate(model.channel_params.items()):
        if cp.adstock_type == "geometric":
            decay = geometric_adstock(impulse, cp.theta)
        else:
            decay = weibull_adstock(impulse, cp.weibull_shape, cp.weibull_scale)
        decay_norm = decay / decay.max() if decay.max() > 0 else decay

        fig_adstock.add_trace(go.Scatter(
            x=list(range(12)), y=decay_norm,
            mode="lines+markers", name=CHANNEL_NAMES.get(ch, ch),
            line=dict(color=colors_resp[i % len(colors_resp)], width=2),
            marker=dict(size=5),
        ))

    fig_adstock.update_layout(
        title="各渠道 Adstock 衰减曲线（归一化）| 第0周投放100万，后续周的残留效果",
        xaxis_title="滞后周数（0=投放当周）",
        yaxis_title="相对效果（1=当周全量）",
        height=360, hovermode="x unified",
    )
    st.plotly_chart(fig_adstock, use_container_width=True)

    with st.expander("📖 如何解读 Adstock 衰减曲线？", expanded=False):
        st.markdown("""
        - **横轴**：投放后的第几周（0=投放当周）
        - **纵轴**：相对效果（1=当周全量效果）
        - **衰减快**（曲线陡降）：广告效果主要集中在当周，"余热"短
        - **衰减慢**（曲线平缓）：广告效果持续多周，"品牌效应"更强
        - **实际意义**：
          - 如果某渠道衰减慢（θ 大），本周削减预算的影响会在未来几周才完全体现
          - 如果某渠道衰减快（θ 小），本周增加预算当周就能看到效果
        """)

    st.markdown("""
    <div class="guide-card">
        <b>→ 下一步</b>：查看「💡 预算优化建议」Tab，获取基于等边际原则的最优预算分配方案，
        作为「预算调整」页面的参考锚点。
    </div>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# Tab4：预算优化建议
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("💡 预算再分配建议（等边际原则）")

    with st.expander("📖 预算优化是怎么算出来的？", expanded=False):
        st.markdown("""
        **等边际原则（Equal Marginal Principle）**：
        
        最优预算分配的条件是：**每个渠道最后一元花费带来的边际效益相等**。
        
        如果渠道 A 的边际效益 > 渠道 B，应将预算从 B 转移到 A，直到两者边际效益相等。
        
        **计算方法**：
        1. 给定总预算约束（可自定义）
        2. 使用 Optuna 贝叶斯优化，搜索各渠道预算比例
        3. 目标函数：最大化 MMM 模型预测的总借款金额
        4. 约束：各渠道预算比例之和 = 1，每渠道占比在 2%~60% 之间
        
        **重要说明**：
        - 优化结果是**参考建议**，不是强制执行方案
        - 实际预算调整需结合业务判断（渠道容量、素材储备、运营能力等）
        - 建议将优化结果作为「预算调整」页面的**起点**，再手动微调
        """)

    current_total = float(df_train[[f"{ch}_spend" for ch in model._channel_keys
                                    if f"{ch}_spend" in df_train.columns]].mean().sum())

    col_opt1, col_opt2 = st.columns([2, 1])
    with col_opt1:
        opt_total = st.number_input(
            "优化总预算（万元/周）",
            min_value=100.0, max_value=10000.0,
            value=round(current_total, 0),
            step=50.0,
            help=f"当前历史均值总预算约 {current_total:.0f} 万元/周",
        )
    with col_opt2:
        st.metric("当前历史均值总预算", f"{current_total:.0f} 万元/周",
                  delta=f"{opt_total - current_total:+.0f} 万元")

    opt_btn = st.button("🔍 运行预算优化（约 20 秒）", type="primary")

    if opt_btn:
        with st.spinner("正在运行等边际优化（Optuna 200次迭代）..."):
            optimal = model.budget_optimization(opt_total, df_train, n_points=50)
            st.session_state["mmm_optimal_budget"] = optimal
            st.success("✅ 优化完成！以下为建议分配方案。")

    if "mmm_optimal_budget" in st.session_state:
        if st.session_state.get("mmm_opt_total") != opt_total:
            st.info("当前展示的是上一次预算优化结果；如果已修改优化总预算，请重新点击“运行预算优化”。")
        optimal = st.session_state["mmm_optimal_budget"]

        current_spends = {ch: round(df_train[f"{ch}_spend"].mean(), 1)
                          for ch in model._channel_keys
                          if f"{ch}_spend" in df_train.columns}

        opt_df = pd.DataFrame({
            "渠道": [CHANNEL_NAMES.get(ch, ch) for ch in optimal],
            "当前均值（万元）": [current_spends.get(ch, 0) for ch in optimal],
            "MMM 优化建议（万元）": [round(v, 1) for v in optimal.values()],
        })
        opt_df["变化（万元）"] = (opt_df["MMM 优化建议（万元）"] - opt_df["当前均值（万元）"]).round(1)
        opt_df["变化率（%）"] = (opt_df["变化（万元）"] / opt_df["当前均值（万元）"].replace(0, np.nan) * 100).round(1)
        opt_df["操作建议"] = opt_df["变化率（%）"].apply(
            lambda x: "⬆️ 建议加投" if x > 10 else ("⬇️ 建议减投" if x < -10 else "➡️ 维持现状")
        )

        st.dataframe(opt_df, use_container_width=True, hide_index=True,
                     column_config={
                         "变化率（%）": st.column_config.NumberColumn("变化率（%）", format="%.1f%%"),
                     })

        with st.expander("📖 如何使用这份优化建议？", expanded=False):
            st.markdown("""
            **这份建议的含义**：
            - 在总预算 {total:.0f} 万元/周的约束下，按此分配可最大化预测借款金额
            - **⬆️ 建议加投**：该渠道当前花费低于最优水平，边际效益较高
            - **⬇️ 建议减投**：该渠道当前花费高于最优水平，边际效益已递减
            - **➡️ 维持现状**：当前花费接近最优水平
            
            **使用步骤**：
            1. 参考此建议，前往「预算调整」页面调整各渠道花费
            2. 在「预算调整」页面可以看到 MMM 建议值作为参考线
            3. 结合业务判断（渠道容量、素材储备等）进行微调
            4. 在「方案对比」页面对比调整前后的效果
            
            > **注意**：优化结果基于历史数据和模型假设，实际效果可能因执行质量、竞争环境等因素而有所不同。
            """.format(total=opt_total))

        col_o1, col_o2 = st.columns(2)
        with col_o1:
            fig_opt_bar = go.Figure()
            fig_opt_bar.add_trace(go.Bar(
                x=opt_df["渠道"], y=opt_df["当前均值（万元）"],
                name="当前均值", marker_color="#90CAF9",
            ))
            fig_opt_bar.add_trace(go.Bar(
                x=opt_df["渠道"], y=opt_df["MMM 优化建议（万元）"],
                name="MMM 优化建议", marker_color="#1976D2",
            ))
            fig_opt_bar.update_layout(
                title="当前均值 vs MMM 优化建议（万元/周）",
                barmode="group", height=360,
                yaxis_title="花费（万元/周）",
            )
            st.plotly_chart(fig_opt_bar, use_container_width=True)

        with col_o2:
            fig_opt_pie = px.pie(
                values=list(optimal.values()),
                names=[CHANNEL_NAMES.get(ch, ch) for ch in optimal],
                title="MMM 优化后渠道占比",
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.35,
            )
            fig_opt_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_opt_pie.update_layout(height=360, showlegend=False)
            st.plotly_chart(fig_opt_pie, use_container_width=True)

        # 存入 session_state 供预算调整页使用
        st.session_state["mmm_budget_suggestion"] = optimal
        st.session_state["mmm_opt_total"] = opt_total

        st.markdown("""
        <div class="guide-card">
            <b>→ 下一步</b>：前往「<b>预算调整</b>」页面，MMM 优化建议将作为参考线显示，
            帮助你在手动调整时有量化依据。
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("点击「运行预算优化」按钮获取 MMM 最优分配建议。")

# ══════════════════════════════════════════════════════════════════════════════
# Tab5：与规则层对比
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("🔗 MMM 层 vs 规则层结果对比")

    with st.expander("📖 规则层 vs MMM 层：有什么区别？", expanded=False):
        st.markdown("""
        | 对比维度 | 规则层 | MMM 层 |
        |---|---|---|
        | **计算方式** | 基于历史均值系数的线性外推 | Adstock + Hill 饱和曲线的非线性建模 |
        | **速度** | 实时（毫秒级） | 需要训练（分钟级） |
        | **精度** | 较低，忽略滞后效应和饱和效应 | 较高，考虑媒体响应的真实规律 |
        | **可解释性** | 强（系数直观） | 中等（参数有物理意义但较复杂） |
        | **适用场景** | 快速预估、实时反馈 | 渠道效率分析、预算优化建议 |
        | **使用建议** | 在「预算调整」页面实时预览效果 | 在「MMM 洞察」页面获取优化建议 |
        
        **两层结果差异的含义**：
        - 差异小：两种方法对当前预算水平的预测一致，结论可信
        - 差异大：说明存在明显的滞后效应或饱和效应，规则层可能高估或低估效果
        """)

    from engine.rule_engine import RuleEngine, BudgetInput

    rule_engine = RuleEngine(df_train)
    default_spends = {ch: round(df_train[f"{ch}_spend"].mean(), 1)
                      for ch in CHANNEL_KEYS if f"{ch}_spend" in df_train.columns}

    rule_budget = BudgetInput(**{f"{ch}_spend": default_spends[ch] for ch in CHANNEL_KEYS
                                  if f"{ch}_spend" in df_train.columns})
    rule_result = rule_engine.simulate(rule_budget, "规则层基准")

    mmm_pred = model.predict(df_train.tail(1))
    mmm_loan_amt = float(mmm_pred[0]) if len(mmm_pred) > 0 else 0.0
    actual_loan_amt = float(df_train["loan_amt"].mean())

    compare_data = {
        "来源": ["历史实际（均值）", "规则层预测", "MMM 层预测（最近周）"],
        "借款金额（万元）": [
            round(actual_loan_amt, 1),
            round(rule_result.loan_amt, 1),
            round(mmm_loan_amt, 1),
        ],
        "说明": [
            "历史104周均值，作为基准参考",
            "基于历史比率系数的线性外推",
            "基于 MMM 模型对最近1周的预测",
        ],
    }
    compare_df = pd.DataFrame(compare_data)
    compare_df["vs 实际（%）"] = (
        (compare_df["借款金额（万元）"] - actual_loan_amt) / actual_loan_amt * 100
    ).round(1)

    st.dataframe(compare_df, use_container_width=True, hide_index=True)

    fig_compare = go.Figure(go.Bar(
        x=compare_data["来源"],
        y=compare_data["借款金额（万元）"],
        marker_color=["#90CAF9", "#1976D2", "#FF7043"],
        text=[f"{v:.1f}" for v in compare_data["借款金额（万元）"]],
        textposition="outside",
    ))
    fig_compare.update_layout(
        title="历史实际 vs 规则层 vs MMM 层（借款金额，万元）",
        yaxis_title="借款金额（万元）",
        height=360,
    )
    st.plotly_chart(fig_compare, use_container_width=True)

    st.markdown("""
    <div class="guide-card">
        <b>→ 下一步</b>：前往「<b>预算调整</b>」页面，参考 MMM 优化建议进行渠道预算分配，
        规则层将提供实时预测反馈。
    </div>
    """, unsafe_allow_html=True)
