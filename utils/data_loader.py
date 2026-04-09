"""数据加载与预处理工具"""
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path

MOCK_DATA_PATH = Path(__file__).parent.parent / "data" / "mock_weekly.csv"
REAL_DATA_PATH = Path(__file__).parent.parent / "data" / "分渠道转化_贷前合并_20260407_1810.csv"
WEEKLY_DATA_PATH = Path(__file__).parent.parent / "data" / "四月数据.csv"

CHANNEL_NAMES = {
    "tencent_moments":      "腾讯·朋友圈",
    "tencent_video":        "腾讯·视频号",
    "tencent_wechat":       "腾讯·公小",
    "tencent_search":       "腾讯·搜索",
    "douyin":               "抖音",
    "app_store":            "商店",
    "precision_marketing":  "精准营销",
}

# Real data uses 4 paid channels (V01 granularity)
REAL_CHANNEL_NAMES = {
    "tencent":              "腾讯",
    "douyin":               "抖音",
    "precision_marketing":  "精准营销",
    "app_store":            "付费商店",
}

# Weekly data: 4 paid + 1 organic (免费渠道)
WEEKLY_CHANNEL_NAMES = {
    "tencent":              "腾讯",
    "douyin":               "抖音",
    "precision_marketing":  "精准营销",
    "app_store":            "付费商店",
    "free_channel":         "免费渠道",
}

CHANNEL_KEYS = list(CHANNEL_NAMES.keys())
REAL_CHANNEL_KEYS = list(REAL_CHANNEL_NAMES.keys())
WEEKLY_CHANNEL_KEYS = list(WEEKLY_CHANNEL_NAMES.keys())

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


@st.cache_data
def load_real_data(csv_path: str = None) -> pd.DataFrame:
    """Load and transform real business data for MMM training.

    Combines: 分渠道转化 CSV → transform → merge external macro data.
    Returns DataFrame with 4 channel _spend columns + DV + context variables.
    """
    from core.real_data_transformer import transform_real_data
    from core.external_data import fetch_macro_data, merge_external_data, add_holiday_flag

    if csv_path is None:
        csv_path = str(REAL_DATA_PATH)

    if not Path(csv_path).exists():
        raise FileNotFoundError(
            f"真实数据文件不存在: {csv_path}\n"
            "请将分渠道转化CSV文件放置到 data/ 目录下，或切换为内置Mock数据。"
        )

    df = transform_real_data(csv_path)
    macro = fetch_macro_data()
    df = merge_external_data(df, macro)
    df = add_holiday_flag(df)
    return df


@st.cache_data
def load_weekly_data(csv_path: str = None) -> pd.DataFrame:
    """Load and transform weekly business data for MMM training.

    Combines: 四月数据.csv → transform_weekly_data → add Prophet features.
    Returns DataFrame with 4 paid channel _spend columns + organic + DV + context.
    """
    from core.real_data_transformer import transform_weekly_data
    from core.external_data import add_prophet_features, add_stl_features

    if csv_path is None:
        csv_path = str(WEEKLY_DATA_PATH)

    if not Path(csv_path).exists():
        raise FileNotFoundError(
            f"周度数据文件不存在: {csv_path}\n"
            "请将四月数据CSV文件放置到 data/ 目录下，或切换为其他数据来源。"
        )

    df = transform_weekly_data(csv_path)
    df = add_prophet_features(df, "week_start")
    # STL decomposition for nonlinear trend/seasonal (replaces linear Fourier when available)
    dv_col = "dv_first_loan_amt" if "dv_first_loan_amt" in df.columns else "dv_total_loan_amt"
    df = add_stl_features(df, dv_col=dv_col, date_col="week_start")
    return df
