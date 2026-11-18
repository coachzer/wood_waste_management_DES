"""Entity counts belong to one run's FacilityBuilder, so back-to-back runs in a process
(Monte Carlo) each report their own totals instead of a running sum."""
import contextlib
import io

from config.base_config import get_scenario_config
from core.simulation_manager import SimulationManager
from models.enums import InventoryPolicy, StockStrategy


def _facility_counts_after_initialization(seed):
    with contextlib.redirect_stdout(io.StringIO()):
        manager = SimulationManager(seed=seed)
        manager.initialize_entities(get_scenario_config("Baseline"), InventoryPolicy.PULL, StockStrategy.ON_DEMAND)
    return dict(manager.facility_builder.facility_counts), manager


def test_a_second_run_counts_only_its_own_entities():
    first_counts, first_manager = _facility_counts_after_initialization(seed=1)
    second_counts, _ = _facility_counts_after_initialization(seed=2)

    assert second_counts == first_counts
    assert first_counts["TreatmentOperator"] == len(first_manager.state.treatment_operators)
