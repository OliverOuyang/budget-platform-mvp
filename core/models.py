"""
数据模型定义
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import html
import pandas as pd


@dataclass
class BudgetParameters:
    """预算参数"""
    total_budget: float  # 总花费 (万元)

    # 渠道固定参数 (key: 渠道名称)
    channel_1_3_approval_rate: Dict[str, float] = field(default_factory=dict)  # 1-3过件率
    channel_1_8_cps: Dict[str, float] = field(default_factory=dict)  # 1-8 CPS（小数，0.3=30%）
    channel_t0_completion_cost: Dict[str, float] = field(default_factory=dict)  # T0申完成本
    channel_budget_shares: Dict[str, float] = field(default_factory=dict)  # 渠道花费结构（小数）

    # 第二张表手动输入参数
    non_initial_credit_transaction: float = 0.0  # 非初审授信户首借交易额 (亿元)
    existing_m0_expense: float = 0.0  # 存量首登M0花费 (万元)
    rta_promotion_fee: float = 0.0  # RTA费用+促申完 (万元)

    # 当月预估参数
    month_total_days: int = 30  # 当月总天数
    days_elapsed: int = 25  # 已完成天数

    # 存量首登M0交易计算周期（3或6个月）
    existing_m0_calculation_months: int = 3  # 默认3个月


@dataclass
class CalculationCoefficients:
    """计算系数"""
    m0_t0_ratio: float  # M0/T0 交易比值系数 (前6月均值)
    existing_m0_cps_avg: float  # 存量首登M0 CPS均值（小数，0.3=30%）

    # 调试信息
    m0_t0_ratio_history: List[float] = field(default_factory=list)
    existing_m0_cps_history: List[float] = field(default_factory=list)

    # 系数来源说明（用于可解释性展示）
    m0_t0_source_months: List[str] = field(default_factory=list)   # 用了哪几个月
    existing_m0_source_months: List[str] = field(default_factory=list)  # 用了哪几个月


@dataclass
class ChannelData:
    """渠道数据 (用于第一张表)"""
    channel_name: str  # 渠道名称

    # 固定参数 (输入)
    approval_rate_1_3: float  # 1-3过件率
    cps_1_8: float  # 1-8 CPS（小数，0.3=30%）
    t0_completion_cost: float  # T0申完成本

    # 分配的花费
    expense: float  # 花费 (万元)

    # 计算的衍生指标
    t0_transaction: float = 0.0  # T0交易额 (亿元)
    t0_completion_volume: float = 0.0  # T0申完量
    expense_structure: float = 0.0  # 花费结构 (%)
    m0_transaction: float = 0.0  # 当月首登M0交易额 (亿元)
    credit_volume_1_3: float = 0.0  # 1-3 T0授信量
    completion_structure: float = 0.0  # 申完结构 (%)

    # 历史数据 (用于参考)
    historical_loan_amount_1_8: float = 0.0  # 1-8首借24h借款金额
    non_age_reject_completion: float = 0.0  # 非年龄拒绝申完量


@dataclass
class Table1Result:
    """第一张表结果"""
    channels: List[ChannelData]
    total_expense: float  # 总花费 (万元)
    total_t0_transaction: float  # 总T0交易额 (亿元)
    total_m0_transaction: float  # 总M0交易额 (亿元)
    total_completion_volume: float  # 总申完量

    def to_dataframe(self) -> pd.DataFrame:
        """转换为 DataFrame（不含总计行，总计行单独处理）"""
        data = []
        for ch in self.channels:
            if ch.channel_name == "总计":
                continue
            data.append({
                '渠道名称': ch.channel_name,
                '1-3 T0过件率': ch.approval_rate_1_3,
                '1-8 T0CPS': ch.cps_1_8,
                '花费(千万元)': ch.expense / 100,  # 万元 → 千万元
                '花费结构': ch.expense_structure,
                'T0交易额(千万元)': ch.t0_transaction * 10,  # 亿元 → 千万元
                '当月首登M0交易额(千万元)': ch.m0_transaction * 10,  # 亿元 → 千万元
                'T0申完成本(元)': ch.t0_completion_cost,
                'T0申完量': ch.t0_completion_volume,
                '申完结构': ch.completion_structure,
                '1-3 T0授信量': ch.credit_volume_1_3,
            })

        # 添加汇总行
        total_ch = next((ch for ch in self.channels if ch.channel_name == "总计"), None)
        if total_ch:
            data.append({
                '渠道名称': '总计',
                '1-3 T0过件率': total_ch.approval_rate_1_3,
                '1-8 T0CPS': total_ch.cps_1_8 if total_ch.cps_1_8 else None,
                '花费(千万元)': self.total_expense / 100,  # 万元 → 千万元
                '花费结构': 100.0,
                'T0交易额(千万元)': self.total_t0_transaction * 10,
                '当月首登M0交易额(千万元)': self.total_m0_transaction * 10,
                'T0申完成本(元)': total_ch.t0_completion_cost,
                'T0申完量': self.total_completion_volume,
                '申完结构': 100.0,
                '1-3 T0授信量': sum(ch.credit_volume_1_3 for ch in self.channels if ch.channel_name != "总计"),
            })

        return pd.DataFrame(data)


@dataclass
class CustomerGroupData:
    """客群数据 (用于第二张表)"""
    category: str  # 分类名称
    value: float  # 交易额 (亿元)
    level: int = 0  # 层级 (0=顶层, 1=一级, 2=二级)
    parent: Optional[str] = None  # 父分类


@dataclass
class Table2Result:
    """第二张表结果"""
    # 层级数据（交易额，单位：亿元）
    initial_credit_total: float      # 1) 初审授信户首借交易额 = a_m0 + a_t0 + b
    current_month_initial_m0: float  # a) 当月首登初审M0交易额
    first_login_t0: float            # a) 首登T0交易额（含在初审总计中）
    existing_initial_m0: float       # b) 存量首登初审M0交易额
    non_initial_credit: float        # 2) 非初审授信户首借交易额
    total_transaction: float         # 整体首借交易额 = 1) + 2)

    # 费用指标（单位：万元）
    total_expense: float             # 投放花费（含存量首登花费）
    rta_promotion_fee: float         # RTA费用+促申完
    calculated_existing_m0_expense: float = 0.0  # 自动计算的存量首登花费

    # 效率指标
    total_cps: float = 0.0           # 全业务CPS（小数，0.3=30%）
    approval_rate_1_3_excl_age: float = 0.0  # 1-3组T0过件率(排年龄，加权平均)

    def to_dataframe(self) -> pd.DataFrame:
        """
        转换为 DataFrame（层级展示，多列分离单位）
        列：指标名称 | 交易额(亿元) | 花费(万元) | 效率指标
        """
        rows = [
            {
                '指标': '整体首借交易额',
                '交易额(亿元)': f"{self.total_transaction:.2f}",
                '花费(万元)': f"{self.total_expense:,.0f}",
                '效率指标': f"全业务CPS={self.total_cps:.2%}",
                '层级': 0,
            },
            {
                '指标': '  1) 初审授信户首借交易额',
                '交易额(亿元)': f"{self.initial_credit_total:.2f}",
                '花费(万元)': '',
                '效率指标': '',
                '层级': 1,
            },
            {
                '指标': '    ① 当月首登初审M0交易额',
                '交易额(亿元)': f"{self.current_month_initial_m0:.2f}",
                '花费(万元)': '',
                '效率指标': '',
                '层级': 2,
            },
            {
                '指标': '      首登T0交易额',
                '交易额(亿元)': f"{self.first_login_t0:.2f}",
                '花费(万元)': '',
                '效率指标': '',
                '层级': 3,
            },
            {
                '指标': '    ② 存量首登初审M0交易额',
                '交易额(亿元)': f"{self.existing_initial_m0:.2f}",
                '花费(万元)': f"{self.calculated_existing_m0_expense:,.0f}",
                '效率指标': '',
                '层级': 2,
            },
            {
                '指标': '  2) 非初审授信户首借交易额',
                '交易额(亿元)': f"{self.non_initial_credit:.2f}",
                '花费(万元)': '',
                '效率指标': '',
                '层级': 1,
            },
            {
                '指标': '─── 费用汇总 ───',
                '交易额(亿元)': '',
                '花费(万元)': '',
                '效率指标': '',
                '层级': -1,
            },
            {
                '指标': '  投放花费',
                '交易额(亿元)': '',
                '花费(万元)': f"{self.total_expense:,.0f}",
                '效率指标': '',
                '层级': 1,
            },
            {
                '指标': '  RTA费用+促申完',
                '交易额(亿元)': '',
                '花费(万元)': f"{self.rta_promotion_fee:,.0f}",
                '效率指标': '',
                '层级': 1,
            },
            {
                '指标': '─── 效率指标 ───',
                '交易额(亿元)': '',
                '花费(万元)': '',
                '效率指标': '',
                '层级': -1,
            },
            {
                '指标': '  全业务CPS',
                '交易额(亿元)': '',
                '花费(万元)': '',
                '效率指标': f"{self.total_cps:.2%}",
                '层级': 1,
            },
            {
                '指标': '  1-3组T0过件率（排年龄）',
                '交易额(亿元)': '',
                '花费(万元)': '',
                '效率指标': f"{self.approval_rate_1_3_excl_age:.1%}",
                '层级': 1,
            },
        ]
        return pd.DataFrame(rows)

    def to_html(self) -> str:
        """
        生成 Table2 HTML 表格，用于在 Streamlit 中渲染层级缩进结构
        """
        def level_style(level: int) -> str:
            styles = {
                0: "font-weight:bold; font-size:15px; background:#E3F2FD; padding:8px; border-radius:4px;",
                1: "font-size:13px; padding-left:16px; padding:4px 0;",
                2: "font-size:12px; padding-left:32px; padding:3px 0; color:#555;",
                3: "font-size:11px; padding-left:48px; padding:2px 0; color:#888;",
                -1: "color:#999; font-size:11px; padding:4px 0; border-top:1px dashed #ddd; margin-top:4px;",
            }
            return styles.get(level, "")

        def format_cell(val: str) -> str:
            if not val or val == '':
                return ''
            return html.escape(str(val))

        rows = [
            {"指标": "整体首借交易额", "交易额(亿元)": f"{self.total_transaction:.2f}", "花费(万元)": f"{self.total_expense:,.0f}", "效率指标": f"全业务CPS={self.total_cps:.2%}", "层级": 0},
            {"指标": "  1) 初审授信户首借交易额", "交易额(亿元)": f"{self.initial_credit_total:.2f}", "花费(万元)": "", "效率指标": "", "层级": 1},
            {"指标": "    ① 当月首登初审M0交易额", "交易额(亿元)": f"{self.current_month_initial_m0:.2f}", "花费(万元)": "", "效率指标": "", "层级": 2},
            {"指标": "      首登T0交易额", "交易额(亿元)": f"{self.first_login_t0:.2f}", "花费(万元)": "", "效率指标": "", "层级": 3},
            {"指标": "    ② 存量首登初审M0交易额", "交易额(亿元)": f"{self.existing_initial_m0:.2f}", "花费(万元)": f"{self.calculated_existing_m0_expense:,.0f}", "效率指标": "", "层级": 2},
            {"指标": "  2) 非初审授信户首借交易额", "交易额(亿元)": f"{self.non_initial_credit:.2f}", "花费(万元)": "", "效率指标": "", "层级": 1},
            {"指标": "─── 费用汇总 ───", "交易额(亿元)": "", "花费(万元)": "", "效率指标": "", "层级": -1},
            {"指标": "  投放花费", "交易额(亿元)": "", "花费(万元)": f"{self.total_expense:,.0f}", "效率指标": "", "层级": 1},
            {"指标": "  RTA费用+促申完", "交易额(亿元)": "", "花费(万元)": f"{self.rta_promotion_fee:,.0f}", "效率指标": "", "层级": 1},
            {"指标": "─── 效率指标 ───", "交易额(亿元)": "", "花费(万元)": "", "效率指标": "", "层级": -1},
            {"指标": "  全业务CPS", "交易额(亿元)": "", "花费(万元)": "", "效率指标": f"{self.total_cps:.2%}", "层级": 1},
            {"指标": "  1-3组T0过件率（排年龄）", "交易额(亿元)": "", "花费(万元)": "", "效率指标": f"{self.approval_rate_1_3_excl_age:.1%}", "层级": 1},
        ]

        html_out = """<table style="width:100%; border-collapse:collapse;">"""
        html_out += """<tr style="background:#f5f5f5;">
            <th style="padding:8px; text-align:left; border-bottom:2px solid #ddd;">指标</th>
            <th style="padding:8px; text-align:right; border-bottom:2px solid #ddd;">交易额(亿元)</th>
            <th style="padding:8px; text-align:right; border-bottom:2px solid #ddd;">花费(万元)</th>
            <th style="padding:8px; text-align:left; border-bottom:2px solid #ddd;">效率指标</th>
        </tr>"""
        for row in rows:
            style = level_style(row["层级"])
            indicator = format_cell(row["指标"])
            transaction = format_cell(row["交易额(亿元)"])
            expense = format_cell(row["花费(万元)"])
            efficiency = format_cell(row["效率指标"])
            html_out += f"""<tr style="{style}">
                <td style="padding:6px;">{indicator}</td>
                <td style="padding:6px; text-align:right;">{transaction}</td>
                <td style="padding:6px; text-align:right;">{expense}</td>
                <td style="padding:6px; text-align:left;">{efficiency}</td>
            </tr>"""
        html_out += "</table>"
        return html_out


@dataclass
class Scenario:
    """场景 (用于对比)"""
    name: str  # 场景名称
    timestamp: str  # 创建时间
    parameters: BudgetParameters  # 参数
    table1_result: Table1Result  # 第一张表结果
    table2_result: Table2Result  # 第二张表结果
    coefficients: CalculationCoefficients  # 计算系数
