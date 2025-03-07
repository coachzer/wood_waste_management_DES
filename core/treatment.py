from typing import Dict, Optional, Set, TYPE_CHECKING
from models.data_classes import WasteTransformation
from models.enums import RegionType, WasteType
from optimization.stochastic import UncertaintySet
from monitoring.data_collector import DataCollector
from core.collection_coordinator import CollectionCoordinator
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
        data_collector: Optional['DataCollector'] = None,
    ):
        # Initialize monitoring
        if data_collector is None:
            raise ValueError("data_collector is required for TreatmentOperator")
        self.data_collector = data_collector
        
        # Initialize collection coordinator
        self.collection_coordinator = CollectionCoordinator(env, region)

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
        # Convert to enum for internal use, replacing hyphen with underscore for lookup
        self.region_type = RegionType[region.upper().replace('-', '_')] if region else None
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
            for (input_type, output_type), transformation in self.transformations.items():
                if self.waste_storage[input_type] > 0:
                    self._process_waste_transformation(input_type, output_type, transformation)

            # Wait for processing time before next cycle
            yield self.env.timeout(self.processing_time)
            
    def _process_waste_transformation(self, input_type, output_type, transformation):
        """Process a single waste transformation"""
        # Skip processing if input type is already a final product
        final_products = {
            WasteType.WOODEN_PACKAGING,
            WasteType.PAPER_PACKAGING,
            WasteType.MIXED_WOOD,
        }
        if input_type in final_products:
            return
            
        # Calculate amount to process
        amount_to_process = min(
            self.waste_storage[input_type], self.processing_capacity
        )
        
        # Get transformation efficiency with uncertainty
        efficiency = self._get_transformation_efficiency(input_type, transformation)
        
        # Calculate output and handle capacity constraints
        amount_to_process, output_amount = self._calculate_output_amounts(
            amount_to_process, efficiency
        )
        
        # Update waste storage and tracking
        self._update_waste_storage(input_type, output_type, amount_to_process, output_amount)
        
        # Handle demand fulfillment for final products
        if output_type in final_products:
            self._fulfill_demand(output_type, output_amount)
        
        # Track processing costs
        self._track_processing_costs(amount_to_process, transformation)
        
        # Update utilization metrics
        self._update_utilization_metrics(amount_to_process)
    
    def _get_transformation_efficiency(self, input_type, transformation):
        """Calculate transformation efficiency with uncertainty if applicable"""
        efficiency = transformation.conversion_efficiency
        if self.uncertainty_set:
            # Get treatment conversion uncertainty for input type
            mean, std = self.uncertainty_set.treatment_conversion.get(
                input_type,
                (efficiency, 0.05),  # Default 5% variation if not specified
            )
            # Apply stochastic variation within reasonable bounds
            efficiency = np.clip(self.rng.normal(mean, std), 0.6, 1.0)
        return efficiency
    
    def _calculate_output_amounts(self, amount_to_process, efficiency):
        """Calculate actual processing and output amounts considering capacity constraints"""
        potential_output = amount_to_process * efficiency
        available_capacity = self.storage_capacity - self.current_storage
        
        if potential_output > available_capacity:
            scaling_factor = available_capacity / potential_output
            amount_to_process *= scaling_factor
            output_amount = available_capacity
            # Track overflow through data collector
            overflow_amount = potential_output - available_capacity
            self.data_collector.track_overflow("treatment", overflow_amount)
        else:
            output_amount = potential_output
            
        return amount_to_process, output_amount
    
    def _update_waste_storage(self, input_type, output_type, amount_to_process, output_amount):
        """Update waste storage and track production"""
        # Update input storage and processed volumes
        self.waste_storage[input_type] -= amount_to_process
        self.processed_volumes[input_type] += amount_to_process
        
        # Store transformed output and update tracking
        self.waste_storage[output_type] = (
            self.waste_storage.get(output_type, 0.0) + output_amount
        )
        self.total_products_created += output_amount
        self.production_history.append((self.env.now, output_amount))
    
    def _fulfill_demand(self, output_type, output_amount):
        """Fulfill demand for final products"""
        fulfilled_amount = min(output_amount, self.demand)
        if fulfilled_amount > 0:
            self.waste_storage[output_type] -= fulfilled_amount
            self.demand -= fulfilled_amount
            print(
                f"{self.env.now}: Fulfilled {fulfilled_amount:.12f} m³ of {output_type.value} demand"
            )
    
    def _track_processing_costs(self, amount_to_process, transformation):
        """Track energy and operational costs"""
        energy_cost = (
            amount_to_process
            * transformation.energy_required
            * self.energy_consumption
        )
        operational_cost = amount_to_process * self.operational_costs
        # Track costs through data collector
        self.data_collector.track_energy_cost(energy_cost, self.env.now)
        self.data_collector.track_processing_cost(operational_cost, self.env.now)
    
    def _update_utilization_metrics(self, amount_to_process):
        """Update utilization history for capacity management"""
        current_utilization = amount_to_process / self.processing_capacity
        self.utilization_history.append(current_utilization)
        if len(self.utilization_history) > self.utilization_window:
            self.utilization_history.pop(0)

    def trigger_collection(self):
        """Request waste collection based on current needs"""
        required_waste = self._calculate_required_waste()

        if required_waste <= 0:
            return 0, 0

        # Get input waste types from transformations
        input_waste_types = set(key[0] for key in self.transformations.keys())
        
        # Request collection through coordinator
        collection_result = self.collection_coordinator.request_collection(
            required_waste,
            input_waste_types
        )

        # Track this collection's demand
        self.demand_history.append((self.env.now, required_waste))
        self.data_collector.track_processing(self, self.env.now)

        # Add to storage
        actually_stored = self._add_to_storage(collection_result.waste_by_type)
        if actually_stored < collection_result.total_collected:
            print(
                f"Could only store {actually_stored:.12f} m³ due to capacity constraints"
            )
            # Track overflow through data collector
            overflow_amount = collection_result.total_collected - actually_stored
            self.data_collector.track_overflow("treatment", overflow_amount)
            
        return actually_stored, collection_result.total_collected

    def _calculate_required_waste(self):
        """Calculate how much waste needs to be collected"""
        available_storage = self.storage_capacity - self.current_storage
        required_waste = min(
            self.demand / self.conversion_rate, available_storage * 0.8
        )
        return required_waste

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        # Transformation efficiencies from behavior model
        base_transformations = {
            WasteType.SAWDUST: (0.95, 0.5),  # 95% efficiency
            WasteType.WOOD_CUTTINGS: (0.90, 0.8),  # 90% efficiency
            WasteType.BARK_WASTE: (0.85, 0.7),  # 85% efficiency
            WasteType.CONSTRUCTION_WOOD: (0.98, 0.9),  # 98% efficiency
            WasteType.PAPER_PACKAGING: (0.80, 0.4),  # 80% efficiency
            WasteType.WOODEN_PACKAGING: (0.88, 0.7),  # 88% efficiency
            WasteType.MIXED_WOOD: (1.0, 0.3),  # Already mixed
        }

        # Create default transformations mapping for each input-output pair
        transformations = {}

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            WasteType.SAWDUST: [WasteType.WOODEN_PACKAGING],
            WasteType.WOOD_CUTTINGS: [WasteType.WOODEN_PACKAGING],
            WasteType.BARK_WASTE: [WasteType.MIXED_WOOD],
            WasteType.CONSTRUCTION_WOOD: [WasteType.PAPER_PACKAGING],
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
            # Track overflow through data collector
            overflow_amount = total_incoming - available_capacity
            self.data_collector.track_overflow("treatment", overflow_amount)

        # Add waste to storage
        for waste_type, amount in waste_amounts.items():
            self.waste_storage[waste_type] += amount
            total_added += amount

        return total_added
