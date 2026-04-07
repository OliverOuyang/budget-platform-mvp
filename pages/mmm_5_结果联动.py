"""
结果联动展示页 - 重构版
核心改进：
1. 增加各指标组的含义说明
2. 敏感性分析增加解读折叠模块
3. 渠道效率分析增加 MMM ROI 对比
4. 历史趋势图增加解读说明
5. 增加引导提示
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
from plotly.subplots import make_subplots

from utils.data_loader import load_mock_data, CHANNEL_NAMES, CHANNEL_KEYS, METRIC_LABELS
from engine.rule_engine import RuleEngine, BudgetInput
from engine.mmm_engine import load_model


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
</style>
""", unsafe_allow_html=True)

# ─── 页面标题 ─────────────────────────────────────────────────────────────────
st.title("🔗 结果联动展示")
st.markdown("""
> **本页面的作用**：对拍板方案进行深度分析，包括敏感性分析、渠道效率全景和历史趋势对比。
> 
> **在决策链路中的位置**：数据检查 → MMM 洞察 → 预算调整 → 方案对比 → **结果联动（当前）**
""")

with st.expander("📖 本页面各模块说明（点击展开）", expanded=False):
    st.markdown("""
    | 模块 | 内容 | 用途 |
    |---|---|---|
    | **综合指标看板** | 全量 KPI 展示（规模/成本/质量/LTV/风险） | 一览当前方案的完整预测结果 |
    | **敏感性分析** | 总预算变化 ±50% 对各指标的影响曲线 | 了解预算弹性，判断加投/减投的边际效益 |
    | **渠道效率分析** | CPM/CPC/CTR + MMM ROI 综合效率表 | 横向对比各渠道的流量效率和转化效率 |
    | **历史趋势对比** | 历史实际值 vs 当前预测值 | 判断预测值是否在历史正常范围内 |
    
    **数据来源**：
    - 综合指标看板：规则层预测（基于「预算调整」页的设置）
    - 敏感性分析：规则层批量模拟（31个预算水平）
    - 渠道效率：历史数据统计（104周均值）+ MMM 模型输出（若已训练）
    - 历史趋势：原始 Mock 数据（104周）
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

if "budget_input" in st.session_state:
    base_budget = st.session_state["budget_input"]
else:
    base_budget = BudgetInput(**{f"{ch}_spend": default_spends[ch] for ch in CHANNEL_KEYS
                                  if f"{ch}_spend" in df.columns})
    st.markdown("""
    <div class="guide-card">
        ⚠️ <b>提示</b>：未检测到「预算调整」页的设置，当前使用历史均值作为分析基准。
    </div>
    """, unsafe_allow_html=True)

result   = engine.simulate(base_budget, "当前方案")
baseline_input = BudgetInput(**{f"{ch}_spend": default_spends[ch] for ch in CHANNEL_KEYS
                                 if f"{ch}_spend" in df.columns})
baseline = engine.simulate(baseline_input, "历史均值基准")

# 若有拍板方案，显示提示
if "approved_plan" in st.session_state:
    ap = st.session_state["approved_plan"]
    st.success(f"✅ 当前分析基于已拍板方案：**{ap['scenario']}**（审核人：{ap['reviewer']}）")

# ─── 综合指标看板 ─────────────────────────────────────────────────────────────
st.subheader("📊 综合指标看板")

def delta_pct(cur, base):
    if base == 0: return "N/A"
    return f"{(cur - base) / base * 100:+.1f}%"

with st.expander("📖 各指标含义说明", expanded=False):
    st.markdown("""
    ##### 规模指标
    | 指标 | 含义 | 优化方向 |
    |---|---|---|
    | 总花费 | 所有渠道当期投放总金额（万元） | 在预算约束下最大化效果 |
    | 首登数 | 首次登录用户数，流量漏斗入口 | 越高越好（流量规模） |
    | 申完数 | 完成申请用户数，核心转化节点 | 越高越好 |
    | 借款数 | 实际借款用户数 | 越高越好 |
    | 借款金额 | 各渠道获客产生的借款总额（万元） | 越高越好（MMM 因变量） |
    
    ##### 成本 & 质量指标
    | 指标 | 含义 | 优化方向 |
    |---|---|---|
    | CPS | 花费/借款金额，每元借款的获客成本 | 越低越好 |
    | 授信数 | 获得授信用户数 | 越高越好 |
    | A卡1-3授信数 | 优质授信用户数（A卡1-3档） | 越高越好 |
    | 1-3授信率 | A卡1-3授信数/申完数，客群质量 | 越高越好 |
    | 授信金额 | 授信总额（万元） | 越高越好 |
    
    ##### LTV & 风险指标
    | 指标 | 含义 | 优化方向 |
    |---|---|---|
    | LTV_12m | 12个月生命周期价值（万元） | 越高越好 |
    | LTV_24m | 24个月生命周期价值（万元） | 越高越好 |
    | FPD30+ | 首期逾期30天以上比率 | 越低越好 |
    | 首借交易 | 首次借款用户的交易笔数 | 关注占比和越势 |
    | 复借交易 | 复借用户的交易笔数 | 越高越好（复借用户质量更高） |
    | 首借终损率 | 首借用户的终期损失率，包含全周期逃废损失 | 越低越好，首借用户风险较高 |
    | 复借终损率 | 复借用户的终期损失率，经过筛选风险较低 | 越低越好，通常低于首借终损率 |
    
    > **首借 vs 复借风险对比**：首借终损率通常是复借终损率的 2–3倍。当首借占比过高时，整体风险上升；复借占比提升说明客群质量在改善。
    """)

# 规模
st.markdown("##### 📦 规模指标")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("总花费（万元）",   f"{result.total_spend:.1f}",
          delta_pct(result.total_spend, baseline.total_spend),
          help="所有渠道当期投放总金额")
c2.metric("首登数",           f"{int(result.first_login_cnt):,}",
          delta_pct(result.first_login_cnt, baseline.first_login_cnt),
          help="首次登录用户数，流量漏斗入口")
c3.metric("申完数",           f"{int(result.apply_submit_cnt):,}",
          delta_pct(result.apply_submit_cnt, baseline.apply_submit_cnt),
          help="完成申请用户数")
c4.metric("借款数",           f"{int(result.loan_cnt):,}",
          delta_pct(result.loan_cnt, baseline.loan_cnt),
          help="实际借款用户数")
c5.metric("借款金额（万元）", f"{result.loan_amt:.1f}",
          delta_pct(result.loan_amt, baseline.loan_amt),
          help="各渠道获客产生的借款总额（MMM 因变量）")

# 成本 & 质量
st.markdown("##### 💰 成本 & 质量指标")
c6, c7, c8, c9, c10 = st.columns(5)
c6.metric("CPS",              f"{result.cps_amt:.4f}",
          delta_pct(result.cps_amt, baseline.cps_amt),
          delta_color="inverse",
          help="花费/借款金额，越低越好")
c7.metric("授信数",           f"{int(result.credit_cnt):,}",
          delta_pct(result.credit_cnt, baseline.credit_cnt))
c8.metric("A卡1-3授信数",     f"{int(result.credit_a13_cnt):,}",
          delta_pct(result.credit_a13_cnt, baseline.credit_a13_cnt))
c9.metric("1-3授信率",        f"{result.quality_a13_rate:.3f}",
          delta_pct(result.quality_a13_rate, baseline.quality_a13_rate),
          help="A卡1-3授信数/申完数，越高越好")
c10.metric("授信金额（万元）", f"{result.credit_amt:.1f}",
           delta_pct(result.credit_amt, baseline.credit_amt))

# LTV & 风险
st.markdown("##### 📈 LTV & 风险指标")
c11, c12, c13 = st.columns(3)
c11.metric("LTV_12m（万元）", f"{result.ltv_12m:.1f}",
           delta_pct(result.ltv_12m, baseline.ltv_12m),
           help="12个月生命周期价值")
c12.metric("LTV_24m（万元）", f"{result.ltv_24m:.1f}",
           delta_pct(result.ltv_24m, baseline.ltv_24m),
           help="24个月生命周期价值")
c13.metric("FPD30+风险率",    f"{result.fpd30_plus_rate:.4f}",
           delta_pct(result.fpd30_plus_rate, baseline.fpd30_plus_rate),
           delta_color="inverse",
           help="首期逾期30天以上比率，越低越好")

# 首借 / 复借风险
st.markdown("##### 🛡️ 首借 & 复借风险指标")
ca, cb, cc, cd = st.columns(4)
ca.metric("首借交易（笔）",
          f"{int(result.first_loan_txn):,}",
          delta_pct(result.first_loan_txn, baseline.first_loan_txn),
          help="首次借款用户的交易笔数，占总借款的 65–75%")
cb.metric("复借交易（笔）",
          f"{int(result.repeat_loan_txn):,}",
          delta_pct(result.repeat_loan_txn, baseline.repeat_loan_txn),
          help="复借用户的交易笔数，越高说明客群质量越好")
cc.metric("首借终损率",
          f"{result.first_loan_final_loss_rate:.4f}",
          delta_pct(result.first_loan_final_loss_rate, baseline.first_loan_final_loss_rate),
          delta_color="inverse",
          help="首借用户终期损失率，包含全周期逃废，越低越好")
cd.metric("复借终损率",
          f"{result.repeat_loan_final_loss_rate:.4f}",
          delta_pct(result.repeat_loan_final_loss_rate, baseline.repeat_loan_final_loss_rate),
          delta_color="inverse",
          help="复借用户终期损失率，经过筛选风险较低，越低越好")

st.divider()

# ─── 敏感性分析 ───────────────────────────────────────────────────────────────
st.subheader("🔬 敏感性分析（总预算变化对各指标的影响）")

with st.expander("📖 敏感性分析说明：如何计算？如何解读？", expanded=False):
    st.markdown("""
    #### 计算方式
    固定各渠道**预算比例**不变，将总预算从历史均值的 50% 扫描到 200%（步长 5%），
    对每个预算水平使用规则层计算各 KPI 预测值，绘制影响曲线。
    
    #### 如何解读
    - **曲线斜率越陡**：该指标对预算变化越敏感，加投/减投效果越明显
    - **曲线趋于平缓**：边际效益递减，继续加投效果有限
    - **当前预算位置**（橙色虚线）：判断当前处于曲线的哪个阶段
      - 在陡峭段：加投有较好回报
      - 在平缓段：加投边际效益低，可考虑维持或减投
    
    #### 注意
    规则层敏感性分析是**线性外推**，不考虑饱和效应。
    真实的边际效益曲线（非线性）请参考「MMM 洞察」→「响应曲线」Tab。
    """)

scale_range = np.arange(0.5, 2.05, 0.05)
sens_results = []
for scale in scale_range:
    b = BudgetInput(**{f"{ch}_spend": default_spends[ch] * scale for ch in CHANNEL_KEYS
                       if f"{ch}_spend" in df.columns})
    r = engine.simulate(b)
    sens_results.append({
        "scale": scale,
        "total_spend": r.total_spend,
        "loan_amt": r.loan_amt,
        "cps_amt": r.cps_amt,
        "quality_a13_rate": r.quality_a13_rate,
        "fpd30_plus_rate": r.fpd30_plus_rate,
        "ltv_12m": r.ltv_12m,
    })
sens_df = pd.DataFrame(sens_results)

col_sens1, col_sens2 = st.columns([2, 1])
with col_sens1:
    sens_col = st.selectbox(
        "选择分析指标",
        ["loan_amt", "cps_amt", "quality_a13_rate", "fpd30_plus_rate", "ltv_12m"],
        format_func=lambda x: METRIC_LABELS.get(x, x),
    )
with col_sens2:
    show_all = st.checkbox("同时显示所有指标（归一化）", value=False)

if show_all:
    # 归一化后多线展示
    fig_sens = go.Figure()
    colors_sens = px.colors.qualitative.Plotly
    for i, col in enumerate(["loan_amt", "cps_amt", "quality_a13_rate", "fpd30_plus_rate", "ltv_12m"]):
        vals = sens_df[col]
        norm_vals = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9)
        # CPS 和 FPD30+ 反向（越低越好，归一化后越高越好）
        if col in ["cps_amt", "fpd30_plus_rate"]:
            norm_vals = 1 - norm_vals
        fig_sens.add_trace(go.Scatter(
            x=sens_df["total_spend"], y=norm_vals,
            mode="lines", name=METRIC_LABELS.get(col, col),
            line=dict(color=colors_sens[i], width=2),
        ))
    fig_sens.add_vline(x=result.total_spend, line_dash="dash", line_color="#FF7043",
                       annotation_text="当前预算")
    fig_sens.update_layout(
        title="总预算 vs 各指标（归一化，越高越好）",
        xaxis_title="总花费（万元）", yaxis_title="归一化值（0-1）",
        height=420, hovermode="x unified",
    )
else:
    fig_sens = go.Figure()
    fig_sens.add_trace(go.Scatter(
        x=sens_df["total_spend"], y=sens_df[sens_col],
        mode="lines+markers", name=METRIC_LABELS.get(sens_col, sens_col),
        line=dict(color="#1976D2", width=2), marker=dict(size=5),
    ))
    fig_sens.add_vline(x=result.total_spend, line_dash="dash", line_color="#FF7043",
                       annotation_text=f"当前预算 ({result.total_spend:.0f}万)")
    fig_sens.update_layout(
        title=f"总预算 vs {METRIC_LABELS.get(sens_col, sens_col)}",
        xaxis_title="总花费（万元）", yaxis_title=METRIC_LABELS.get(sens_col, sens_col),
        height=420, hovermode="x unified",
    )

st.plotly_chart(fig_sens, use_container_width=True)

# 敏感性关键数字
current_val = getattr(result, sens_col if not show_all else "loan_amt")
val_at_80 = sens_df.loc[(sens_df["scale"] - 0.8).abs().idxmin(), sens_col if not show_all else "loan_amt"]
val_at_120 = sens_df.loc[(sens_df["scale"] - 1.2).abs().idxmin(), sens_col if not show_all else "loan_amt"]

if not show_all:
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric(f"预算-20%时的{METRIC_LABELS.get(sens_col, sens_col)}",
                  f"{val_at_80:.4f}" if "rate" in sens_col or "cps" in sens_col else f"{val_at_80:.1f}",
                  delta=f"{(val_at_80 - current_val) / current_val * 100:+.1f}% vs 当前",
                  delta_color="inverse" if sens_col in ["cps_amt", "fpd30_plus_rate"] else "normal")
    col_s2.metric(f"当前预算时的{METRIC_LABELS.get(sens_col, sens_col)}",
                  f"{current_val:.4f}" if "rate" in sens_col or "cps" in sens_col else f"{current_val:.1f}")
    col_s3.metric(f"预算+20%时的{METRIC_LABELS.get(sens_col, sens_col)}",
                  f"{val_at_120:.4f}" if "rate" in sens_col or "cps" in sens_col else f"{val_at_120:.1f}",
                  delta=f"{(val_at_120 - current_val) / current_val * 100:+.1f}% vs 当前",
                  delta_color="inverse" if sens_col in ["cps_amt", "fpd30_plus_rate"] else "normal")

st.divider()

# ─── 渠道效率分析 ─────────────────────────────────────────────────────────────
st.subheader("📡 渠道效率全景分析")

with st.expander("📖 渠道效率指标说明", expanded=False):
    st.markdown("""
    | 指标 | 计算公式 | 含义 | 优化方向 |
    |---|---|---|---|
    | **CPM（元）** | 花费×10000 / 曝光量 × 1000 | 千次曝光成本 | 越低越好（流量价格） |
    | **CPC（元）** | 花费×10000 / 点击量 | 每次点击成本 | 越低越好（点击价格） |
    | **CTR** | 点击量 / 曝光量 | 点击率，反映素材吸引力 | 越高越好 |
    | **MMM ROI** | MMM贡献量 / 花费 | 每万元花费带来的借款金额增量 | 越高越好（效率） |
    
    **注意**：CPM/CPC/CTR 是流量效率指标（媒体端），MMM ROI 是业务效率指标（转化端）。
    两者结合才能全面评估渠道效率：
    - CPM 低 + ROI 高：该渠道流量便宜且转化好，优先加投
    - CPM 高 + ROI 高：流量贵但转化好，可维持
    - CPM 低 + ROI 低：流量便宜但转化差，需优化素材/定向
    - CPM 高 + ROI 低：流量贵且转化差，建议减投
    """)

# 加载 MMM 模型获取 ROI
model = st.session_state.get("mmm_model") or load_model()
mmm_roi_map = {}
if model and model.is_fitted:
    contribs = model.channel_contribution(df)
    for ch in model._channel_keys:
        spend_col = f"{ch}_spend"
        if spend_col not in df.columns:
            continue
        total_spend_ch = df[spend_col].sum()
        total_contrib_ch = contribs.get(ch, np.zeros(len(df))).sum()
        mmm_roi_map[ch] = total_contrib_ch / total_spend_ch if total_spend_ch > 0 else 0

ch_efficiency = []
for ch in CHANNEL_KEYS:
    if f"{ch}_spend" not in df.columns:
        continue
    avg_spend = df[f"{ch}_spend"].mean()
    avg_imp   = df[f"{ch}_impressions"].mean() if f"{ch}_impressions" in df.columns else 0
    avg_clk   = df[f"{ch}_clicks"].mean() if f"{ch}_clicks" in df.columns else 0

    cpm_val = avg_spend * 10000 / avg_imp * 1000 if avg_imp > 0 else 0
    cpc_val = avg_spend * 10000 / avg_clk if avg_clk > 0 else 0
    ctr_val = avg_clk / avg_imp if avg_imp > 0 else 0

    row = {
        "渠道": CHANNEL_NAMES[ch],
        "周均花费（万元）": round(avg_spend, 1),
        "CPM（元）": round(cpm_val, 2),
        "CPC（元）": round(cpc_val, 2),
        "CTR": round(ctr_val, 4),
        "周均曝光": int(avg_imp),
        "周均点击": int(avg_clk),
    }
    if mmm_roi_map:
        row["MMM ROI"] = round(mmm_roi_map.get(ch, 0), 3)
        row["效率评级"] = "🔥 高效" if mmm_roi_map.get(ch, 0) > 2 else (
            "✅ 正常" if mmm_roi_map.get(ch, 0) > 0.5 else (
            "⚠️ 偏低" if mmm_roi_map.get(ch, 0) > 0 else "❓ 无数据"))
    ch_efficiency.append(row)

eff_df = pd.DataFrame(ch_efficiency)
st.dataframe(eff_df, use_container_width=True, hide_index=True,
             column_config={
                 "CTR": st.column_config.NumberColumn("CTR", format="%.4f"),
             } if "MMM ROI" not in eff_df.columns else {
                 "CTR": st.column_config.NumberColumn("CTR", format="%.4f"),
                 "MMM ROI": st.column_config.NumberColumn("MMM ROI", format="%.3f"),
             })

# 散点图：花费 vs CPC（气泡=曝光量）
col_eff1, col_eff2 = st.columns(2)
with col_eff1:
    fig_eff = px.scatter(
        eff_df, x="周均花费（万元）", y="CPC（元）",
        size="周均曝光", color="渠道", text="渠道",
        title="渠道花费 vs CPC（气泡大小=曝光量）",
        color_discrete_sequence=px.colors.qualitative.Set2, height=380,
    )
    fig_eff.update_traces(textposition="top center")
    fig_eff.update_layout(showlegend=False)
    st.plotly_chart(fig_eff, use_container_width=True)

with col_eff2:
    if mmm_roi_map and "MMM ROI" in eff_df.columns:
        fig_roi = px.bar(
            eff_df.sort_values("MMM ROI", ascending=True),
            x="MMM ROI", y="渠道", orientation="h",
            title="渠道 MMM ROI 排名（越高越值得加投）",
            color="MMM ROI",
            color_continuous_scale="RdYlGn",
            height=380,
        )
        fig_roi.update_layout(showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig_roi, use_container_width=True)
    else:
        st.info("训练 MMM 模型后可查看渠道 ROI 排名。")

st.divider()

# ─── 历史趋势 vs 预测对比 ─────────────────────────────────────────────────────
st.subheader("📉 历史趋势 vs 当前预测")

with st.expander("📖 历史趋势对比说明", expanded=False):
    st.markdown("""
    - **历史实际值**（蓝色细线）：原始 Mock 数据，104周历史记录
    - **8周均线**（蓝色虚线）：8周移动平均，反映趋势方向
    - **当前预测值**（橙色水平线）：规则层对当前预算设置的预测结果
    
    **如何解读**：
    - 预测值在历史正常范围内：预测合理，可信度高
    - 预测值明显高于历史最高值：规则层可能高估，需结合 MMM 层验证
    - 预测值明显低于历史最低值：可能预算设置过低，或目标模式影响了系数
    
    **注意**：历史数据包含大促、节假日等异常周次，正常周次的实际值通常在历史均值附近波动。
    """)

trend_metric = st.selectbox(
    "选择对比指标",
    ["loan_amt", "cps_amt", "quality_a13_rate", "fpd30_plus_rate", "ltv_12m"],
    format_func=lambda x: METRIC_LABELS.get(x, x),
)

fig_hist = go.Figure()
fig_hist.add_trace(go.Scatter(
    x=df["week_start"], y=df[trend_metric],
    mode="lines", name="历史实际",
    line=dict(color="#90CAF9", width=1.5),
))
ma8 = df[trend_metric].rolling(8).mean()
fig_hist.add_trace(go.Scatter(
    x=df["week_start"], y=ma8,
    mode="lines", name="8周均线",
    line=dict(color="#1976D2", width=2, dash="dot"),
))
pred_val = getattr(result, trend_metric)
hist_mean = df[trend_metric].mean()
hist_max  = df[trend_metric].max()
hist_min  = df[trend_metric].min()

fig_hist.add_hline(y=pred_val, line_dash="dash", line_color="#FF7043",
                   annotation_text=f"当前预测：{pred_val:.4f}",
                   annotation_position="bottom right")
fig_hist.add_hline(y=hist_mean, line_dash="dot", line_color="#9C27B0", opacity=0.5,
                   annotation_text=f"历史均值：{hist_mean:.4f}",
                   annotation_position="top right")

fig_hist.update_layout(
    title=f"{METRIC_LABELS.get(trend_metric, trend_metric)} 历史趋势 vs 当前预测",
    xaxis_title="周次",
    yaxis_title=METRIC_LABELS.get(trend_metric, trend_metric),
    height=420, hovermode="x unified",
)
st.plotly_chart(fig_hist, use_container_width=True)

# 预测值位置判断
pct_rank = (pred_val - hist_min) / (hist_max - hist_min) * 100 if hist_max > hist_min else 50
col_h1, col_h2, col_h3 = st.columns(3)
col_h1.metric("历史最小值", f"{hist_min:.4f}" if "rate" in trend_metric or "cps" in trend_metric else f"{hist_min:.1f}")
col_h2.metric("当前预测值（百分位）",
              f"{pred_val:.4f}" if "rate" in trend_metric or "cps" in trend_metric else f"{pred_val:.1f}",
              delta=f"历史 {pct_rank:.0f}% 分位",
              delta_color="normal")
col_h3.metric("历史最大值", f"{hist_max:.4f}" if "rate" in trend_metric or "cps" in trend_metric else f"{hist_max:.1f}")

st.divider()

st.markdown("""
<div class="guide-card">
    <b>✅ 决策闭环完成</b>：您已完成「数据检查 → MMM 洞察 → 预算调整 → 方案对比 → 结果联动」的完整决策链路。<br>
    如需调整，可返回「预算调整」页修改参数，或返回「MMM 洞察」页重新训练模型。
</div>
""", unsafe_allow_html=True)
