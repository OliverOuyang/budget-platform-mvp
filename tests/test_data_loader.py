import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd

from core.data_loader import validate_excel_structure


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
