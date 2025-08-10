import os
import json
from typing import Dict, Any
from models.enums import WasteType
from config.constants import SIMULATION_DURATION
from models.state import SimulationState

class WasteMonitor:
    """Monitoring system for waste management operations"""

    def __init__(self, env=None):
        self.env = env
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}
        self.environmental_history = {}
        self.event_history = {}
        self.entity_status_history = {
            "generators": {},
            "collectors": {}, 
            "treatments": {}
        }

        if not os.path.exists("plots"):
            os.makedirs("plots")

    @property
    def get_generation_history(self):
        return self.generation_history

    @property
    def get_collection_history(self):
        return self.collection_history

    @property
    def get_processing_history(self):
        return self.processing_history

    @property
    def get_environmental_history(self):
        return self.environmental_history

    @property
    def get_event_history(self):
        return self.event_history

    @property
    def get_entity_status_history(self):
        return self.entity_status_history

    def track_generation(self, generator, timestamp, region=None):
        """Track waste generation events with timestamps, region info, and costs"""
        if generator.name not in self.generation_history:
            self.generation_history[generator.name] = {
                "timestamps": [],
                "volumes": {},
                "efficiency": [],
                "total_generated": {},
                "storage_utilization": [],
                "regions": [],
                "status": [],
                "energy_costs": [],
                "operational_costs": [],
                "total_costs": []
            }

        # Initialize entity_status_history entry if it doesn't exist
        if generator.name not in self.entity_status_history["generators"]:
            self.entity_status_history["generators"][generator.name] = {
                "timestamps": [], 
                "status": []
            }

        self.entity_status_history["generators"][generator.name]["timestamps"].append(timestamp)
        self.entity_status_history["generators"][generator.name]["status"].append(generator.status.value)

        history = self.generation_history[generator.name]
        history["timestamps"].append(timestamp)
        history["status"].append(generator.status.value) 
        history["regions"].append(region if region is not None else getattr(generator, "region", None))

        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )

        history["efficiency"].append(generator.efficiency)

        utilization = (generator.current_storage / generator.waste_storage_capacity) * 100
        history["storage_utilization"].append(utilization)
        history["energy_costs"].append(0.0)
        history["operational_costs"].append(0.0)
        history["total_costs"].append(0.0)

    def track_collection(self, collector, timestamp: float, region=None):
        """Track waste collection events with region info and costs"""
        if collector.name not in self.collection_history:
            self.collection_history[collector.name] = {
                "timestamps": [],
                "collected_volumes": {},
                "efficiency": [],
                "transport_costs": [],
                "storage_utilization": [],
                "utilization_rate": [],
                "regions": [],
                "status": [],
                "energy_costs": [],
                "operational_costs": [],
                "total_costs": []
            }

        # Initialize entity_status_history entry if it doesn't exist
        if collector.name not in self.entity_status_history["collectors"]:
            self.entity_status_history["collectors"][collector.name] = {
                "timestamps": [], 
                "status": []
            }

        self.entity_status_history["collectors"][collector.name]["timestamps"].append(timestamp)
        self.entity_status_history["collectors"][collector.name]["status"].append(collector.status.value)

        history = self.collection_history[collector.name]
        history["timestamps"].append(timestamp)
        history["status"].append(collector.status.value)
        history["regions"].append(region if region is not None else getattr(collector, "region", None))

        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(collector.transport_cost)

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
        if treatment.name not in self.processing_history:
            self._initialize_treatment_history(treatment.name)

        # Initialize entity_status_history entry if it doesn't exist
        if treatment.name not in self.entity_status_history["treatments"]:
            self.entity_status_history["treatments"][treatment.name] = {
                "timestamps": [], 
                "status": []
            }

        self.entity_status_history["treatments"][treatment.name]["timestamps"].append(timestamp)
        self.entity_status_history["treatments"][treatment.name]["status"].append(treatment.status.value)

        history = self.processing_history[treatment.name]
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

    def _initialize_treatment_history(self, treatment_name):
        """Initialize the treatment history structure"""
        product_types = self._get_product_types()
        self.processing_history[treatment_name] = {
            "timestamps": [],
            "storage": {
                "total": [],
                "by_type": {waste_type: [] for waste_type in WasteType},
                "utilization": [],
                "waste_utilization": [],
                "product_utilization": [],
                "product_to_sell_utilization": [],
                "product_to_sell_by_type": {ptype: [] for ptype in product_types},
                "product_storage_by_type": {ptype: [] for ptype in product_types},
            },
            "processed": {
                "total": [],
                "by_type": {waste_type: [] for waste_type in WasteType},
            },
            "products": {
                "total": [],
                "by_type": {ptype: [] for ptype in product_types},
                "quality": [],
                "unmet_by_type": {ptype: [] for ptype in product_types},
                "coverage_ratio_by_type": {ptype: [] for ptype in product_types},
                "met_event_timestamps_by_type": {ptype: [] for ptype in product_types},
                "unmet_event_timestamps_by_type": {
                    ptype: [] for ptype in product_types
                },
                "first_met_timestamp_by_type": dict.fromkeys(product_types, None),
            },
            "operational": {
                "energy_consumption": [],
                "conversion_rate": [],
                "demand": [],
                "demand_satisfaction": [],
                "energy_costs": [],
                "processing_costs": [],
                "total_costs": [],
            },
            "status": [],
        }

    def update_entity_costs(self, entity_name: str, entity_type: str, 
                       energy_cost: float = 0.0, processing_cost: float = 0.0, 
                       transport_cost: float = 0.0):
        """Update costs in the most recent tracking entry for an entity"""

        if entity_type == "generator" and entity_name in self.generation_history:
            history = self.generation_history[entity_name]
            if history["timestamps"]:
                history["energy_costs"][-1] += energy_cost
                history["operational_costs"][-1] += processing_cost
                history["total_costs"][-1] += energy_cost + processing_cost

        elif entity_type == "collector" and entity_name in self.collection_history:
            history = self.collection_history[entity_name]
            if history["timestamps"]:
                history["energy_costs"][-1] += energy_cost
                history["operational_costs"][-1] += processing_cost
                history["transport_costs"][-1] += transport_cost
                history["total_costs"][-1] += energy_cost + processing_cost + transport_cost

        elif entity_type == "treatment" and entity_name in self.processing_history:
            history = self.processing_history[entity_name]
            if history["timestamps"]:
                history["operational"]["energy_costs"][-1] += energy_cost
                history["operational"]["processing_costs"][-1] += processing_cost
                history["operational"]["total_costs"][-1] += energy_cost + processing_cost

    def _get_entity_category(self, entity_type: str) -> str:
        """Standardize entity type mapping"""
        mapping = {
            "generator": "generators",
            "collector": "collectors", 
            "treatment": "treatments"
        }
        return mapping.get(entity_type, entity_type)

    def track_event(self, facility_type: str, volume: float, strategy: str, 
                    cost_incurred: float, timestamp: float):
        """Event tracking"""

        event_key = "system_events"

        if event_key not in self.event_history:
            self.event_history[event_key] = {
                "timestamps": [],
                "overflow_events": [],
                "landfill_usage": [],
                "storage_expansions": [],
                "landfill_costs": [],
                "expansion_costs": [],
                "total_costs": []
            }

        history = self.event_history[event_key]
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

        print(f"[EVENT TRACKED] {facility_type} at {timestamp}: {volume:.2f}m³ via {strategy}, cost: €{cost_incurred:.2f}")

    def track_environmental_impact(self, entity_name: str, entity_type: str, 
                                environmental_impact: float, timestamp: float, 
                                impact_category: str = "carbon_emissions"):
        """Environmental impact tracking - emissions only (kg CO₂e)"""

        if entity_name not in self.environmental_history:
            self.environmental_history[entity_name] = {
                "timestamps": [],
                "carbon_emissions": [],
                "transport_emissions": [],
                "landfill_emissions": [],
                "total_impact": [],
                "entity_type": entity_type
            }

        history = self.environmental_history[entity_name]

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
        total_generated = self._sum_totals(self.generation_history, "total_generated")
        total_collected = self._sum_totals(self.collection_history, "collected_volumes")

        total_processed = 0
        for history in self.processing_history.values():
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

        if entity_name not in self.entity_status_history[history_category]:
            self.entity_status_history[history_category][entity_name] = {
                "timestamps": [],
                "status": []
            }

        entity_history = self.entity_status_history[history_category][entity_name]

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
        prod_util = (sum(treatment.product_storage.current_storage.values()) / treatment.product_storage_capacity * 100) if treatment.product_storage_capacity > 0 else 0.0
        history["storage"]["product_utilization"].append(prod_util)
        prod_sell_util = (sum(treatment.product_to_sell.current_storage.values()) / treatment.product_to_sell_capacity * 100) if treatment.product_to_sell_capacity > 0 else 0.0
        history["storage"]["product_to_sell_utilization"].append(prod_sell_util)

        for out_enum, qty in treatment.product_to_sell.current_storage.items():
            key = out_enum.value
            if key not in history["storage"]["product_to_sell_by_type"]:
                history["storage"]["product_to_sell_by_type"][key] = []
            history["storage"]["product_to_sell_by_type"][key].append(qty)
        for out_enum, qty in treatment.product_storage.current_storage.items():
            key = out_enum.value
            if key not in history["storage"]["product_storage_by_type"]:
                history["storage"]["product_storage_by_type"][key] = []
            history["storage"]["product_storage_by_type"][key].append(qty)

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
        history["operational"]["demand"].append(treatment.demand)
        history["operational"]["demand_satisfaction"].append(
            total_processed >= treatment.demand if treatment.demand > 0 else 1.0
        )

    def _track_product_metrics(self, treatment, history, timestamp):
        """Track product-related metrics"""
        product_types = self._get_product_types()
        total_products = 0
        if hasattr(treatment, 'product_volumes'):
            total_products = sum(treatment.product_volumes.get(ptype, 0) for ptype in product_types)
        history["products"]["total"].append(total_products)

        self._track_production_history(treatment, history, timestamp)
        quality = getattr(treatment, 'product_quality', 1.0)
        history["products"]["quality"].append(quality)

        state = SimulationState.get_instance()
        unmet = state.get_unmet_demands() if state else {}

        pts_by_key = {}
        for out_enum, qty in treatment.product_to_sell.current_storage.items():
            pts_by_key[out_enum.value] = qty

        for ptype in product_types:
            current_unmet = max(unmet.get(ptype, 0.0), 0.0)
            if ptype not in history["products"]["unmet_by_type"]:
                history["products"]["unmet_by_type"][ptype] = []
            history["products"]["unmet_by_type"][ptype].append(current_unmet)

            current_pts = pts_by_key.get(ptype, 0.0)
            ratio = (current_pts / current_unmet) if current_unmet > 0 else None
            if ptype not in history["products"]["coverage_ratio_by_type"]:
                history["products"]["coverage_ratio_by_type"][ptype] = []
            history["products"]["coverage_ratio_by_type"][ptype].append(ratio)

            prev_unmet = None
            prev_series = history["products"]["unmet_by_type"][ptype]
            if len(prev_series) >= 2:
                prev_unmet = prev_series[-2]

            if prev_unmet is not None:
                if prev_unmet > 0 and current_unmet <= 0:
                    history["products"]["met_event_timestamps_by_type"][ptype].append(
                        timestamp
                    )
                    if (
                        history["products"]["first_met_timestamp_by_type"].get(ptype)
                        is None
                    ):
                        history["products"]["first_met_timestamp_by_type"][
                            ptype
                        ] = timestamp
                elif (prev_unmet <= 0) and (current_unmet > 0):
                    history["products"]["unmet_event_timestamps_by_type"][ptype].append(
                        timestamp
                    )

    def get_demand_met_times_for_treatment(self, treatment_name: str) -> dict:
        hist = self.processing_history.get(treatment_name)
        if not hist:
            return {}
        return {
            "first_met": hist["products"]["first_met_timestamp_by_type"],
            "all_met_events": hist["products"]["met_event_timestamps_by_type"],
            "unmet_events": hist["products"]["unmet_event_timestamps_by_type"],
        }

    def _track_production_history(self, treatment, history, timestamp):
        """Track detailed production history"""
        product_types = self._get_product_types()
        if hasattr(treatment, 'production_history'):
            current_totals = dict.fromkeys(product_types, 0)
            for t, product_type, amount in treatment.production_history:
                if t <= timestamp and product_type in current_totals:
                    current_totals[product_type] += amount
            for product_type, total in current_totals.items():
                if product_type not in history["products"]["by_type"]:
                    history["products"]["by_type"][product_type] = []
                history["products"]["by_type"][product_type].append(total)

    def _get_product_types(self):
        """Load product types from demand.json"""
        demand_path = os.path.join(os.path.dirname(__file__), '../data/demand.json')
        try:
            with open(demand_path, 'r') as f:
                data = json.load(f)
            return list(data.get('national_demand', {}).keys())
        except Exception:
            return []

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
        for generator_name, history in self.generation_history.items():
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
        for collector_name, history in self.collection_history.items():
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
        for facility_name, history in self.processing_history.items():
            report.append(f"\n{facility_name}:")
            if history["processed"]["total"]:
                total_processed = history["processed"]["total"][-1]
                report.append(f"- Total waste processed: {total_processed:.2f} m³")
            if history["storage"]["utilization"]:
                report.append(f"- Current storage utilization: {history['storage']['utilization'][-1]:.1f}%")
            if history["operational"]["demand_satisfaction"]:
                satisfaction_rate = history["operational"]["demand_satisfaction"][-1] * 100
                report.append(f"- Current demand satisfaction rate: {satisfaction_rate:.1f}%")
