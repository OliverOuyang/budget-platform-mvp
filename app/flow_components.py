from __future__ import annotations

import streamlit as st
from typing import Iterable


def render_flow_header(
    *,
    title: str,
    purpose: str,
    chain: str,
    current_label: str,
) -> None:
    """Render a consistent workflow header across Streamlit pages."""
    st.title(title)
    st.markdown(
        f"""
> **本页面的作用**：{purpose}
>
> **在决策链路中的位置**：{chain}
"""
    )
    st.caption(f"当前步骤：{current_label}")


def render_step_progress(steps: list[str], current_step: int) -> None:
    """Render a compact step progress strip."""
    cols = st.columns(len(steps))
    for index, (col, label) in enumerate(zip(cols, steps), start=1):
        state = "✅ 已完成" if index < current_step else "➡️ 当前" if index == current_step else "⏳ 待进行"
        with col.container(border=True):
            st.caption(f"步骤 {index}")
            st.markdown(f"**{label}**")
            st.caption(state)


def render_guidance_card(title: str, body: str, *, kind: str = "info") -> None:
    """Render a lightweight guidance box without custom HTML."""
    if kind == "success":
        st.success(f"**{title}**\n\n{body}")
    elif kind == "warning":
        st.warning(f"**{title}**\n\n{body}")
    else:
        st.info(f"**{title}**\n\n{body}")


def render_next_step_card(title: str, body: str) -> None:
    """Render a standard next-step callout."""
    st.info(f"**下一步：{title}**\n\n{body}")


def render_section_intro(title: str, body: str) -> None:
    """Render a compact section heading with short guidance."""
    st.markdown(f"**{title}**")
    st.caption(body)


def render_status_card(title: str, value: str, detail: str, *, status: str = "info") -> None:
    """Render a compact bordered status block for workflow comparisons."""
    icon = {
        "success": "✅",
        "warning": "⚠️",
        "danger": "⛔",
        "info": "ℹ️",
    }.get(status, "ℹ️")
    with st.container(border=True):
        st.caption(f"{icon} {title}")
        st.markdown(f"**{value}**")
        st.caption(detail)


def render_bullet_summary(title: str, items: Iterable[str], *, empty_message: str = "暂无可展示内容。") -> None:
    """Render short decision bullets in a stable format."""
    st.markdown(f"**{title}**")
    filtered = [item for item in items if item]
    if not filtered:
        st.caption(empty_message)
        return
    for item in filtered:
        st.write(f"- {item}")


def render_section_header(title: str, body: str | None = None) -> None:
    """Render a compact section header used inside bordered blocks."""
    st.markdown(f"**{title}**")
    if body:
        st.caption(body)
