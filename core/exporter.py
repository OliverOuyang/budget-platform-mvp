"""
Excel导出模块

负责将计算结果导出为格式化的Excel文件
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from core.models import Table1Result, Table2Result
from app.config import (
    TRANSACTION_DECIMALS,
    EXPENSE_DECIMALS,
    PERCENTAGE_DECIMALS,
    TABLE1_COLUMNS
)


class ExporterError(Exception):
    """导出错误"""
    pass


def export_to_excel(
    table1: Table1Result,
    table2: Table2Result,
    output_path: Optional[str] = None
) -> str:
    """
    导出计算结果到Excel文件

    Args:
        table1: 渠道维度预算表结果
        table2: 客群维度汇总表结果
        output_path: 输出文件路径 (可选, 默认自动生成)

    Returns:
        str: 输出文件的绝对路径

    Raises:
        ExporterError: 导出失败时抛出
    """
    try:
        # 生成默认文件名
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"预算推算结果_{timestamp}.xlsx"
            output_path = str(Path.cwd() / "export" / filename)

        # 确保输出目录存在
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        # 转换为DataFrame
        df1 = table1.to_dataframe()
        df2 = table2.to_dataframe()

        # 应用格式化
        df1_formatted = _format_dataframe(df1, sheet_type="table1")
        df2_formatted = _format_dataframe(df2, sheet_type="table2")

        # 写入Excel
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df1_formatted.to_excel(writer, sheet_name='渠道维度预算表', index=False)
            df2_formatted.to_excel(writer, sheet_name='客群维度汇总表', index=False)

        # 应用样式
        _apply_excel_styles(output_path)

        return str(Path(output_path).resolve())

    except Exception as e:
        raise ExporterError(f"导出Excel失败: {e}")


def _format_dataframe(df: pd.DataFrame, sheet_type: str) -> pd.DataFrame:
    """
    格式化DataFrame的数值

    Args:
        df: 待格式化的DataFrame
        sheet_type: 表类型 ("table1" 或 "table2")

    Returns:
        pd.DataFrame: 格式化后的DataFrame
    """
    df = df.copy()

    if sheet_type == "table1":
        # 花费: 万元/千万元, 取整（无小数）—— 匹配 Table1 to_dataframe() 输出的列名
        expense_col = '花费(千万元)' if '花费(千万元)' in df.columns else ('花费(万元)' if '花费(万元)' in df.columns else '花费')
        if expense_col in df.columns:
            df[expense_col] = df[expense_col].apply(
                lambda x: f"{int(round(x)):,}" if pd.notna(x) else ""
            )

        # 交易额: 千万元, 2位小数
        transaction_cols = ['T0交易额(千万元)', '当月首登M0交易额(千万元)', 'T0交易额', '当月首登M0交易额']
        for col in transaction_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: f"{x:.{TRANSACTION_DECIMALS}f}" if pd.notna(x) else ""
                )

        # 百分比: XX.X%, 1位小数
        percentage_cols = ['花费结构', '申完结构', '1-3 T0过件率', '1-8 T0CPS']
        for col in percentage_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: f"{x*100:.{PERCENTAGE_DECIMALS}f}%" if pd.notna(x) and isinstance(x, float) and x <= 1 else (
                        f"{x:.{PERCENTAGE_DECIMALS}f}%" if pd.notna(x) else ""
                    )
                )

        # 其他数值列保留2位小数
        numeric_cols = ['非年龄拒绝申完量', '1-3 T0授信量', 'T0申完量']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: f"{x:,.0f}" if pd.notna(x) else ""
                )

    elif sheet_type == "table2":
        # 第二张表已在 to_dataframe() 中格式化为字符串，直接返回
        pass

    return df


def _apply_excel_styles(filepath: str) -> None:
    """
    应用Excel样式

    Args:
        filepath: Excel文件路径
    """
    try:
        wb = load_workbook(filepath)

        # 样式Sheet 1: 渠道维度预算表
        if '渠道维度预算表' in wb.sheetnames:
            ws = wb['渠道维度预算表']
            _style_table1_sheet(ws)

        # 样式Sheet 2: 客群维度汇总表
        if '客群维度汇总表' in wb.sheetnames:
            ws = wb['客群维度汇总表']
            _style_table2_sheet(ws)

        wb.save(filepath)

    except Exception as e:
        # 样式应用失败不应该阻止导出
        print(f"Warning: 应用Excel样式失败: {e}")


def _style_table1_sheet(ws) -> None:
    """
    为Sheet 1应用样式

    Args:
        ws: openpyxl worksheet对象
    """
    # 表头样式
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 边框
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # 应用表头样式
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border

    # 数据行样式
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center", vertical="center")

    # 汇总行样式 (最后一行)
    total_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")
    total_font = Font(bold=True, size=11)

    for cell in ws[ws.max_row]:
        cell.fill = total_fill
        cell.font = total_font
        cell.border = thin_border

    # 调整列宽
    for col_idx, col in enumerate(ws.columns, start=1):
        column_letter = get_column_letter(col_idx)
        max_length = 0
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass
        # 设置列宽 (最小12, 最大30)
        adjusted_width = min(max(max_length + 2, 12), 30)
        ws.column_dimensions[column_letter].width = adjusted_width

    # 冻结首行
    ws.freeze_panes = "A2"


def _style_table2_sheet(ws) -> None:
    """
    为Sheet 2应用样式 (保留指标名称中的缩进格式)

    Args:
        ws: openpyxl worksheet对象
    """
    # 表头样式
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_alignment = Alignment(horizontal="center", vertical="center")

    # 边框
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    # 应用表头样式
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = thin_border

    # 数据行样式
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
        # 第一列样式（已包含缩进）
        if row:
            first_cell = row[0]
            first_cell.alignment = Alignment(horizontal="left", vertical="center")

            # 判断是否为顶层指标（不包含缩进空格）
            if first_cell.value and not str(first_cell.value).startswith(' '):
                first_cell.font = Font(bold=True, size=11)

        # 其他列居中
        for cell in row[1:]:
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 应用边框
        for cell in row:
            cell.border = thin_border

    # 调整列宽
    ws.column_dimensions['A'].width = 35  # 指标列宽一些
    ws.column_dimensions['B'].width = 20  # 交易额列

    # 冻结首行
    ws.freeze_panes = "A2"
