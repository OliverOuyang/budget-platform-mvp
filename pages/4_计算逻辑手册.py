"""V4.3c 计算逻辑手册 — 独立页面，包含 7 个逻辑说明章节。"""
from __future__ import annotations

import streamlit as st
from app.styles import inject_custom_css, render_impact_chain, render_formula_box, render_callout


inject_custom_css()

st.markdown("## 📐 计算逻辑手册")
st.caption("完整说明预算推算的计算逻辑、公式、参数来源和目标方案的影响方式。适合向领导汇报、新人理解系统、以及未来优化计算逻辑时的参考文档。")

render_callout(
    "<b>本页用途：</b>完整说明预算推算的计算逻辑、公式、参数来源和目标方案的影响方式。"
    "适合向领导汇报、新人理解系统、以及未来优化计算逻辑时的参考文档。",
    kind="info",
)

# ==================== Section 1: 总体流程 ====================
st.markdown("---")
st.markdown('<span class="logic-num">1</span> **总体流程**', unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:center;gap:8px;padding:10px 14px;border:1px solid #E0E0E0;border-radius:6px;
     margin-bottom:8px;font-size:13px;background:white;flex-wrap:wrap">
    <span>📂 上传Excel</span>
    <span style="color:#2E7D32;font-weight:700;font-size:14px">→</span>
    <span>🔍 质检+护栏检测</span>
    <span style="color:#2E7D32;font-weight:700;font-size:14px">→</span>
    <span>📐 提取历史系数</span>
    <span style="color:#2E7D32;font-weight:700;font-size:14px">→</span>
    <span>⚙️ 设定目标+参数</span>
    <span style="color:#2E7D32;font-weight:700;font-size:14px">→</span>
    <span>🔢 计算引擎</span>
    <span style="color:#2E7D32;font-weight:700;font-size:14px">→</span>
    <span>📊 结果展示</span>
</div>
""", unsafe_allow_html=True)

st.markdown("""
- **数据来源：** raw_达成情况（渠道维度月度数据）+ raw_客群首借金额（客群维度）
- **系数提取：** 自动从历史数据计算 M0/T0 比值和存量 M0 CPS
- **双引擎：** V01（规则引擎，历史系数外推）+ MMM（统计模型，Adstock+Hill 回归）
""")

# ==================== Section 2: V01 核心公式 ====================
st.markdown("---")
st.markdown('<span class="logic-num">2</span> **V01 核心公式 — Table 1（渠道维度）**', unsafe_allow_html=True)

render_formula_box([
    "{var}渠道花费{/var} {op}={/op} {var}总花费{/var} {op}×{/op} {var}渠道占比{/var}",
    "",
    "{result}T0交易额(亿){/result} {op}={/op} {var}渠道花费(万){/var} {op}/{/op} {var}CPS{/var} {op}/{/op} 10000",
    "{result}T0申完量{/result} {op}={/op} {var}渠道花费(元){/var} {op}/{/op} {var}T0申完成本(元){/var}",
    "",
    "{result}当月首登M0交易额{/result} {op}={/op} {var}T0交易额{/var} {op}×{/op} {var}M0/T0系数{/var}",
    "{result}1-3 T0授信量{/result} {op}={/op} {var}T0申完量{/var} {op}×{/op} {var}1-3过件率{/var}",
])

render_callout(
    "<b>免费渠道特殊处理：</b>CPS=0（无投放成本），T0 交易额使用历史数据外推而非上述公式计算。",
    kind="success",
)

# ==================== Section 3: Table 2 ====================
st.markdown("---")
st.markdown('<span class="logic-num">3</span> **客群汇总 — Table 2**', unsafe_allow_html=True)

render_formula_box([
    "{result}初审M0交易额{/result} {op}={/op} {var}当月首登M0(各渠道之和){/var} {op}+{/op} {var}存量首登M0{/var}",
    "{result}初审合计{/result} {op}={/op} {var}初审M0{/var} {op}+{/op} {var}初审M1+{/var}",
    "",
    "{result}整体首借交易额{/result} {op}={/op} {var}初审合计{/var} {op}+{/op} {var}非初审交易额{/var}",
    "",
    "{result}全业务CPS{/result} {op}={/op} ({var}投放花费{/var} {op}+{/op} {var}RTA费用{/var}) {op}/{/op} {var}整体首借交易额{/var}",
])

st.caption("**存量M0交易额** 和 **初审M1+** 使用历史均值（3/6月）外推，**非初审交易额** 为用户手动输入。")

# ==================== Section 4: 关键系数 ====================
st.markdown("---")
st.markdown('<span class="logic-num">4</span> **关键系数来源**', unsafe_allow_html=True)

import pandas as pd
coeff_data = pd.DataFrame([
    {"系数": "M0/T0比值", "计算方式": "最近6个月月度(M0交易额/T0交易额)的均值", "典型值": "~1.49", "稳定性": "CV≈1.5%", "说明": "M0范围大于T0，系数>1"},
    {"系数": "存量M0 CPS", "计算方式": "最近3个月月度CPS均值", "典型值": "~34.4%", "稳定性": "下降趋势", "说明": "用于计算存量M0交易额"},
    {"系数": "渠道CPS", "计算方式": "用户输入 / MMM推荐", "典型值": "各渠道不同", "稳定性": "—", "说明": "核心可调参数"},
    {"系数": "过件率", "计算方式": "用户输入 / 历史均值", "典型值": "加权~14.6%", "稳定性": "—", "说明": "影响授信量计算"},
])
st.dataframe(coeff_data, use_container_width=True, hide_index=True)

# ==================== Section 5: 目标方案影响 ====================
st.markdown("---")
st.markdown('<span class="logic-num">5</span> **目标方案如何影响计算**', unsafe_allow_html=True)

render_callout(
    "选择不同目标方向，系统自动调整不同参数，生成 3 个梯度（保守5%/标准10%/激进15%）的方案。",
    kind="warning",
)

# 降成本
with st.container(border=True):
    st.markdown("**💰 降成本**")
    render_formula_box([
        "{var}CPS_new{/var} {op}={/op} {var}CPS_old{/var} {op}×{/op} (1 {op}-{/op} {var}幅度{/var})",
        '<span style="color:#999">例: 腾讯CPS 32.5% × (1-10%) = 29.25%</span>',
    ])
    chain_html = render_impact_chain([
        {"text": "调整: CPS", "type": "param"},
        {"text": "CPS ↓", "type": "down"},
        {"text": "T0交易额 ↑", "type": "up"},
        {"text": "M0 ↑", "type": "up"},
        {"text": "首借 ↑", "type": "up"},
        {"text": "全业务CPS ↓", "type": "down"},
    ])
    st.markdown(chain_html, unsafe_allow_html=True)
    st.caption("原理：CPS 是 T0 交易额公式的分母，CPS 降低直接导致 T0 增加，连锁影响 M0 和首借。")

# 提规模
with st.container(border=True):
    st.markdown("**📈 提规模**")
    render_formula_box([
        "{var}总花费_new{/var} {op}={/op} {var}总花费_old{/var} {op}×{/op} (1 {op}+{/op} {var}幅度{/var})",
        '<span style="color:#999">例: 3,000万 × (1+10%) = 3,300万</span>',
    ])
    chain_html = render_impact_chain([
        {"text": "调整: 总预算", "type": "param"},
        {"text": "总花费 ↑", "type": "up"},
        {"text": "各渠道等比 ↑", "type": "up"},
        {"text": "T0 ↑", "type": "up"},
        {"text": "M0 ↑", "type": "up"},
        {"text": "CPS 不变", "type": "neutral"},
    ])
    st.markdown(chain_html, unsafe_allow_html=True)
    st.caption("原理：预算等比放大，CPS 不变因此效率不变，但绝对量增加。")

# 提质量
with st.container(border=True):
    st.markdown("**⭐ 提质量**")
    render_formula_box([
        "{var}过件率_new{/var} {op}={/op} {var}过件率_old{/var} {op}×{/op} (1 {op}+{/op} {var}幅度{/var})",
        '<span style="color:#999">例: 14% × (1+10%) = 15.4%</span>',
    ])
    chain_html = render_impact_chain([
        {"text": "调整: 过件率", "type": "param"},
        {"text": "过件率 ↑", "type": "up"},
        {"text": "授信量 ↑", "type": "up"},
        {"text": "结构优化", "type": "up"},
        {"text": "T0交易额 不直接变化", "type": "neutral"},
    ])
    st.markdown(chain_html, unsafe_allow_html=True)
    st.caption("原理：过件率影响授信量（1-3授信 = 申完量 × 过件率），不直接改变 T0 交易额公式。")

# ==================== Section 6: MMM 方法论 ====================
st.markdown("---")
st.markdown('<span class="logic-num">6</span> **MMM 方法论简述**', unsafe_allow_html=True)

col_model, col_compare = st.columns(2)

with col_model:
    st.markdown("**模型结构**")
    render_formula_box([
        "{result}y{/result} {op}={/op} {var}intercept{/var} {op}+{/op} {var}trend{/var} {op}+{/op} Σ {var}coeff_i{/var} {op}×{/op} Hill(Adstock({var}spend_i{/var}))",
    ])
    st.markdown("""
- **Adstock 变换：** Weibull PDF 衰减，模拟广告滞后效应
- **Hill 饱和变换：** S 曲线，模拟边际效益递减
- **回归方法：** Ridge 回归，非负系数约束
- **超参优化：** Optuna TPE，300 轮试验
""")

with col_compare:
    st.markdown("**V01 vs MMM 方法论差异**")
    compare_data = pd.DataFrame([
        {"对比项": "方法", "V01 规则引擎": "历史系数外推", "MMM 统计模型": "Adstock+Hill回归"},
        {"对比项": "数据", "V01 规则引擎": "月度渠道数据", "MMM 统计模型": "周度花费时序"},
        {"对比项": "优势", "V01 规则引擎": "直观可解释", "MMM 统计模型": "捕捉饱和+滞后"},
        {"对比项": "局限", "V01 规则引擎": "假设线性关系", "MMM 统计模型": "依赖数据量"},
        {"对比项": "适用", "V01 规则引擎": "稳态预算估算", "MMM 统计模型": "渠道优化分配"},
    ])
    st.dataframe(compare_data, use_container_width=True, hide_index=True)

# ==================== Section 7: 护栏指标体系 ====================
st.markdown("---")
st.markdown('<span class="logic-num">7</span> **护栏指标体系**', unsafe_allow_html=True)

st.caption('护栏指标从上传的 Excel 数据中自动检测，通过 validate_guardrail_flexible() 函数扫描列名匹配。可用指标自动加入监控，缺失指标标为「无数据」。')

guardrail_data = pd.DataFrame([
    {"指标": "FPD30", "含义": "首次逾期30天率", "阈值": "<5%", "用途": "短期资产质量监控"},
    {"指标": "首借终损率", "含义": "首次借款最终坏账率", "阈值": "<10%", "用途": "首借资产质量约束"},
    {"指标": "复借终损率", "含义": "复借用户最终坏账率", "阈值": "<8%", "用途": "复借资产质量约束"},
    {"指标": "复借交易额", "含义": "复借用户交易总额", "阈值": "趋势监控", "用途": "业务规模健康度"},
    {"指标": "首借件均", "含义": "首借平均交易金额", "阈值": "趋势监控", "用途": "客群质量指标"},
    {"指标": "复借件均", "含义": "复借平均交易金额", "阈值": "趋势监控", "用途": "客群质量指标"},
    {"指标": "渠道LTV", "含义": "用户生命周期价值", "阈值": "趋势监控", "用途": "长期ROI评估"},
])
st.dataframe(guardrail_data, use_container_width=True, hide_index=True)
