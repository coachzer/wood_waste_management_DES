"""Collector efficiency is the same for every policy and strategy (ADR 0025)."""
import itertools

import pytest
import simpy

from config.constants import COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY
from core.collector import CollectorCompany
from core.strategies.inventory_policy import build_inventory_policy
from core.strategies.stock_strategy import build_stock_strategy
from models.enums import InventoryPolicy, StockStrategy


class _Signals:
    def __init__(self, count):
        self.count = count

    def get_signals(self, now):
        return [{"id": i} for i in range(self.count)]


def _efficiency(policy, strategy, utilization, signal_count, now):
    collector = CollectorCompany.__new__(CollectorCompany)
    collector.env = simpy.Environment(initial_time=now)
    collector.inventory_policy_behavior = build_inventory_policy(policy)
    collector.stock_strategy_behavior = build_stock_strategy(strategy)
    collector.kanban_manager = _Signals(signal_count)
    collector._calculate_utilization = lambda: utilization
    collector.update_efficiency()
    return collector.efficiency


@pytest.mark.parametrize("utilization,signal_count", [(0.0, 0), (0.5, 3), (0.95, 10)])
def test_every_combo_gets_the_same_aging_only_efficiency(utilization, signal_count):
    now = 200.0
    efficiencies = {
        (policy, strategy): _efficiency(policy, strategy, utilization, signal_count, now)
        for policy, strategy in itertools.product(InventoryPolicy, StockStrategy)
    }

    expected = 1.0 - now * COLLECTOR_TIME_DEGRADATION_RATE_PER_DAY
    assert efficiencies == {combo: pytest.approx(expected) for combo in efficiencies}
