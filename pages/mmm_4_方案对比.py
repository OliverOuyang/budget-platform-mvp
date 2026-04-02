"""
方案对比页 - 重构版
核心改进：
1. 增加四方案生成逻辑说明（如何从基准方案派生）
2. 每个图表增加结果解读折叠模块
3. 增加 MMM 优化方案作为第五方案（若已运行优化）
4. 增加引导下一步提示
"""
import sys
sys.path.insert(0, "/home/ubuntu/budget_combined")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from utils.data_loader import load_mock_data, CHANNEL_NAMES, CHANNEL_KEYS, METRIC_LABELS
from engine.rule_engine import RuleEngine, BudgetInput


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
.scenario-card {
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    margin: 4px;
}
</style>
""", unsafe_allow_html=True)

# ─── 页面标题 ─────────────────────────────────────────────────────────────────
st.title("📊 方案对比")
st.markdown("""
> **本页面的作用**：基于「预算调整」页的设置，自动生成四个梯度方案，多维度对比后人工拍板。
> 
> **在决策链路中的位置**：数据检查 → MMM 洞察 → 预算调整 → **方案对比（当前）** → 结果联动
""")

with st.expander("📖 四方案是怎么生成的？推导逻辑说明（点击展开）", expanded=False):
    st.markdown("""
    #### 四方案生成逻辑
    
    基于「预算调整」页设置的**基准预算**，按以下比例自动派生四个方案：
    
    | 方案 | 总预算倍数 | 渠道分配逻辑 | 适用场景 |
    |---|---|---|---|
    | **基准方案** | 1.0× | 与「预算调整」页设置完全一致 | 当前预算水平的预测结果 |
    | **保守方案** | 0.8× | 所有渠道等比缩减 20% | 预算收紧、风险优先场景 |
    | **标准方案** | 1.1× | 所有渠道等比增加 10% | 稳健增长场景 |
    | **激进方案** | 1.3× | 所有渠道等比增加 30% | 规模冲刺、大促场景 |
    
    #### 方案预测计算方式
    每个方案的 KPI 预测均使用**规则层**计算：
    ```
    借款金额 = 总花费 × 历史均值（借款金额/总花费）× 目标模式系数
    CPS = 总花费 / 借款金额
    1-3授信率 = 历史均值 × 渠道质量加权系数
    FPD30+ = 历史均值 × 渠道风险加权系数
    LTV_12m = 借款金额 × 历史均值（LTV/借款金额）
    ```
    
    #### 如果已运行 MMM 预算优化
    MMM 优化方案将作为**第五方案**显示，其预算分配基于等边际原则，
    代表在相同总预算下 MMM 模型认为最优的渠道分配。
    
    #### 数据来源
    - 历史均值系数：基于训练数据（104周）计算
    - 基准预算：来自「预算调整」页面的当前设置（若未设置，使用历史均值）
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

# 获取预算输入
if "budget_input" in st.session_state:
    base_budget = st.session_state["budget_input"]
    st.info("✅ 已读取「预算调整」页的预算设置作为基准方案。")
else:
    base_budget = BudgetInput(**{f"{ch}_spend": default_spends[ch] for ch in CHANNEL_KEYS
                                  if f"{ch}_spend" in df.columns})
    st.markdown("""
    <div class="guide-card">
        ⚠️ <b>提示</b>：未检测到「预算调整」页的设置，当前使用历史均值作为基准方案。
        建议先前往「预算调整」页面完成预算分配，再回此页面查看对比。
    </div>
    """, unsafe_allow_html=True)

# ─── 生成四方案 ───────────────────────────────────────────────────────────────
scenarios = engine.generate_scenarios(base_budget)
scenario_names = list(scenarios.keys())

# 若有 MMM 优化方案，生成第五方案
mmm_suggestion = st.session_state.get("mmm_budget_suggestion", {})
if mmm_suggestion:
    mmm_budget = BudgetInput(
        **{f"{ch}_spend": mmm_suggestion.get(ch, default_spends.get(ch, 0))
           for ch in CHANNEL_KEYS if f"{ch}_spend" in df.columns},
        goal_mode=base_budget.goal_mode,
        budget_target=base_budget.budget_target,
        cps_target=base_budget.cps_target,
        quality_target=base_budget.quality_target,
        risk_threshold=base_budget.risk_threshold,
    )
    mmm_result = engine.simulate(mmm_budget, "MMM优化方案")
    scenarios["MMM优化方案"] = mmm_result
    scenario_names = list(scenarios.keys())

# ─── 方案概览卡片 ─────────────────────────────────────────────────────────────
st.subheader("📋 方案概览")

scenario_colors = {
    "基准方案": "#dbeafe",
    "保守方案": "#dcfce7",
    "标准方案": "#fef9c3",
    "激进方案": "#fce7f3",
    "MMM优化方案": "#f3e8ff",
}
scenario_icons = {
    "基准方案": "📌",
    "保守方案": "🛡️",
    "标准方案": "📈",
    "激进方案": "🚀",
    "MMM优化方案": "🧪",
}

cols = st.columns(len(scenarios))
for i, (name, res) in enumerate(scenarios.items()):
    with cols[i]:
        bg = scenario_colors.get(name, "#f8fafc")
        icon = scenario_icons.get(name, "📊")
        st.markdown(f"""
        <div style="background:{bg};border-radius:10px;padding:14px;text-align:center">
            <div style="font-size:1.5em">{icon}</div>
            <div style="font-weight:700;font-size:0.95em;margin:4px 0">{name}</div>
            <div style="font-size:0.8em;color:#555">花费: {res.total_spend:.0f} 万</div>
            <div style="font-size:0.8em;color:#1976D2">借款: {res.loan_amt:.0f} 万</div>
            <div style="font-size:0.8em;color:#555">CPS: {res.cps_amt:.4f}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ─── 方案汇总表 ───────────────────────────────────────────────────────────────
st.subheader("📋 方案汇总对比表")

rows = [res.to_dict() for res in scenarios.values()]
compare_df = pd.DataFrame(rows)
compare_df = compare_df.set_index("方案名称").T

def highlight_best(row):
    styles = [""] * len(row)
    try:
        if row.name in ["借款金额（万元）", "借款数", "LTV_12m（万元）", "LTV_24m（万元）", "1-3授信率"]:
            best_idx = row.astype(float).idxmax()
            styles[list(row.index).index(best_idx)] = "background-color: #c8e6c9; font-weight: bold"
        elif row.name in ["CPS", "FPD30+风险率"]:
            best_idx = row.astype(float).idxmin()
            styles[list(row.index).index(best_idx)] = "background-color: #c8e6c9; font-weight: bold"
    except Exception:
        pass
    return styles

styled = compare_df.style.apply(highlight_best, axis=1)
st.dataframe(styled, use_container_width=True)

with st.expander("📖 如何解读方案汇总表？", expanded=False):
    st.markdown("""
    - **绿色高亮**：该行指标的最优值（借款金额/LTV/授信率越高越好，CPS/FPD30+越低越好）
    - **行 = 指标，列 = 方案**：每行对比各方案在该指标上的表现
    - **关键权衡**：
      - 激进方案通常借款金额最高，但 CPS 可能更高（规模 vs 成本的权衡）
      - 保守方案通常 CPS 最低，但借款金额最小
      - MMM 优化方案（若有）在相同总预算下通过优化渠道分配，可能在多个指标上优于标准方案
    """)

st.divider()

# ─── 雷达图 ───────────────────────────────────────────────────────────────────
st.subheader("🕸️ 多维度雷达图对比")

radar_vals = {}
for name, res in scenarios.items():
    radar_vals[name] = {
        "规模（借款金额）": res.loan_amt,
        "成本（CPS 倒数）": 1 / res.cps_amt if res.cps_amt > 0 else 0,
        "质量（1-3授信率）": res.quality_a13_rate,
        "LTV_12m": res.ltv_12m,
        "风险（FPD 倒数）": 1 / res.fpd30_plus_rate if res.fpd30_plus_rate > 0 else 0,
    }

all_vals = pd.DataFrame(radar_vals).T
norm_df = (all_vals - all_vals.min()) / (all_vals.max() - all_vals.min() + 1e-9)
categories = list(all_vals.columns)

fig_radar = go.Figure()
colors_radar = ["#1976D2", "#4CAF50", "#FF9800", "#e53935", "#9c27b0"]

for i, (name, row) in enumerate(norm_df.iterrows()):
    vals = row.tolist() + [row.tolist()[0]]
    fig_radar.add_trace(go.Scatterpolar(
        r=vals,
        theta=categories + [categories[0]],
        fill="toself",
        name=name,
        line=dict(color=colors_radar[i % len(colors_radar)], width=2),
        opacity=0.55,
    ))

fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
    showlegend=True,
    title="方案多维度雷达图（归一化，越靠外越好）",
    height=500,
)
st.plotly_chart(fig_radar, use_container_width=True)

with st.expander("📖 如何解读雷达图？", expanded=False):
    st.markdown("""
    - **五个维度**（均已归一化到 0-1，越靠外越好）：
      - **规模**：借款金额（越大越好）
      - **成本**：CPS 倒数（CPS 越低，倒数越大，越靠外越好）
      - **质量**：1-3授信率（越高越好）
      - **LTV_12m**：12个月生命周期价值（越高越好）
      - **风险**：FPD30+ 倒数（FPD30+ 越低，倒数越大，越靠外越好）
    
    - **面积越大**：该方案综合表现越好
    - **形状越均衡**：各维度表现越平衡（无明显短板）
    - **决策建议**：
      - 若追求综合最优 → 选面积最大的方案
      - 若有特定优先级 → 关注对应维度的突出方案
      - MMM 优化方案（若有）通常在成本和质量维度有优势
    """)

st.divider()

# ─── 核心指标对比柱状图 ───────────────────────────────────────────────────────
st.subheader("📊 核心指标对比")

tab1, tab2, tab3 = st.tabs(["规模 & 成本", "质量 & 风险", "LTV & 预算"])
colors_bar = ["#1976D2", "#4CAF50", "#FF9800", "#e53935", "#9c27b0"]
names = list(scenarios.keys())

with tab1:
    fig_sc = make_subplots(rows=1, cols=2,
                            subplot_titles=["借款金额（万元，越高越好）", "CPS（越低越好）"])
    fig_sc.add_trace(go.Bar(
        x=names, y=[scenarios[n].loan_amt for n in names],
        marker_color=colors_bar[:len(names)], name="借款金额",
        text=[f"{scenarios[n].loan_amt:.1f}" for n in names], textposition="outside",
    ), row=1, col=1)
    fig_sc.add_trace(go.Bar(
        x=names, y=[scenarios[n].cps_amt for n in names],
        marker_color=colors_bar[:len(names)], name="CPS",
        text=[f"{scenarios[n].cps_amt:.4f}" for n in names], textposition="outside",
    ), row=1, col=2)
    fig_sc.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig_sc, use_container_width=True)
    with st.expander("📖 规模 & 成本解读", expanded=False):
        st.markdown("""
        - **借款金额**：规模指标，越高代表获客规模越大。激进方案通常最高，保守方案最低。
        - **CPS**（花费/借款金额）：成本指标，越低代表获客效率越高。
        - **规模 vs 成本的权衡**：增加预算通常会提升借款金额，但 CPS 可能同时上升（边际效益递减）。
          MMM 优化方案通过优化渠道分配，可能在相同总预算下同时改善规模和成本。
        """)

with tab2:
    fig_qr = make_subplots(rows=1, cols=2,
                            subplot_titles=["1-3授信率（越高越好）", "FPD30+风险率（越低越好）"])
    fig_qr.add_trace(go.Bar(
        x=names, y=[scenarios[n].quality_a13_rate for n in names],
        marker_color=colors_bar[:len(names)],
        text=[f"{scenarios[n].quality_a13_rate:.3f}" for n in names], textposition="outside",
    ), row=1, col=1)
    fig_qr.add_trace(go.Bar(
        x=names, y=[scenarios[n].fpd30_plus_rate for n in names],
        marker_color=colors_bar[:len(names)],
        text=[f"{scenarios[n].fpd30_plus_rate:.4f}" for n in names], textposition="outside",
    ), row=1, col=2)
    fig_qr.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig_qr, use_container_width=True)
    with st.expander("📖 质量 & 风险解读", expanded=False):
        st.markdown("""
        - **1-3授信率**：A卡1-3档授信数 / 申完数，反映客群质量，越高越好。
          不同渠道的客群质量差异较大（精准营销通常质量最高，商店次之）。
        - **FPD30+**：首期逾期30天以上比率，反映风险，越低越好。
        - **质量 vs 规模的权衡**：追求规模（激进方案）可能引入更多低质量客群，导致授信率下降、风险上升。
          在质量优先模式下，系数会向高质量渠道倾斜。
        """)

with tab3:
    fig_lt = make_subplots(rows=1, cols=2,
                            subplot_titles=["LTV_12m（万元，越高越好）", "总花费（万元）"])
    fig_lt.add_trace(go.Bar(
        x=names, y=[scenarios[n].ltv_12m for n in names],
        marker_color=colors_bar[:len(names)],
        text=[f"{scenarios[n].ltv_12m:.1f}" for n in names], textposition="outside",
    ), row=1, col=1)
    fig_lt.add_trace(go.Bar(
        x=names, y=[scenarios[n].total_spend for n in names],
        marker_color=colors_bar[:len(names)],
        text=[f"{scenarios[n].total_spend:.1f}" for n in names], textposition="outside",
    ), row=1, col=2)
    fig_lt.update_layout(height=380, showlegend=False)
    st.plotly_chart(fig_lt, use_container_width=True)
    with st.expander("📖 LTV & 预算解读", expanded=False):
        st.markdown("""
        - **LTV_12m**：12个月生命周期价值，反映客群的长期价值，越高越好。
          基于历史均值（LTV/借款金额）比率估算，是借款金额的线性函数。
        - **总花费**：各方案的实际总预算，可验证各方案的预算倍数是否符合预期。
        - **ROI 视角**：LTV_12m / 总花费 可以衡量长期投资回报率，
          MMM 优化方案在此指标上通常有优势（相同花费带来更高 LTV）。
        """)

st.divider()

# ─── 与基准差异瀑布图 ─────────────────────────────────────────────────────────
st.subheader("📈 与基准方案差异（%）")

diff_options = [n for n in scenario_names if n != "基准方案"]
diff_scenario = st.selectbox("选择对比方案（vs 基准方案）", diff_options,
                              help="选择要与基准方案对比的方案，查看各指标的变化幅度")
diff_res = scenarios[diff_scenario]

if diff_res.vs_baseline:
    diff_labels = {
        "total_spend":      "总花费",
        "loan_amt":         "借款金额",
        "loan_cnt":         "借款数",
        "cps_amt":          "CPS",
        "quality_a13_rate": "1-3授信率",
        "fpd30_plus_rate":  "FPD30+",
        "ltv_12m":          "LTV_12m",
    }
    diff_keys   = [k for k in diff_labels if k in diff_res.vs_baseline]
    diff_values = [diff_res.vs_baseline[k] for k in diff_keys]
    diff_names  = [diff_labels[k] for k in diff_keys]
    colors_diff = ["#4CAF50" if v >= 0 else "#e53935" for v in diff_values]
    for i, k in enumerate(diff_keys):
        if k in ["cps_amt", "fpd30_plus_rate"]:
            colors_diff[i] = "#e53935" if diff_values[i] >= 0 else "#4CAF50"

    fig_diff = go.Figure(go.Bar(
        x=diff_names, y=diff_values,
        marker_color=colors_diff,
        text=[f"{v:+.1f}%" for v in diff_values],
        textposition="outside",
    ))
    fig_diff.add_hline(y=0, line_dash="dash", line_color="gray")
    fig_diff.update_layout(
        title=f"{diff_scenario} vs 基准方案（各指标变化率%）",
        yaxis_title="变化率（%）",
        height=380,
    )
    st.plotly_chart(fig_diff, use_container_width=True)

    with st.expander("📖 如何解读差异图？", expanded=False):
        st.markdown("""
        - **绿色柱**：相对基准方案有正向改善
          - 借款金额/借款数/LTV 增加 → 好
          - CPS/FPD30+ 增加 → 坏（颜色已反转为红色）
        - **红色柱**：相对基准方案有负向变化
          - 借款金额/借款数/LTV 减少 → 坏
          - CPS/FPD30+ 减少 → 好（颜色已反转为绿色）
        - **总花费变化**：反映预算倍数（保守-20%，标准+10%，激进+30%）
        - **决策参考**：若某方案在规模提升的同时，CPS 和 FPD30+ 变化幅度较小，说明该方案效率较好
        """)

st.divider()

# ─── 人工拍板 ─────────────────────────────────────────────────────────────────
st.subheader("✅ 人工拍板")

with st.expander("📖 拍板流程说明", expanded=False):
    st.markdown("""
    **拍板流程**：
    1. 综合查看上方各维度对比结果
    2. 根据本期决策重点（规模/成本/质量）选择最优方案
    3. 填写审核人和拍板理由
    4. 点击「确认拍板」锁定方案
    5. 前往「结果联动」页面进行深度分析
    
    **拍板建议参考**：
    | 决策重点 | 建议方案 |
    |---|---|
    | 规模冲刺（大促、季末） | 激进方案 |
    | 稳健增长（常规期） | 标准方案 |
    | 成本控制（预算收紧） | 保守方案 |
    | 效率优先（基于数据） | MMM 优化方案（若有） |
    """)

col_ap1, col_ap2 = st.columns([1, 2])

with col_ap1:
    selected_plan = st.radio(
        "选择最终方案",
        scenario_names,
        index=min(2, len(scenario_names) - 1),
        help="建议综合雷达图和指标对比后选择",
    )
    reviewer = st.text_input("审核人", placeholder="请输入姓名")
    review_note = st.text_area("拍板理由 / 风险提示",
                                placeholder="例如：本期规模优先，接受 CPS 小幅上升；需关注 FPD30+ 风险...")

    if st.button("🔒 确认拍板", type="primary", use_container_width=True):
        if reviewer:
            st.session_state["approved_plan"] = {
                "scenario": selected_plan,
                "reviewer": reviewer,
                "note": review_note,
                "result": scenarios[selected_plan].to_dict(),
                "spends": {ch: getattr(base_budget, f"{ch}_spend", 0) for ch in CHANNEL_KEYS},
            }
            st.success(f"✅ 已拍板：**{selected_plan}**（审核人：{reviewer}）")
            st.markdown("""
            <div class="guide-card">
                <b>→ 下一步</b>：前往「<b>结果联动</b>」页面，对拍板方案进行敏感性分析和渠道效率深度分析。
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("请填写审核人姓名")

with col_ap2:
    if "approved_plan" in st.session_state:
        ap = st.session_state["approved_plan"]
        st.success(f"**✅ 已拍板方案：{ap['scenario']}**")
        st.markdown(f"- **审核人**：{ap['reviewer']}")
        st.markdown(f"- **拍板理由**：{ap['note'] or '无'}")
        result_df = pd.DataFrame([ap["result"]]).T
        result_df.columns = ["数值"]
        st.dataframe(result_df, use_container_width=True)
    else:
        sel_res = scenarios[selected_plan]
        st.markdown(f"**{selected_plan} 关键指标预览**")
        m1, m2, m3 = st.columns(3)
        m1.metric("借款金额（万元）", f"{sel_res.loan_amt:.1f}")
        m2.metric("CPS", f"{sel_res.cps_amt:.4f}")
        m3.metric("1-3授信率", f"{sel_res.quality_a13_rate:.3f}")
        m4, m5, m6 = st.columns(3)
        m4.metric("LTV_12m（万元）", f"{sel_res.ltv_12m:.1f}")
        m5.metric("FPD30+风险率", f"{sel_res.fpd30_plus_rate:.4f}")
        m6.metric("总花费（万元）", f"{sel_res.total_spend:.1f}")

        st.markdown("""
        <div class="guide-card">
            <b>→ 建议</b>：综合查看上方雷达图和指标对比，选择方案后填写审核人并点击「确认拍板」。
        </div>
        """, unsafe_allow_html=True)
