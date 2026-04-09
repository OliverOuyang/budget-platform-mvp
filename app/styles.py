"""V4.3c 全局样式注入 — 绿色主题 + 卡片/指标/影响链路组件"""
import streamlit as st


def inject_custom_css():
    """注入 V4.3c 绿色主题 CSS，匹配线稿设计。"""
    st.markdown("""
<style>
/* ===== V4.3c Green Theme ===== */
:root {
    --v43-primary: #1A3A2A;
    --v43-accent: #2E7D32;
    --v43-accent-light: #E8F5E9;
    --v43-purple: #7B1FA2;
    --v43-purple-light: #F3E5F5;
    --v43-info: #1976D2;
    --v43-info-light: #E3F2FD;
    --v43-warning: #F57C00;
    --v43-warning-light: #FFF3E0;
    --v43-danger: #D32F2F;
    --v43-danger-light: #FFEBEE;
    --v43-border: #E0E0E0;
    --v43-bg: #FAFAF8;
    --v43-surface: #FFFFFF;
}

/* Sidebar theming */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1A3A2A 0%, #1E4D35 100%);
}
[data-testid="stSidebar"],
[data-testid="stSidebar"] * {
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] .stSelectbox label {
    color: rgba(255,255,255,0.7) !important;
}
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] caption {
    color: rgba(255,255,255,0.55) !important;
}
[data-testid="stSidebar"] a {
    color: rgba(255,255,255,0.95) !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: rgba(255,255,255,0.85) !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.15) !important;
}
[data-testid="stSidebar"] .stProgress > div > div {
    background-color: rgba(255,255,255,0.2) !important;
}
[data-testid="stSidebar"] .stProgress > div > div > div {
    background-color: #66BB6A !important;
}

/* Main background */
.stApp {
    background-color: #FAFAF8;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: white;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    padding: 12px 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.3rem;
    font-weight: 700;
}

/* Decision card */
.decision-card {
    background: linear-gradient(135deg, #E8F5E9, #F1F8E9);
    border: 1px solid #C8E6C9;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}
.decision-headline {
    font-size: 14px;
    font-weight: 700;
    color: #1A3A2A;
    margin-bottom: 6px;
}

/* Smart banner */
.smart-banner {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
    border-radius: 8px;
    background: linear-gradient(135deg, #E3F2FD, #E8F5E9);
    border: 1px solid #B2DFDB;
    margin-bottom: 12px;
}

/* Impact chain pills */
.impact-chain {
    display: flex;
    align-items: center;
    gap: 0;
    margin: 6px 0;
    flex-wrap: wrap;
}
.impact-node {
    padding: 4px 10px;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
    display: inline-block;
    margin: 2px 0;
}
.impact-node.param { background: #E3F2FD; color: #1976D2; }
.impact-node.up { background: #E8F5E9; color: #2E7D32; }
.impact-node.down { background: #FFEBEE; color: #D32F2F; }
.impact-node.neutral { background: #F5F5F5; color: #999; }
.impact-arrow { padding: 0 4px; color: #2E7D32; font-weight: 700; font-size: 14px; }

/* Status badges */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 3px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
}
.status-ok { background: #E8F5E9; color: #2E7D32; }
.status-warn { background: #FFF3E0; color: #F57C00; }
.status-bad { background: #FFEBEE; color: #D32F2F; }

/* Callout boxes */
.callout {
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 10px;
    border-left: 3px solid;
}
.callout-info { background: #E3F2FD; border-color: #1976D2; color: #0D47A1; }
.callout-success { background: #E8F5E9; border-color: #2E7D32; color: #1B5E20; }
.callout-warning { background: #FFF3E0; border-color: #F57C00; color: #E65100; }
.callout-mmm { background: #F3E5F5; border-color: #7B1FA2; color: #4A148C; }

/* Formula box */
.formula-box {
    background: #F8F9FA;
    border: 1px solid #E0E0E0;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 8px;
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.8;
}
.formula-box .var { color: #1976D2; font-weight: 700; }
.formula-box .op { color: #999; }
.formula-box .result { color: #2E7D32; font-weight: 700; }

/* Risk cards */
.risk-card {
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #E0E0E0;
    text-align: center;
}
.risk-card.ok { background: #E8F5E9; border-color: #A5D6A7; }
.risk-card.warn { background: #FFF3E0; border-color: #FFCC80; }
.risk-card.bad { background: #FFEBEE; border-color: #EF9A9A; }

/* Guardrail grid */
.guardrail-item {
    padding: 8px;
    border-radius: 6px;
    text-align: center;
    border: 1px solid #E0E0E0;
}
.guardrail-item.detected { border-color: #A5D6A7; background: #E8F5E9; }
.guardrail-item.missing { border-style: dashed; }

/* Goal cards */
.goal-card {
    padding: 10px;
    border: 2px solid #E0E0E0;
    border-radius: 8px;
    cursor: pointer;
    text-align: center;
    transition: 0.2s;
}
.goal-card:hover, .goal-card.active {
    border-color: #2E7D32;
    background: #E8F5E9;
}

/* Export option cards */
.export-option {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 1px solid #E0E0E0;
    border-radius: 8px;
    margin-bottom: 8px;
    transition: 0.2s;
}
.export-option:hover { border-color: #2E7D32; background: #E8F5E9; }

/* Saturation bar */
.sat-bar-wrap {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 5px;
}
.sb-track {
    flex: 1;
    height: 7px;
    background: #E8E0EE;
    border-radius: 4px;
    overflow: hidden;
}
.sb-fill { height: 100%; border-radius: 4px; }

/* What-if buttons */
.whatif-btn {
    padding: 6px 12px;
    border: 1px solid #E0E0E0;
    border-radius: 16px;
    font-size: 12px;
    font-weight: 600;
    display: inline-block;
    margin: 2px;
}

/* Logic section numbering */
.logic-num {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: #2E7D32;
    color: white;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    flex-shrink: 0;
    margin-right: 8px;
}

/* MMM badge */
.badge-mmm {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    background: #F3E5F5;
    color: #7B1FA2;
}

/* Better tab styling */
.stTabs [data-baseweb="tab-list"] {
    gap: 0px;
    border-bottom: 2px solid #E0E0E0;
}
.stTabs [data-baseweb="tab"] {
    padding: 8px 16px;
    font-size: 13px;
}
.stTabs [aria-selected="true"] {
    border-bottom-color: #2E7D32 !important;
    color: #2E7D32 !important;
}

/* Compact data editor */
[data-testid="stDataEditor"] {
    font-size: 12px;
}

/* Progress bar accent */
.stProgress > div > div > div {
    background-color: #2E7D32;
}
</style>
""", unsafe_allow_html=True)


def render_impact_chain(nodes: list[dict]) -> str:
    """Render an impact chain as HTML pills.

    Each node: {"text": "CPS ↓", "type": "up|down|param|neutral"}
    """
    parts = []
    for i, node in enumerate(nodes):
        css_class = f"impact-node {node.get('type', 'neutral')}"
        parts.append(f'<span class="{css_class}">{node["text"]}</span>')
        if i < len(nodes) - 1:
            parts.append('<span class="impact-arrow">→</span>')
    return f'<div class="impact-chain">{"".join(parts)}</div>'


def render_status_badge(text: str, status: str = "ok") -> str:
    """Render an inline status badge. status: ok, warn, bad."""
    return f'<span class="status-badge status-{status}">{text}</span>'


def render_callout(text: str, kind: str = "info") -> None:
    """Render a styled callout box. kind: info, success, warning, mmm."""
    st.markdown(f'<div class="callout callout-{kind}">{text}</div>', unsafe_allow_html=True)


def render_formula_box(lines: list[str]) -> None:
    """Render a formula box with styled variables.

    Use {var}text{/var}, {op}text{/op}, {result}text{/result} for styling.
    """
    formatted = []
    for line in lines:
        line = line.replace("{var}", '<span class="var">').replace("{/var}", "</span>")
        line = line.replace("{op}", '<span class="op">').replace("{/op}", "</span>")
        line = line.replace("{result}", '<span class="result">').replace("{/result}", "</span>")
        formatted.append(f"<div>{line}</div>")
    st.markdown(f'<div class="formula-box">{"".join(formatted)}</div>', unsafe_allow_html=True)


def render_risk_card(title: str, value: str, threshold: str, status: str = "ok") -> str:
    """Return HTML for a risk card. status: ok, warn, bad."""
    return f'''<div class="risk-card {status}">
        <div style="font-size:11px;color:#666;margin-bottom:2px">{title}</div>
        <div style="font-size:20px;font-weight:700">{value}</div>
        <div style="font-size:10px;color:#999">{threshold}</div>
    </div>'''
