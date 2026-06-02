"""Pluggable stock-strategy and inventory-policy behavior objects.

The ``StockStrategy`` and ``InventoryPolicy`` enums in ``models.enums`` stay as
configuration selectors. ``FacilityBuilder`` maps each selected enum to one of
the concrete behavior classes here and injects it into every entity, so the
process modules delegate strategy/policy decisions instead of branching on the
enum. Adding a strategy or policy means adding one class plus its factory
mapping -- the process modules do not change.
"""

from core.strategies.stock_strategy import (
    StockStrategyProtocol,
    OnDemandStrategy,
    Reorder50Strategy,
    Reorder90Strategy,
    build_stock_strategy,
)
from core.strategies.inventory_policy import (
    InventoryPolicyProtocol,
    PushPolicy,
    PullPolicy,
    build_inventory_policy,
)

__all__ = [
    "StockStrategyProtocol",
    "OnDemandStrategy",
    "Reorder50Strategy",
    "Reorder90Strategy",
    "build_stock_strategy",
    "InventoryPolicyProtocol",
    "PushPolicy",
    "PullPolicy",
    "build_inventory_policy",
]
