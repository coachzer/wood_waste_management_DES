from copy import deepcopy
from dataclasses import dataclass
from typing import Dict, Tuple, List
from config.constants import FINISHED_GOODS_BUFFER_WEEKS
from models.data_classes import FailureConfig

@dataclass
class ScenarioConfig:
    """The operating environment of one scenario; policy and strategy are a separate grid axis."""
    name: str
    waste_generation_mean: float  # multiplier on the calibrated regional rates
    waste_generation_variability: float  # std of the daily Normal(1, std) generation factor
    treatment_conversion: Tuple[float, float]  # (mean multiplier, std) on catalogue efficiency
    transportation_time: Tuple[float, float]  # (mean, std) road circuity over great-circle distance (ADR 0015)
    generator_failure: FailureConfig
    collector_failure: FailureConfig
    treatment_failure: FailureConfig
    finished_goods_buffer_weeks: int = FINISHED_GOODS_BUFFER_WEEKS  # swept by the bucket-C sensitivity scenarios

LOW_FAILURE = FailureConfig(
    probability=0.0024,
    min_duration=1.0,
    max_duration=3.0,
)

MEDIUM_FAILURE = FailureConfig(
    probability=0.06,
    min_duration=0.5,
    max_duration=2.0,
)

HIGH_FAILURE = FailureConfig(
    probability=0.12,
    min_duration=0.25,
    max_duration=1.5,
)

DISASTER_FAILURE = FailureConfig(
    probability=0.24,
    min_duration=30.0,
    max_duration=60.0,
)

SCENARIO_CONFIGS: Dict[str, ScenarioConfig] = {
    "Baseline": ScenarioConfig(
        name="Baseline",
        waste_generation_mean=1.0,
        waste_generation_variability=0.1,
        treatment_conversion=(0.9, 0.03),
        transportation_time=(1.35, 0.1),  # Road circuity over great-circle distance (ADR 0015)
        generator_failure=LOW_FAILURE,
        collector_failure=MEDIUM_FAILURE,
        treatment_failure=HIGH_FAILURE,
    ),
    # Contracted, volatile generation with degraded collection/treatment and
    # stretched transport. Calibration anchor: 2020 COVID contraction (-9%
    # total, -11% C&D waste, Eurostat env_wasgen W075); the 0.60 multiplier is
    # deliberately more severe than observed -- a beyond-observed stress case.
    # Reorder checks count on-hand stock only (not in-transit), so the long
    # transportation_time lets orders stack before the first lands -- expected overshoot,
    # stated as a manuscript footnote. Bullwhip amplification grows with both
    # the mean and variance of lead time (Chen et al. 2000, "Quantifying the
    # bullwhip effect in a simple supply chain", Management Science 46(3)),
    # which motivates the stretched transportation_time=(4.0, 1.2) here.
    "SupplyDisruption": ScenarioConfig(
        name="SupplyDisruption",
        waste_generation_mean=0.60,
        waste_generation_variability=0.25,
        treatment_conversion=(0.9, 0.03),
        transportation_time=(4.0, 1.2),
        generator_failure=LOW_FAILURE,
        collector_failure=HIGH_FAILURE,
        treatment_failure=HIGH_FAILURE,
    ),
    # Abundant waste GENERATION with fast transport and reliable infrastructure.
    # The surge is in feedstock supply (waste available for treatment capacity),
    # not in market product demand -- the demand envelope (annual_demand in
    # demand.json) is unchanged across all scenarios. This distinction is why
    # the scenario is named GenerationSurge rather than DemandSurge.
    # Calibration anchor: 2023 Slovenia floods (+15% wood waste nationally;
    # Savinjska +21%, Koroska +19%; SURS/Eurostat env_wasgen), pushed to a
    # 1.50 multiplier. Tests whether PUSH buffers saturate or PULL exploits
    # the abundance.
    "GenerationSurge": ScenarioConfig(
        name="GenerationSurge",
        waste_generation_mean=1.50,
        waste_generation_variability=0.15,
        treatment_conversion=(0.9, 0.03),
        transportation_time=(1.5, 0.15),
        generator_failure=LOW_FAILURE,
        collector_failure=LOW_FAILURE,
        treatment_failure=LOW_FAILURE,
    ),
}

# Finished-goods buffer sensitivity sweep (bucket-C C1): each scenario is Baseline
# with only the finished-goods buffer resized, built from Baseline so shared
# parameters cannot drift. Buffer4 is the default and must reproduce Baseline.
BUFFER_SWEEP_WEEKS: Tuple[int, ...] = (2, 4, 6, 8)
for _buffer_weeks in BUFFER_SWEEP_WEEKS:
    _scenario = deepcopy(SCENARIO_CONFIGS["Baseline"])
    _scenario.name = f"Buffer{_buffer_weeks}"
    _scenario.finished_goods_buffer_weeks = _buffer_weeks
    SCENARIO_CONFIGS[_scenario.name] = _scenario

def validate_all_numeric_positive(
    config_dict: Dict[str, float],
    allow_zero: bool = False
) -> None:
    """Validate that all numeric values in a dictionary are positive

    Args:
        config_dict: Dictionary of configuration values
        allow_zero: Whether to allow zero values
    """
    for key, value in config_dict.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if allow_zero:
            if value < 0:
                raise ValueError(f"{key} must be non-negative")
        else:
            if value <= 0:
                raise ValueError(f"{key} must be positive")

def validate_tuple(mean_std_tuple: Tuple[float, float], name: str) -> None:
    """Validate a mean/std tuple

    Both mean and std are validated as non-negative via allow_zero=True. The std
    field previously carried a manual re-check after being excluded through an
    `exceptions` argument; that exclusion-then-recheck applied the identical
    `value < 0` rule, so it was redundant and has been removed.
    """
    config_dict = {
        f"{name}_mean": mean_std_tuple[0],
        f"{name}_std": mean_std_tuple[1]
    }

    validate_all_numeric_positive(config_dict, allow_zero=True)

def validate_scenario_config(config: ScenarioConfig) -> None:
    """Validate a scenario configuration"""
    validate_tuple((config.waste_generation_mean, config.waste_generation_variability), "Waste generation")
    validate_tuple(config.treatment_conversion, "Treatment conversion")
    validate_tuple(config.transportation_time, "Transportation time")
    if config.finished_goods_buffer_weeks <= 0:
        raise ValueError("finished_goods_buffer_weeks must be positive")

for config in SCENARIO_CONFIGS.values():
    validate_scenario_config(config)

def get_scenario_config(scenario_name: str) -> ScenarioConfig:
    """Get scenario configuration by name"""
    if scenario_name not in SCENARIO_CONFIGS:
        raise KeyError(f"Scenario '{scenario_name}' not found")
    return SCENARIO_CONFIGS[scenario_name]

def list_available_scenarios() -> List[str]:
    """List all available scenario names"""
    return list(SCENARIO_CONFIGS.keys())
