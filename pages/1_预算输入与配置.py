import tempfile
from typing import Dict

import pandas as pd
import streamlit as st

from app.flow_components import (
    render_flow_header,
    render_guidance_card,
    render_next_step_card,
    render_section_intro,
    render_status_card,
    render_step_progress,
)
from app.ui_utils import (
    ensure_flow_state,
    format_month,
    get_v01_flow,
    normalize_channel_history,
    reset_v01_flow_for_new_upload,
    update_v01_flow,
)
from core.data_loader import load_excel, validate_excel_structure


def _render_upload_diagnostics(df_raw1: pd.DataFrame, df_raw2: pd.DataFrame, file_name: str) -> Dict[str, int]:
    """展示上传后的数据质量、统计特征与趋势分布。"""
    normalized = normalize_channel_history(df_raw1)
    missing_cells = int(df_raw1.isna().sum().sum() + df_raw2.isna().sum().sum())
    duplicated_rows = int(df_raw1.duplicated().sum() + df_raw2.duplicated().sum())
    shared_months = sorted(
        set(normalized.get("月份标签", pd.Series(dtype=str)).dropna().tolist())
        & set(df_raw2.get("月份", pd.Series(dtype="datetime64[ns]")).dropna().map(format_month).tolist())
    )

    issues = []
    if missing_cells > 0:
        issues.append(f"发现 {missing_cells:,} 个缺失单元格")
    if duplicated_rows > 0:
        issues.append(f"发现 {duplicated_rows:,} 行重复记录")
    if not shared_months:
        issues.append("两张表没有交集月份，结果可信度会下降")

    render_section_intro("检查摘要", "先看本次上传是否存在结构风险，再按 tab 深入查看数据细节。")
    summary_cols = st.columns(4)
    summary_cols[0].metric("上传文件", file_name)
    summary_cols[1].metric("raw_达成情况", f"{len(df_raw1):,} 行")
    summary_cols[2].metric("raw_客群首借金额", f"{len(df_raw2):,} 行")
    summary_cols[3].metric("共享月份", len(shared_months))

    status_cols = st.columns(3)
    with status_cols[0]:
        render_status_card(
            "缺失单元格",
            f"{missing_cells:,}",
            "0 表示未发现明显缺失。" if missing_cells == 0 else "建议重点查看质量检查 tab 中的字段缺失率。",
            status="success" if missing_cells == 0 else "warning",
        )
    with status_cols[1]:
        render_status_card(
            "重复记录",
            f"{duplicated_rows:,}",
            "0 表示未发现重复记录。" if duplicated_rows == 0 else "重复记录可能影响后续历史基线判断。",
            status="success" if duplicated_rows == 0 else "warning",
        )
    with status_cols[2]:
        render_status_card(
            "交集月份",
            f"{len(shared_months)} 个月",
            "两张表时间范围可对齐。" if shared_months else "没有交集月份时，结果可信度会明显下降。",
            status="success" if shared_months else "danger",
        )

    if issues:
        st.warning("；".join(issues))
    else:
        st.success("数据完整性检查通过，未发现明显结构问题。")

    tabs = st.tabs(["📋 数据预览", "🩺 质量检查", "📊 统计特征", "📈 趋势与分布"])

    with tabs[0]:
        render_section_intro("双表预览", "先确认字段命名、月份格式和关键数值列是否符合预期。")
        preview_col1, preview_col2 = st.columns(2)
        with preview_col1:
            st.caption("raw_达成情况")
            st.dataframe(df_raw1.head(10), width="stretch", hide_index=True)
        with preview_col2:
            st.caption("raw_客群首借金额")
            st.dataframe(df_raw2.head(10), width="stretch", hide_index=True)

    with tabs[1]:
        render_section_intro("结构质量", "这里主要看缺失率、重复记录和两张表的时间对齐情况。")
        quality_rows = []
        for sheet_name, df in [("raw_达成情况", df_raw1), ("raw_客群首借金额", df_raw2)]:
            missing_rate = df.isna().mean().mul(100).sort_values(ascending=False)
            for col_name, pct in missing_rate.items():
                if pct > 0:
                    quality_rows.append(
                        {
                            "数据表": sheet_name,
                            "字段": col_name,
                            "缺失率(%)": pct,
                            "数据类型": str(df[col_name].dtype),
                        }
                    )

        quality_cols = st.columns(3)
        quality_cols[0].metric("缺失单元格", f"{missing_cells:,}")
        quality_cols[1].metric("重复记录", f"{duplicated_rows:,}")
        quality_cols[2].metric("共享月份", len(shared_months))

        if quality_rows:
            st.dataframe(
                pd.DataFrame(quality_rows).sort_values(["缺失率(%)", "数据表"], ascending=[False, True]),
                width="stretch",
                hide_index=True,
                column_config={"缺失率(%)": st.column_config.NumberColumn(format="%.2f%%")},
            )
        else:
            st.info("两张表均未发现缺失字段。")

    with tabs[2]:
        render_section_intro("统计特征", "这些统计量会成为结果页上调整参数时的历史参考。")
        stats_left, stats_right = st.columns(2)
        with stats_left:
            numeric_cols_raw1 = df_raw1.select_dtypes(include="number")
            if not numeric_cols_raw1.empty:
                st.markdown("**raw_达成情况数值字段统计**")
                st.dataframe(numeric_cols_raw1.describe().T.round(4), width="stretch")
            else:
                st.info("raw_达成情况暂无可统计的数值字段。")
        with stats_right:
            numeric_cols_raw2 = df_raw2.select_dtypes(include="number")
            if not numeric_cols_raw2.empty:
                st.markdown("**raw_客群首借金额数值字段统计**")
                st.dataframe(numeric_cols_raw2.describe().T.round(4), width="stretch")
            else:
                st.info("raw_客群首借金额暂无可统计的数值字段。")

    with tabs[3]:
        render_section_intro("趋势与结构", "优先观察近月总花费趋势和最新月渠道花费结构是否符合业务预期。")
        if normalized.empty or "月份标签" not in normalized.columns:
            st.info("当前数据不足以生成趋势与分布图。")
        else:
            trend_col1, trend_col2 = st.columns(2)
            monthly_expense = normalized.groupby("月份标签", as_index=False)["花费"].sum().sort_values("月份标签")
            latest_month = normalized["月份标签"].dropna().max()
            latest_channel = normalized[normalized["月份标签"] == latest_month].copy().dropna(subset=["渠道类别"])

            with trend_col1:
                if not monthly_expense.empty:
                    st.line_chart(monthly_expense, x="月份标签", y="花费")
                    st.caption("近月总花费趋势（元）")
            with trend_col2:
                if not latest_channel.empty:
                    latest_share = latest_channel.groupby("渠道类别", as_index=False)["花费"].sum()
                    st.bar_chart(latest_share, x="渠道类别", y="花费")
                    st.caption(f"{latest_month} 渠道花费分布（元）")

    return {
        "missing_cells": missing_cells,
        "duplicated_rows": duplicated_rows,
        "shared_months": len(shared_months),
        "raw1_rows": len(df_raw1),
        "raw2_rows": len(df_raw2),
    }


def _handle_upload(uploaded_file) -> None:
    if uploaded_file is None:
        st.session_state.uploaded_data = None
        st.session_state.last_file_id = None
        reset_v01_flow_for_new_upload()
        return

    if st.session_state.get("last_file_id") == uploaded_file.file_id:
        return

    try:
        with st.spinner("正在读取文件..."):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_path = tmp.name
            df_raw1, df_raw2 = load_excel(tmp_path)
            validate_excel_structure(df_raw1, df_raw2)

        st.session_state.uploaded_data = {
            "df_raw1": df_raw1,
            "df_raw2": df_raw2,
            "file_name": uploaded_file.name,
        }
        st.session_state.last_file_id = uploaded_file.file_id
        st.session_state.table1_result = None
        st.session_state.table2_result = None
        reset_v01_flow_for_new_upload()
        update_v01_flow(
            current_step=1,
            data={"file_name": uploaded_file.name},
            next_step="查看数据检查 tabs，确认质量后进入预算推算结果页",
        )
        st.success(f"✅ 文件 '{uploaded_file.name}' 加载成功")
    except Exception as exc:
        st.error(f"❌ 加载失败: {exc}")
        st.session_state.uploaded_data = None
        st.session_state.last_file_id = None
        reset_v01_flow_for_new_upload()


ensure_flow_state()
flow = get_v01_flow()
steps = ["数据上传与检查", "预算推算结果"]

render_flow_header(
    title="📊 V01 · 数据上传与检查",
    purpose="上传业务数据并完成质量检查、统计特征和趋势浏览，为预算推算结果页上的参数配置提供可靠输入基础。",
    chain="数据上传与检查 → 预算推算结果",
    current_label="数据上传与检查",
)
render_step_progress(steps, 1)
update_v01_flow(current_step=1, next_step="上传数据后检查 tabs，再进入预算推算结果页")

st.subheader("上传数据文件")
hero_left, hero_right = st.columns([1.4, 1])
with hero_left:
    with st.container(border=True):
        render_section_intro("上传入口", "先上传 Excel，再在下方完成数据检查，最后进入预算推算结果页。")
        uploaded_file = st.file_uploader("上传 Excel 文件 (*.xlsx)", type=["xlsx"], label_visibility="visible")
        st.caption("支持预算输入所需的双表 Excel 结构。上传成功后会直接展开检查内容。")
with hero_right:
    with st.container(border=True):
        render_section_intro("本页流程", "两步式 V01 的第一步只做上传与检查，不在这里配置预算参数。")
        st.write("- 上传文件")
        st.write("- 查看质量检查、统计特征、趋势分布")
        st.write("- 确认后进入结果页进行参数配置和计算")
_handle_upload(uploaded_file)

data = st.session_state.get("uploaded_data")
if data is None:
    render_guidance_card(
        "尚未上传数据",
        "请先上传预算输入 Excel。上传成功后，页面下方会直接出现数据检查 tabs。",
        kind="warning",
    )
    st.stop()

st.subheader("数据检查")
diagnostics = _render_upload_diagnostics(data["df_raw1"], data["df_raw2"], data["file_name"])
update_v01_flow(
    current_step=1,
    data={"file_name": data["file_name"]},
    diagnostics=diagnostics,
    next_step="进入预算推算结果页，在顶部完成参数配置和预算计算",
)

with st.container(border=True):
    render_next_step_card(
        "预算推算结果",
        "确认数据质量后，跳转到预算推算结果页，在页面顶部配置参数、管理模板并执行计算。",
    )
    action_left, action_right = st.columns([1, 1.4])
    if action_left.button("重新上传文件", use_container_width=True):
        st.session_state.uploaded_data = None
        st.session_state.last_file_id = None
        reset_v01_flow_for_new_upload()
        st.rerun()
    if action_right.button("进入预算推算结果页", type="primary", use_container_width=True):
        st.switch_page("pages/2_预算推算结果.py")
