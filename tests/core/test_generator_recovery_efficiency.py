"""A recovering generator produces efficiency x its rate, not efficiency^2 (T5)."""

import simpy
import pytest

from config.constants import RECOVERING_BASE_EFFICIENCY
from models.enums import EntityStatus, WasteType
from tests.core.factories import make_waste_generator


PAPER = WasteType.PAPER_PACKAGING_15_01_01


def _potential_after_one_recovering_tick(recovery_progress):
    generator = make_waste_generator(simpy.Environment(), None, {PAPER: 100.0})
    generator._calculate_daily_factors = lambda: [1.0]
    generator.status = EntityStatus.FAILED
    generator.apply_failure_tick()
    generator.status = EntityStatus.RECOVERING
    generator.recovery_progress = recovery_progress
    generator.apply_failure_tick()
    generator._generate_waste_for_period(seasonal_factor=1.0)
    return generator.total_potential_generated[PAPER], generator


def test_recovering_generation_scales_by_efficiency_once():
    potential, generator = _potential_after_one_recovering_tick(0.5)
    ramp = RECOVERING_BASE_EFFICIENCY + (1.0 - RECOVERING_BASE_EFFICIENCY) * 0.5

    assert generator.efficiency == pytest.approx(ramp)
    assert potential == pytest.approx(100.0 * ramp)


def test_back_to_operational_restores_full_rate():
    _, generator = _potential_after_one_recovering_tick(0.5)
    generator.status = EntityStatus.OPERATIONAL
    generator.apply_failure_tick()
    before = generator.total_potential_generated[PAPER]
    generator._generate_waste_for_period(seasonal_factor=1.0)

    assert generator.total_potential_generated[PAPER] - before == pytest.approx(100.0)


def test_configured_efficiency_survives_a_failure_cycle():
    generator = make_waste_generator(simpy.Environment(), None, {PAPER: 100.0}, efficiency=0.8)
    for status in (EntityStatus.FAILED, EntityStatus.RECOVERING, EntityStatus.OPERATIONAL):
        generator.status = status
        generator.apply_failure_tick()

    assert generator.efficiency == pytest.approx(0.8)


def test_failed_generator_reports_zero_efficiency():
    generator = make_waste_generator(simpy.Environment(), None, {PAPER: 100.0})
    generator.status = EntityStatus.FAILED
    generator.apply_failure_tick()

    assert generator.efficiency == 0.0
