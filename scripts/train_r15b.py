"""
R15b Training: cny_week + first_loan_loss_rate (no total_spend — it caused multicollinearity)
R15a with total_spend regressed badly: R2=0.60, CV R2=0.19, alpha=86
Baseline R14: CV R²=0.33, Train NRMSE=0.43, R2=0.81, 3/4 stable channels
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

# Load data
from core.real_data_transformer import transform_weekly_data
from core.external_data import add_prophet_features, add_stl_features

csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "四月数据.csv")
df = transform_weekly_data(csv_path)
df = add_prophet_features(df, "week_start")
dv_col = "dv_first_loan_amt"
df = add_stl_features(df, dv_col=dv_col, date_col="week_start")

print(f"Data: {len(df)} rows")
print(f"New features: cny_week={df['cny_week'].sum()}, first_loan_loss_rate range=[{df['first_loan_loss_rate'].min():.4f}, {df['first_loan_loss_rate'].max():.4f}]")
print()

from engine.mmm_engine import MMMTrainer, ModelRegistry

trainer = MMMTrainer(df, dv_col=dv_col, n_trials=300, n_models=5, adstock_type="auto")

print(f"=== R15b: cny_week + first_loan_loss_rate (no total_spend) ===")
print(f"Context keys ({len(trainer.context_keys)}): {trainer.context_keys}")
print()

model = trainer.fit()

print(f"Train NRMSE: {model.train_nrmse:.4f}")
print(f"Holdout NRMSE: {model.nrmse:.4f}")
print(f"R2(train): {model.r_squared:.4f}")
print(f"DecompRSSD: {model.decomp_rssd:.4f}")
print(f"DW stat: {model.dw_stat:.4f}")
meta = model.training_meta
print(f"Best alpha: {meta.get('best_alpha')}")
print(f"Final alpha: {meta.get('final_alpha')}")
print(f"Alpha boosted: {meta.get('alpha_boosted')}")
print(f"Pruned: {meta.get('pruned_impressions')}")
print()

bs = model.bootstrap_stability
spend_chs = trainer.channel_keys
stable_spend = [ch for ch in spend_chs if ch in bs and bs[ch].get("cv", 99) < 0.5]
print(f"Stable spend ch (CV<0.5): {len(stable_spend)} - {stable_spend}")
for ch, info in bs.items():
    if isinstance(info, dict):
        print(f"  {ch}: mean={info['mean']:.4f}, cv={info['cv']:.4f}")
print()

cv = model.cv_results
print(f"CV R2: {cv.get('mean_r2', 0):.4f}")
print(f"CV NRMSE: {cv.get('mean_nrmse', 0):.4f}")
print()

# Context coefs
print("Context coefficients:")
for ctx, coef in model.context_coefs.items():
    print(f"  {ctx}: {coef:.4f}")
print()

reg = ModelRegistry()
reg.save(model, name="R15b_cny_lossrate")
print("Saved as R15b_cny_lossrate")

# Comparison
print("\n=== R15b vs R14 Comparison ===")
print(f"{'Metric':<25} {'R14':>10} {'R15b':>10} {'Delta':>10}")
print("-" * 57)
r14 = {"train_nrmse": 0.4341, "cv_r2": 0.3331, "r2_train": 0.8116,
       "holdout_nrmse": 1.3178, "stable_spend": 3, "rssd": 0.2664}
r15 = {"train_nrmse": model.train_nrmse, "cv_r2": cv.get("mean_r2", 0),
       "r2_train": model.r_squared, "holdout_nrmse": model.nrmse,
       "stable_spend": len(stable_spend), "rssd": model.decomp_rssd}
for key in r14:
    v14, v15 = r14[key], r15[key]
    delta = v15 - v14
    better = "+" if ((key in ["cv_r2", "r2_train", "stable_spend"] and delta > 0) or
                     (key in ["train_nrmse", "holdout_nrmse", "rssd"] and delta < 0)) else "-" if delta != 0 else "="
    print(f"  {key:<23} {v14:>10.4f} {v15:>10.4f} {delta:>+10.4f} {better}")
