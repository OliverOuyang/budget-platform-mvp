"""
护栏指标模块
负责护栏指标的定义、加载和评估
"""

from typing import Tuple, Dict, List
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Guardrail indicator support (Phase 1 — display only)
# ---------------------------------------------------------------------------

DEFAULT_GUARDRAIL_THRESHOLDS = {
    "FPD30": 0.05,        # > 5% triggers red highlight
    "首借终损率": 0.10,    # > 10%
    "复借终损率": 0.08,    # > 8%
}

GUARDRAIL_REQUIRED_COLUMNS = ["月份", "渠道类别", "FPD30", "首借终损率", "复借终损率", "复借交易额", "渠道LTV"]


def validate_guardrail_structure(df: pd.DataFrame) -> Tuple[bool, list]:
    """Check that all required guardrail columns exist.

    Returns
    -------
    (is_valid, missing_columns)
    """
    missing = [c for c in GUARDRAIL_REQUIRED_COLUMNS if c not in df.columns]
    return (len(missing) == 0, missing)


def load_guardrail_data(source) -> pd.DataFrame:
    """Load guardrail indicator data from DataFrame, CSV path, or Excel path.

    Parameters
    ----------
    source : pd.DataFrame | str | Path | None
        - DataFrame: validate and return
        - str/Path ending .csv: read CSV then validate
        - str/Path ending .xlsx/.xls: read first sheet then validate
        - None: return empty DataFrame with correct columns

    Returns
    -------
    pd.DataFrame with columns: 月份, 渠道类别, FPD30, 首借终损率, 复借终损率, 复借交易额, 渠道LTV

    Raises
    ------
    ValueError if required columns are missing (lists the missing columns)
    """
    if source is None:
        return pd.DataFrame(columns=GUARDRAIL_REQUIRED_COLUMNS)

    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        path = str(source)
        if path.endswith(".csv"):
            df = pd.read_csv(path)
        elif path.endswith((".xlsx", ".xls")):
            df = pd.read_excel(path, sheet_name=0)
        else:
            raise ValueError(f"不支持的文件格式: {path}，请提供 .csv 或 .xlsx 文件")

    # Normalise sentinel values consistently with load_excel()
    df = df.replace("\\N", np.nan)

    is_valid, missing = validate_guardrail_structure(df)
    if not is_valid:
        raise ValueError(f"护栏指标数据缺少必需列: {', '.join(missing)}")

    return df


# ---------------------------------------------------------------------------
# Extended guardrail metrics (Phase 2 — real data support)
# ---------------------------------------------------------------------------

GUARDRAIL_METRICS: Dict[str, Dict] = {
    # Risk metrics
    "首借终损率": {"threshold": 0.10, "direction": "lower_is_better", "format": "pct", "category": "风险"},
    "复借终损率": {"threshold": 0.08, "direction": "lower_is_better", "format": "pct", "category": "风险"},
    "合计终损率": {"threshold": 0.08, "direction": "lower_is_better", "format": "pct", "category": "风险"},
    "FPD30": {"threshold": 0.05, "direction": "lower_is_better", "format": "pct", "category": "风险"},
    # Cost metrics
    "全量t0_cps": {"threshold": 0.15, "direction": "lower_is_better", "format": "pct", "category": "成本"},
    "t0申完成本": {"threshold": 2000, "direction": "lower_is_better", "format": "number", "category": "成本"},
    # Quality metrics
    "安全t0过件率": {"threshold": 0.15, "direction": "higher_is_better", "format": "pct", "category": "质量"},
    "全量t0过件率": {"threshold": 0.30, "direction": "higher_is_better", "format": "pct", "category": "质量"},
    # Volume metrics
    "首借交易额": {"threshold": None, "direction": "higher_is_better", "format": "currency", "category": "规模"},
    "复借交易额": {"threshold": None, "direction": "higher_is_better", "format": "currency", "category": "规模"},
    "合计交易额": {"threshold": None, "direction": "higher_is_better", "format": "currency", "category": "规模"},
}


def validate_guardrail_flexible(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Check which guardrail metrics are available vs missing.

    Returns (available_metrics, missing_metrics) — never raises.
    """
    available = [m for m in GUARDRAIL_METRICS if m in df.columns]
    missing = [m for m in GUARDRAIL_METRICS if m not in df.columns]
    return available, missing


def load_guardrail_from_conversion_data(csv_path) -> pd.DataFrame:
    """Load guardrail data from the 分渠道转化 CSV.

    Extracts both summary-level (渠道类别 is NaN) and channel-level
    guardrail metrics.

    Parameters
    ----------
    csv_path : str or Path

    Returns
    -------
    pd.DataFrame with columns: 月份, 渠道类别, plus all available guardrail metrics
    """
    df = pd.read_csv(str(csv_path), encoding='utf-8-sig')
    df = df.replace('\\N', np.nan)

    # Select columns that exist in GUARDRAIL_METRICS + identifiers
    id_cols = ['月份', '渠道类别']
    metric_cols = [m for m in GUARDRAIL_METRICS if m in df.columns]

    result = df[id_cols + metric_cols].copy()

    # Convert numeric columns
    for col in metric_cols:
        result[col] = pd.to_numeric(result[col], errors='coerce')

    return result


def evaluate_guardrails(df: pd.DataFrame) -> pd.DataFrame:
    """Evaluate guardrail metrics against thresholds.

    Returns DataFrame with columns: 指标, 当前值, 阈值, 状态(正常/预警/超限), 类别
    """
    results = []
    for metric, config in GUARDRAIL_METRICS.items():
        if metric not in df.columns:
            continue
        current_val = df[metric].iloc[-1] if len(df) > 0 else None  # latest month
        if current_val is None or pd.isna(current_val):
            continue

        threshold = config["threshold"]
        if threshold is None:
            status = "正常"
        elif config["direction"] == "lower_is_better":
            status = "超限" if current_val > threshold * 1.2 else "预警" if current_val > threshold else "正常"
        else:
            status = "超限" if current_val < threshold * 0.8 else "预警" if current_val < threshold else "正常"

        results.append({
            "指标": metric,
            "当前值": current_val,
            "阈值": threshold,
            "状态": status,
            "类别": config["category"],
        })

    return pd.DataFrame(results)
