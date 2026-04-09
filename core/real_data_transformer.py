"""
real_data_transformer.py
Transform raw channel-level CSV data into wide-format DataFrames
suitable for MMM model training and V01 guardrail display.

Expected CSV format:
  - 96 rows × 44 columns (16 months × 6 rows)
  - Each month: 1 summary row (渠道类别 is NaN) + 5 channel rows
  - Channels: 付费商店, 免费渠道, 抖音, 精准营销, 腾讯
  - Encoding: UTF-8 with BOM (utf-8-sig)
"""

from __future__ import annotations

import pandas as pd

# ── Column name constants (positional fallback handled in _load) ─────────────
_COL_MONTH = "月份"
_COL_CHANNEL = "渠道类别"
_COL_SPEND = "花费"
_COL_IMPRESSIONS = "曝光量"
_COL_CLICKS = "点击量"
_COL_FIRST_LOGIN = "首登数"
_COL_FIRST_LOAN_AMT = "首借交易额"
_COL_REPEAT_LOAN_AMT = "复借交易额"
_COL_TOTAL_LOAN_AMT = "合计交易额"
_COL_FIRST_LOSS_RATE = "首借终损率"
_COL_REPEAT_LOSS_RATE = "复借终损率"
_COL_TOTAL_LOSS_RATE = "合计终损率"
_COL_T0_CPS = "1-8组t0_cps"
_COL_SAFE_T0_RATE = "1-8组t0过件率"
_COL_T0_COST = "t0申完成本"
_COL_NON_AGE_T0 = "非年龄拒绝t0申完量"
_COL_FULL_T0_CPS = "全量t0_cps"
_COL_T0_APPROVAL_RATE = "全量t0过件率"
_COL_SAFE_T0_APPROVAL_RATE = "安全t0过件率"
_COL_13_APPROVAL = "实际1_3档授信人数"

# ── Channel mapping: CSV name → MMM key ─────────────────────────────────────
# 免费渠道 excluded — no spend data (NaN throughout)
CHANNEL_MAP: dict[str, str] = {
    "腾讯": "tencent",
    "抖音": "douyin",
    "精准营销": "precision_marketing",
    "付费商店": "app_store",
}

_PAID_CHANNELS = list(CHANNEL_MAP.keys())

# Conversion factor: 元 → 万元
_YUAN_TO_WAN = 1.0 / 10_000.0


def _load(csv_path: str) -> pd.DataFrame:
    """Read CSV with UTF-8 BOM encoding."""
    return pd.read_csv(csv_path, encoding="utf-8-sig")


def transform_real_data(csv_path: str) -> pd.DataFrame:
    """
    Transform raw channel CSV into a wide-format monthly DataFrame for MMM.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file (UTF-8 BOM encoded).

    Returns
    -------
    pd.DataFrame
        One row per month with columns:
        - month (str, "YYYY-MM")
        - {channel}_spend (万元) for each paid channel
        - {channel}_impressions, {channel}_clicks, {channel}_first_login
        - total_spend (万元)
        - dv_first_loan_amt, dv_repeat_loan_amt, dv_total_loan_amt (万元)
        - first_loan_loss_rate, repeat_loan_loss_rate
        Sorted by month ascending.
    """
    df = _load(csv_path)

    # ── Split summary rows vs channel rows ──────────────────────────────────
    is_summary = df[_COL_CHANNEL].isna()
    summary_df = df[is_summary].copy()
    channel_df = df[~is_summary].copy()

    # ── Build summary-level DV columns (one row per month) ──────────────────
    summary_cols = [
        _COL_MONTH,
        _COL_FIRST_LOAN_AMT,
        _COL_REPEAT_LOAN_AMT,
        _COL_TOTAL_LOAN_AMT,
        _COL_FIRST_LOSS_RATE,
        _COL_REPEAT_LOSS_RATE,
    ]
    monthly = (
        summary_df[summary_cols]
        .rename(columns={_COL_MONTH: "month"})
        .copy()
    )
    monthly["dv_first_loan_amt"] = monthly[_COL_FIRST_LOAN_AMT] * _YUAN_TO_WAN
    monthly["dv_repeat_loan_amt"] = monthly[_COL_REPEAT_LOAN_AMT] * _YUAN_TO_WAN
    monthly["dv_total_loan_amt"] = monthly[_COL_TOTAL_LOAN_AMT] * _YUAN_TO_WAN
    monthly["first_loan_loss_rate"] = monthly[_COL_FIRST_LOSS_RATE]
    monthly["repeat_loan_loss_rate"] = monthly[_COL_REPEAT_LOSS_RATE]
    monthly = monthly[
        [
            "month",
            "dv_first_loan_amt",
            "dv_repeat_loan_amt",
            "dv_total_loan_amt",
            "first_loan_loss_rate",
            "repeat_loan_loss_rate",
        ]
    ].reset_index(drop=True)

    # ── Pivot paid channels to wide format ──────────────────────────────────
    paid_df = channel_df[channel_df[_COL_CHANNEL].isin(_PAID_CHANNELS)].copy()

    # Metrics to pivot per channel
    pivot_metrics = {
        _COL_SPEND: "spend",
        _COL_IMPRESSIONS: "impressions",
        _COL_CLICKS: "clicks",
        _COL_FIRST_LOGIN: "first_login",
        _COL_T0_CPS: "t0_cps",
        _COL_SAFE_T0_RATE: "safe_t0_rate",
        _COL_T0_COST: "t0_cost",
        _COL_NON_AGE_T0: "non_age_t0_vol",
    }

    wide_parts: list[pd.DataFrame] = []
    for raw_col, metric_suffix in pivot_metrics.items():
        pivoted = paid_df.pivot_table(
            index=_COL_MONTH,
            columns=_COL_CHANNEL,
            values=raw_col,
            aggfunc="first",
        )
        # Rename columns: channel_name → mmm_key_metric
        rename_map = {
            ch_name: f"{mmm_key}_{metric_suffix}"
            for ch_name, mmm_key in CHANNEL_MAP.items()
            if ch_name in pivoted.columns
        }
        pivoted = pivoted.rename(columns=rename_map)
        # Keep only renamed columns (drops any unexpected channels)
        pivoted = pivoted[[c for c in pivoted.columns if c in rename_map.values()]]
        wide_parts.append(pivoted)

    wide_df = pd.concat(wide_parts, axis=1).reset_index().rename(
        columns={_COL_MONTH: "month"}
    )

    # ── Unit conversion: spend 元 → 万元 ────────────────────────────────────
    spend_cols = [f"{mmm_key}_spend" for mmm_key in CHANNEL_MAP.values()]
    for col in spend_cols:
        if col in wide_df.columns:
            wide_df[col] = wide_df[col] * _YUAN_TO_WAN

    # ── total_spend ──────────────────────────────────────────────────────────
    existing_spend_cols = [c for c in spend_cols if c in wide_df.columns]
    wide_df["total_spend"] = wide_df[existing_spend_cols].sum(axis=1, min_count=1)

    # ── Aggregate first_login across all paid channels ───────────────────────
    first_login_cols = [
        f"{mmm_key}_first_login" for mmm_key in CHANNEL_MAP.values()
    ]
    existing_fl_cols = [c for c in first_login_cols if c in wide_df.columns]
    wide_df["paid_total_first_login"] = wide_df[existing_fl_cols].sum(
        axis=1, min_count=1
    )

    # ── Merge summary DVs with wide channel data ─────────────────────────────
    result = monthly.merge(wide_df, on="month", how="left")

    # ── Sort by month ascending ──────────────────────────────────────────────
    result = result.sort_values("month").reset_index(drop=True)

    return result


# ── Weekly data support ─────────────────────────────────────────────────────

_COL_WEEK_START = "周起始日"

# Columns available for weekly pivot
_WEEKLY_PIVOT_METRICS = {
    _COL_SPEND: "spend",
    _COL_IMPRESSIONS: "impressions",
    _COL_CLICKS: "clicks",
    _COL_FIRST_LOGIN: "first_login",
    _COL_T0_CPS: "t0_cps",
    _COL_SAFE_T0_RATE: "safe_t0_rate",
    _COL_T0_COST: "t0_cost",
    _COL_NON_AGE_T0: "non_age_t0_vol",
}


def _detect_incomplete_tail(df: pd.DataFrame, date_col: str,
                            spend_col: str, threshold: float = 0.3) -> list:
    """Return list of tail dates whose total spend is < threshold × median.

    Detects partial weeks at the end of the dataset (e.g. data pulled mid-week).
    """
    weekly_spend = (
        pd.to_numeric(df[spend_col], errors="coerce")
        .groupby(df[date_col])
        .sum()
    )
    weekly_spend = weekly_spend.sort_index()
    if len(weekly_spend) < 3:
        return []
    median_spend = weekly_spend.iloc[:-1].median()
    if median_spend <= 0:
        return []
    drop = []
    for dt in reversed(weekly_spend.index):
        if weekly_spend[dt] < median_spend * threshold:
            drop.append(dt)
        else:
            break
    return drop


def transform_weekly_data(csv_path: str) -> pd.DataFrame:
    """
    Transform raw weekly channel CSV into wide-format DataFrame for MMM.

    Parameters
    ----------
    csv_path : str
        Path to 四月数据.csv (UTF-8 BOM, 67wk × 5ch = 335 rows).

    Returns
    -------
    pd.DataFrame
        One row per week with columns:
        - week_start (datetime)
        - {channel}_spend (万元) for each paid channel
        - {channel}_impressions, {channel}_clicks, {channel}_first_login
        - free_channel_first_login (organic variable)
        - total_spend (万元)
        - dv_first_loan_amt, dv_repeat_loan_amt, dv_total_loan_amt (万元)
        - first_loan_loss_rate, repeat_loan_loss_rate, total_loan_loss_rate
        Sorted by week_start ascending, incomplete tail weeks excluded.
    """
    df = _load(csv_path)

    # Parse date column
    df[_COL_WEEK_START] = pd.to_datetime(df[_COL_WEEK_START])

    # Replace \N sentinel with NaN
    df = df.replace(r"\N", pd.NA)

    # Convert numeric columns
    numeric_cols = [
        _COL_SPEND, _COL_IMPRESSIONS, _COL_CLICKS, _COL_FIRST_LOGIN,
        _COL_FIRST_LOAN_AMT, _COL_REPEAT_LOAN_AMT, _COL_TOTAL_LOAN_AMT,
        _COL_T0_CPS, _COL_SAFE_T0_RATE, _COL_T0_COST, _COL_NON_AGE_T0,
        _COL_FULL_T0_CPS, _COL_T0_APPROVAL_RATE, _COL_SAFE_T0_APPROVAL_RATE,
        _COL_13_APPROVAL,
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Detect and exclude incomplete tail weeks
    drop_dates = _detect_incomplete_tail(df, _COL_WEEK_START, _COL_SPEND)
    if drop_dates:
        df = df[~df[_COL_WEEK_START].isin(drop_dates)]

    # ── Separate paid channels and 免费渠道 ────────────────────────────────
    paid_df = df[df[_COL_CHANNEL].isin(_PAID_CHANNELS)].copy()
    free_df = df[df[_COL_CHANNEL] == "免费渠道"].copy()

    # ── Pivot paid channels to wide format ──────────────────────────────────
    wide_parts: list[pd.DataFrame] = []
    for raw_col, metric_suffix in _WEEKLY_PIVOT_METRICS.items():
        if raw_col not in paid_df.columns:
            continue
        pivoted = paid_df.pivot_table(
            index=_COL_WEEK_START,
            columns=_COL_CHANNEL,
            values=raw_col,
            aggfunc="first",
        )
        rename_map = {
            ch_name: f"{mmm_key}_{metric_suffix}"
            for ch_name, mmm_key in CHANNEL_MAP.items()
            if ch_name in pivoted.columns
        }
        pivoted = pivoted.rename(columns=rename_map)
        pivoted = pivoted[[c for c in pivoted.columns if c in rename_map.values()]]
        wide_parts.append(pivoted)

    wide_df = pd.concat(wide_parts, axis=1).reset_index().rename(
        columns={_COL_WEEK_START: "week_start"}
    )

    # ── Unit conversion: spend 元 → 万元 ────────────────────────────────────
    spend_cols = [f"{mmm_key}_spend" for mmm_key in CHANNEL_MAP.values()]
    for col in spend_cols:
        if col in wide_df.columns:
            wide_df[col] = wide_df[col] * _YUAN_TO_WAN

    # ── total_spend ──────────────────────────────────────────────────────────
    existing_spend = [c for c in spend_cols if c in wide_df.columns]
    wide_df["total_spend"] = wide_df[existing_spend].sum(axis=1, min_count=1)

    # ── 免费渠道 organic variable (首登数) ───────────────────────────────────
    if not free_df.empty and _COL_FIRST_LOGIN in free_df.columns:
        free_organic = (
            free_df[[_COL_WEEK_START, _COL_FIRST_LOGIN]]
            .rename(columns={
                _COL_WEEK_START: "week_start",
                _COL_FIRST_LOGIN: "free_channel_first_login",
            })
        )
        wide_df = wide_df.merge(free_organic, on="week_start", how="left")

    # ── DV: sum across ALL channels per week (万元) ─────────────────────────
    dv_map = {
        _COL_FIRST_LOAN_AMT: "dv_first_loan_amt",
        _COL_REPEAT_LOAN_AMT: "dv_repeat_loan_amt",
        _COL_TOTAL_LOAN_AMT: "dv_total_loan_amt",
    }
    for raw_col, dv_name in dv_map.items():
        if raw_col in df.columns:
            weekly_sum = (
                df.groupby(_COL_WEEK_START)[raw_col]
                .sum()
                .reset_index()
                .rename(columns={_COL_WEEK_START: "week_start", raw_col: dv_name})
            )
            weekly_sum[dv_name] = weekly_sum[dv_name] * _YUAN_TO_WAN
            wide_df = wide_df.merge(weekly_sum, on="week_start", how="left")

    # ── DV: simple sum across ALL channels per week (count, no conversion) ───
    dv_count_map = {
        _COL_13_APPROVAL: "dv_13_approval_count",
    }
    for raw_col, dv_name in dv_count_map.items():
        if raw_col in df.columns:
            weekly_sum = (
                df.groupby(_COL_WEEK_START)[raw_col]
                .sum()
                .reset_index()
                .rename(columns={_COL_WEEK_START: "week_start", raw_col: dv_name})
            )
            wide_df = wide_df.merge(weekly_sum, on="week_start", how="left")

    # ── Loss rates: spend-weighted average across paid channels ──────────────
    loss_cols = {
        "首借终损率": "first_loan_loss_rate",
        "复借终损率": "repeat_loan_loss_rate",
        "合计终损率": "total_loan_loss_rate",
    }
    for raw_col, out_name in loss_cols.items():
        if raw_col in paid_df.columns:
            paid_with_loss = paid_df[[_COL_WEEK_START, _COL_SPEND, raw_col]].copy()
            paid_with_loss[_COL_SPEND] = pd.to_numeric(paid_with_loss[_COL_SPEND], errors="coerce").fillna(0)
            paid_with_loss[raw_col] = pd.to_numeric(paid_with_loss[raw_col], errors="coerce").fillna(0)

            def _weighted_mean(g):
                w = g[_COL_SPEND]
                v = g[raw_col]
                total_w = w.sum()
                if total_w > 0:
                    return (v * w).sum() / total_w
                return v.mean()

            weekly_loss = (
                paid_with_loss
                .groupby(_COL_WEEK_START, group_keys=False)
                .apply(_weighted_mean, include_groups=False)
                .reset_index()
                .rename(columns={_COL_WEEK_START: "week_start", 0: out_name})
            )
            wide_df = wide_df.merge(weekly_loss, on="week_start", how="left")

    # ── DV rates/costs: spend-weighted average across paid channels ──────────
    dv_weighted_cols = {
        _COL_FULL_T0_CPS: "dv_t0_cps",
        _COL_T0_APPROVAL_RATE: "dv_t0_approval_rate",
        _COL_SAFE_T0_APPROVAL_RATE: "dv_safe_t0_approval_rate",
        _COL_T0_COST: "dv_t0_cost",
    }
    for raw_col, out_name in dv_weighted_cols.items():
        if raw_col in paid_df.columns:
            paid_with_dv = paid_df[[_COL_WEEK_START, _COL_SPEND, raw_col]].copy()
            paid_with_dv[_COL_SPEND] = pd.to_numeric(paid_with_dv[_COL_SPEND], errors="coerce").fillna(0)
            paid_with_dv[raw_col] = pd.to_numeric(paid_with_dv[raw_col], errors="coerce").fillna(0)

            def _weighted_mean_dv(g, _col=raw_col):
                w = g[_COL_SPEND]
                v = g[_col]
                total_w = w.sum()
                if total_w > 0:
                    return (v * w).sum() / total_w
                return v.mean()

            weekly_dv = (
                paid_with_dv
                .groupby(_COL_WEEK_START, group_keys=False)
                .apply(_weighted_mean_dv, include_groups=False)
                .reset_index()
                .rename(columns={_COL_WEEK_START: "week_start", 0: out_name})
            )
            wide_df = wide_df.merge(weekly_dv, on="week_start", how="left")

    # ── Sort and return ──────────────────────────────────────────────────────
    wide_df = wide_df.sort_values("week_start").reset_index(drop=True)
    return wide_df


def get_channel_guardrails(csv_path: str) -> pd.DataFrame:
    """
    Return full channel-level data (not pivoted) for V01 guardrail display.

    Includes all risk and quality metrics per channel per month.
    Summary rows (渠道类别 is NaN) are excluded.

    Parameters
    ----------
    csv_path : str
        Path to the CSV file (UTF-8 BOM encoded).

    Returns
    -------
    pd.DataFrame
        Columns: 月份, 渠道类别, plus all quality/risk metrics.
        Sorted by 月份 then 渠道类别.
    """
    df = _load(csv_path)

    # Keep only actual channel rows (exclude summary rows)
    channel_df = df[df[_COL_CHANNEL].notna()].copy()

    # Select relevant columns for guardrail display
    guardrail_cols = [
        _COL_MONTH,
        _COL_CHANNEL,
        _COL_SPEND,
        _COL_IMPRESSIONS,
        _COL_CLICKS,
        _COL_FIRST_LOGIN,
        _COL_T0_CPS,
        _COL_SAFE_T0_RATE,
        _COL_T0_COST,
        _COL_NON_AGE_T0,
        _COL_FIRST_LOAN_AMT,
        _COL_REPEAT_LOAN_AMT,
        _COL_TOTAL_LOAN_AMT,
        _COL_FIRST_LOSS_RATE,
        _COL_REPEAT_LOSS_RATE,
    ]
    # Only keep columns that exist in the DataFrame
    existing_cols = [c for c in guardrail_cols if c in channel_df.columns]
    result = channel_df[existing_cols].copy()

    result = result.sort_values([_COL_MONTH, _COL_CHANNEL]).reset_index(drop=True)
    return result
