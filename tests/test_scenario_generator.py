"""Tests for core/scenario_generator.py"""
import copy
import pytest
from core.scenario_generator import (
    generate_goal_scenarios,
    VALID_DIRECTIONS,
    GRADIENT_LABELS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_params():
    """Typical 5-channel V01 parameter set."""
    return {
        "channel_budget_shares": {"腾讯": 0.30, "抖音": 0.25, "精准营销": 0.20, "付费商店": 0.15, "免费渠道": 0.10},
        "channel_1_3_rate": {"腾讯": 0.15, "抖音": 0.12, "精准营销": 0.10, "付费商店": 0.08, "免费渠道": 0.20},
        "channel_1_8_cps": {"腾讯": 0.25, "抖音": 0.30, "精准营销": 0.22, "付费商店": 0.35, "免费渠道": 0.18},
        "channel_t0_cost": {"腾讯": 150.0, "抖音": 180.0, "精准营销": 120.0, "付费商店": 200.0, "免费渠道": 80.0},
        "total_budget": 3000.0,
    }


# ---------------------------------------------------------------------------
# Basic generation tests
# ---------------------------------------------------------------------------

class TestGenerateGoalScenarios:

    def test_returns_3_scenarios(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        assert len(result) == 3

    def test_each_scenario_has_required_keys(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        required_keys = {"total_budget", "channel_budget_shares", "channel_1_3_rate", "channel_1_8_cps", "channel_t0_cost", "label"}
        for sc in result:
            assert required_keys.issubset(sc.keys()), f"Missing keys: {required_keys - sc.keys()}"


class TestCostReduction:
    """降成本: only CPS changes, multiplied by (1 - gradient)."""

    def test_cps_reduced(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        for i, gradient in enumerate([0.05, 0.10, 0.15]):
            for ch in sample_params["channel_1_8_cps"]:
                expected = sample_params["channel_1_8_cps"][ch] * (1 - gradient)
                assert abs(result[i]["channel_1_8_cps"][ch] - expected) < 1e-10

    def test_other_params_unchanged(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        for sc in result:
            assert sc["total_budget"] == sample_params["total_budget"]
            assert sc["channel_budget_shares"] == sample_params["channel_budget_shares"]
            assert sc["channel_1_3_rate"] == sample_params["channel_1_3_rate"]
            assert sc["channel_t0_cost"] == sample_params["channel_t0_cost"]

    def test_labels(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        assert result[0]["label"] == "保守(CPS-5%)"
        assert result[1]["label"] == "标准(CPS-10%)"
        assert result[2]["label"] == "激进(CPS-15%)"


class TestQualityImprovement:
    """提质量: only 1-3 rate changes, multiplied by (1 + gradient)."""

    def test_rate_increased(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提质量", gradients=[0.05, 0.10, 0.15])
        for i, gradient in enumerate([0.05, 0.10, 0.15]):
            for ch in sample_params["channel_1_3_rate"]:
                expected = sample_params["channel_1_3_rate"][ch] * (1 + gradient)
                assert abs(result[i]["channel_1_3_rate"][ch] - expected) < 1e-10

    def test_other_params_unchanged(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提质量", gradients=[0.05, 0.10, 0.15])
        for sc in result:
            assert sc["total_budget"] == sample_params["total_budget"]
            assert sc["channel_1_8_cps"] == sample_params["channel_1_8_cps"]
            assert sc["channel_t0_cost"] == sample_params["channel_t0_cost"]

    def test_labels(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提质量", gradients=[0.05, 0.10, 0.15])
        assert result[0]["label"] == "保守(过件率+5%)"
        assert result[1]["label"] == "标准(过件率+10%)"
        assert result[2]["label"] == "激进(过件率+15%)"


class TestScaleUp:
    """提规模: only total_budget changes, multiplied by (1 + gradient)."""

    def test_budget_increased(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提规模", gradients=[0.05, 0.10, 0.15])
        for i, gradient in enumerate([0.05, 0.10, 0.15]):
            expected = sample_params["total_budget"] * (1 + gradient)
            assert abs(result[i]["total_budget"] - expected) < 1e-10

    def test_shares_unchanged(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提规模", gradients=[0.05, 0.10, 0.15])
        for sc in result:
            assert sc["channel_budget_shares"] == sample_params["channel_budget_shares"]
            assert sc["channel_1_3_rate"] == sample_params["channel_1_3_rate"]
            assert sc["channel_1_8_cps"] == sample_params["channel_1_8_cps"]

    def test_labels(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="提规模", gradients=[0.05, 0.10, 0.15])
        assert result[0]["label"] == "保守(预算+5%)"
        assert result[2]["label"] == "激进(预算+15%)"


class TestEdgeCases:

    def test_gradient_zero_returns_identical(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.0, 0.0, 0.0])
        for sc in result:
            assert sc["channel_1_8_cps"] == sample_params["channel_1_8_cps"]
            assert sc["total_budget"] == sample_params["total_budget"]

    def test_gradient_one_sets_cps_to_zero(self, sample_params):
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[1.0, 1.0, 1.0])
        for sc in result:
            for ch in sc["channel_1_8_cps"]:
                assert sc["channel_1_8_cps"][ch] == 0.0

    def test_deep_copy_isolation(self, sample_params):
        original_cps = copy.deepcopy(sample_params["channel_1_8_cps"])
        result = generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        # Modify the result — should NOT affect input
        result[0]["channel_1_8_cps"]["腾讯"] = 999.0
        assert sample_params["channel_1_8_cps"]["腾讯"] == original_cps["腾讯"]

    def test_zero_cps_no_error(self):
        params = {
            "channel_budget_shares": {"A": 0.5, "B": 0.5},
            "channel_1_3_rate": {"A": 0.1, "B": 0.2},
            "channel_1_8_cps": {"A": 0.0, "B": 0.0},
            "channel_t0_cost": {"A": 100.0, "B": 200.0},
            "total_budget": 1000.0,
        }
        result = generate_goal_scenarios(**params, goal_direction="降成本", gradients=[0.05, 0.10, 0.15])
        for sc in result:
            assert sc["channel_1_8_cps"]["A"] == 0.0
            assert sc["channel_1_8_cps"]["B"] == 0.0


class TestValidation:

    def test_invalid_direction_raises(self, sample_params):
        with pytest.raises(ValueError, match="goal_direction"):
            generate_goal_scenarios(**sample_params, goal_direction="无效方向", gradients=[0.05, 0.10, 0.15])

    def test_wrong_gradient_count_raises(self, sample_params):
        with pytest.raises(ValueError, match="gradients"):
            generate_goal_scenarios(**sample_params, goal_direction="降成本", gradients=[0.05, 0.10])

    def test_constants_correct(self):
        assert VALID_DIRECTIONS == ["降成本", "提质量", "提规模"]
        assert GRADIENT_LABELS == ["保守", "标准", "激进"]
