from typing import Dict, Optional
from models.data_classes import WasteTransformation
from models.enums import RegionType, WasteType
from models.state import SimulationState
from optimization.stochastic import UncertaintySet
from core.overflow import OverflowTracker
from core.cost_tracker import CostTracker, CostType
import numpy as np


class TreatmentOperator:
    """Treatment operator that processes waste into products"""

    def __init__(
        self,
        env,
        name,
        processing_time,
        storage_capacity,
        energy_consumption,
        environmental_impact,
        conversion_rate,
        operational_costs,
        region: str,
        transformations: Optional[Dict[WasteType, WasteTransformation]] = None,
        uncertainty_set: Optional[UncertaintySet] = None,
    ):
        # Initialize trackers
        self.overflow_tracker = OverflowTracker()
        self.cost_tracker = CostTracker()

        # Track utilization history for dynamic capacity management
        self.utilization_history = []
        self.utilization_window = 10  # Rolling window size
        self.env = env
        self.name = name
        self.processing_capacity = (
            processing_time * storage_capacity * 0.8
        )  # Initial processing capacity (80% of theoretical max)
        self.initial_processing_capacity = (
            self.processing_capacity
        )  # Store initial value
        self.processing_time = processing_time
        # Storage capacity configuration
        self.initial_storage_capacity = storage_capacity
        self.storage_capacity = storage_capacity
        self.min_capacity = storage_capacity * 0.75  # Minimum 75% of initial
        self.max_capacity = storage_capacity * 2.0  # Maximum 200% of initial

        self.energy_consumption = energy_consumption
        self.environmental_impact = environmental_impact
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs

        # Store original region string for tracking
        self.region = region
        # Convert to enum for internal use
        self.region_type = RegionType[region.upper()] if region else None
        self.demand = 0

        self.total_products_created = 0.0
        self.demand_history = []
        self.production_history = []

        self.waste_storage = {waste_type: 0.0 for waste_type in WasteType}
        self.processed_volumes = {waste_type: 0.0 for waste_type in WasteType}

        # Capacity management state
        self.last_capacity_check = env.now
        self.capacity_check_interval = 1.0  # Check every time unit

        # Initialize stochastic components
        self.uncertainty_set = uncertainty_set
        self.rng = np.random.default_rng(42)  # For reproducibility
        self.transformation_efficiency = 0.95  # Base efficiency

        self.transformations = transformations or self._default_transformations()

        # Start processing loop
        self.process = env.process(self.run_facility())
        # Start demand-based collection process
        env.process(self.run_collection())

    @property
    def current_storage(self) -> float:
        """Get total current storage across all waste types"""
        return sum(self.waste_storage.values())

    @property
    def storage_utilization(self) -> float:
        """Get current storage utilization as a percentage"""
        return (
            (self.current_storage / self.storage_capacity) * 100
            if self.storage_capacity > 0
            else 0.0
        )

    def run_collection(self):
        """Process to periodically trigger collection based on demand"""
        while True:
            if self.demand > 0:
                self.trigger_collection()
            yield self.env.timeout(
                self.processing_time
            )  # Check at same interval as processing

    def run_facility(self):
        """Main process loop for the treatment facility"""
        while True:
            # Process waste based on available storage and transformations
            for (
                input_type,
                output_type,
            ), transformation in self.transformations.items():
                if self.waste_storage[input_type] > 0:
                    # Calculate amount to process
                    amount_to_process = min(
                        self.waste_storage[input_type], self.processing_capacity
                    )

                    # Apply transformation efficiency
                    efficiency = transformation.conversion_efficiency
                    if self.uncertainty_set:
                        # Get treatment conversion uncertainty for input type
                        mean, std = self.uncertainty_set.treatment_conversion.get(
                            input_type,
                            (efficiency, 0.05),  # Default 5% variation if not specified
                        )
                        # Apply stochastic variation within reasonable bounds
                        efficiency = np.clip(self.rng.normal(mean, std), 0.6, 1.0)

                    # Calculate potential output and check storage capacity
                    potential_output = amount_to_process * efficiency
                    available_capacity = self.storage_capacity - self.current_storage

                    # Scale down processing if not enough capacity for output
                    if potential_output > available_capacity:
                        scaling_factor = available_capacity / potential_output
                        amount_to_process *= scaling_factor
                        output_amount = available_capacity
                        # Track overflow
                        overflow_amount = potential_output - available_capacity
                        self.overflow_tracker.track_overflow(
                            "treatment", overflow_amount
                        )
                    else:
                        output_amount = potential_output

                    # Skip processing if output type is already a final product
                    final_products = {
                        WasteType.WOOD_PACKAGING,
                        WasteType.PAPER_PACKAGING,
                        WasteType.MIXED_WOOD,
                    }
                    if input_type in final_products:
                        continue

                    # Update input storage and processed volumes
                    self.waste_storage[input_type] -= amount_to_process
                    self.processed_volumes[input_type] += amount_to_process

                    # Store transformed output and update tracking
                    self.waste_storage[output_type] = (
                        self.waste_storage.get(output_type, 0.0) + output_amount
                    )
                    self.total_products_created += output_amount
                    self.production_history.append((self.env.now, output_amount))

                    # Fulfill demand for output product if it's a final product
                    if output_type in final_products:
                        # Remove the amount that fulfills demand
                        fulfilled_amount = min(output_amount, self.demand)
                        if fulfilled_amount > 0:
                            self.waste_storage[output_type] -= fulfilled_amount
                            self.demand -= fulfilled_amount
                            print(
                                f"{self.env.now}: Fulfilled {fulfilled_amount:.2f} m³ of {output_type.value} demand"
                            )

                    # Track costs
                    energy_cost = (
                        amount_to_process
                        * transformation.energy_required
                        * self.energy_consumption
                    )
                    operational_cost = amount_to_process * self.operational_costs
                    self.cost_tracker.track_cost(
                        CostType.ENERGY, energy_cost, self.env.now
                    )
                    self.cost_tracker.track_cost(
                        CostType.PROCESSING, operational_cost, self.env.now
                    )

                    # Update utilization history
                    current_utilization = amount_to_process / self.processing_capacity
                    self.utilization_history.append(current_utilization)
                    if len(self.utilization_history) > self.utilization_window:
                        self.utilization_history.pop(0)

            # Wait for processing time before next cycle
            yield self.env.timeout(self.processing_time)

    def trigger_collection(self):
        """Request waste collection based on current needs"""
        required_waste = self._calculate_required_waste()

        if required_waste <= 0:
            return 0, 0

        print(
            f"\n{self.env.now}: {self.name} requesting collection of {required_waste:.2f} m³"
        )

        total_by_type, total_collected = self._collect_waste(required_waste)

        # Track this collection's demand
        self.demand_history.append((self.env.now, required_waste))

        # Add to storage
        actually_stored = self._add_to_storage(total_by_type)
        if actually_stored < total_collected:
            print(
                f"Could only store {actually_stored:.2f} m³ due to capacity constraints"
            )
        return actually_stored, total_collected

    def _calculate_required_waste(self):
        """Calculate how much waste needs to be collected"""
        available_storage = self.storage_capacity - self.current_storage
        required_waste = min(
            self.demand / self.conversion_rate, available_storage * 0.8
        )
        return required_waste

    def _collect_waste(self, required_waste):
        """Collect waste from collectors in the region"""
        state = SimulationState.get_instance()
        total_collected = 0
        total_by_type = {waste_type: 0.0 for waste_type in WasteType}

        # Get collectors with stored waste and those that can collect more
        collectors_with_stored_waste = self._get_collectors_with_waste(state)
        collectors_for_collection = self._get_available_collectors(state)

        # First use stored waste
        total_collected = self._transfer_stored_waste(
            collectors_with_stored_waste, required_waste, total_by_type
        )

        # Then request additional collection if needed
        total_collected = self._request_additional_collection(
            collectors_for_collection, required_waste, total_collected, total_by_type
        )

        if total_collected > 0:
            print(f"Total waste collected: {total_collected:.2f} m³")

        return total_by_type, total_collected

    def _get_collectors_with_waste(self, state):
        """Get collectors that have waste stored"""
        return [
            c
            for c in state.collectors
            if c.region_type == self.region_type
            and c.availability
            and sum(c.collection_center.current_storage.values()) > 0
        ]

    def _get_available_collectors(self, state):
        """Get all available collectors in the region"""
        return [
            c
            for c in state.collectors
            if c.region_type == self.region_type and c.availability
        ]

    def _transfer_stored_waste(self, collectors, required_waste, total_by_type):
        """Transfer waste from collectors' storage"""
        total_collected = 0
        input_waste_types = set(key[0] for key in self.transformations.keys())

        for collector in collectors:
            if total_collected >= required_waste:
                break

            remaining_need = required_waste - total_collected
            for waste_type in input_waste_types:
                if waste_type in collector.collection_center.current_storage:
                    available = collector.collection_center.current_storage[waste_type]
                    if available > 0:
                        transfer_amount = min(available, remaining_need)
                        collector.collection_center.current_storage[
                            waste_type
                        ] -= transfer_amount
                        total_by_type[waste_type] += transfer_amount
                        total_collected += transfer_amount
                        print(
                            f"Transferred {transfer_amount:.2f} m³ of {waste_type} from {collector.name}'s storage"
                        )

        return total_collected

    def _request_additional_collection(
        self, collectors, required_waste, total_collected, total_by_type
    ):
        """Request additional waste collection if needed"""
        if total_collected >= required_waste:
            return total_collected

        for collector in collectors:
            remaining_need = required_waste - total_collected
            if remaining_need <= 0:
                break

            collected_amounts = collector.collect_waste_for_demand(remaining_need)

            for waste_type, amount in collected_amounts.items():
                if amount > 0:
                    total_by_type[waste_type] += amount
                    total_collected += amount
                    print(
                        f"Collected {amount:.2f} m³ of {waste_type.value} from {collector.name}"
                    )

        return total_collected

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        # Transformation efficiencies from behavior model
        base_transformations = {
            WasteType.SAWDUST: (0.95, 0.5),  # 95% efficiency
            WasteType.WOOD_CUTTINGS: (0.90, 0.8),  # 90% efficiency
            WasteType.BARK: (0.85, 0.7),  # 85% efficiency
            WasteType.CORK: (0.92, 0.6),  # 92% efficiency
            WasteType.SOLID_WOOD: (0.98, 0.9),  # 98% efficiency
            WasteType.PAPER_PACKAGING: (0.80, 0.4),  # 80% efficiency
            WasteType.WOOD_PACKAGING: (0.88, 0.7),  # 88% efficiency
            WasteType.MIXED_WOOD: (1.0, 0.3),  # Already mixed
        }

        # Create default transformations mapping for each input-output pair
        transformations = {}

        # Define final products that cannot be inputs
        final_products = {
            WasteType.WOOD_PACKAGING,
            WasteType.PAPER_PACKAGING,
            WasteType.MIXED_WOOD,
        }

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            WasteType.SAWDUST: [WasteType.WOOD_PACKAGING],
            WasteType.WOOD_CUTTINGS: [WasteType.WOOD_PACKAGING],
            WasteType.BARK: [WasteType.MIXED_WOOD],
            WasteType.CORK: [WasteType.MIXED_WOOD],
            WasteType.SOLID_WOOD: [WasteType.PAPER_PACKAGING],
        }

        for input_type, (efficiency, energy) in base_transformations.items():
            for output_type in default_output_mapping[input_type]:
                key = (input_type, output_type)
                transformations[key] = WasteTransformation(
                    input_type=input_type,
                    output_type=output_type,
                    conversion_efficiency=efficiency,
                    energy_required=energy,
                )
        return transformations

    def _add_to_storage(self, waste_amounts: Dict[WasteType, float]) -> float:
        """Add waste to storage considering capacity constraints"""
        total_added = 0.0

        # Calculate available capacity
        available_capacity = self.storage_capacity - self.current_storage

        # Calculate total incoming waste
        total_incoming = sum(waste_amounts.values())

        if total_incoming <= 0:
            return 0.0

        # If not enough capacity, scale down amounts proportionally
        if total_incoming > available_capacity:
            scaling_factor = available_capacity / total_incoming
            waste_amounts = {
                waste_type: amount * scaling_factor
                for waste_type, amount in waste_amounts.items()
            }
            # Track overflow
            overflow_amount = total_incoming - available_capacity
            self.overflow_tracker.track_overflow("treatment", overflow_amount)

        # Add waste to storage
        for waste_type, amount in waste_amounts.items():
            self.waste_storage[waste_type] += amount
            total_added += amount

        return total_added
