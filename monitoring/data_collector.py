from typing import Dict, Any, TYPE_CHECKING
from models.enums import WasteType


class DataCollector:
    """Handles data collection from various system components"""

    def __init__(self):
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
            "facility_types": [],
            "volumes": [],
            "timestamps": []
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

        # Track efficiency metrics
        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(collector.transport_cost)

    def track_overflow(self, facility_type: str, volume: float):
        """Track overflow events"""
        self.overflow_history["facility_types"].append(facility_type)
        self.overflow_history["volumes"].append(volume)
        self.overflow_history["timestamps"].append(self.last_timestamp)

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

    def track_processing(self, treatment, timestamp: float):
        """Track treatment facility metrics"""
        if treatment.name not in self.processing_history:
            self.processing_history[treatment.name] = {
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

        history = self.processing_history[treatment.name]

        # Only record if this is a new timestamp
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)

            # Storage metrics
            history["storage"]["total"].append(treatment.current_storage)
            history["storage"]["utilization"].append(treatment.storage_utilization)
            for waste_type in WasteType:
                history["storage"]["by_type"][waste_type].append(
                    treatment.waste_storage[waste_type]
                )

            # Processing metrics
            total_processed = sum(treatment.processed_volumes.values())
            history["processed"]["total"].append(total_processed)
            for waste_type in WasteType:
                history["processed"]["by_type"][waste_type].append(
                    treatment.processed_volumes[waste_type]
                )

            # Operational metrics
            history["operational"]["energy_consumption"].append(
                treatment.energy_consumption
            )
            history["operational"]["conversion_rate"].append(treatment.conversion_rate)
            history["operational"]["demand"].append(treatment.demand)
            history["operational"]["demand_satisfaction"].append(
                total_processed >= treatment.demand if treatment.demand > 0 else 1.0
            )

            # Product metrics
            total_products = sum(treatment.product_volumes.values()) if hasattr(treatment, 'product_volumes') else 0
            history["products"]["total"].append(total_products)
            
            # Track products by type
            if hasattr(treatment, 'product_volumes'):
                for product_type, volume in treatment.product_volumes.items():
                    if product_type not in history["products"]["by_type"]:
                        history["products"]["by_type"][product_type] = []
                    history["products"]["by_type"][product_type].append(volume)
            
            # Track product quality
            quality = treatment.product_quality if hasattr(treatment, 'product_quality') else 1.0
            history["products"]["quality"].append(quality)

    def get_generation_history(self) -> Dict[str, Any]:
        """Get the generation history data"""
        return self.generation_history

    def get_collection_history(self) -> Dict[str, Any]:
        """Get the collection history data"""
        return self.collection_history

    def get_processing_history(self) -> Dict[str, Any]:
        """Get the processing history data"""
        return self.processing_history
