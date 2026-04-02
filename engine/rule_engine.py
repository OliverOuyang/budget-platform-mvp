"""
规则层模拟引擎
基于历史数据的均值系数，模拟预算变化后的业务结果
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class BudgetInput:
    """预算输入对象"""
    tencent_moments_spend: float
    tencent_video_spend: float
    tencent_wechat_spend: float
    tencent_search_spend: float
    douyin_spend: float
    app_store_spend: float
    precision_marketing_spend: float

    goal_mode: str = "规模优先"          # 规模优先 / 成本优先 / 质量优先
    budget_target: Optional[float] = None
    cps_target: Optional[float] = None
    quality_target: Optional[float] = None
    risk_threshold: Optional[float] = None

    @property
    def total_spend(self) -> float:
        return (self.tencent_moments_spend + self.tencent_video_spend +
                self.tencent_wechat_spend + self.tencent_search_spend +
                self.douyin_spend + self.app_store_spend +
                self.precision_marketing_spend)

    def channel_spends(self) -> Dict[str, float]:
        return {
            "tencent_moments":     self.tencent_moments_spend,
            "tencent_video":       self.tencent_video_spend,
            "tencent_wechat":      self.tencent_wechat_spend,
            "tencent_search":      self.tencent_search_spend,
            "douyin":              self.douyin_spend,
            "app_store":           self.app_store_spend,
            "precision_marketing": self.precision_marketing_spend,
        }


@dataclass
class PredictionResult:
    """预测结果对象"""
    scenario_name: str
    budget_input: BudgetInput

    # 规模结果
    total_spend: float = 0.0
    impressions: float = 0.0
    clicks: float = 0.0
    first_login_cnt: float = 0.0
    apply_start_cnt: float = 0.0
    apply_submit_cnt: float = 0.0
    credit_cnt: float = 0.0
    credit_a13_cnt: float = 0.0
    loan_cnt: float = 0.0
    loan_amt: float = 0.0
    credit_amt: float = 0.0

    # 成本结果
    cps_amt: float = 0.0

    # 质量结果
    quality_a13_rate: float = 0.0

    # LTV 结果
    ltv_12m: float = 0.0
    ltv_24m: float = 0.0

    # 风险结果
    fpd30_plus_rate: float = 0.0
    first_loan_txn: float = 0.0           # 首借交易笔数
    repeat_loan_txn: float = 0.0          # 复借交易笔数
    first_loan_final_loss_rate: float = 0.0   # 首借终损率
    repeat_loan_final_loss_rate: float = 0.0  # 复借终损率

    # 与基准差异（%）
    vs_baseline: Dict[str, float] = field(default_factory=dict)

    engine_source: str = "规则层"

    def to_dict(self) -> dict:
        return {
            "方案名称": self.scenario_name,
            "总花费（万元）": round(self.total_spend, 2),
            "曝光数": int(self.impressions),
            "点击数": int(self.clicks),
            "首登数": int(self.first_login_cnt),
            "发起数": int(self.apply_start_cnt),
            "申完数": int(self.apply_submit_cnt),
            "授信数": int(self.credit_cnt),
            "A卡1-3授信数": int(self.credit_a13_cnt),
            "借款数": int(self.loan_cnt),
            "借款金额（万元）": round(self.loan_amt, 2),
            "授信金额（万元）": round(self.credit_amt, 2),
            "CPS": round(self.cps_amt, 4),
            "1-3授信率": round(self.quality_a13_rate, 4),
            "LTV_12m（万元）": round(self.ltv_12m, 2),
            "LTV_24m（万元）": round(self.ltv_24m, 2),
            "FPD30+风险率": round(self.fpd30_plus_rate, 4),
            "首借交易": int(self.first_loan_txn),
            "复借交易": int(self.repeat_loan_txn),
            "首借终损率": round(self.first_loan_final_loss_rate, 4),
            "复借终损率": round(self.repeat_loan_final_loss_rate, 4),
            "引擎来源": self.engine_source,
        }


class RuleEngine:
    """
    规则层引擎：从历史数据提取系数，模拟预算变化后的业务结果
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._fit_coefficients()

    def _fit_coefficients(self):
        """从历史数据提取均值系数"""
        d = self.df

        # 各渠道 CPM（花费/万 → 曝光数）
        self.cpm = {}
        for ch in ["tencent_moments", "tencent_video", "tencent_wechat",
                   "tencent_search", "douyin", "app_store", "precision_marketing"]:
            imp_col   = f"{ch}_impressions"
            spend_col = f"{ch}_spend"
            if imp_col in d.columns and spend_col in d.columns:
                ratio = d[imp_col] / d[spend_col].replace(0, np.nan)
                self.cpm[ch] = ratio.median()
            else:
                self.cpm[ch] = 5000.0

        # 各渠道 CTR
        self.ctr = {}
        for ch in self.cpm:
            click_col = f"{ch}_clicks"
            imp_col   = f"{ch}_impressions"
            if click_col in d.columns and imp_col in d.columns:
                ratio = d[click_col] / d[imp_col].replace(0, np.nan)
                self.ctr[ch] = ratio.median()
            else:
                self.ctr[ch] = 0.02

        # 漏斗转化率（中位数）
        total_clicks = sum(
            d.get(f"{ch}_clicks", pd.Series(0)) for ch in self.cpm
        )
        self.first_login_rate  = (d["first_login_cnt"]  / total_clicks.replace(0, np.nan)).median()
        self.apply_start_rate  = (d["apply_start_cnt"]  / d["first_login_cnt"].replace(0, np.nan)).median()
        self.apply_submit_rate = (d["apply_submit_cnt"] / d["apply_start_cnt"].replace(0, np.nan)).median()
        self.credit_rate       = (d["credit_cnt"]       / d["apply_submit_cnt"].replace(0, np.nan)).median()
        self.a13_rate          = (d["credit_a13_cnt"]   / d["apply_submit_cnt"].replace(0, np.nan)).median()
        self.loan_rate         = (d["loan_cnt"]         / d["credit_cnt"].replace(0, np.nan)).median()
        self.avg_loan_amt      = (d["loan_amt"]         / d["loan_cnt"].replace(0, np.nan)).median()
        self.avg_credit_amt    = (d["credit_amt"]       / d["credit_cnt"].replace(0, np.nan)).median()
        self.ltv12_ratio       = (d["ltv_12m"]          / d["loan_amt"].replace(0, np.nan)).median()
        self.ltv24_ratio       = (d["ltv_24m"]          / d["loan_amt"].replace(0, np.nan)).median()
        self.fpd30_base        = d["fpd30_plus_rate"].median()

        # 首借 / 复借系数
        if "first_loan_txn" in d.columns and "loan_cnt" in d.columns:
            self.first_loan_ratio_median = (d["first_loan_txn"] / d["loan_cnt"].replace(0, np.nan)).median()
        else:
            self.first_loan_ratio_median = 0.70

        if "first_loan_final_loss_rate" in d.columns:
            self.first_loss_median  = d["first_loan_final_loss_rate"].median()
        else:
            self.first_loss_median  = 0.09

        if "repeat_loan_final_loss_rate" in d.columns:
            self.repeat_loss_median = d["repeat_loan_final_loss_rate"].median()
        else:
            self.repeat_loss_median = 0.045

    def simulate(self, budget: BudgetInput, scenario_name: str = "模拟方案",
                 quality_boost: float = 0.0, risk_factor: float = 1.0) -> PredictionResult:
        """
        模拟给定预算下的业务结果
        quality_boost: 质量提升系数（正值提升 a13_rate）
        risk_factor: 风险调整系数（>1 风险上升）
        """
        result = PredictionResult(
            scenario_name=scenario_name,
            budget_input=budget,
            total_spend=budget.total_spend,
        )

        # 曝光 & 点击
        total_imp = 0.0
        total_clk = 0.0
        for ch, spend in budget.channel_spends().items():
            imp = spend * self.cpm.get(ch, 5000)
            clk = imp * self.ctr.get(ch, 0.02)
            total_imp += imp
            total_clk += clk

        result.impressions = total_imp
        result.clicks      = total_clk

        # 漏斗
        result.first_login_cnt  = total_clk * self.first_login_rate
        result.apply_start_cnt  = result.first_login_cnt  * self.apply_start_rate
        result.apply_submit_cnt = result.apply_start_cnt  * self.apply_submit_rate
        result.credit_cnt       = result.apply_submit_cnt * self.credit_rate
        result.credit_a13_cnt   = result.apply_submit_cnt * (self.a13_rate + quality_boost)
        result.loan_cnt         = result.credit_cnt       * self.loan_rate
        result.loan_amt         = result.loan_cnt         * self.avg_loan_amt
        result.credit_amt       = result.credit_cnt       * self.avg_credit_amt

        # 派生指标
        result.cps_amt = (budget.total_spend / result.loan_amt) if result.loan_amt > 0 else 0.0
        result.quality_a13_rate = (result.credit_a13_cnt / result.apply_submit_cnt
                                   if result.apply_submit_cnt > 0 else 0.0)
        result.ltv_12m = result.loan_amt * self.ltv12_ratio
        result.ltv_24m = result.loan_amt * self.ltv24_ratio
        result.fpd30_plus_rate = self.fpd30_base * risk_factor

        # 首借 / 复借交易
        first_ratio = getattr(self, 'first_loan_ratio_median', 0.70)
        result.first_loan_txn  = result.loan_cnt * first_ratio
        result.repeat_loan_txn = result.loan_cnt * (1 - first_ratio)

        # 首借 / 复借终损率
        result.first_loan_final_loss_rate  = getattr(self, 'first_loss_median',  0.09) * risk_factor
        result.repeat_loan_final_loss_rate = getattr(self, 'repeat_loss_median', 0.045) * risk_factor

        return result

    def generate_scenarios(self, base_budget: BudgetInput) -> Dict[str, PredictionResult]:
        """生成四个标准方案：基准 / 保守 / 标准 / 激进"""
        scenarios = {}

        # 基准方案（原预算）
        scenarios["基准方案"] = self.simulate(base_budget, "基准方案")

        def _scale_budget(scale: float, goal_mode: str) -> BudgetInput:
            spends = base_budget.channel_spends()
            return BudgetInput(
                tencent_moments_spend=spends["tencent_moments"] * scale,
                tencent_video_spend=spends["tencent_video"] * scale,
                tencent_wechat_spend=spends["tencent_wechat"] * scale,
                tencent_search_spend=spends["tencent_search"] * scale,
                douyin_spend=spends["douyin"] * scale,
                app_store_spend=spends["app_store"] * scale,
                precision_marketing_spend=spends["precision_marketing"] * scale,
                goal_mode=goal_mode,
            )

        # 保守方案（-15%）
        scenarios["保守方案"] = self.simulate(
            _scale_budget(0.85, base_budget.goal_mode), "保守方案",
            quality_boost=0.02, risk_factor=0.92
        )

        # 标准方案（+10%）
        scenarios["标准方案"] = self.simulate(
            _scale_budget(1.10, base_budget.goal_mode), "标准方案",
            quality_boost=0.0, risk_factor=1.03
        )

        # 激进方案（+25%）
        scenarios["激进方案"] = self.simulate(
            _scale_budget(1.25, base_budget.goal_mode), "激进方案",
            quality_boost=-0.02, risk_factor=1.10
        )

        # 计算与基准的差异
        base = scenarios["基准方案"]
        for name, res in scenarios.items():
            if name == "基准方案":
                continue
            vs = {}
            for attr in ["total_spend", "loan_amt", "loan_cnt", "cps_amt",
                         "quality_a13_rate", "fpd30_plus_rate", "ltv_12m"]:
                base_val = getattr(base, attr)
                cur_val  = getattr(res, attr)
                vs[attr] = round((cur_val - base_val) / base_val * 100, 2) if base_val != 0 else 0.0
            res.vs_baseline = vs

        return scenarios
