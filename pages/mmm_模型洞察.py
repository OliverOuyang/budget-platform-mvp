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

from pages._mmm_config import render_mmm_config
from pages._mmm_summary import render_model_summary
from pages._mmm_tab_fit import render_tab_fit
from pages._mmm_tab_contribution import render_tab_contribution
from pages._mmm_tab_response import render_tab_response
from pages._mmm_tab_optimization import render_tab_optimization

# ─── 页面标题 ─────────────────────────────────────────────────────────────────
st.title("🧪 MMM 模型洞察")
st.markdown("训练和管理 MMM 模型。训练完成后，模型参数自动提供给预算推算结果页使用。")

# ─── 配置、数据加载、训练 ─────────────────────────────────────────────────────
_df_container = {}
model, df, dv_col, data_mode, ch_names, time_col, period_label = render_mmm_config(_df_container)

if model is None:
    st.info("请先训练模型或加载已有模型。")
    st.stop()

# ─── 模型结论摘要 + 训练透明度面板 ───────────────────────────────────────────
render_model_summary(model, df, dv_col, ch_names, data_mode, time_col)

# ─── 4 个 Tab ─────────────────────────────────────────────────────────────────
tab0, tab1, tab2, tab3 = st.tabs([
    "📈 拟合效果",
    "🍰 渠道贡献",
    "📉 响应曲线",
    "💡 预算优化",
])

with tab0:
    render_tab_fit(model, df, dv_col, ch_names, data_mode, time_col, period_label)

with tab1:
    render_tab_contribution(model, df, ch_names, data_mode, time_col, period_label)

with tab2:
    render_tab_response(model, df, ch_names, data_mode, period_label)

with tab3:
    render_tab_optimization(model, df, dv_col, ch_names, data_mode, time_col, period_label)
