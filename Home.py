import streamlit as st
from core.template_manager import TemplateManager
from app.ui_utils import ensure_flow_state
from app.styles import inject_custom_css

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="信贷获客预算管理平台",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 全局样式 ====================
inject_custom_css()

# ==================== Session State 初始化 ====================
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
    "mmm_model": None,
    "operation_logs": [],
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
ensure_flow_state()

# ==================== V4.3c 五页导航 ====================
pg_input  = st.Page("pages/1_预算输入与配置.py",  title="数据准备",       icon="📋", default=True)
pg_result = st.Page("pages/2_预算推算结果.py",    title="预算工作台",     icon="📊")
pg_mmm    = st.Page("pages/mmm_模型洞察.py",      title="MMM模型洞察",    icon="🧪")
pg_logic  = st.Page("pages/4_计算逻辑手册.py",    title="计算逻辑手册",   icon="📐")
pg_export = st.Page("pages/5_导出与归档.py",      title="导出与归档",     icon="📥")

pg = st.navigation({
    "工作流": [pg_input, pg_result, pg_mmm, pg_logic, pg_export],
})

# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("#### 预算管理平台 v4.3c")

    # 工作流进度
    step_map = {
        "数据准备": 1,
        "预算工作台": 2,
        "MMM模型洞察": 3,
        "计算逻辑手册": 4,
        "导出与归档": 5,
    }
    has_data = st.session_state.get("uploaded_data") is not None
    has_result = st.session_state.get("table1_result") is not None
    progress = 0
    if has_data:
        progress = 1
    if has_result:
        progress = 2
    st.progress(progress / 5, text=f"步骤 {progress}/5")

    st.markdown("---")
    with st.expander("📖 平台说明", expanded=False):
        st.markdown("""
**工作流程：** 数据准备 → 预算工作台 → MMM洞察 → 逻辑手册 → 导出

**V01 规则引擎：** 历史系数外推，直观可解释

**MMM 统计模型：** Adstock + Hill + Optuna，捕捉饱和与滞后效应

**计算逻辑手册：** 完整公式说明，适合汇报与培训
        """)
    with st.expander("ℹ️ 参数说明", expanded=False):
        st.markdown("""
**总花费**：月度营销预算总额（万元）

**1-3 T0过件率**：1-3年龄段用户通过率

**1-8 T0CPS**：花费 / 借款额，界面按百分比展示

**T0申完成本**：每笔申请完成所需花费（元）
        """)
    st.markdown("---")
    st.caption("v4.3c 终极版 · 2026")
    st.caption("© 信贷获客预算管理平台")

pg.run()
