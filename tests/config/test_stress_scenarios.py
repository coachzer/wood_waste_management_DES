"""The two stress scenarios exist and carry their documented calibration anchors.

Scenario-config redesign, second half: `SCENARIO_CONFIGS` gains Supply
Disruption and Generation Surge beside Baseline. The failure mode guarded here
is calibration drift -- a scenario silently missing from the registry, or its
anchor parameters (researched against Eurostat env_wasgen W075 for the COVID
contraction and the 2023 Slovenia floods for the generation surge) drifting
away from the documented values, which would invalidate any cross-scenario
comparison in the paper.

Non-vacuity: each assertion pins an exact anchor value that differs from
Baseline's, so a deepcopy-of-Baseline placeholder (the easy wrong
implementation, cf. the buffer sweep) goes red.
"""

from config.base_config import (
    HIGH_FAILURE,
    LOW_FAILURE,
    SCENARIO_CONFIGS,
    get_scenario_config,
)


def test_supply_disruption_scenario_carries_its_calibration_anchors():
    """Supply Disruption: contracted volatile generation, degraded collection
    and treatment, stretched transport -- beyond-observed COVID contraction."""
    scenario = get_scenario_config("SupplyDisruption")

    assert scenario.waste_gen == (0.60, 0.25)
    assert scenario.trans_time == (4.0, 1.2)
    assert scenario.treat_conv == SCENARIO_CONFIGS["Baseline"].treat_conv
    assert scenario.generator_failure == LOW_FAILURE
    assert scenario.collector_failure == HIGH_FAILURE
    assert scenario.treatment_failure == HIGH_FAILURE


def test_generation_surge_scenario_carries_its_calibration_anchors():
    """Generation Surge: abundant waste generation, fast transport, low failures
    at every echelon -- the 2023 Slovenia floods anchor (feedstock supply surge,
    not a market product demand increase)."""
    scenario = get_scenario_config("GenerationSurge")

    assert scenario.waste_gen == (1.50, 0.15)
    assert scenario.trans_time == (1.5, 0.15)
    assert scenario.treat_conv == SCENARIO_CONFIGS["Baseline"].treat_conv
    assert scenario.generator_failure == LOW_FAILURE
    assert scenario.collector_failure == LOW_FAILURE
    assert scenario.treatment_failure == LOW_FAILURE
