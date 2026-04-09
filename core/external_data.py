"""
外部宏观数据模块
负责获取 CPI、LPR、M2 等宏观经济指标，以及节假日标记
用于 MMM 模型的控制变量
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# 硬编码备用数据 (2025-01 ~ 2026-04)
FALLBACK_DATA = {
    "2025-01": {"cpi_yoy": 0.5, "lpr_1y": 3.10, "m2_yoy": 7.5},
    "2025-02": {"cpi_yoy": 0.7, "lpr_1y": 3.10, "m2_yoy": 7.8},
    "2025-03": {"cpi_yoy": 0.4, "lpr_1y": 3.10, "m2_yoy": 8.0},
    "2025-04": {"cpi_yoy": 0.3, "lpr_1y": 3.10, "m2_yoy": 8.2},
    "2025-05": {"cpi_yoy": 0.2, "lpr_1y": 3.10, "m2_yoy": 8.0},
    "2025-06": {"cpi_yoy": 0.2, "lpr_1y": 3.10, "m2_yoy": 7.8},
    "2025-07": {"cpi_yoy": 0.3, "lpr_1y": 3.00, "m2_yoy": 7.9},
    "2025-08": {"cpi_yoy": 0.4, "lpr_1y": 3.00, "m2_yoy": 8.0},
    "2025-09": {"cpi_yoy": 0.5, "lpr_1y": 3.00, "m2_yoy": 8.1},
    "2025-10": {"cpi_yoy": 0.6, "lpr_1y": 3.00, "m2_yoy": 8.2},
    "2025-11": {"cpi_yoy": 0.5, "lpr_1y": 3.00, "m2_yoy": 8.3},
    "2025-12": {"cpi_yoy": 0.4, "lpr_1y": 3.00, "m2_yoy": 8.5},
    "2026-01": {"cpi_yoy": 0.6, "lpr_1y": 2.90, "m2_yoy": 8.6},
    "2026-02": {"cpi_yoy": 0.5, "lpr_1y": 2.90, "m2_yoy": 8.8},
    "2026-03": {"cpi_yoy": 0.4, "lpr_1y": 2.90, "m2_yoy": 9.0},
    "2026-04": {"cpi_yoy": 0.3, "lpr_1y": 2.90, "m2_yoy": 9.1},
}

# 节假日/大促月份标记
HOLIDAY_MONTHS = {
    "2025-01": 1,  # 春节
    "2025-02": 1,  # 春节
    "2025-05": 1,  # 五一
    "2025-06": 1,  # 618大促
    "2025-10": 1,  # 国庆
    "2025-11": 1,  # 双11
    "2025-12": 1,  # 双12
    "2026-01": 1,  # 春节
    "2026-02": 1,  # 春节
}


def _build_fallback_df(start_month: str, end_month: str) -> pd.DataFrame:
    """从硬编码数据构建 DataFrame，按月份范围过滤。"""
    all_months = sorted(FALLBACK_DATA.keys())
    months = [m for m in all_months if start_month <= m <= end_month]
    rows = [{"month": m, **FALLBACK_DATA[m]} for m in months]
    return pd.DataFrame(rows, columns=["month", "cpi_yoy", "lpr_1y", "m2_yoy"])


def _fetch_via_akshare(start_month: str, end_month: str) -> Optional[pd.DataFrame]:
    """
    尝试通过 akshare 获取宏观数据。
    任何异常都返回 None，由调用方降级到备用数据。
    """
    try:
        import akshare as ak  # noqa: PLC0415

        # --- CPI 同比 ---
        cpi_raw = ak.macro_china_cpi_monthly()
        # 常见列名：'日期', '今值'
        cpi_raw.columns = [c.strip() for c in cpi_raw.columns]
        date_col = next((c for c in cpi_raw.columns if "日期" in c or "date" in c.lower()), cpi_raw.columns[0])
        val_col = next((c for c in cpi_raw.columns if "今值" in c or "value" in c.lower() or "同比" in c), cpi_raw.columns[1])
        cpi_raw["month"] = pd.to_datetime(cpi_raw[date_col]).dt.strftime("%Y-%m")
        cpi_raw = cpi_raw.rename(columns={val_col: "cpi_yoy"})[["month", "cpi_yoy"]]
        cpi_raw["cpi_yoy"] = pd.to_numeric(cpi_raw["cpi_yoy"], errors="coerce")

        # --- LPR ---
        lpr_raw = ak.macro_china_lpr()
        lpr_raw.columns = [c.strip() for c in lpr_raw.columns]
        lpr_date_col = next((c for c in lpr_raw.columns if "日期" in c or "date" in c.lower()), lpr_raw.columns[0])
        lpr_val_col = next((c for c in lpr_raw.columns if "1年" in c or "1Y" in c or "lpr" in c.lower()), lpr_raw.columns[1])
        lpr_raw["month"] = pd.to_datetime(lpr_raw[lpr_date_col]).dt.strftime("%Y-%m")
        lpr_raw = lpr_raw.rename(columns={lpr_val_col: "lpr_1y"})[["month", "lpr_1y"]]
        lpr_raw["lpr_1y"] = pd.to_numeric(lpr_raw["lpr_1y"], errors="coerce")

        # --- M2 同比 ---
        m2_raw = ak.macro_china_m2_yearly()
        m2_raw.columns = [c.strip() for c in m2_raw.columns]
        m2_date_col = next((c for c in m2_raw.columns if "日期" in c or "date" in c.lower()), m2_raw.columns[0])
        m2_val_col = next((c for c in m2_raw.columns if "今值" in c or "同比" in c or "value" in c.lower()), m2_raw.columns[1])
        m2_raw["month"] = pd.to_datetime(m2_raw[m2_date_col]).dt.strftime("%Y-%m")
        m2_raw = m2_raw.rename(columns={m2_val_col: "m2_yoy"})[["month", "m2_yoy"]]
        m2_raw["m2_yoy"] = pd.to_numeric(m2_raw["m2_yoy"], errors="coerce")

        # 合并三个来源
        df = (
            cpi_raw
            .merge(lpr_raw, on="month", how="outer")
            .merge(m2_raw, on="month", how="outer")
        )
        df = df.sort_values("month").reset_index(drop=True)

        # 按月份范围过滤
        df = df[(df["month"] >= start_month) & (df["month"] <= end_month)].reset_index(drop=True)

        # 如果获取到的数据行数不足，返回 None 触发降级
        if len(df) == 0 or df[["cpi_yoy", "lpr_1y", "m2_yoy"]].isna().all(axis=None):
            logger.warning("akshare 返回数据为空，降级到硬编码备用数据")
            return None

        # 用备用数据填补 akshare 缺失值
        fallback_df = _build_fallback_df(start_month, end_month)
        fallback_lookup = fallback_df.set_index("month")
        for col in ["cpi_yoy", "lpr_1y", "m2_yoy"]:
            mask = df[col].isna()
            if mask.any():
                df.loc[mask, col] = df.loc[mask, "month"].map(
                    lambda m, c=col: fallback_lookup.at[m, c] if m in fallback_lookup.index else None
                )

        logger.info("akshare 数据获取成功，共 %d 行", len(df))
        return df[["month", "cpi_yoy", "lpr_1y", "m2_yoy"]]

    except ImportError:
        logger.info("akshare 未安装，使用硬编码备用数据")
        return None
    except Exception as exc:
        logger.warning("akshare 获取数据失败: %s，降级到硬编码备用数据", exc)
        return None


def fetch_macro_data(
    start_month: str = "2025-01",
    end_month: str = "2026-04",
) -> pd.DataFrame:
    """
    获取宏观经济控制变量数据。

    优先通过 akshare 获取实时数据；若 akshare 未安装或请求失败，
    自动降级到硬编码的备用数据。

    Args:
        start_month: 起始月份，格式 "YYYY-MM"
        end_month:   截止月份，格式 "YYYY-MM"

    Returns:
        DataFrame，列：month, cpi_yoy, lpr_1y, m2_yoy
    """
    df = _fetch_via_akshare(start_month, end_month)
    if df is None:
        df = _build_fallback_df(start_month, end_month)
        logger.info("使用硬编码备用数据，共 %d 行", len(df))
    return df


def merge_external_data(df: pd.DataFrame, macro_df: pd.DataFrame) -> pd.DataFrame:
    """
    将宏观数据合并到主数据 DataFrame。

    Args:
        df:       主数据 DataFrame，必须包含 'month' 列（格式 "YYYY-MM"）
        macro_df: fetch_macro_data() 返回的宏观数据

    Returns:
        合并后的 DataFrame（left join，不丢失主数据行）
    """
    if "month" not in df.columns:
        raise ValueError("主数据 DataFrame 缺少 'month' 列")
    if "month" not in macro_df.columns:
        raise ValueError("宏观数据 DataFrame 缺少 'month' 列")

    merged = df.merge(macro_df, on="month", how="left")
    return merged


def add_holiday_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    为 DataFrame 添加 holiday_month 列，标记节假日/大促月份。

    Args:
        df: 包含 'month' 列的 DataFrame（格式 "YYYY-MM"）

    Returns:
        添加 holiday_month 列后的 DataFrame（1=节假日月，0=普通月）
    """
    if "month" not in df.columns:
        raise ValueError("DataFrame 缺少 'month' 列")

    df = df.copy()
    df["holiday_month"] = df["month"].map(lambda m: HOLIDAY_MONTHS.get(m, 0))
    return df


# ---------------------------------------------------------------------------
# Prophet-style decomposition features (lightweight, no Prophet dependency)
# ---------------------------------------------------------------------------

import numpy as np


# ---------------------------------------------------------------------------
# STL decomposition features (replaces manual Fourier for better trend capture)
# ---------------------------------------------------------------------------

def add_stl_features(df: pd.DataFrame, dv_col: str = "dv_total_loan_amt",
                     date_col: str = "week_start", period: int = 52) -> pd.DataFrame:
    """
    Add STL (Seasonal-Trend decomposition using LOESS) features.

    Decomposes the dependent variable into trend + seasonal + residual.
    STL trend captures nonlinear patterns that linear trend+trend_sq cannot.
    STL seasonal captures the actual seasonal shape without assuming sinusoidal form.

    Falls back to existing Fourier features if STL fails.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain the DV column and date column.
    dv_col : str
        Name of the dependent variable column.
    period : int
        Seasonal period (52 for weekly data, 12 for monthly).
    """
    df = df.copy()

    if dv_col not in df.columns or len(df) < period + 10:
        # Not enough data for STL — caller should use Fourier fallback
        return df

    try:
        from statsmodels.tsa.seasonal import STL
        dv = df[dv_col].values.astype(float)
        # Fill any NaN with interpolation for STL
        dv_series = pd.Series(dv).interpolate(limit_direction="both")

        stl = STL(dv_series, period=period, robust=True)
        result = stl.fit()
        df["stl_trend"] = result.trend.values
        df["stl_seasonal"] = result.seasonal.values
    except Exception as exc:
        logger.warning("STL decomposition failed: %s — falling back to Fourier", exc)

    return df

# Chinese holiday week ranges (ISO week numbers)
# Each entry: (start_week, end_week) inclusive
_CN_HOLIDAY_WEEKS = {
    # 春节 (late Jan / early Feb) — typically ISO weeks 4-6
    "chunji": (4, 6),
    # 五一 (May 1) — ISO week ~18
    "wuyi": (18, 18),
    # 618 (mid Jun) — ISO week ~24-25
    "618": (24, 25),
    # 国庆 (Oct 1-7) — ISO week ~40
    "guoqing": (40, 41),
    # 双11 (Nov 11) — ISO week ~45-46
    "shuang11": (45, 46),
    # 双12 (Dec 12) — ISO week ~50
    "shuang12": (50, 50),
}


def add_prophet_features(df: pd.DataFrame, date_col: str = "week_start",
                         n_changepoints: int = 2) -> pd.DataFrame:
    """
    Add Prophet-style decomposition features to a weekly DataFrame.

    Mirrors Robyn's `prophet_vars = c("trend", "season", "holiday")` without
    requiring the Prophet library.

    Trend: piecewise linear with changepoints (Prophet's default growth model).
    Each changepoint adds a slope-change basis function: max(0, t - cp_position).
    This extrapolates linearly beyond training data (unlike polynomial trend_sq
    which explodes on extrapolation).

    Parameters
    ----------
    df : pd.DataFrame
        Must contain a datetime column specified by date_col.
    date_col : str
        Name of the datetime column (default "week_start").
    n_changepoints : int
        Number of trend changepoints (default 5). Placed in first 80% of data.

    Returns
    -------
    pd.DataFrame with added columns:
        - trend: normalized linear index [0, 1]
        - trend_cp_1..N: piecewise slope-change basis functions
        - season_sin/cos: annual Fourier
        - season_sin2/cos2: biannual Fourier
        - holiday_week: Chinese holiday/promo weeks
    """
    if date_col not in df.columns:
        raise ValueError(f"DataFrame 缺少 '{date_col}' 列")

    df = df.copy()
    dates = pd.to_datetime(df[date_col])
    n = len(df)

    # Trend: piecewise linear with changepoints (Prophet-style)
    t = np.linspace(0, 1, n)
    df["trend"] = t

    # Changepoints in first 80% of data (Prophet default)
    cp_positions = np.linspace(0, 0.8, n_changepoints + 2)[1:-1]
    for i, cp in enumerate(cp_positions):
        df[f"trend_cp_{i+1}"] = np.maximum(0, t - cp)

    # Seasonality: Fourier features for annual cycle (period = 52 weeks)
    iso_weeks = dates.dt.isocalendar().week.astype(float).values
    df["season_sin"] = np.sin(2 * np.pi * iso_weeks / 52.0)
    df["season_cos"] = np.cos(2 * np.pi * iso_weeks / 52.0)

    # 2nd harmonic: captures biannual patterns (period = 26 weeks)
    df["season_sin2"] = np.sin(4 * np.pi * iso_weeks / 52.0)
    df["season_cos2"] = np.cos(4 * np.pi * iso_weeks / 52.0)

    # 3rd harmonic: captures quarterly patterns (period ≈ 17.3 weeks)
    df["season_sin3"] = np.sin(6 * np.pi * iso_weeks / 52.0)
    df["season_cos3"] = np.cos(6 * np.pi * iso_weeks / 52.0)

    # Holiday: mark Chinese holiday/promo weeks
    def _is_holiday_week(iso_wk: int) -> int:
        for _, (start, end) in _CN_HOLIDAY_WEEKS.items():
            if start <= iso_wk <= end:
                return 1
        return 0

    df["holiday_week"] = [_is_holiday_week(int(w)) for w in iso_weeks]

    # CNY-specific indicator: weeks 4-6 (春节 has outsized negative DV effect vs other holidays)
    cny_start, cny_end = _CN_HOLIDAY_WEEKS["chunji"]
    df["cny_week"] = [1 if cny_start <= int(w) <= cny_end else 0 for w in iso_weeks]

    return df
