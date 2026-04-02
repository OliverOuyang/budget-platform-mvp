"""
数据加载和验证模块
负责从Excel文件加载数据、验证结构、提取关键参数
"""

from typing import Tuple, Dict
import pandas as pd
import numpy as np

from app.config import REQUIRED_SHEETS, CHANNEL_NAMES

# Note: 'future.no_silent_downcasting' removed — modern pandas (>=2.0) no longer
# performs silent downcasting by default, so this global option is unnecessary.

def load_excel(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    加载Excel文件中的两个数据表

    Args:
        file_path: Excel文件路径

    Returns:
        Tuple[pd.DataFrame, pd.DataFrame]: (raw_达成情况, raw_客群首借金额)

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: Sheet不存在或格式错误
    """
    try:
        # 读取两个Sheet
        df_raw1 = pd.read_excel(file_path, sheet_name='raw_达成情况')
        df_raw2 = pd.read_excel(file_path, sheet_name='raw_客群首借金额')

        # 处理'\N' -> NaN转换
        df_raw1 = df_raw1.replace('\\N', np.nan)
        df_raw2 = df_raw2.replace('\\N', np.nan)

        return df_raw1, df_raw2

    except FileNotFoundError:
        raise FileNotFoundError(f"文件不存在: {file_path}")
    except ValueError as e:
        raise ValueError(f"Excel文件格式错误: {str(e)}")


def validate_excel_structure(df1: pd.DataFrame, df2: pd.DataFrame) -> bool:
    """
    验证Excel文件结构是否符合要求

    Args:
        df1: raw_达成情况 DataFrame
        df2: raw_客群首借金额 DataFrame

    Returns:
        bool: 验证通过返回True

    Raises:
        ValueError: 验证失败时抛出详细错误信息
    """
    # 获取必需列配置
    sheet1_config = REQUIRED_SHEETS['raw_达成情况']
    sheet2_config = REQUIRED_SHEETS['raw_客群首借金额']

    # 检查第一张表
    missing_cols_1 = set(sheet1_config['required_columns']) - set(df1.columns)
    if missing_cols_1:
        raise ValueError(
            f"raw_达成情况 缺少必需列: {', '.join(missing_cols_1)}\n"
            f"当前列: {', '.join(df1.columns.tolist())}"
        )

    # 检查第二张表
    missing_cols_2 = set(sheet2_config['required_columns']) - set(df2.columns)
    if missing_cols_2:
        raise ValueError(
            f"raw_客群首借金额 缺少必需列: {', '.join(missing_cols_2)}\n"
            f"当前列: {', '.join(df2.columns.tolist())}"
        )

    # 检查数据是否为空
    if df1.empty:
        raise ValueError("raw_达成情况 表为空")
    if df2.empty:
        raise ValueError("raw_客群首借金额 表为空")

    return True


def extract_last_month_data(df: pd.DataFrame) -> Dict:
    """
    从raw_达成情况提取最新月份数据,用于预填充参数

    Args:
        df: raw_达成情况 DataFrame

    Returns:
        Dict: {渠道类别: {参数名: 值}}
        示例: {
            '腾讯': {
                '1-3t0过件率': 0.45,
                '1-8t0cps': 1200,
                '1-8t0过件率': 0.38,
                't0申完成本': 150,
                '1-7过件率': 0.42,
                '花费': 3200000
            },
            ...
        }
    """
    # 处理空DataFrame
    if df.empty or '月份' not in df.columns:
        return {}

    # 获取最新月份
    df_clean = df.dropna(subset=['月份'])
    if df_clean.empty:
        return {}

    latest_month = df_clean['月份'].max()

    # 筛选最新月份数据
    df_latest = df_clean[df_clean['月份'] == latest_month].copy()

    # 提取各渠道数据
    result = {}

    for _, row in df_latest.iterrows():
        channel = row.get('渠道类别')
        if pd.isna(channel) or channel not in CHANNEL_NAMES:
            continue

        # 提取关键参数,处理可能的缺失值
        params = {}

        # 1-3t0过件率
        if '1-3t0过件率' in row and not pd.isna(row['1-3t0过件率']):
            params['1-3t0过件率'] = float(row['1-3t0过件率'])

        # 1-8t0cps
        if '1-8t0cps' in row and not pd.isna(row['1-8t0cps']):
            params['1-8t0cps'] = float(row['1-8t0cps'])

        # 1-8t0过件率
        if '1-8t0过件率' in row and not pd.isna(row['1-8t0过件率']):
            params['1-8t0过件率'] = float(row['1-8t0过件率'])

        # t0申完成本
        if 't0申完成本' in row and not pd.isna(row['t0申完成本']):
            params['t0申完成本'] = float(row['t0申完成本'])

        # 最新月花费，用于结果页历史花费基线和结构参考
        if '花费' in row and not pd.isna(row['花费']):
            params['花费'] = float(row['花费'])

        # 1-7过件率 (可能不存在)
        if '1-7过件率' in df.columns and '1-7过件率' in row and not pd.isna(row['1-7过件率']):
            params['1-7过件率'] = float(row['1-7过件率'])

        if params:
            result[channel] = params

    return result
