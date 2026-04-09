"""
业务配置常量

所有核心常量定义在 core/constants.py 中，
此处 re-export 以保持 app/ 层和 pages/ 层的 import 兼容。
"""

from core.constants import (  # noqa: F401 — re-export for backward compatibility
    REQUIRED_SHEETS,
    CHANNEL_NAMES,
    M0_T0_COEFFICIENT_MONTHS,
    EXISTING_M0_CPS_MONTHS,
    DEFAULT_1_3_RATES,
    DEFAULT_1_8_CPS,
    TABLE1_COLUMNS,
    TABLE2_HIERARCHY,
    EXCLUDED_CUSTOMER_GROUPS,
    CUSTOMER_GROUP_MAPPING,
    EXPENSE_UNIT_DIVISOR,
    TRANSACTION_UNIT_DIVISOR,
    PERCENTAGE_DECIMALS,
    TRANSACTION_DECIMALS,
    EXPENSE_DECIMALS,
    DEFAULT_TOTAL_BUDGET,
    DEFAULT_MONTH_DAYS,
    DEFAULT_DAYS_ELAPSED,
)
