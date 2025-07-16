from typing import Dict, Any
from models.enums import WasteType

class DataCollector:
    """Handles data collection from various system components"""

    def __init__(self, env=None):
        self.env = env
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
            # Basic overflow tracking
            "generator_overflow": {"values": [0.0], "timestamps": [0.0]},
            "collector_overflow": {"values": [0.0], "timestamps": [0.0]},
            "treatment_overflow": {"values": [0.0], "timestamps": [0.0]},
            
            # Strategy usage tracking
            "landfill_usage": {"values": [0.0], "timestamps": [0.0]},
            "expand_storage_usage": {"values": [0.0], "timestamps": [0.0]},
            "emergency_transport_usage": {"values": [0.0], "timestamps": [0.0]},
            "reduce_intake_usage": {"values": [0.0], "timestamps": [0.0]},
            
            # Cost tracking
            "landfill_penalties": {"values": [0.0], "timestamps": [0.0]},
            "storage_expansion": {"values": [0.0], "timestamps": [0.0]},
            "emergency_transport": {"values": [0.0], "timestamps": [0.0]},
            "total_cost": {"values": [0.0], "timestamps": [0.0]}
        }
        self.last_timestamp = 0.0  # Initialize timestamp tracker

    def track_generation(self, generator, timestamp):
        """Track waste generation events with timestamps"""
        if generator.name not in self.generation_history:
            self.generation_history[generator.name] = {
                "timestamps": [],
                "volumes": {},
                "total_generated": {},
                "storage_utilization": [],
            }

        history = self.generation_history[generator.name]
        history["timestamps"].append(timestamp)

        # Track volumes by waste type
        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )

        # Track storage utilization
        utilization = (generator.current_storage / generator.storage_capacity) * 100
        history["storage_utilization"].append(utilization)

    def track_collection(self, collector, timestamp: float):
        """Track waste collection events"""
        if collector.name not in self.collection_history:
            self.collection_history[collector.name] = {
                "timestamps": [],
                "collected_volumes": {},
                "efficiency": [],
                "transport_costs": [],
            }

        history = self.collection_history[collector.name]
        history["timestamps"].append(timestamp)

        # Track collected volumes by waste type
        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        # Debug: Track what's being recorded
        total_collected = sum(collector.collected_waste.values())
        if total_collected > 0:
            print(f"[DATA COLLECTOR DEBUG] Recording {collector.name}: total collected = {total_collected:.2f}")

        # Track efficiency metrics
        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(collector.transport_cost)

    def track_overflow(self, facility_type: str, volume: float, strategy: str, timestamp: float):
        """Track overflow events and their handling strategy"""
        # Track facility-specific overflow
        overflow_key = f"{facility_type}_overflow"
        self.overflow_history[overflow_key]["values"].append(volume)
        self.overflow_history[overflow_key]["timestamps"].append(timestamp)
        
        # Track strategy usage (1 for used, 0 for others)
        for strat in ["landfill", "expand_storage", "emergency_transport", "reduce_intake"]:
            usage_key = f"{strat}_usage"
            value = 1.0 if strat == strategy else 0.0
            self.overflow_history[usage_key]["values"].append(value)
            self.overflow_history[usage_key]["timestamps"].append(timestamp)
        
        # Track costs based on strategy
        cost = 0.0
        if strategy == "landfill":
            cost = volume * 100.0  # Base penalty rate
            self.overflow_history["landfill_penalties"]["values"].append(cost)
            self.overflow_history["storage_expansion"]["values"].append(0.0)
            self.overflow_history["emergency_transport"]["values"].append(0.0)
        elif strategy == "expand_storage":
            cost = volume * 250.0  # Storage expansion cost rate
            self.overflow_history["landfill_penalties"]["values"].append(0.0)
            self.overflow_history["storage_expansion"]["values"].append(cost)
            self.overflow_history["emergency_transport"]["values"].append(0.0)
        elif strategy == "emergency_transport":
            cost = volume * 400.0  # Emergency transport cost rate
            self.overflow_history["landfill_penalties"]["values"].append(0.0)
            self.overflow_history["storage_expansion"]["values"].append(0.0)
            self.overflow_history["emergency_transport"]["values"].append(cost)
        else:  # reduce_intake
            self.overflow_history["landfill_penalties"]["values"].append(0.0)
            self.overflow_history["storage_expansion"]["values"].append(0.0)
            self.overflow_history["emergency_transport"]["values"].append(0.0)
            
        # Track total cost
        self.overflow_history["total_cost"]["values"].append(cost)
        self.overflow_history["total_cost"]["timestamps"].append(timestamp)
        
        # Update timestamps for cost tracking
        for cost_key in ["landfill_penalties", "storage_expansion", "emergency_transport"]:
            self.overflow_history[cost_key]["timestamps"].append(timestamp)

    def track_energy_cost(self, cost: float, timestamp: float):
        """Track energy consumption costs"""
        self.cost_history["energy"].append(cost)
        self.cost_history["timestamps"].append(timestamp)
        self.last_timestamp = timestamp

    def track_processing_cost(self, cost: float, timestamp: float):
        """Track processing operation costs"""
        self.cost_history["processing"].append(cost)
        if timestamp not in self.cost_history["timestamps"]:
            self.cost_history["timestamps"].append(timestamp)
        self.last_timestamp = timestamp

    def track_transport_cost(self, cost: float, timestamp: float):
        """Track transportation costs"""
        self.cost_history["transport"].append(cost)
        if timestamp not in self.cost_history["timestamps"]:
            self.cost_history["timestamps"].append(timestamp)
        self.last_timestamp = timestamp

    def _initialize_treatment_history(self, treatment_name):
        """Initialize the treatment history structure"""
        self.processing_history[treatment_name] = {
            "timestamps": [],
            "storage": {
                "total": [],
                "by_type": {waste_type: [] for waste_type in WasteType},
                "utilization": [],
            },
            "processed": {
                "total": [],
                "by_type": {waste_type: [] for waste_type in WasteType},
            },
            "products": {
                "total": [],
                "by_type": {},
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
        # Calculate total products
        total_products = 0
        if hasattr(treatment, 'product_volumes'):
            total_products = sum(treatment.product_volumes.values())
        history["products"]["total"].append(total_products)
        
        # Track production history
        self._track_production_history(treatment, history, timestamp)
        
        # Track product quality
        quality = treatment.product_quality if hasattr(treatment, 'product_quality') else 1.0
        history["products"]["quality"].append(quality)

    def _track_production_history(self, treatment, history, timestamp):
        """Track detailed production history"""
        if hasattr(treatment, 'production_history'):
            current_totals = {'wooden_furniture': 0, 'wooden_packaging': 0, 'paper_packaging': 0}
            
            for t, product_type, amount in treatment.production_history:
                if t <= timestamp:
                    current_totals[product_type] += amount

            for product_type, total in current_totals.items():
                if product_type not in history["products"]["by_type"]:
                    history["products"]["by_type"][product_type] = []
                history["products"]["by_type"][product_type].append(total)

    def track_processing(self, treatment, timestamp: float):
        """Track treatment facility metrics"""
        if treatment.name not in self.processing_history:
            self._initialize_treatment_history(treatment.name)

        history = self.processing_history[treatment.name]

        # Only record if this is a new timestamp
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)
            
            # Track metrics using helper methods
            self._track_storage_metrics(treatment, history)
            total_processed = self._track_processing_metrics(treatment, history)
            self._track_operational_metrics(treatment, history, total_processed)
            self._track_product_metrics(treatment, history, timestamp)

    def get_generation_history(self) -> Dict[str, Any]:
        """Get the generation history data"""
        return self.generation_history

    def get_collection_history(self) -> Dict[str, Any]:
        """Get the collection history data"""
        return self.collection_history

    def get_processing_history(self) -> Dict[str, Any]:
        """Get the processing history data"""
        return self.processing_history

    def get_overflow_history(self) -> Dict[str, Any]:
        """Get the overflow history data"""
        return self.overflow_history
