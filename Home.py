import streamlit as st
from core.template_manager import TemplateManager
from app.ui_utils import ensure_flow_state

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="信贷获客预算管理平台",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== Session State 初始化（V01 部分）====================
defaults = {
    "uploaded_data": None,
    "table1_result": None,
    "table2_result": None,
    "parameters": None,
    "coefficients": None,
    "previous_parameters": None,
    "previous_table1_result": None,
    "previous_table2_result": None,
    "template_manager": TemplateManager(),
    "current_template_params": {},
    "comparison_scenarios": {},
    "last_file_id": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
ensure_flow_state()

# ==================== 导航配置（两组）====================
# 第一组：V01 规则推导预算
pg_input  = st.Page("pages/1_预算输入与配置.py",  title="数据上传与检查",  icon="📋", default=True)
pg_result = st.Page("pages/2_预算推算结果.py",    title="预算推算结果",    icon="📊")

# 第二组：MMM 预算管理（带模型）
pg_data   = st.Page("pages/mmm_1_数据检查.py",    title="数据检查",        icon="🔍")
pg_mmm    = st.Page("pages/mmm_2_MMM洞察.py",     title="MMM 模型洞察",    icon="🧪")
pg_budget = st.Page("pages/mmm_3_预算调整.py",    title="预算调整",        icon="💰")
pg_plan   = st.Page("pages/mmm_4_方案对比.py",    title="方案对比",        icon="📈")
pg_link   = st.Page("pages/mmm_5_结果联动.py",    title="结果联动",        icon="🔗")

# Tab 子模块（不在导航中显示，仅供页面内部调用）
_tab_pages = [
    st.Page("pages/_tab_overview.py",           title="总览"),
    st.Page("pages/_tab_channel_result.py",     title="渠道结果"),
    st.Page("pages/_tab_customer_result.py",    title="客群结果"),
    st.Page("pages/_tab_coefficient_trace.py",  title="系数追溯"),
    st.Page("pages/_tab_scenario_manager.py",   title="方案管理"),
]

pg = st.navigation({
    "📌 V01 · 规则推导预算": [pg_input, pg_result],
    "🤖 MMM · 模型驱动预算": [pg_data, pg_mmm, pg_budget, pg_plan, pg_link],
})

# ==================== 共享侧边栏说明 ====================
with st.sidebar:
    st.markdown("---")
    with st.expander("📖 平台说明", expanded=False):
        st.markdown("""
**V01 · 规则推导预算**
先上传业务 Excel 并检查数据质量、统计特征和趋势分布，
再进入预算推算结果页参考最新月基线配置参数、运行计算并查看结果拆解，
适合做规则口径下的快速预算推算与方案试算。

---

**MMM · 模型驱动预算**
基于 Marketing Mix Modeling，
通过 Adstock + Hill 饱和曲线 + Optuna 优化，
量化各渠道 ROI，给出数据驱动的预算分配建议。
        """)
    with st.expander("ℹ️ 参数说明", expanded=False):
        st.markdown("""
**总花费**：月度营销预算总额（万元）

**1-3 T0过件率**：1-3年龄段用户通过率

**1-8 T0CPS**：花费 / 借款额，界面按百分比展示

**T0申完成本**：每笔申请完成所需花费（元）
        """)
    st.markdown("---")
    st.markdown("[← 返回 React 介绍页](http://localhost:3000)")
    st.caption("http://localhost:3000")
    st.markdown("---")
    st.caption("© 2026 信贷获客预算管理平台")

pg.run()
