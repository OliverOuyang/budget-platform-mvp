"""
生成 2 年周度 mock 数据，字段贴近真实业务输入
覆盖：时间列、渠道 spend、impressions/clicks、业务结果列、派生指标、策略变量、外部控制变量
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path

np.random.seed(42)

# ─── 时间范围：2024-01-01 ~ 2025-12-29（104 周）──────────────────────────────
start = date(2024, 1, 1)
weeks = 104
dates = [start + timedelta(weeks=i) for i in range(weeks)]

df = pd.DataFrame()
df["week_start"] = [d.strftime("%Y-%m-%d") for d in dates]
df["year"]       = [d.year for d in dates]
df["month"]      = [d.month for d in dates]
df["quarter"]    = [(d.month - 1) // 3 + 1 for d in dates]

# ─── 季节性系数（Q4 旺季，Q2 次旺）────────────────────────────────────────────
season = np.array([
    1.0 if q == 1 else
    1.15 if q == 2 else
    0.95 if q == 3 else
    1.25
    for q in df["quarter"]
])

# ─── 渠道 spend（万元）────────────────────────────────────────────────────────
base_spend = {
    "tencent_moments":      300,
    "tencent_video":        200,
    "tencent_wechat":       150,
    "tencent_search":       120,
    "douyin":               350,
    "app_store":             80,
    "precision_marketing":  100,
}

for ch, base in base_spend.items():
    noise = np.random.normal(0, 0.08, weeks)
    trend = np.linspace(1.0, 1.12, weeks)          # 两年微增趋势
    df[f"{ch}_spend"] = np.round(base * season * trend * (1 + noise), 2)

df["total_spend"] = df[[f"{ch}_spend" for ch in base_spend]].sum(axis=1).round(2)

# ─── Impressions & Clicks ─────────────────────────────────────────────────────
cpm = {"tencent_moments": 25, "tencent_video": 20, "tencent_wechat": 18,
       "tencent_search": 30, "douyin": 15, "app_store": 22, "precision_marketing": 28}
ctr = {"tencent_moments": 0.018, "tencent_video": 0.022, "tencent_wechat": 0.015,
       "tencent_search": 0.045, "douyin": 0.025, "app_store": 0.020, "precision_marketing": 0.030}

for ch in base_spend:
    imp = (df[f"{ch}_spend"] * 10000 / cpm[ch]).astype(int)
    imp = np.maximum(imp + np.random.randint(-5000, 5000, weeks), 0)
    df[f"{ch}_impressions"] = imp
    df[f"{ch}_clicks"] = np.maximum(
        (imp * ctr[ch] * np.random.uniform(0.9, 1.1, weeks)).astype(int), 0
    )

total_impressions = df[[f"{ch}_impressions" for ch in base_spend]].sum(axis=1)
total_clicks      = df[[f"{ch}_clicks"      for ch in base_spend]].sum(axis=1)

# ─── 业务漏斗链路 ─────────────────────────────────────────────────────────────
# 首登 = 总点击 * 首登率（约 8%）
first_login_rate = 0.08 * season * np.random.uniform(0.92, 1.08, weeks)
df["first_login_cnt"] = np.maximum((total_clicks * first_login_rate).astype(int), 0)

# 发起 = 首登 * 发起率（约 55%）
apply_start_rate = 0.55 * np.random.uniform(0.93, 1.07, weeks)
df["apply_start_cnt"] = np.maximum((df["first_login_cnt"] * apply_start_rate).astype(int), 0)

# 申完 = 发起 * 申完率（约 72%）
apply_submit_rate = 0.72 * np.random.uniform(0.95, 1.05, weeks)
df["apply_submit_cnt"] = np.maximum((df["apply_start_cnt"] * apply_submit_rate).astype(int), 0)

# 授信 = 申完 * 授信率（约 48%）
credit_rate = 0.48 * np.random.uniform(0.93, 1.07, weeks)
df["credit_cnt"] = np.maximum((df["apply_submit_cnt"] * credit_rate).astype(int), 0)

# A卡1-3授信 = 申完 * 1-3授信率（约 35%）
a13_rate_base = 0.35 * np.random.uniform(0.90, 1.10, weeks)
df["credit_a13_cnt"] = np.maximum((df["apply_submit_cnt"] * a13_rate_base).astype(int), 0)

# 借款 = 授信 * 借款率（约 62%）
loan_rate = 0.62 * np.random.uniform(0.94, 1.06, weeks)
df["loan_cnt"] = np.maximum((df["credit_cnt"] * loan_rate).astype(int), 0)

# 借款金额（万元）= 借款笔数 * 均借款额（约 1.8 万）
avg_loan_amt = 1.8 * np.random.uniform(0.92, 1.08, weeks)
df["loan_amt"] = np.round(df["loan_cnt"] * avg_loan_amt, 2)

# 授信金额（万元）= 授信笔数 * 均授信额（约 3.2 万）
avg_credit_amt = 3.2 * np.random.uniform(0.93, 1.07, weeks)
df["credit_amt"] = np.round(df["credit_cnt"] * avg_credit_amt, 2)

# ─── 派生业务指标 ─────────────────────────────────────────────────────────────
df["quality_a13_rate"] = np.round(
    df["credit_a13_cnt"] / df["apply_submit_cnt"].replace(0, np.nan), 4
).fillna(0)

df["cps_amt"] = np.round(
    df["total_spend"] / df["loan_amt"].replace(0, np.nan), 4
).fillna(0)

# LTV（相对借款金额的倍数，12m ≈ 2.1x，24m ≈ 3.5x）
df["ltv_12m"] = np.round(df["loan_amt"] * np.random.uniform(1.9, 2.3, weeks), 2)
df["ltv_24m"] = np.round(df["loan_amt"] * np.random.uniform(3.2, 3.8, weeks), 2)

# FPD30+ 风险率（约 3.5%，Q4 略高）
fpd_base = 0.035 + (df["quarter"] == 4).astype(float) * 0.005
df["fpd30_plus_rate"] = np.round(
    fpd_base * np.random.uniform(0.85, 1.15, weeks), 4
)

# ─── 腾讯策略变量 ─────────────────────────────────────────────────────────────
tencent_imp = df[[f"tencent_{p}_impressions" for p in ["moments","video","wechat","search"]]].sum(axis=1)
df["tencent_impression_cnt"] = tencent_imp
df["tencent_bid_cnt"]        = (tencent_imp / np.random.uniform(0.55, 0.70, weeks)).astype(int)
df["tencent_request_cnt"]    = (df["tencent_bid_cnt"] / np.random.uniform(0.60, 0.75, weeks)).astype(int)

df["win_rate"]      = np.round(df["tencent_impression_cnt"] / df["tencent_bid_cnt"].replace(0, np.nan), 4).fillna(0)
df["exclude_rate"]  = np.round(1 - df["tencent_bid_cnt"] / df["tencent_request_cnt"].replace(0, np.nan), 4).fillna(0)

# 回传变量
df["callback_ratio"]       = np.round(np.random.uniform(0.55, 0.80, weeks), 4)
df["callback_credit_cnt"]  = (df["credit_cnt"] * df["callback_ratio"]).astype(int)

# ─── 外部控制变量（宏观 & 利率，月度数据按周填充）────────────────────────────
# CPI 同比（%）
cpi_monthly = np.array([0.7, 0.7, 0.1, 0.3, 0.3, 0.2, 0.5, 0.6, 0.4, 0.3, 0.2, 0.1,
                         0.5, 0.7, 0.4, 0.3, 0.2, 0.2, 0.3, 0.4, 0.5, 0.6, 0.5, 0.4])
df["cpi_yoy"] = [cpi_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# PPI 同比（%）
ppi_monthly = np.array([-2.5,-2.7,-2.8,-2.5,-1.4,-0.8,-0.8,-1.8,-2.5,-2.9,-2.5,-2.2,
                          -1.8,-1.5,-1.2,-0.8,-0.5,-0.3,-0.2, 0.1, 0.2, 0.3, 0.4, 0.5])
df["ppi_yoy"] = [ppi_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# 社零同比（%）
retail_monthly = np.array([5.5, 5.5, 3.1, 2.3, 3.7, 2.0, 2.7, 2.1, 3.2, 4.8, 3.0, 3.7,
                             4.0, 4.2, 4.5, 4.0, 3.8, 3.5, 3.6, 3.8, 4.0, 4.2, 4.5, 5.0])
df["social_retail_yoy"] = [retail_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# 城镇调查失业率（%）
unemp_monthly = np.array([5.2, 5.3, 5.2, 5.0, 5.0, 5.0, 5.2, 5.3, 5.1, 5.0, 5.1, 5.1,
                            5.0, 5.0, 5.1, 5.0, 4.9, 4.9, 5.0, 5.0, 4.9, 4.9, 5.0, 5.0])
df["unemployment_rate"] = [unemp_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# M2 同比（%）
m2_monthly = np.array([8.7, 8.7, 8.3, 7.2, 7.0, 6.2, 6.3, 6.3, 6.8, 7.5, 7.1, 7.3,
                         7.5, 7.8, 8.0, 8.2, 8.0, 7.8, 7.9, 8.0, 8.1, 8.2, 8.3, 8.5])
df["m2_yoy"] = [m2_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# 社融同比（%）
sf_monthly = np.array([9.5, 9.0, 8.7, 8.3, 8.4, 8.1, 8.2, 8.1, 8.0, 7.8, 7.8, 8.0,
                         8.2, 8.5, 8.7, 8.8, 8.6, 8.5, 8.6, 8.7, 8.8, 8.9, 9.0, 9.2])
df["social_financing_yoy"] = [sf_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# LPR（%）
lpr1y_monthly  = np.array([3.45]*6 + [3.35]*6 + [3.10]*12)
lpr5y_monthly  = np.array([3.95]*2 + [3.75]*4 + [3.60]*6 + [3.50]*12)
shibor_monthly = np.array([1.85, 1.90, 1.88, 1.82, 1.80, 1.78, 1.75, 1.72, 1.70, 1.68, 1.65, 1.63,
                             1.62, 1.60, 1.58, 1.55, 1.53, 1.52, 1.50, 1.50, 1.48, 1.47, 1.45, 1.45])
df["lpr_1y"]    = [lpr1y_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]
df["lpr_5y"]    = [lpr5y_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]
df["shibor_1w"] = [shibor_monthly[(d.year - 2024) * 12 + d.month - 1] for d in dates]

# ─── 节假日 & 大促标记 ────────────────────────────────────────────────────────
holiday_weeks = {
    "2024-01-01", "2024-02-12", "2024-04-01", "2024-05-06",
    "2024-06-10", "2024-09-16", "2024-10-07",
    "2025-01-27", "2025-04-07", "2025-05-05",
    "2025-06-02", "2025-10-06",
}
big_promo_weeks = {
    "2024-06-03", "2024-11-04", "2024-11-11",
    "2025-06-02", "2025-11-03", "2025-11-10",
}
df["holiday_days"]   = df["week_start"].apply(lambda x: 2 if x in holiday_weeks else 0)
df["big_promo_flag"] = df["week_start"].apply(lambda x: 1 if x in big_promo_weeks else 0)

# ─── 主因变量（MMM 用）────────────────────────────────────────────────────────
df["dv_t0_loan_amt"] = df["loan_amt"]

# ─── 新增风险指标：首借交易、复借交易、首借终损、复借终损 ──────────────────────────
# 首借交易：首次借款用户的交易笔数（借款数 * 首借占比，首借用户约占 70%）
first_loan_ratio = np.random.uniform(0.65, 0.75, weeks)
df["first_loan_txn"] = np.round(df["loan_cnt"] * first_loan_ratio, 0).astype(int)

# 复借交易：复借用户的交易笔数（借款数 - 首借交易）
df["repeat_loan_txn"] = df["loan_cnt"] - df["first_loan_txn"]

# 首借终损率：首借用户的终期损失率（首借用户风险较高，约 8-12%，Q4 略高）
first_loss_base = 0.09 + (df["quarter"] == 4).astype(float) * 0.015
df["first_loan_final_loss_rate"] = np.round(
    first_loss_base * np.random.uniform(0.88, 1.12, weeks), 4
)

# 复借终损率：复借用户经过筛选，风险较低，终损率约 4-6%
repeat_loss_base = 0.045 + (df["quarter"] == 4).astype(float) * 0.008
df["repeat_loan_final_loss_rate"] = np.round(
    repeat_loss_base * np.random.uniform(0.88, 1.12, weeks), 4
)

# ─── 保存 ─────────────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "mock_weekly.csv"
df.to_csv(out_path, index=False)
print(f"Mock data generated: {out_path}")
print(f"  rows: {len(df)}, cols: {len(df.columns)}")
print(f"  range: {df['week_start'].iloc[0]} ~ {df['week_start'].iloc[-1]}")
