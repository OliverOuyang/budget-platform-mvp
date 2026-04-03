"""
预算调整页 - 重构版
核心改进：
1. 嵌入 MMM 洞察面板作为决策参考（渠道 ROI、饱和度、优化建议）
2. 每个调整项旁边显示 MMM 建议值作为参考锚点
3. 增加推导逻辑说明和引导提示
4. 增加结果解读说明
"""
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from utils.data_loader import load_mock_data, CHANNEL_NAMES, CHANNEL_KEYS, METRIC_LABELS
from engine.rule_engine import RuleEngine, BudgetInput
from engine.mmm_engine import load_model, hill_saturation


def _sync_scaled_channel_spends(default_spends: dict) -> None:
    """Keep keyed channel inputs in sync with the quick total-scale control."""
    total_scale = float(st.session_state.get("mmm_total_scale", 1.0))
    for ch, hist_spend in default_spends.items():
        st.session_state[f"spend_{ch}"] = round(hist_spend * total_scale, 1)


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
.mmm-ref-card {
    background: #f0fdf4;
    border: 1px solid #86efac;
    border-radius: 6px;
    padding: 10px 14px;
    margin: 4px 0;
    font-size: 0.88em;
}
.warn-card {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    border-radius: 6px;
    padding: 10px 14px;
    margin: 4px 0;
}
</style>
""", unsafe_allow_html=True)

# ─── 页面标题 ─────────────────────────────────────────────────────────────────
st.title("💰 预算调整")
st.markdown("""
> **本页面的作用**：在 MMM 洞察的量化支撑下，手动分配各渠道预算，实时查看规则层预测结果。
> 
> **在决策链路中的位置**：数据检查 → MMM 洞察 → **预算调整（当前）** → 方案对比 → 结果联动
""")

with st.expander("📖 预算调整页面如何使用？推导逻辑是什么？（点击展开）", expanded=False):
    st.markdown("""
    #### 使用流程
    1. **查看左侧 MMM 参考面板**：了解各渠道的 ROI、饱和度和 MMM 优化建议值
    2. **调整渠道预算**：参考 MMM 建议，拖动滑块或输入数值
    3. **选择目标模式**：根据本期决策重点选择规模/成本/质量优先
    4. **查看实时预测**：规则层实时计算预测结果，观察 KPI 变化
    5. **确认保存**：满意后点击「保存当前方案」，进入方案对比页
    
    #### 两层预测的分工
    | 层次 | 用途 | 特点 |
    |---|---|---|
    | **规则层（本页实时预测）** | 快速反馈预算调整效果 | 基于历史比率系数，实时计算，精度较低 |
    | **MMM 层（左侧参考面板）** | 提供渠道效率量化依据 | 考虑滞后效应和饱和效应，精度较高，但需预先训练 |
    
    #### 规则层预测原理
    ```
    借款金额 = 总花费 × 历史均值（借款金额/总花费）× 目标模式系数
    CPS = 总花费 / 借款金额
    1-3授信率 = 历史均值 × 渠道质量加权系数
    FPD30+ = 历史均值 × 渠道风险加权系数
    ```
    历史均值基于训练数据（104周）计算，渠道质量/风险系数基于各渠道历史表现差异。
    """)

# ─── 加载数据 ─────────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    df = load_mock_data()
    st.session_state["df"] = df
else:
    df = st.session_state["df"]

engine = RuleEngine(df)
default_spends = {ch: round(df[f"{ch}_spend"].mean(), 1) for ch in CHANNEL_KEYS
                  if f"{ch}_spend" in df.columns}

# 历史统计
cps_mean   = float(round(df["cps_amt"].mean(), 4))
cps_max    = float(round(df["cps_amt"].max() * 2, 2))
qual_mean  = float(round(df["quality_a13_rate"].mean(), 4))
fpd_mean   = float(round(df["fpd30_plus_rate"].mean() * 1.2, 4))
fpd_max    = float(round(df["fpd30_plus_rate"].max() * 2, 4))
total_mean = float(round(df["total_spend"].mean(), 0))

# ─── 加载 MMM 模型（用于参考面板） ───────────────────────────────────────────
model = st.session_state.get("mmm_model") or load_model()
mmm_suggestion = st.session_state.get("mmm_budget_suggestion", {})

# 计算 MMM 渠道 ROI 和饱和度
mmm_roi = {}
mmm_saturation = {}
if model and model.is_fitted:
    contribs = model.channel_contribution(df)
    for ch in model._channel_keys:
        spend_col = f"{ch}_spend"
        if spend_col not in df.columns:
            continue
        total_spend_ch = df[spend_col].sum()
        total_contrib_ch = contribs.get(ch, np.zeros(len(df))).sum()
        mmm_roi[ch] = total_contrib_ch / total_spend_ch if total_spend_ch > 0 else 0

        params = model.channel_params.get(ch)
        if params:
            avg_spend = df[spend_col].mean()
            max_spend = df[spend_col].max() + 1e-9
            norm_spend = avg_spend / max_spend
            mmm_saturation[ch] = float(hill_saturation(np.array([norm_spend]), params.alpha, params.gamma)[0])

# ─── 侧边栏：目标模式 & 目标参数 ─────────────────────────────────────────────
with st.sidebar:
    st.header("🎯 目标模式")
    goal_mode = st.radio(
        "选择决策模式",
        ["规模优先", "成本优先", "质量优先"],
        help=(
            "规模优先：最大化借款金额，花费达到预算目标\n"
            "成本优先：降低 CPS，控制获客成本\n"
            "质量优先：提升 1-3授信率，优化客群质量"
        ),
    )

    with st.expander("📖 目标模式如何影响预测？", expanded=False):
        st.markdown("""
        目标模式影响规则层的**系数调整**：
        - **规模优先**：系数 × 1.05（适度放大规模预测）
        - **成本优先**：CPS 系数 × 0.95（预测成本更优）
        - **质量优先**：质量系数 × 1.05（预测质量更优）
        
        注意：这是规则层的简化处理，MMM 层不受目标模式影响。
        """)

    st.divider()
    st.header("📋 目标参数")

    budget_target = st.number_input(
        "预算目标（万元/周）",
        min_value=100.0, max_value=10000.0,
        value=total_mean, step=10.0,
        help="本期预算上限，用于目标达成判断",
    )
    cps_target = st.number_input(
        "CPS 目标（花费/借款金额）",
        min_value=0.001, max_value=max(cps_max, 100.0),
        value=cps_mean, step=0.01, format="%.4f",
        help=f"历史均值 CPS = {cps_mean:.4f}",
    )
    quality_target = st.number_input(
        "1-3授信率目标",
        min_value=0.05, max_value=0.95,
        value=min(max(qual_mean, 0.05), 0.95),
        step=0.005, format="%.4f",
        help=f"历史均值 1-3授信率 = {qual_mean:.4f}",
    )
    risk_threshold = st.number_input(
        "FPD30+ 风险阈值",
        min_value=0.001, max_value=max(fpd_max, 0.20),
        value=min(fpd_mean, 0.15),
        step=0.001, format="%.4f",
        help=f"历史均值 FPD30+ = {float(df['fpd30_plus_rate'].mean()):.4f}",
    )

    st.session_state["goal_mode"]      = goal_mode
    st.session_state["budget_target"]  = budget_target
    st.session_state["cps_target"]     = cps_target
    st.session_state["quality_target"] = quality_target
    st.session_state["risk_threshold"] = risk_threshold

# ─── MMM 参考面板（顶部横向展示） ────────────────────────────────────────────
st.subheader("🧪 MMM 洞察参考面板")

if not model or not model.is_fitted:
    st.markdown("""
    <div class="warn-card">
        ⚠️ <b>MMM 模型尚未训练</b>，无法显示渠道效率参考数据。<br>
        建议先前往「MMM 洞察」页面训练或加载模型，再回此页面进行预算调整。<br>
        当前仍可使用规则层进行预算调整，但缺少量化效率参考。
    </div>
    """, unsafe_allow_html=True)
else:
    # 构建 MMM 参考数据表
    mmm_ref_rows = []
    for ch in CHANNEL_KEYS:
        if f"{ch}_spend" not in df.columns:
            continue
        roi = mmm_roi.get(ch, 0)
        sat = mmm_saturation.get(ch, 0)
        mmm_sug = mmm_suggestion.get(ch, default_spends.get(ch, 0))
        hist_avg = default_spends.get(ch, 0)
        mmm_ref_rows.append({
            "渠道": CHANNEL_NAMES.get(ch, ch),
            "历史均值（万元/周）": round(hist_avg, 1),
            "MMM 优化建议（万元/周）": round(mmm_sug, 1) if mmm_suggestion else "—",
            "ROI（贡献/花费）": round(roi, 3),
            "饱和度": round(sat, 3),
            "效率评级": "🔥 高效" if roi > 2 else ("✅ 正常" if roi > 0.5 else ("⚠️ 偏低" if roi > 0 else "❓ 无数据")),
            "饱和状态": "⚠️ 接近饱和" if sat > 0.65 else ("✅ 有空间" if sat < 0.4 else "🔶 适中"),
        })

    mmm_ref_df = pd.DataFrame(mmm_ref_rows)
    st.dataframe(mmm_ref_df, use_container_width=True, hide_index=True,
                 column_config={
                     "ROI（贡献/花费）": st.column_config.NumberColumn("ROI（贡献/花费）", format="%.3f"),
                     "饱和度": st.column_config.ProgressColumn("饱和度", min_value=0, max_value=1),
                 })

    if not mmm_suggestion:
        st.markdown("""
        <div class="mmm-ref-card">
            💡 <b>提示</b>：「MMM 优化建议」列暂无数据。
            请前往「MMM 洞察」→「💡 预算优化建议」Tab，运行预算优化后，建议值将自动同步到此处。
        </div>
        """, unsafe_allow_html=True)

    with st.expander("📖 如何利用 MMM 参考面板做预算决策？", expanded=False):
        st.markdown("""
        **决策参考逻辑**：
        
        | 渠道状态 | 建议操作 |
        |---|---|
        | ROI 高 + 饱和度低（有空间） | **优先加投**，边际效益高 |
        | ROI 高 + 饱和度高（接近饱和） | **谨慎加投**，可小幅增加但边际效益递减 |
        | ROI 低 + 饱和度低 | **维持或减投**，效率低但可能有其他价值（品牌、质量） |
        | ROI 低 + 饱和度高 | **建议减投**，效率低且已饱和，预算转移到高效渠道 |
        
        **MMM 优化建议 vs 历史均值**：
        - 建议 > 历史均值：MMM 认为该渠道当前投入不足，有加投空间
        - 建议 < 历史均值：MMM 认为该渠道当前投入过多，建议减投
        - 建议 ≈ 历史均值：当前分配接近最优
        
        **注意**：MMM 建议是基于历史数据的量化参考，实际决策还需考虑：
        渠道容量上限、素材储备、运营人力、竞争环境等业务因素。
        """)

st.divider()

# ─── 主区域：预算调整 ─────────────────────────────────────────────────────────
st.subheader("📊 渠道预算分配")

col_left, col_right = st.columns([1, 1])

with col_left:
    st.markdown("**调整各渠道周度花费（万元）**")

    if mmm_suggestion:
        st.markdown("""
        <div class="mmm-ref-card">
            🧪 <b>MMM 建议已加载</b>：各渠道输入框旁显示 MMM 优化建议值作为参考。
        </div>
        """, unsafe_allow_html=True)

    total_scale = st.slider(
        "总预算缩放比例（快速调整所有渠道）",
        min_value=0.5, max_value=2.0, value=1.0, step=0.05,
        format="%.2fx",
        help="拖动此滑块可按比例同步缩放所有渠道预算，适合整体预算变化场景",
        key="mmm_total_scale",
        on_change=_sync_scaled_channel_spends,
        args=(default_spends,),
    )

    channel_spends = {}
    for ch in CHANNEL_KEYS:
        if f"{ch}_spend" not in df.columns:
            continue
        widget_key = f"spend_{ch}"
        default_val = round(default_spends[ch] * total_scale, 1)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = default_val
        mmm_sug_val = mmm_suggestion.get(ch)

        # 显示 MMM 建议标注
        if mmm_sug_val is not None:
            diff = mmm_sug_val - default_spends[ch]
            diff_pct = diff / default_spends[ch] * 100 if default_spends[ch] > 0 else 0
            arrow = "⬆️" if diff > 5 else ("⬇️" if diff < -5 else "➡️")
            label = f"{CHANNEL_NAMES[ch]}（MMM建议: {mmm_sug_val:.0f}万 {arrow} {diff_pct:+.0f}%）"
        else:
            label = CHANNEL_NAMES[ch]

        channel_spends[ch] = st.number_input(
            label,
            min_value=0.0,
            max_value=5000.0,
            value=float(st.session_state[widget_key]),
            step=5.0,
            key=widget_key,
            help=f"历史均值: {default_spends[ch]:.1f} 万元/周" +
                 (f" | MMM 优化建议: {mmm_sug_val:.1f} 万元/周" if mmm_sug_val is not None else ""),
        )

    total_budget = sum(channel_spends.values())
    st.metric("当前总预算（万元/周）", f"{total_budget:.1f}",
              delta=f"{total_budget - sum(default_spends.values()):+.1f} vs 历史均值")

with col_right:
    st.markdown("**渠道预算占比**")
    pie_data = {CHANNEL_NAMES[ch]: v for ch, v in channel_spends.items() if v > 0}
    fig_pie = px.pie(
        values=list(pie_data.values()),
        names=list(pie_data.keys()),
        title="渠道预算分配占比",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.35,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(height=360, showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)

    # 当前设置 vs 历史均值 vs MMM建议 三列对比
    compare_rows = []
    for ch in CHANNEL_KEYS:
        if f"{ch}_spend" not in df.columns:
            continue
        hist = round(default_spends[ch], 1)
        curr = round(channel_spends.get(ch, 0), 1)
        mmm_s = round(mmm_suggestion.get(ch, 0), 1) if mmm_suggestion else None
        row = {
            "渠道": CHANNEL_NAMES[ch],
            "历史均值": hist,
            "当前设置": curr,
            "变化率": f"{(curr - hist) / hist * 100:+.1f}%" if hist > 0 else "—",
        }
        if mmm_s:
            row["MMM建议"] = mmm_s
            row["vs MMM"] = f"{curr - mmm_s:+.1f}"
        compare_rows.append(row)

    compare_df = pd.DataFrame(compare_rows)
    st.dataframe(compare_df, use_container_width=True, hide_index=True)

st.divider()

# ─── 实时模拟结果 ─────────────────────────────────────────────────────────────
st.subheader("⚡ 实时模拟结果（规则层预测）")

with st.expander("📖 规则层预测是怎么算的？", expanded=False):
    st.markdown("""
    **规则层计算逻辑**（基于历史 104 周数据）：
    
    ```
    借款金额 = 总花费 × 历史均值（借款金额/总花费）× 目标模式系数
    CPS = 总花费 / 借款金额
    申完数 = 借款金额 / 历史均值（借款金额/申完数）
    授信数 = 申完数 × 历史均值（授信率）× 渠道质量加权系数
    1-3授信率 = A卡1-3授信数 / 申完数
    LTV_12m = 借款金额 × 历史均值（LTV_12m/借款金额）
    FPD30+ = 历史均值（FPD30+）× 渠道风险加权系数
    ```
    
    **渠道质量/风险加权系数**：基于各渠道历史 1-3授信率 / FPD30+ 的相对差异计算，
    反映不同渠道的客群质量差异。
    
    **与 MMM 层的区别**：规则层不考虑 Adstock 滞后效应和 Hill 饱和效应，
    是线性外推，适合快速预估，精度低于 MMM 层。
    """)

budget_input = BudgetInput(
    tencent_moments_spend=channel_spends.get("tencent_moments", 0),
    tencent_video_spend=channel_spends.get("tencent_video", 0),
    tencent_wechat_spend=channel_spends.get("tencent_wechat", 0),
    tencent_search_spend=channel_spends.get("tencent_search", 0),
    douyin_spend=channel_spends.get("douyin", 0),
    app_store_spend=channel_spends.get("app_store", 0),
    precision_marketing_spend=channel_spends.get("precision_marketing", 0),
    goal_mode=goal_mode,
    budget_target=budget_target,
    cps_target=cps_target,
    quality_target=quality_target,
    risk_threshold=risk_threshold,
)

st.session_state["budget_input"] = budget_input

result   = engine.simulate(budget_input, "当前方案")
baseline_input = BudgetInput(**{f"{ch}_spend": default_spends[ch] for ch in CHANNEL_KEYS
                                 if f"{ch}_spend" in df.columns})
baseline = engine.simulate(baseline_input, "历史均值基准")

def delta_str(cur, base, fmt=".2f"):
    d = cur - base
    pct = d / base * 100 if base != 0 else 0
    return f"{d:{fmt}} ({pct:+.1f}%)"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("借款金额（万元）", f"{result.loan_amt:.1f}",
          delta=delta_str(result.loan_amt, baseline.loan_amt, ".1f"),
          help="规则层预测的本期借款金额，delta 为相对历史均值的变化")
c2.metric("CPS", f"{result.cps_amt:.4f}",
          delta=delta_str(result.cps_amt, baseline.cps_amt, ".4f"),
          delta_color="inverse",
          help="CPS = 总花费 / 借款金额，越低越好，delta 反向（红色=上升=变差）")
c3.metric("1-3授信率", f"{result.quality_a13_rate:.3f}",
          delta=delta_str(result.quality_a13_rate, baseline.quality_a13_rate, ".4f"),
          help="A卡1-3档授信数 / 申完数，反映客群质量，越高越好")
c4.metric("LTV_12m（万元）", f"{result.ltv_12m:.1f}",
          delta=delta_str(result.ltv_12m, baseline.ltv_12m, ".1f"),
          help="12个月生命周期价值，越高越好")
c5.metric("FPD30+风险率", f"{result.fpd30_plus_rate:.4f}",
          delta=delta_str(result.fpd30_plus_rate, baseline.fpd30_plus_rate, ".4f"),
          delta_color="inverse",
          help="首期逾期30天以上比率，越低越好，delta 反向（红色=上升=变差）")

with st.expander("📖 如何解读这些预测指标？", expanded=False):
    st.markdown("""
    | 指标 | 含义 | 优化方向 | 注意事项 |
    |---|---|---|---|
    | **借款金额** | 预测本期各渠道获客产生的借款总额 | 越高越好（规模） | 规则层线性外推，仅供参考 |
    | **CPS** | 每元借款的获客成本 = 花费/借款金额 | 越低越好（成本） | delta 红色=上升=变差 |
    | **1-3授信率** | 优质客群比例，反映客群质量 | 越高越好（质量） | 不同渠道差异较大 |
    | **LTV_12m** | 12个月生命周期价值，反映长期价值 | 越高越好（价值） | 基于历史比率估算 |
    | **FPD30+** | 首期逾期率，反映风险 | 越低越好（风险） | delta 红色=上升=变差 |
    
    **delta 说明**：括号内为相对历史均值基准的变化量和变化率。
    """)

# ─── 目标达成判断 ─────────────────────────────────────────────────────────────
st.subheader("🎯 目标达成判断")

with st.expander("📖 目标达成判断逻辑说明", expanded=False):
    st.markdown("""
    - **预算达成**：当前总花费 ≥ 预算目标 × 95%（允许 5% 误差）
    - **CPS 达成**：预测 CPS ≤ CPS 目标 × 105%（允许 5% 误差）
    - **质量达成**：预测 1-3授信率 ≥ 质量目标 × 95%（允许 5% 误差）
    - **风险控制**：预测 FPD30+ ≤ 风险阈值（严格控制）
    
    目标参数在左侧边栏设置。
    """)

col_g1, col_g2, col_g3, col_g4 = st.columns(4)

def status_icon(ok): return "✅" if ok else "❌"

budget_ok  = result.total_spend >= budget_target * 0.95
cps_ok     = result.cps_amt <= cps_target * 1.05
quality_ok = result.quality_a13_rate >= quality_target * 0.95
risk_ok    = result.fpd30_plus_rate <= risk_threshold

col_g1.metric(f"{status_icon(budget_ok)} 预算达成",
              f"{result.total_spend:.1f} / {budget_target:.1f} 万元",
              help="当前总花费 vs 预算目标")
col_g2.metric(f"{status_icon(cps_ok)} CPS 达成",
              f"{result.cps_amt:.4f} / {cps_target:.4f}",
              help="预测 CPS vs CPS 目标（越低越好）")
col_g3.metric(f"{status_icon(quality_ok)} 质量达成",
              f"{result.quality_a13_rate:.3f} / {quality_target:.3f}",
              help="预测 1-3授信率 vs 质量目标（越高越好）")
col_g4.metric(f"{status_icon(risk_ok)} 风险控制",
              f"{result.fpd30_plus_rate:.4f} ≤ {risk_threshold:.4f}",
              help="预测 FPD30+ vs 风险阈值（越低越好）")

# ─── 业务漏斗 ─────────────────────────────────────────────────────────────────
st.subheader("📉 业务转化漏斗（预测）")

with st.expander("📖 漏斗各环节含义说明", expanded=False):
    st.markdown("""
    | 环节 | 含义 | 计算方式 |
    |---|---|---|
    | **首登** | 首次登录用户数 | 总花费 × 历史均值（首登/花费） |
    | **发起** | 发起申请用户数 | 首登 × 历史均值（发起/首登率） |
    | **申完** | 完成申请用户数 | 发起 × 历史均值（申完/发起率） |
    | **授信** | 获得授信用户数 | 申完 × 历史均值（授信率） |
    | **A卡1-3授信** | 优质授信用户数（A卡1-3档） | 申完 × 渠道质量加权 1-3授信率 |
    | **借款** | 实际借款用户数 | 申完 × 历史均值（借款/申完率） |
    
    漏斗数据基于规则层预测，各环节转化率使用历史均值，渠道质量差异通过加权系数体现。
    """)

funnel_data = {
    "首登": int(result.first_login_cnt),
    "发起": int(result.apply_start_cnt),
    "申完": int(result.apply_submit_cnt),
    "授信": int(result.credit_cnt),
    "A卡1-3授信": int(result.credit_a13_cnt),
    "借款": int(result.loan_cnt),
}
fig_funnel = go.Figure(go.Funnel(
    y=list(funnel_data.keys()),
    x=list(funnel_data.values()),
    textinfo="value+percent initial",
    marker=dict(color=["#1976D2", "#42A5F5", "#90CAF9", "#4CAF50", "#81C784", "#FF7043"]),
))
fig_funnel.update_layout(title="业务转化漏斗（规则层预测）", height=380)
st.plotly_chart(fig_funnel, use_container_width=True)

st.divider()

# ─── 保存方案 ─────────────────────────────────────────────────────────────────
st.subheader("💾 保存当前方案")

col_save1, col_save2 = st.columns([1, 2])
with col_save1:
    plan_name = st.text_input("方案名称", value="自定义方案",
                               help="为当前预算分配方案命名，保存后可在方案对比页查看")
with col_save2:
    st.write("")
    st.write("")
    if st.button("💾 保存方案并前往方案对比", type="primary", use_container_width=True):
        saved_plans = st.session_state.get("saved_plans", [])
        saved_plans.append({
            "name": plan_name,
            "spends": channel_spends.copy(),
            "result": result,
            "goal_mode": goal_mode,
        })
        st.session_state["saved_plans"] = saved_plans
        st.success(f"✅ 方案「{plan_name}」已保存！共 {len(saved_plans)} 个方案。请前往「方案对比」页面查看。")
        st.switch_page("pages/mmm_4_方案对比.py")

st.markdown("""
<div class="guide-card">
    <b>→ 下一步</b>：前往「<b>方案对比</b>」页面，查看基准/保守/标准/激进四方案的自动生成结果，
    与当前自定义方案进行多维对比，选择最优方案拍板确认。
</div>
""", unsafe_allow_html=True)
