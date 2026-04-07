import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
import shutil

from core.template_manager import TemplateManager
from core.models import BudgetParameters
from app.config import CHANNEL_NAMES


@pytest.fixture
def manager():
    dirpath = tempfile.mkdtemp()
    yield TemplateManager(templates_dir=str(Path(dirpath) / "templates"))
    shutil.rmtree(dirpath, ignore_errors=True)


@pytest.fixture
def sample_params():
    return BudgetParameters(
        total_budget=3000.0,
        channel_1_3_approval_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_completion_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        non_initial_credit_transaction=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
        month_total_days=30,
        days_elapsed=25,
    )


def test_save_and_load_roundtrip(manager, sample_params):
    """Save then load returns same total_budget."""
    manager.save_template(
        template_name="test_template",
        params=sample_params,
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        channel_1_3_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        non_initial_credit=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
        description="test",
    )
    loaded = manager.load_template("test_template")
    assert loaded is not None
    assert loaded["parameters"]["total_budget"] == sample_params.total_budget


def test_delete_template(manager, sample_params):
    """delete_template returns True; subsequent load returns None."""
    manager.save_template(
        template_name="to_delete",
        params=sample_params,
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        channel_1_3_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        non_initial_credit=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
    )
    deleted = manager.delete_template("to_delete")
    assert deleted is True
    assert manager.load_template("to_delete") is None


def test_list_templates(manager, sample_params):
    """Saved templates appear in list_templates."""
    manager.save_template(
        template_name="alpha",
        params=sample_params,
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        channel_1_3_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        non_initial_credit=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
    )
    manager.save_template(
        template_name="beta",
        params=sample_params,
        channel_budget_shares={ch: 0.2 for ch in CHANNEL_NAMES},
        channel_1_3_rate={ch: 0.45 for ch in CHANNEL_NAMES},
        channel_1_8_cps={ch: 0.30 for ch in CHANNEL_NAMES},
        channel_t0_cost={ch: 150.0 for ch in CHANNEL_NAMES},
        non_initial_credit=0.5,
        existing_m0_expense=500.0,
        rta_promotion_fee=100.0,
    )
    names = [t["name"] for t in manager.list_templates()]
    assert "alpha" in names
    assert "beta" in names
