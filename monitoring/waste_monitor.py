import os
import json
from typing import Dict, Any
from models.enums import WasteType
from config.base_config import SIMULATION_DURATION

class WasteMonitor:
    """Unified monitoring system for waste management operations"""
    
    def __init__(self, env=None):
        self.env = env
        # Data collection structures
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}
        self.cost_history = {
            "energy": [],
            "processing": [],
            "transport": [],
            "timestamps": []
        }
        self.overflow_history = {
            "generator_overflow": {"values": [0.0], "timestamps": [0.0]},
            "collector_overflow": {"values": [0.0], "timestamps": [0.0]},
            "treatment_overflow": {"values": [0.0], "timestamps": [0.0]},
            "landfill_usage": {"values": [0.0], "timestamps": [0.0]},
            "expand_storage_usage": {"values": [0.0], "timestamps": [0.0]},
            "landfill_penalties": {"values": [0.0], "timestamps": [0.0]},
            "storage_expansion": {"values": [0.0], "timestamps": [0.0]},
            "total_cost": {"values": [0.0], "timestamps": [0.0]}
        }
        
        # Create plots directory
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
    def get_cost_history(self):
        return self.cost_history

    @property
    def get_overflow_history(self):
        return self.overflow_history

    def track_generation(self, generator, timestamp, region=None):
        """Track waste generation events with timestamps and region info"""
        if generator.name not in self.generation_history:
            self.generation_history[generator.name] = {
                "timestamps": [],
                "volumes": {},
                "total_generated": {},
                "storage_utilization": [],
                "regions": []
            }

        history = self.generation_history[generator.name]
        history["timestamps"].append(timestamp)
        history["regions"].append(region if region is not None else getattr(generator, "region", None))

        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )

        utilization = (generator.current_storage / generator.waste_storage_capacity) * 100
        history["storage_utilization"].append(utilization)

    def track_collection(self, collector, timestamp: float, region=None):
        """Track waste collection events with region info"""
        if collector.name not in self.collection_history:
            self.collection_history[collector.name] = {
                "timestamps": [],
                "collected_volumes": {},
                "efficiency": [],
                "transport_costs": [],
                "regions": []
            }

        history = self.collection_history[collector.name]
        history["timestamps"].append(timestamp)
        history["regions"].append(region if region is not None else getattr(collector, "region", None))

        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(collector.transport_cost)

    def track_processing(self, treatment, timestamp: float):
        """Track treatment facility metrics"""
        if treatment.name not in self.processing_history:
            self._initialize_treatment_history(treatment.name)

        history = self.processing_history[treatment.name]
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            
            self._track_storage_metrics(treatment, history)
            total_processed = self._track_processing_metrics(treatment, history)
            self._track_operational_metrics(treatment, history, total_processed)
            self._track_product_metrics(treatment, history, timestamp)

    def track_overflow(self, facility_type: str, volume: float, strategy: str, timestamp: float, region=None):
        """Track overflow events and their handling strategies"""
        overflow_key = f"{facility_type}_overflow"
        self.overflow_history[overflow_key]["values"].append(volume)
        self.overflow_history[overflow_key]["timestamps"].append(timestamp)
        
        if "regions" not in self.overflow_history[overflow_key]:
            self.overflow_history[overflow_key]["regions"] = []
        self.overflow_history[overflow_key]["regions"].append(region)

        for strat in ["landfill", "expand_storage"]:
            usage_key = f"{strat}_usage"
            value = 1.0 if strat == strategy else 0.0
            self.overflow_history[usage_key]["values"].append(value)
            self.overflow_history[usage_key]["timestamps"].append(timestamp)
            if "regions" not in self.overflow_history[usage_key]:
                self.overflow_history[usage_key]["regions"] = []
            self.overflow_history[usage_key]["regions"].append(region)

        cost = 0.0
        match strategy:
            case "landfill":
                cost = volume * 100.0
                self.overflow_history["landfill_penalties"]["values"].append(cost)
                self.overflow_history["storage_expansion"]["values"].append(0.0)
            case "expand_storage":
                cost = volume * 250.0
                self.overflow_history["landfill_penalties"]["values"].append(0.0)
                self.overflow_history["storage_expansion"]["values"].append(cost)
            case _:
                self.overflow_history["landfill_penalties"]["values"].append(0.0)
                self.overflow_history["storage_expansion"]["values"].append(0.0)

        self.overflow_history["total_cost"]["values"].append(cost)
        self.overflow_history["total_cost"]["timestamps"].append(timestamp)
        if "regions" not in self.overflow_history["total_cost"]:
            self.overflow_history["total_cost"]["regions"] = []
        self.overflow_history["total_cost"]["regions"].append(region)

    def track_energy_cost(self, energy_cost: float, timestamp: float):
        """Track energy costs incurred by treatment facilities"""
        self.cost_history["energy"].append(energy_cost)
        self.cost_history["timestamps"].append(timestamp)

    def track_processing_cost(self, processing_cost: float, timestamp: float):
        """Track processing costs incurred by treatment facilities"""
        self.cost_history["processing"].append(processing_cost)
        self.cost_history["timestamps"].append(timestamp)
        
    def track_transport_cost(self, cost: float, timestamp: float):
        """Track transportation costs"""
        self.cost_history["transport"].append(cost)
        self.cost_history["timestamps"].append(timestamp)

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
        """SimPy process for continuous monitoring"""
        while True:
            for generator in generators:
                self.track_generation(generator, self.env.now)
            for collector in collectors:
                self.track_collection(collector, self.env.now)
            for treatment in treatment_operators:
                self.track_processing(treatment, self.env.now)
                
            if self.env.now == SIMULATION_DURATION - 1:
                print(self.generate_summary_report())
                
            yield self.env.timeout(1)

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
            },
            "processed": {
                "total": [],
                "by_type": {waste_type: [] for waste_type in WasteType},
            },
            "products": {
                "total": [],
                "by_type": {ptype: [] for ptype in product_types},
                "quality": [],
            },
            "operational": {
                "energy_consumption": [],
                "conversion_rate": [],
                "demand": [],
                "demand_satisfaction": [],
            },
        }

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
