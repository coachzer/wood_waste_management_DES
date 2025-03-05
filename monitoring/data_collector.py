from typing import Dict, Any
from core.collector import CollectorCompany
from core.generator import WasteGenerator
from core.treatment import TreatmentOperator
from models.enums import WasteType


class DataCollector:
    """Handles data collection from various system components"""

    def __init__(self):
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}

    def track_generation(self, generator: WasteGenerator, timestamp: float):
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

    def track_collection(self, collector: CollectorCompany, timestamp: float):
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

    def track_processing(self, treatment: TreatmentOperator, timestamp: float):
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

    def get_generation_history(self) -> Dict[str, Any]:
        """Get the generation history data"""
        return self.generation_history

    def get_collection_history(self) -> Dict[str, Any]:
        """Get the collection history data"""
        return self.collection_history

    def get_processing_history(self) -> Dict[str, Any]:
        """Get the processing history data"""
        return self.processing_history
