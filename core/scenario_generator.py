"""
目标驱动场景生成器

根据用户选择的优化方向（降成本/提质量/提规模）和梯度百分比，
自动生成3个参数集（保守/标准/激进），供场景对比计算使用。
"""
import copy
from typing import Dict, List


# ---------------------------------------------------------------------------
# 公共常量
# ---------------------------------------------------------------------------

VALID_DIRECTIONS: List[str] = ["降成本", "提质量", "提规模"]
GRADIENT_LABELS: List[str] = ["保守", "标准", "激进"]


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _format_pct(gradient: float) -> str:
    """将小数梯度格式化为整数百分比字符串，例如 0.05 → '5%'。"""
    return f"{round(gradient * 100)}%"


def _build_label(direction: str, gradient: float, level_label: str) -> str:
    """
    按方向构建场景标签。

    示例：
        降成本, 0.05, "保守" → "保守(CPS-5%)"
        提质量, 0.10, "标准" → "标准(过件率+10%)"
        提规模, 0.15, "激进" → "激进(预算+15%)"
    """
    pct = _format_pct(gradient)
    if direction == "降成本":
        return f"{level_label}(CPS-{pct})"
    elif direction == "提质量":
        return f"{level_label}(过件率+{pct})"
    else:  # 提规模
        return f"{level_label}(预算+{pct})"


def _apply_direction(
    direction: str,
    gradient: float,
    channel_budget_shares: Dict[str, float],
    channel_1_3_rate: Dict[str, float],
    channel_1_8_cps: Dict[str, float],
    channel_t0_cost: Dict[str, float],
    total_budget: float,
) -> dict:
    """
    对单个梯度应用方向映射，返回完整的参数字典（深拷贝）。

    参数修改规则：
        降成本 → channel_1_8_cps  × (1 - gradient)
        提质量 → channel_1_3_rate × (1 + gradient)
        提规模 → total_budget     × (1 + gradient)
    """
    shares = copy.deepcopy(channel_budget_shares)
    rate   = copy.deepcopy(channel_1_3_rate)
    cps    = copy.deepcopy(channel_1_8_cps)
    cost   = copy.deepcopy(channel_t0_cost)
    budget = total_budget

    if direction == "降成本":
        cps = {ch: v * (1.0 - gradient) for ch, v in cps.items()}
    elif direction == "提质量":
        rate = {ch: v * (1.0 + gradient) for ch, v in rate.items()}
    else:  # 提规模
        budget = total_budget * (1.0 + gradient)

    return {
        "total_budget":          budget,
        "channel_budget_shares": shares,
        "channel_1_3_rate":      rate,
        "channel_1_8_cps":       cps,
        "channel_t0_cost":       cost,
    }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def generate_goal_scenarios(
    channel_budget_shares: Dict[str, float],
    channel_1_3_rate: Dict[str, float],
    channel_1_8_cps: Dict[str, float],
    channel_t0_cost: Dict[str, float],
    total_budget: float,
    goal_direction: str,
    gradients: List[float],
) -> List[dict]:
    """
    生成3个目标驱动场景参数字典（保守/标准/激进）。

    Args:
        channel_budget_shares: 各渠道预算占比 {"渠道名": float, ...}
        channel_1_3_rate:      各渠道1/3过件率 {"渠道名": float, ...}
        channel_1_8_cps:       各渠道1/8 CPS  {"渠道名": float, ...}
        channel_t0_cost:       各渠道T0成本   {"渠道名": float, ...}
        total_budget:          总预算（万元）
        goal_direction:        优化方向，须为 VALID_DIRECTIONS 之一
        gradients:             3个梯度值列表，对应保守/标准/激进

    Returns:
        长度为3的列表，每个元素为包含以下键的字典：
            total_budget, channel_budget_shares, channel_1_3_rate,
            channel_1_8_cps, channel_t0_cost, label

    Raises:
        ValueError: goal_direction 不合法，或 gradients 长度不为3
    """
    if goal_direction not in VALID_DIRECTIONS:
        raise ValueError(
            f"goal_direction 须为 {VALID_DIRECTIONS} 之一，"
            f"实际传入：'{goal_direction}'"
        )
    if len(gradients) != 3:
        raise ValueError(
            f"gradients 须包含恰好3个值（保守/标准/激进），"
            f"实际长度：{len(gradients)}"
        )

    scenarios: List[dict] = []
    for level_label, gradient in zip(GRADIENT_LABELS, gradients):
        params = _apply_direction(
            direction=goal_direction,
            gradient=gradient,
            channel_budget_shares=channel_budget_shares,
            channel_1_3_rate=channel_1_3_rate,
            channel_1_8_cps=channel_1_8_cps,
            channel_t0_cost=channel_t0_cost,
            total_budget=total_budget,
        )
        params["label"] = _build_label(goal_direction, gradient, level_label)
        scenarios.append(params)

    return scenarios
