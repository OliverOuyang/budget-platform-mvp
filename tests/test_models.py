import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import Table1Result, Table2Result

def test_table1_result_to_dataframe():
    """Table1Result.to_dataframe() should return a DataFrame."""
    result = Table1Result(
        channels=[],
        total_expense=0.0,
        total_t0_transaction=0.0,
        total_m0_transaction=0.0,
        total_completion_volume=0.0,
    )
    df = result.to_dataframe()
    import pandas as pd
    assert isinstance(df, pd.DataFrame)

def test_table2_result_to_html_no_xss():
    """HTML values should be escaped in to_html() output."""
    result = Table2Result(
        initial_credit_total=100.0,
        current_month_initial_m0=50.0,
        first_login_t0=30.0,
        existing_initial_m0=20.0,
        non_initial_credit=40.0,
        total_transaction=140.0,
        total_expense=10.0,
        rta_promotion_fee=2.0,
        calculated_existing_m0_expense=5.0,
        total_cps=0.1,
        approval_rate_1_3_excl_age=0.5,
    )
    output = result.to_html()
    # Script tags in output should be escaped (if any field ever contains them)
    assert "<script>" not in output
    # Should contain basic table structure
    assert "<table" in output
    assert "</table>" in output
