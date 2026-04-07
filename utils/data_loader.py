"""数据加载与预处理工具"""
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path

MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "mock_weekly.csv"

CHANNEL_NAMES = {
    "tencent_moments":      "腾讯·朋友圈",
    "tencent_video":        "腾讯·视频号",
    "tencent_wechat":       "腾讯·公小",
    "tencent_search":       "腾讯·搜索",
    "douyin":               "抖音",
    "app_store":            "商店",
    "precision_marketing":  "精准营销",
}

CHANNEL_KEYS = list(CHANNEL_NAMES.keys())

METRIC_LABELS = {
    "total_spend":        "总花费（万元）",
    "first_login_cnt":    "首登数",
    "apply_start_cnt":    "发起数",
    "apply_submit_cnt":   "申完数",
    "credit_cnt":         "授信数",
    "credit_a13_cnt":     "A卡1-3授信数",
    "loan_cnt":           "借款数",
    "loan_amt":           "借款金额（万元）",
    "credit_amt":         "授信金额（万元）",
    "quality_a13_rate":   "1-3授信率",
    "cps_amt":            "CPS（万元/万元）",
    "ltv_12m":            "LTV_12m（万元）",
    "ltv_24m":            "LTV_24m（万元）",
    "fpd30_plus_rate":    "FPD30+风险率",
}


@st.cache_data
def load_mock_data() -> pd.DataFrame:
    if not MOCK_DATA_PATH.exists():
        import subprocess, sys
        gen_script = Path(__file__).parent.parent / "data" / "generate_mock.py"
        subprocess.run([sys.executable, str(gen_script)], check=True)
    df = pd.read_csv(MOCK_DATA_PATH, parse_dates=["week_start"])
    return df


def load_uploaded_data(uploaded_file) -> pd.DataFrame:
    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file, parse_dates=["week_start"])
    else:
        df = pd.read_excel(uploaded_file)
        if "week_start" in df.columns:
            df["week_start"] = pd.to_datetime(df["week_start"])
    return df


def validate_data(df: pd.DataFrame) -> dict:
    """基础数据校验，返回校验结果字典"""
    required_cols = [
        "week_start", "total_spend", "loan_amt", "apply_submit_cnt",
        "credit_a13_cnt", "loan_cnt", "credit_cnt",
    ]
    missing = [c for c in required_cols if c not in df.columns]
    issues = []
    if missing:
        issues.append(f"缺少必要列：{missing}")
    null_counts = df.isnull().sum()
    null_cols = null_counts[null_counts > 0].to_dict()
    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "null_cols": null_cols,
        "row_count": len(df),
        "col_count": len(df.columns),
        "time_range": (df["week_start"].min(), df["week_start"].max()) if "week_start" in df.columns else None,
    }
