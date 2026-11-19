from typing import Dict
from config.constants import WASTE_HOLDING_COST_PER_M3_PER_DAY
from instrumentation.history_store import HistoryStore


HISTORY_CATEGORY_BY_FACILITY_TYPE = {
    "generator": "generators",
    "collector": "collectors",
    "treatment": "treatments",
}


class WasteMonitor:
    """Monitoring system for waste management operations"""

    def __init__(self, env=None):
        self.env = env
        self.store = HistoryStore()
        self._costs_before_first_sample: Dict[str, Dict[str, float]] = {}

    def track_generation(self, generator, timestamp):
        """Track waste generation events with timestamps and costs"""
        self.store.ensure_generation(generator.name)
        self.store.ensure_entity_status("generators", generator.name)

        self.store.entity_status_history["generators"][generator.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["generators"][generator.name]["status"].append(generator.status.name)

        history = self.store.generation_history[generator.name]
        history["timestamps"].append(timestamp)
        history["status"].append(generator.status.name)

        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []
                history["total_potential_generated"][waste_type] = []
                history["total_uncollected"][waste_type] = []
                history["total_outlet"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )
            history["total_potential_generated"][waste_type].append(
                generator.total_potential_generated[waste_type]
            )
            history["total_uncollected"][waste_type].append(
                generator.total_uncollected[waste_type]
            )
            history["total_outlet"][waste_type].append(
                generator.total_outlet[waste_type]
            )

        history["efficiency"].append(generator.efficiency)

        utilization = (generator.current_storage / generator.waste_storage_capacity) * 100
        history["storage_utilization"].append(utilization)

        # One monitor sample == one simulated day (monitor_system_process yields
        # timeout(1)), so each sample accrues a full day of holding cost on the
        # waste currently stored.
        history["holding_costs"].append(
            generator.current_storage * WASTE_HOLDING_COST_PER_M3_PER_DAY
        )

    def track_collection(self, collector, timestamp: float):
        """Track waste collection events with costs"""
        self.store.ensure_collection(collector.name)
        self.store.ensure_entity_status("collectors", collector.name)

        self.store.entity_status_history["collectors"][collector.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["collectors"][collector.name]["status"].append(collector.status.name)

        history = self.store.collection_history[collector.name]
        history["timestamps"].append(timestamp)
        history["status"].append(collector.status.name)

        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(0.0)

        total_storage = sum(collector.collection_center.current_storage.values())
        utilization = (total_storage / collector.collection_center.waste_storage_capacity) * 100

        history["storage_utilization"].append(utilization)

        # Daily holding-cost accrual on the collection center's stored waste;
        # kept out of total_costs so the transport KPI component stays pure.
        history["holding_costs"].append(
            total_storage * WASTE_HOLDING_COST_PER_M3_PER_DAY
        )

        history["energy_costs"].append(0.0)
        history["operational_costs"].append(0.0)
        history["total_costs"].append(0.0)
        self._book_costs_before_first_sample(collector.name, history)

    def track_processing(self, treatment, timestamp: float):
        """Track treatment facility metrics with embedded costs"""
        self.store.ensure_processing(treatment.name)
        self.store.ensure_entity_status("treatments", treatment.name)

        self.store.entity_status_history["treatments"][treatment.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["treatments"][treatment.name]["status"].append(treatment.status.name)

        history = self.store.processing_history[treatment.name]
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            history["status"].append(treatment.status.name)

            self._track_storage_metrics(treatment, history)
            self._track_processing_metrics(treatment, history)
            self._track_product_metrics(treatment, history)

            history["operational"]["energy_costs"].append(0.0)
            history["operational"]["processing_costs"].append(0.0)
            history["operational"]["total_costs"].append(0.0)
            self._book_costs_before_first_sample(treatment.name, history["operational"])
            # Daily holding-cost accrual on the waste-side storage; inside the
            # same-timestamp guard so re-entrant calls from the operator's own
            # loop cannot accrue more than once per day. Kept out of
            # total_costs so the processing KPI component stays pure.
            history["operational"]["holding_costs"].append(
                treatment.current_storage * WASTE_HOLDING_COST_PER_M3_PER_DAY
            )

    def update_entity_costs(self, entity_name: str, entity_type: str,
                       energy_cost: float = 0.0, processing_cost: float = 0.0,
                       transport_cost: float = 0.0):
        """Add costs to the entity's latest sample.

        Before its first sample (treatment runs at t=0 ahead of the monitor
        process) the costs are held and booked into that first sample.
        """
        if entity_type == "collector":
            history = self.store.collection_history.get(entity_name)
            columns = {"energy_costs": energy_cost, "operational_costs": processing_cost,
                       "transport_costs": transport_cost}
        elif entity_type == "treatment":
            history = self.store.processing_history.get(entity_name)
            history = history["operational"] if history else None
            columns = {"energy_costs": energy_cost, "processing_costs": processing_cost}
        else:
            raise ValueError(f"No cost series for entity type {entity_type!r}")
        columns["total_costs"] = sum(columns.values())

        if history is None or not history["total_costs"]:
            held = self._costs_before_first_sample.setdefault(entity_name, {})
            for column, cost in columns.items():
                held[column] = held.get(column, 0.0) + cost
            return
        for column, cost in columns.items():
            history[column][-1] += cost

    def _book_costs_before_first_sample(self, entity_name, cost_history):
        for column, cost in self._costs_before_first_sample.pop(entity_name, {}).items():
            cost_history[column][-1] += cost

    def track_expansion(self, volume: float, cost_incurred: float, timestamp: float):
        """Record one storage expansion (the overflow volume that triggered it)."""

        event_key = "system_events"

        self.store.ensure_event(event_key)

        history = self.store.event_history[event_key]
        history["timestamps"].append(timestamp)
        history["storage_expansions"].append(volume)
        history["expansion_costs"].append(cost_incurred)
        history["total_costs"].append(cost_incurred)

    def record_landfill(self, entity_name: str, composition: Dict,
                        cost: float, timestamp: float):
        """Write one landfill event to the store's ledger (see HistoryStore)."""
        self.store.record_landfill(entity_name, composition, cost, timestamp)

    def record_emission(self, entity_name: str, kind: str,
                        kgco2e: float, timestamp: float):
        """Write one emission of ``kind`` to the store's ledger (see HistoryStore)."""
        self.store.record_emission(entity_name, kind, kgco2e, timestamp)

    def record_entity_status(self, entity, timestamp: float):
        """Record entity status at specific moments (like transitions)"""

        history_category = HISTORY_CATEGORY_BY_FACILITY_TYPE[entity.facility_type]
        entity_name = entity.name

        self.store.ensure_entity_status(history_category, entity_name)

        entity_history = self.store.entity_status_history[history_category][entity_name]

        if (not entity_history["timestamps"] or 
            timestamp > entity_history["timestamps"][-1] or
            entity.status.name != entity_history["status"][-1]):

            entity_history["timestamps"].append(timestamp)
            entity_history["status"].append(entity.status.name)

    def monitor_system_process(self, generators, collectors, treatment_operators):
        """Process for continuous monitoring"""
        while True:
            for generator in generators:
                self.track_generation(generator, self.env.now)
            for collector in collectors:
                self.track_collection(collector, self.env.now)
            for treatment in treatment_operators:
                self.track_processing(treatment, self.env.now)
            yield self.env.timeout(1)

    def _track_storage_metrics(self, treatment, history):
        """Track storage-related metrics"""
        history["storage"]["total"].append(treatment.current_storage)
        history["storage"]["utilization"].append(treatment.storage_utilization)
        waste_util = (treatment.current_storage / treatment.waste_storage_capacity * 100) if treatment.waste_storage_capacity > 0 else 0.0
        history["storage"]["waste_utilization"].append(waste_util)
        finished_goods_capacity_total = sum(treatment.finished_goods.capacity.values())
        finished_goods_util = (sum(treatment.finished_goods.current_storage.values()) / finished_goods_capacity_total * 100) if finished_goods_capacity_total > 0 else 0.0
        history["storage"]["finished_goods_utilization"].append(finished_goods_util)

    def _track_processing_metrics(self, treatment, history):
        """Track processing-related metrics"""
        total_processed = sum(treatment.processed_volumes.values())
        history["processed"]["total"].append(total_processed)

    def _track_product_metrics(self, treatment, history):
        """Track product-related metrics"""
        product_types = self.store.product_types
        product_volumes = treatment.product_volumes

        # Cumulative produced volume per output type (C11 avoided-emissions
        # driver). A write-only series consumed post-hoc by
        # analysis.avoided_emissions.
        for ptype in product_types:
            history["products"]["by_type"].setdefault(ptype, []).append(
                product_volumes.get(ptype, 0)
            )
