"""On a real run, every generator node's outflows in the MFA Sankey add up to its potential generation."""
from collections import defaultdict

import pytest

from models.enums import InventoryPolicy, StockStrategy


@pytest.mark.slow
@pytest.mark.parametrize("inventory_policy", [InventoryPolicy.PUSH, InventoryPolicy.PULL])
def test_generator_outflows_sum_to_potential_generation(inventory_policy):
    """Collection links plus the Uncollected, Outlet and Stock at day 365 sinks cover all of it.

    Mutation check (red): drop the Stock at day 365 sink. Slow: a full baseline run.
    """
    from core.simulation_manager import SimulationManager
    from config.base_config import get_scenario_config
    from visualization.mfa_visualization import create_sankey, get_volumes

    manager = SimulationManager(seed=1)
    manager.initialize_entities(get_scenario_config("Baseline"), inventory_policy, StockStrategy.ON_DEMAND)
    manager.setup_processes(raise_on_violation=False)
    manager.run_simulation()
    monitor_data = manager.get_monitor_data()
    volumes = get_volumes(monitor_data["generation_history"], monitor_data["collection_history"],
                          monitor_data["processing_history"], manager.state)

    labels, _, sources, _, values, _, _, _ = create_sankey(*volumes, manager.state)

    outflow = defaultdict(float)
    for source_index, value in zip(sources, values):
        outflow[source_index] += value
    potential_by_generator = volumes[0]
    matched_generators = set()
    for index, label in enumerate(labels):
        name = label.split("\n", 1)[0]
        if name in potential_by_generator:
            matched_generators.add(name)
            assert outflow[index] == pytest.approx(potential_by_generator[name], rel=1e-6, abs=1.0), name
    assert potential_by_generator and matched_generators == set(potential_by_generator)
