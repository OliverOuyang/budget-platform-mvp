# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Credit acquisition budget management platform (信贷获客预算管理平台) built with Streamlit. Two independent budget allocation flows:
- **V01**: Rule-based budget estimation using historical coefficients and funnel simulation
- **MMM**: Marketing Mix Model (Robyn-style) with Adstock + Hill saturation + Optuna optimization

## Commands

```bash
# Run the app (default port 8506)
streamlit run Home.py

# Run all tests
python -m pytest tests/ -q

# Run a single test file
python -m pytest tests/test_coefficient_engine.py -v

# Run a specific test
python -m pytest tests/test_coefficient_engine.py::test_calculate_m0_t0_with_valid_data -v

# Syntax-check a file
python -m py_compile pages/_tab_overview.py

# Generate mock data (104 weeks, 7 channels)
python data/generate_mock.py
```

## Architecture

```
pages/ (Streamlit UI)          ← 展示层，多页面交互
  ├── 1_预算输入与配置.py       ← V01: upload + quality check
  ├── 2_预算推算结果.py         ← V01: parameter config + calculation + results
  ├── _tab_*.py                ← V01 result page tab sub-modules (overview, channel, customer, coefficient, scenario)
  └── mmm_*.py                 ← MMM: 5-page flow (data check → insights → budget adjust → compare → linkage)

app/ (应用层)
  ├── config.py                ← Business constants, channel names, unit conversions
  ├── ui_utils.py              ← Session state management, parameter building, calculation trigger
  └── flow_components.py       ← Reusable flow UI components (headers, cards, progress)

core/ (核心业务逻辑, no Streamlit dependency)
  ├── models.py                ← Dataclasses: BudgetParameters → CalculationCoefficients → Table1Result / Table2Result → Scenario
  ├── calculation_pipeline.py  ← Orchestrator: params → coefficients → Table1 → Table2
  ├── coefficient_engine.py    ← M0/T0 ratio (6-month avg), existing M0 CPS (3/6-month avg)
  ├── channel_calculator.py    ← Table1: budget × share → channel expense → T0 transaction via CPS → M0 via ratio
  ├── customer_group_calculator.py ← Table2: initial credit (M0 + T0 + existing M0) + non-initial → total transaction
  ├── template_manager.py      ← Parameter template save/load/compare
  ├── data_loader.py           ← Excel loading and structure validation
  └── exporter.py              ← Result export to Excel

engine/ (推算引擎, independent of core/)
  ├── rule_engine.py           ← Historical median coefficients → funnel simulation (CPM → CTR → conversion chain)
  └── mmm_engine.py            ← Adstock (geometric/Weibull) → Hill saturation → Ridge regression → Optuna TPE (300 trials)
```

## Key Data Flow (V01)

```
Upload Excel (raw_达成情况 + raw_客群首借金额)
  → coefficient_engine: extract M0/T0 ratio + existing CPS from historical data
  → channel_calculator (Table1): total_budget × channel_shares → per-channel expense → T0 transaction (expense/CPS) → M0 (T0 × ratio)
  → customer_group_calculator (Table2): aggregate by customer group hierarchy → total first-loan transaction + overall CPS
```

## Key Data Flow (MMM)

```
Weekly spend data (7 channels × 104 weeks)
  → MMMTrainer.fit(): Optuna optimizes Adstock + Hill params → Ridge regression (non-negative media coefficients)
  → MMMModel.channel_contribution(): decompose per-channel contribution
  → MMMModel.budget_optimization(): equal-marginal-principle reallocation under total budget constraint
```

## Testing Conventions

- Tests live in `tests/` with shared fixtures in `tests/conftest.py`
- Use `@pytest.mark.parametrize` for multiple input cases
- Follow AAA pattern (Arrange-Act-Assert)
- `core/` modules are tested with real DataFrames from conftest fixtures, no mocks for business logic
- Known issue: `test_mmm_engine.py` has 2 pre-existing Windows `tmp_path` PermissionError failures (not blocking)

## Streamlit Conventions

- Use `use_container_width=True` for all `st.plotly_chart` and `st.dataframe` calls (not `width='stretch'`)
- Navigation via `st.navigation()` in `Home.py`; `_tab_*.py` files are sub-modules called within page 2, not standalone pages
- Session state initialized in `Home.py` with defaults dict pattern
- Flow state managed via `app/ui_utils.py` (`ensure_flow_state`, `update_v01_flow`, `get_v01_flow`)
- pandas >=2.2: use named functions with `include_groups=False` in `groupby().apply()`, not lambdas

## Business Domain Notes

- **CPS** (Cost Per Sale): stored as decimal ratio (0.30 = 30%), displayed as percentage in UI
- **Units**: expense in 万元 (10K CNY), transactions in 亿元 (100M CNY)
- **5 V01 channels**: 腾讯, 抖音, 精准营销, 付费商店, 免费渠道
- **7 MMM channels**: tencent_moments, tencent_video, tencent_wechat, tencent_search, douyin, app_store, precision_marketing
- **Customer groups**: 当月首登M0, 存量首登M0, 非初审-重申, 非初审-重审及其他, 初审M1+ (mapped via `CUSTOMER_GROUP_MAPPING` in config.py)
- Excluded groups: API回流, 其他
