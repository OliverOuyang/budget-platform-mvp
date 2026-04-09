"""
格式化模块

将 Table1Result / Table2Result 转换为展示用 DataFrame 或 HTML 的逻辑。
原先分散在 core/models.py 各方法中，统一收拢到此处。
"""
import html as _html_module

import pandas as pd

from core.models import Table1Result, Table2Result


# ---------------------------------------------------------------------------
# Table 1
# ---------------------------------------------------------------------------

def format_table1_dataframe(result: Table1Result) -> pd.DataFrame:
    """转换 Table1Result 为 DataFrame（不含总计行，总计行单独附加）。"""
    data = []
    for ch in result.channels:
        if ch.channel_name == "总计":
            continue
        data.append({
            '渠道名称': ch.channel_name,
            '1-3 T0过件率': ch.approval_rate_1_3,
            '1-8 T0CPS': ch.cps_1_8,
            '花费(千万元)': ch.expense / 100,          # 万元 → 千万元
            '花费结构': ch.expense_structure,
            'T0交易额(千万元)': ch.t0_transaction * 10,  # 亿元 → 千万元
            '当月首登M0交易额(千万元)': ch.m0_transaction * 10,
            'T0申完成本(元)': ch.t0_completion_cost,
            'T0申完量': ch.t0_completion_volume,
            '申完结构': ch.completion_structure,
            '1-3 T0授信量': ch.credit_volume_1_3,
        })

    # 添加汇总行
    total_ch = next((ch for ch in result.channels if ch.channel_name == "总计"), None)
    if total_ch:
        data.append({
            '渠道名称': '总计',
            '1-3 T0过件率': total_ch.approval_rate_1_3,
            '1-8 T0CPS': total_ch.cps_1_8 if total_ch.cps_1_8 else None,
            '花费(千万元)': result.total_expense / 100,
            '花费结构': 100.0,
            'T0交易额(千万元)': result.total_t0_transaction * 10,
            '当月首登M0交易额(千万元)': result.total_m0_transaction * 10,
            'T0申完成本(元)': total_ch.t0_completion_cost,
            'T0申完量': result.total_completion_volume,
            '申完结构': 100.0,
            '1-3 T0授信量': sum(
                ch.credit_volume_1_3
                for ch in result.channels
                if ch.channel_name != "总计"
            ),
        })

    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Table 2
# ---------------------------------------------------------------------------

def build_table2_rows(result: Table2Result) -> list:
    """共享行定义，供 format_table2_dataframe() 和 render_table2_html() 使用。"""
    return [
        {
            '指标': '整体首借交易额',
            '交易额(亿元)': f"{result.total_transaction:.2f}",
            '花费(万元)': f"{result.total_expense:,.0f}",
            '效率指标': f"全业务CPS={result.total_cps:.2%}",
            '层级': 0,
        },
        {
            '指标': '  1) 初审授信户首借交易额',
            '交易额(亿元)': f"{result.initial_credit_total:.2f}",
            '花费(万元)': '',
            '效率指标': '',
            '层级': 1,
        },
        {
            '指标': '    ① 当月首登初审M0交易额',
            '交易额(亿元)': f"{result.current_month_initial_m0:.2f}",
            '花费(万元)': '',
            '效率指标': '',
            '层级': 2,
        },
        {
            '指标': '      首登T0交易额',
            '交易额(亿元)': f"{result.first_login_t0:.2f}",
            '花费(万元)': '',
            '效率指标': '',
            '层级': 3,
        },
        {
            '指标': '    ② 存量首登初审M0交易额',
            '交易额(亿元)': f"{result.existing_initial_m0:.2f}",
            '花费(万元)': f"{result.calculated_existing_m0_expense:,.0f}",
            '效率指标': '',
            '层级': 2,
        },
        {
            '指标': '  2) 非初审授信户首借交易额',
            '交易额(亿元)': f"{result.non_initial_credit:.2f}",
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
            '花费(万元)': f"{result.total_expense:,.0f}",
            '效率指标': '',
            '层级': 1,
        },
        {
            '指标': '  RTA费用+促申完',
            '交易额(亿元)': '',
            '花费(万元)': f"{result.rta_promotion_fee:,.0f}",
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
            '效率指标': f"{result.total_cps:.2%}",
            '层级': 1,
        },
        {
            '指标': '  1-3组T0过件率（排年龄）',
            '交易额(亿元)': '',
            '花费(万元)': '',
            '效率指标': f"{result.approval_rate_1_3_excl_age:.1%}",
            '层级': 1,
        },
    ]


def format_table2_dataframe(result: Table2Result) -> pd.DataFrame:
    """
    转换 Table2Result 为 DataFrame（层级展示，多列分离单位）。
    列：指标名称 | 交易额(亿元) | 花费(万元) | 效率指标
    """
    rows = build_table2_rows(result)
    return pd.DataFrame(rows)


def render_table2_html(result: Table2Result) -> str:
    """生成 Table2 HTML 表格，用于在 Streamlit 中渲染层级缩进结构。"""

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
        return _html_module.escape(str(val))

    rows = build_table2_rows(result)

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
