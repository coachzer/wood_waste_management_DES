import os
from typing import Dict, Any
from models.enums import WasteType
from config.constants import SIMULATION_DURATION
from instrumentation.history_store import HistoryStore

class WasteMonitor:
    """Monitoring system for waste management operations"""

    def __init__(self, env=None):
        self.env = env
        self.store = HistoryStore()

        if not os.path.exists("plots"):
            os.makedirs("plots")

    def track_generation(self, generator, timestamp, region=None):
        """Track waste generation events with timestamps, region info, and costs"""
        self.store.ensure_generation(generator.name)
        self.store.ensure_entity_status("generators", generator.name)

        self.store.entity_status_history["generators"][generator.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["generators"][generator.name]["status"].append(generator.status.value)

        history = self.store.generation_history[generator.name]
        history["timestamps"].append(timestamp)
        history["status"].append(generator.status.value) 
        history["regions"].append(region if region is not None else getattr(generator, "region", None))

        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []
                history["total_potential_generated"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )
            history["total_potential_generated"][waste_type].append(
                generator.total_potential_generated[waste_type]
            )

        history["efficiency"].append(generator.efficiency)

        utilization = (generator.current_storage / generator.waste_storage_capacity) * 100
        history["storage_utilization"].append(utilization)
        history["energy_costs"].append(0.0)
        history["operational_costs"].append(0.0)
        history["total_costs"].append(0.0)

    def track_collection(self, collector, timestamp: float, region=None):
        """Track waste collection events with region info and costs"""
        self.store.ensure_collection(collector.name)
        self.store.ensure_entity_status("collectors", collector.name)

        self.store.entity_status_history["collectors"][collector.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["collectors"][collector.name]["status"].append(collector.status.value)

        history = self.store.collection_history[collector.name]
        history["timestamps"].append(timestamp)
        history["status"].append(collector.status.value)
        history["regions"].append(region if region is not None else getattr(collector, "region", None))

        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(getattr(collector, 'last_collection_cost', 0.0))

        total_storage = sum(collector.collection_center.current_storage.values())
        utilization = (total_storage / collector.collection_center.waste_storage_capacity) * 100

        history["storage_utilization"].append(utilization)

        if len(history["storage_utilization"]) > 1:
            rate_of_change = utilization - history["storage_utilization"][-2]
            history.setdefault("utilization_rate", []).append(rate_of_change)

        # Add cost tracking (initialize with 0)
        history["energy_costs"].append(0.0)
        history["operational_costs"].append(0.0)
        history["total_costs"].append(0.0)

    def track_processing(self, treatment, timestamp: float):
        """Track treatment facility metrics with embedded costs"""
        self.store.ensure_processing(treatment.name)
        self.store.ensure_entity_status("treatments", treatment.name)

        self.store.entity_status_history["treatments"][treatment.name]["timestamps"].append(timestamp)
        self.store.entity_status_history["treatments"][treatment.name]["status"].append(treatment.status.value)

        history = self.store.processing_history[treatment.name]
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            history["status"].append(treatment.status.value)

            self._track_storage_metrics(treatment, history)
            total_processed = self._track_processing_metrics(treatment, history)
            self._track_operational_metrics(treatment, history, total_processed)
            self._track_product_metrics(treatment, history, timestamp)

            # Add cost tracking (initialize with 0)
            history["operational"]["energy_costs"].append(0.0)
            history["operational"]["processing_costs"].append(0.0)
            history["operational"]["total_costs"].append(0.0)

    def update_entity_costs(self, entity_name: str, entity_type: str,
                       energy_cost: float = 0.0, processing_cost: float = 0.0, 
                       transport_cost: float = 0.0):
        """Update costs in the most recent tracking entry for an entity"""

        if entity_type == "generator" and entity_name in self.store.generation_history:
            history = self.store.generation_history[entity_name]
            if history["timestamps"]:
                history["energy_costs"][-1] += energy_cost
                history["operational_costs"][-1] += processing_cost
                history["total_costs"][-1] += energy_cost + processing_cost

        elif entity_type == "collector" and entity_name in self.store.collection_history:
            history = self.store.collection_history[entity_name]
            if history["timestamps"]:
                history["energy_costs"][-1] += energy_cost
                history["operational_costs"][-1] += processing_cost
                history["transport_costs"][-1] += transport_cost
                history["total_costs"][-1] += energy_cost + processing_cost + transport_cost

        elif entity_type == "treatment" and entity_name in self.store.processing_history:
            history = self.store.processing_history[entity_name]
            if history["timestamps"]:
                history["operational"]["energy_costs"][-1] += energy_cost
                history["operational"]["processing_costs"][-1] += processing_cost
                history["operational"]["total_costs"][-1] += energy_cost + processing_cost

    def track_event(self, facility_type: str, volume: float, strategy: str,
                    cost_incurred: float, timestamp: float):
        """Event tracking"""

        event_key = "system_events"

        self.store.ensure_event(event_key)

        history = self.store.event_history[event_key]
        history["timestamps"].append(timestamp)
        history["overflow_events"].append(0.0)
        history["landfill_usage"].append(0.0)
        history["storage_expansions"].append(0.0)
        history["landfill_costs"].append(0.0)
        history["expansion_costs"].append(0.0)
        history["total_costs"].append(0.0)

        # Update based on strategy
        if strategy == "landfill":
            history["landfill_usage"][-1] = volume
            history["landfill_costs"][-1] = cost_incurred
            history["overflow_events"][-1] = volume
        elif strategy == "expand_storage":
            history["storage_expansions"][-1] = volume
            history["expansion_costs"][-1] = cost_incurred
            history["overflow_events"][-1] = volume

        history["total_costs"][-1] = cost_incurred

    def track_environmental_impact(self, entity_name: str, entity_type: str, 
                                environmental_impact: float, timestamp: float, 
                                impact_category: str = "carbon_emissions"):
        """Environmental impact tracking - emissions only (kg CO₂e)"""

        self.store.ensure_environmental(entity_name, entity_type)

        history = self.store.environmental_history[entity_name]

        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            history["carbon_emissions"].append(0.0)
            history["transport_emissions"].append(0.0)
            history["landfill_emissions"].append(0.0)
            history["total_impact"].append(0.0)

        if impact_category in ["carbon_emissions", "transport_emissions", "landfill_emissions"]:
            history[impact_category][-1] += environmental_impact
            history["total_impact"][-1] += environmental_impact
        else:
            print(f"Warning: Unrecognized environmental impact category: {impact_category}")

    def calculate_efficiency_metrics(self) -> Dict[str, float]:
        """Calculate system-wide efficiency metrics"""
        total_generated = self._sum_totals(self.store.generation_history, "total_generated")
        total_collected = self._sum_totals(self.store.collection_history, "collected_volumes")

        total_processed = 0
        for history in self.store.processing_history.values():
            if history["processed"]["total"]:
                total_processed += history["processed"]["total"][-1]

        return {
            "collection_rate": (total_collected / total_generated * 100) if total_generated > 0 else 0,
            "processing_rate": (total_processed / total_collected * 100) if total_collected > 0 else 0,
            "overall_efficiency": (total_processed / total_generated * 100) if total_generated > 0 else 0,
        }

    def record_entity_status(self, entity, timestamp: float):
        """Record entity status at specific moments (like transitions)"""

        entity_type_name = type(entity).__name__

        type_mapping = {
            'WasteGenerator': 'generators',
            'CollectorCompany': 'collectors', 
            'TreatmentOperator': 'treatments'
        }

        history_category = type_mapping.get(entity_type_name)
        if not history_category:
            print(f"Warning: Unknown entity type {entity_type_name}")
            return

        entity_name = getattr(entity, 'name', str(entity))

        self.store.ensure_entity_status(history_category, entity_name)

        entity_history = self.store.entity_status_history[history_category][entity_name]

        if (not entity_history["timestamps"] or 
            timestamp > entity_history["timestamps"][-1] or
            entity.status.value != entity_history["status"][-1]):

            entity_history["timestamps"].append(timestamp)
            entity_history["status"].append(entity.status.value)

    def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report"""
        efficiency_metrics = self.calculate_efficiency_metrics()
        report = ["\n=== Waste Management System Summary Report ===\n"]

        self._add_generation_summary(report)
        self._add_collection_summary(report)
        self._add_processing_summary(report)

        report.append("\nSystem Efficiency Metrics:")
        report.append(f"- Overall collection rate: {efficiency_metrics['collection_rate']:.1f}%")
        report.append(f"- Overall processing rate: {efficiency_metrics['processing_rate']:.1f}%")
        report.append(f"- System-wide efficiency: {efficiency_metrics['overall_efficiency']:.1f}%")

        return "\n".join(report)

    def monitor_system_process(self, generators, collectors, treatment_operators):
        """Process for continuous monitoring"""
        while True:
            for generator in generators:
                self.track_generation(generator, self.env.now)
            for collector in collectors:
                self.track_collection(collector, self.env.now)
            for treatment in treatment_operators:
                self.track_processing(treatment, self.env.now)  

            if self.env.now == SIMULATION_DURATION:
                print(self.generate_summary_report())
            yield self.env.timeout(1)

    def _track_storage_metrics(self, treatment, history):
        """Track storage-related metrics"""
        history["storage"]["total"].append(treatment.current_storage)
        history["storage"]["utilization"].append(treatment.storage_utilization)
        for waste_type in WasteType:
            history["storage"]["by_type"][waste_type].append(
                treatment.waste_storage[waste_type]
            )
        waste_util = (treatment.current_storage / treatment.waste_storage_capacity * 100) if treatment.waste_storage_capacity > 0 else 0.0
        history["storage"]["waste_utilization"].append(waste_util)
        finished_goods_capacity_total = sum(treatment.finished_goods.capacity.values())
        finished_goods_util = (sum(treatment.finished_goods.current_storage.values()) / finished_goods_capacity_total * 100) if finished_goods_capacity_total > 0 else 0.0
        history["storage"]["finished_goods_utilization"].append(finished_goods_util)

        for out_enum, qty in treatment.finished_goods.current_storage.items():
            key = out_enum.value
            if key not in history["storage"]["finished_goods_by_type"]:
                history["storage"]["finished_goods_by_type"][key] = []
            history["storage"]["finished_goods_by_type"][key].append(qty)

    def _track_processing_metrics(self, treatment, history):
        """Track processing-related metrics"""
        total_processed = sum(treatment.processed_volumes.values())
        history["processed"]["total"].append(total_processed)
        for waste_type in WasteType:
            history["processed"]["by_type"][waste_type].append(
                treatment.processed_volumes[waste_type]
            )
        return total_processed

    def _track_operational_metrics(self, treatment, history, total_processed):
        """Track operational metrics"""
        history["operational"]["energy_consumption"].append(treatment.energy_consumption)
        history["operational"]["conversion_rate"].append(treatment.conversion_rate)

    def _track_product_metrics(self, treatment, history, timestamp):
        """Track product-related metrics"""
        product_types = self.store.product_types
        product_volumes = getattr(treatment, 'product_volumes', {})
        total_products = sum(product_volumes.get(ptype, 0) for ptype in product_types)
        history["products"]["total"].append(total_products)

        # Cumulative produced volume per output type (C11 avoided-emissions
        # driver). Mirrors processed["by_type"]; a write-only series consumed
        # post-hoc by analysis.avoided_emissions.
        for ptype in product_types:
            history["products"]["by_type"].setdefault(ptype, []).append(
                product_volumes.get(ptype, 0)
            )

        quality = getattr(treatment, 'product_quality', 1.0)
        history["products"]["quality"].append(quality)

    def _sum_totals(self, history_dict: Dict[str, Any], key: str) -> float:
        """Helper function to sum totals across all entities"""
        total = 0
        for history in history_dict.values():
            if key not in history:
                continue
            if isinstance(history[key], dict):
                for values in history[key].values():
                    if values and isinstance(values, list):
                        total += values[-1]
            elif isinstance(history[key], list) and history[key]:
                total += history[key][-1]
        return total

    def _add_generation_summary(self, report: list) -> None:
        """Add generation summary to the report"""
        report.append("Generation Summary:")
        for generator_name, history in self.store.generation_history.items():
            report.append(f"\n{generator_name}:")
            for waste_type in history["total_generated"]:
                if history["total_generated"][waste_type]:
                    total = history["total_generated"][waste_type][-1]
                    report.append(f"- Total {waste_type} generated: {total:.2f} m³")
            if history["storage_utilization"]:
                report.append(f"- Current storage utilization: {history['storage_utilization'][-1]:.1f}%")

    def _add_collection_summary(self, report: list) -> None:
        """Add collection summary to the report"""
        report.append("\nCollection Summary:")
        for collector_name, history in self.store.collection_history.items():
            report.append(f"\n{collector_name}:")
            for waste_type in history["collected_volumes"]:
                if history["collected_volumes"][waste_type]:
                    total = history["collected_volumes"][waste_type][-1]
                    report.append(f"- Total {waste_type} collected: {total:.2f} m³")
            if history["efficiency"]:
                report.append(f"- Current efficiency: {history['efficiency'][-1]:.2f}")

    def _add_processing_summary(self, report: list) -> None:
        """Add processing summary to the report"""
        report.append("\nProcessing Summary:")
        for facility_name, history in self.store.processing_history.items():
            report.append(f"\n{facility_name}:")
            if history["processed"]["total"]:
                total_processed = history["processed"]["total"][-1]
                report.append(f"- Total waste processed: {total_processed:.2f} m³")
            if history["storage"]["utilization"]:
                report.append(f"- Current storage utilization: {history['storage']['utilization'][-1]:.1f}%")
