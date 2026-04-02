import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.coefficient_engine import DEFAULT_M0_T0_RATIO, DEFAULT_CPS_RATE

def test_named_constants_exist():
    assert DEFAULT_M0_T0_RATIO == 1.5
    assert DEFAULT_CPS_RATE == 0.05

def test_calculate_m0_t0_coefficient_returns_tuple():
    """When M0/T0 columns are NaN, falls back to DEFAULT_M0_T0_RATIO."""
    from core.coefficient_engine import calculate_m0_t0_coefficient
    import pandas as pd
    import numpy as np
    df = pd.DataFrame({
        "月份": ["2024-01", "2024-02"],
        "1_8m0首登当月首借24h借款金额": [np.nan, np.nan],
        "1-8t0首借24h借款金额": [0.0, 0.0],
    })
    result = calculate_m0_t0_coefficient(df)
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert result[0] == DEFAULT_M0_T0_RATIO
    assert result[1] == []
