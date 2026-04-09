"""
数据加载和验证模块
负责从Excel文件加载数据、验证结构、提取关键参数
"""

from typing import Tuple, Dict, List
import pandas as pd
import numpy as np

from app.config import REQUIRED_SHEETS, CHANNEL_NAMES

# Note: 'future.no_silent_downcasting' removed — modern pandas (>=2.0) no longer
# performs silent downcasting by default, so this global option is unnecessary.

def load_excel(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    加载Excel文件中的两个数据表

    Args:
        file_path: Excel文件路径

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (raw_达成情况, raw_客群首借金额)

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: Sheet不存在或格式错误
    """
    try:
        # 读取两个Sheet
        df_raw1 = pd.read_excel(file_path, sheet_name='raw_达成情况')
        df_raw2 = pd.read_excel(file_path, sheet_name='raw_客群首借金额')

        # 处理'\N' -> NaN转换
        df_raw1 = df_raw1.replace('\\N', np.nan)
        df_raw2 = df_raw2.replace('\\N', np.nan)

        return df_raw1, df_raw2

    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {file_path}")
    except ValueError as e:
        raise ValueError(f"Excel文件格式错误: {str(e)}")


def validate_excel_structure(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """
    验证Excel文件结构是否符合要求

    Args:
        df1: raw_达成情况 DataFrame
        df2: raw_客群首借金额 DataFrame

    Returns:
        bool: 验证通过返回True

    Raises:
        ValueError: 验证失败时抛出详细错误信息
    """
    # 获取必需列配置
    sheet1_config = REQUIRED_SHEETS['raw_达成情况']
    sheet2_config = REQUIRED_SHEETS['raw_客群首借金额']

    # 检查第一张表
    missing_cols_1 = set(sheet1_config['required_columns']) - set(df1.columns)
    if missing_cols_1:
        raise ValueError(
            f"raw_达成情况 缺少必需列: {', '.join(missing_cols_1)}\n"
            f"当前列: {', '.join(df1.columns.tolist())}"
        )

    # 检查第二张表
    missing_cols_2 = set(sheet2_config['required_columns']) - set(df2.columns)
    if missing_cols_2:
        raise ValueError(
            f"raw_客群首借金额 缺少必需列: {', '.join(missing_cols_2)}\n"
            f"当前列: {', '.join(df2.columns.tolist())}"
        )

    # 检查数据是否为空
    if df1.empty:
        raise ValueError("raw_达成情况 表为空")
    if df2.empty:
        raise ValueError("raw_客群首借金额 表为空")

    return True


def extract_last_month_data(df: pd.DataFrame) -> Dict:
    """
    从raw_达成情况提取最新月份数据,用于预填充参数

    Args:
        df: raw_达成情况 DataFrame

    Returns:
        Dict: {渠道类别: {参数名: 值}}
        示例: {
            '腾讯': {
                '1-3t0过件率': 0.45,
                '1-8t0cps': 1200,
                '1-8t0过件率': 0.38,
                't0申完成本': 150,
                '1-7过件率': 0.42,
                '花费': 3200000
            },
            ...
        }
    """
    # 处理空DataFrame
    if df.empty or '月份' not in df.columns:
        return {}

    # 获取最新月份
    df_clean = df.dropna(subset=['月份'])
    if df_clean.empty:
        return {}

    latest_month = df_clean['月份'].max()

    # 筛选最新月份数据
    df_latest = df_clean[df_clean['月份'] == latest_month].copy()

    # 提取各渠道数据
    result = {}

    for _, row in df_latest.iterrows():
        channel = row.get('渠道类别')
        if pd.isna(channel) or channel not in CHANNEL_NAMES:
            continue

        # 提取关键参数,处理可能的缺失值
        params = {}

        # 1-3t0过件率
        if '1-3t0过件率' in row and not pd.isna(row['1-3t0过件率']):
            params['1-3t0过件率'] = float(row['1-3t0过件率'])

        # 1-8t0cps
        if '1-8t0cps' in row and not pd.isna(row['1-8t0cps']):
            params['1-8t0cps'] = float(row['1-8t0cps'])

        # 1-8t0过件率
        if '1-8t0过件率' in row and not pd.isna(row['1-8t0过件率']):
            params['1-8t0过件率'] = float(row['1-8t0过件率'])

        # t0申完成本
        if 't0申完成本' in row and not pd.isna(row['t0申完成本']):
            params['t0申完成本'] = float(row['t0申完成本'])

        # 最新月花费，用于结果页历史花费基线和结构参考
        if '花费' in row and not pd.isna(row['花费']):
            params['花费'] = float(row['花费'])

        # 1-7过件率 (可能不存在)
        if '1-7过件率' in df.columns and '1-7过件率' in row and not pd.isna(row['1-7过件率']):
            params['1-7过件率'] = float(row['1-7过件率'])

        if params:
            result[channel] = params

    return result


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
