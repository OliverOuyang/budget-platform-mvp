import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd

from core.data_loader import validate_excel_structure, load_guardrail_data, GUARDRAIL_REQUIRED_COLUMNS


@pytest.fixture
def valid_df1():
    return pd.DataFrame({
        '月份': ['2024-01'],
        '渠道类别': ['腾讯'],
        '1-3t0过件率': [0.45],
        '1-8t0cps': [0.30],
        '花费': [1000000.0],
        '1-8t0首借24h借款金额': [5000000.0],
        '1-8t0过件率': [0.38],
        't0申完成本': [150.0],
        '非年龄拒绝t0申完量': [6000.0],
        '当月首登m0_t0_24h_交易比值': [1.5],
        '1_8m0首登当月首借24h借款金额': [7500000.0],
    })


@pytest.fixture
def valid_df2():
    return pd.DataFrame({
        '月份': ['2024-01'],
        '客群': ['当月首登M0'],
        '授信人数': [100],
        '发起人数': [120],
        '风险通过人数': [80],
        '动支人数': [60],
        '初始授信额度': [50000.0],
        '首贷金额': [30000.0],
        '渠道类别': ['腾讯'],
    })


def test_validate_excel_structure_success(valid_df1, valid_df2):
    """Valid DataFrames pass validation."""
    result = validate_excel_structure(valid_df1, valid_df2)
    assert result is True


def test_validate_excel_structure_missing_columns(valid_df2):
    """Missing required columns raise ValueError with column names."""
    df_missing = pd.DataFrame({'月份': ['2024-01'], '渠道类别': ['腾讯']})
    with pytest.raises(ValueError) as exc_info:
        validate_excel_structure(df_missing, valid_df2)
    error_msg = str(exc_info.value)
    assert '花费' in error_msg or '缺少必需列' in error_msg


def test_validate_excel_structure_empty_df1(valid_df2):
    """Empty df1 raises ValueError (missing columns fires before empty check)."""
    with pytest.raises(ValueError):
        validate_excel_structure(pd.DataFrame(), valid_df2)


# ---------------------------------------------------------------------------
# Guardrail data loading tests
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_guardrail_df():
    return pd.DataFrame({
        "月份": ["2025-01", "2025-01"],
        "渠道类别": ["腾讯", "抖音"],
        "FPD30": [0.035, 0.042],
        "首借终损率": [0.08, 0.09],
        "复借终损率": [0.05, 0.06],
        "复借交易额": [12000, 8000],
        "渠道LTV": [850, 720],
    })


def test_load_guardrail_valid_df(valid_guardrail_df):
    result = load_guardrail_data(valid_guardrail_df)
    assert len(result) == 2
    assert list(result.columns) == GUARDRAIL_REQUIRED_COLUMNS


def test_load_guardrail_none_returns_empty():
    result = load_guardrail_data(None)
    assert len(result) == 0
    assert list(result.columns) == GUARDRAIL_REQUIRED_COLUMNS


def test_load_guardrail_missing_column():
    df_bad = pd.DataFrame({"月份": ["2025-01"], "渠道类别": ["腾讯"]})
    with pytest.raises(ValueError, match="护栏指标数据缺少必需列"):
        load_guardrail_data(df_bad)


def test_load_guardrail_backslash_n_converted(valid_guardrail_df):
    df = valid_guardrail_df.copy()
    df.loc[0, "FPD30"] = "\\N"
    result = load_guardrail_data(df)
    assert pd.isna(result.loc[0, "FPD30"])
