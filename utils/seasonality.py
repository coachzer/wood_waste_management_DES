import math

from config.constants import SEASONAL_AMPLITUDE, SEASONAL_PERIODS, SIMULATION_DURATION


def current_season_index(current_time: float) -> int:
    """Quarter index (0-based) for a simulation time, clamped to the last period."""
    return min(
        SEASONAL_PERIODS - 1,
        int(current_time / (SIMULATION_DURATION / SEASONAL_PERIODS)),
    )


def seasonal_factor_standard_deviation() -> float:
    """Population standard deviation of the seasonal factor across its periods (mean is 1)."""
    deviations = [
        SEASONAL_AMPLITUDE * math.sin(2 * math.pi * season_index / SEASONAL_PERIODS)
        for season_index in range(SEASONAL_PERIODS)
    ]
    return math.sqrt(sum(deviation ** 2 for deviation in deviations) / SEASONAL_PERIODS)


def seasonal_factor(current_time: float) -> float:
    """Quarter-discretized seasonal multiplier shared by generation and consumption.

    Both waste generation (WasteGenerator) and market consumption
    (SimulationManager) must read the same sinusoid so supply and demand share
    one rhythm; this is the single home for that formula.
    """
    season_index = current_season_index(current_time)
    return 1 + SEASONAL_AMPLITUDE * math.sin(2 * math.pi * season_index / SEASONAL_PERIODS)
