import numpy as np
from typing import Dict, Iterable, Optional
from models.data_classes import WasteTransformation, OperationalEntity
from models.enums import OutputType, RegionType, WasteType, EntityStatus
from models.state import SimulationState
from optimization.uncertainty import UncertaintySet
from monitoring.data_collector import DataCollector
from core.collection_coordinator import CollectionCoordinator
from core.treatment_utils import (
    get_furniture_material_quality,
    get_transformation_efficiency,
    calculate_output_amounts,
    update_waste_storage,
    fulfill_demand,
    track_processing_costs,
    update_utilization_metrics,
    calculate_required_waste
)

from utils.capacity_utils import apply_capacity_constraints, apply_partial_update_with_constraints, handle_overflow_generic, check_storage_capacity

class StorageDict(dict):
    def __init__(self, owner, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        excluded_keys = {key}
        result = apply_capacity_constraints(
            sum(v for k, v in self.items() if k not in excluded_keys),
            value,
            self.owner.storage_capacity
        )
        if result.overflow_amount > 0:
            handle_overflow_generic(
                self.owner.data_collector,
                "treatment",
                result.overflow_amount,
                "landfill",
                self.owner.env.now
            )
        super().__setitem__(key, result.allowed_amount)

class TreatmentOperator(OperationalEntity):
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
        super().__init__()
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

        self._waste_storage = StorageDict(self, {waste_type: 0.0 for waste_type in WasteType})
        self.processed_volumes = {waste_type: 0.0 for waste_type in WasteType}
        self.product_volumes = {
            "wooden_furniture": 0.0,
            "wooden_packaging": 0.0,
            "paper_packaging": 0.0
        }

        # Capacity management state
        self.last_capacity_check = env.now
        self.capacity_check_interval = 1.0  # Check every time unit
        self.minimum_required_waste = 0.1  # Minimum waste required for collection

        # Initialize stochastic components
        self.uncertainty_set = uncertainty_set
        self.rng = np.random.default_rng(42)  # For reproducibility
        self.transformation_efficiency = 0.95  # Base efficiency
        
        # Set failure check interval if configuration is available
        if uncertainty_set and hasattr(uncertainty_set, 'treatment_failure'):
            self.failure_check_interval = uncertainty_set.treatment_failure.check_interval

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

    @property
    def waste_storage(self) -> Dict[WasteType, float]:
        """Get the waste storage dictionary"""
        return self._waste_storage

    @waste_storage.setter
    def waste_storage(self, new_storage: Dict[WasteType, float]):
        """Set waste storage with capacity constraints"""
        if not isinstance(new_storage, dict):
            return
        
        if len(new_storage) == len(self._waste_storage):
            self._handle_full_storage_update(new_storage)
        else:
            self._handle_partial_storage_update(new_storage)

    def _handle_full_storage_update(self, new_storage: Dict[WasteType, float]) -> None:
        """Update all storage values while respecting capacity constraints"""
        result = apply_partial_update_with_constraints(
            current_values=self._waste_storage,
            updates=new_storage,
            capacity=self.storage_capacity
        )
        if result.overflow_amount > 0:
            handle_overflow_generic(
                self.data_collector,
                "treatment",
                result.overflow_amount,
                "landfill",
                self.env.now
            )
        self._waste_storage = StorageDict(self, result.scaled_values)

    def _handle_partial_storage_update(self, partial_update: Dict[WasteType, float]) -> None:
        """Update specific storage values while respecting capacity constraints"""
        result = apply_partial_update_with_constraints(
            current_values=self._waste_storage,
            updates=partial_update,
            capacity=self.storage_capacity,
            excluded_keys=set(partial_update.keys())
        )
        if result.overflow_amount > 0:
            handle_overflow_generic(
                self.data_collector,
                "treatment",
                result.overflow_amount,
                "landfill",
                self.env.now
            )
        for waste_type, amount in result.scaled_values.items():
            self._waste_storage[waste_type] = amount

    def _calculate_current_total_excluding(self, waste_types_to_exclude: Iterable[WasteType]) -> float:
        """Calculate current storage total excluding specified waste types"""
        return sum(
            amount for wtype, amount in self._waste_storage.items() 
            if wtype not in waste_types_to_exclude
        )

    def _apply_partial_update_without_overflow(self, partial_update: Dict[WasteType, float]) -> None:
        """Apply partial update when there's no capacity overflow"""
        for waste_type, amount in partial_update.items():
            self._waste_storage[waste_type] = amount

    def _apply_partial_update_with_scaling(self, partial_update: Dict[WasteType, float], scaling_factor: float) -> None:
        """Apply partial update with scaling to avoid overflow"""
        for waste_type, amount in partial_update.items():
            scaled_amount = amount * scaling_factor
            self._waste_storage[waste_type] = scaled_amount
            overflow_amount = amount - scaled_amount
            self.data_collector.track_overflow(
                "treatment",
                overflow_amount,
                "landfill",  # Use landfill for scaled overflow
                self.env.now
            )

    def run_collection(self):
        """Process to periodically trigger collection based on demand"""
        while True:
            if self.demand > 0:
                self.trigger_collection()
            yield self.env.timeout(
                self.processing_time
            )  # Check at same interval as processing

    def _check_failure_and_recovery(self, current_time):
        """Check for failures and recovery"""
        # Check for failures if uncertainty set is available
        if self.uncertainty_set and hasattr(self.uncertainty_set, 'treatment_failure'):
            self.check_failure(current_time, self.uncertainty_set.treatment_failure.probability)
        
        # Check for recovery
        if (self.status == EntityStatus.FAILED and 
            current_time >= self.recovery_time):
            print(f"{current_time}: Treatment operator {self.name} has recovered from failure")
            self.status = EntityStatus.OPERATIONAL
            self.failure_time = None
            self.recovery_time = None
            
        return self.status == EntityStatus.FAILED
            
    def _get_prioritized_transformations(self):
        """Get transformations sorted by priority based on current demands and system state"""
        # Get current demands and state
        state = SimulationState.get_instance()
        unmet_demands = state.get_unmet_demands()
        
        # Check if any demands are still unmet
        if any(demand > 0 for demand in unmet_demands.values()):
            # Still have unmet demands - prioritize based on remaining demand
            product_demands = {
                OutputType.WOODEN_FURNITURE: unmet_demands.get('wooden_furniture', 0),
                OutputType.WOODEN_PACKAGING: unmet_demands.get('wooden_packaging', 0),
                OutputType.PAPER_PACKAGING: unmet_demands.get('paper_packaging', 0)
            }
            
            # Sort transformations by unmet demand and efficiency
            return sorted(
                self.transformations.items(),
                key=lambda x, demands=product_demands: (
                    # Primary sort: Has unmet demand
                    demands.get(x[0][1], 0) > 0,
                    # Secondary sort: Amount of unmet demand
                    demands.get(x[0][1], 0),
                    # Tertiary sort: Efficiency
                    get_transformation_efficiency(self, x[0][0], x[1])
                ),
                reverse=True
            )
        else:
            # All demands met - sort based on efficiency and material quality
            return sorted(
                self.transformations.items(),
                key=lambda x, get_quality=get_furniture_material_quality: (
                    # Primary sort: Material quality for furniture or transformation efficiency
                    get_quality(x[0][0]) if x[0][1] == OutputType.WOODEN_FURNITURE
                    else get_transformation_efficiency(self, x[0][0], x[1])
                ),
                reverse=True
            )

    def run_facility(self):
        """Main process loop for the treatment facility"""
        while True:
            current_time = self.env.now
            
            # Check for failures and recovery
            is_failed = self._check_failure_and_recovery(current_time)
            
            # Skip processing if failed
            if is_failed:
                print(f"{current_time}: Treatment operator {self.name} is currently failed, skipping processing")
                yield self.env.timeout(self.processing_time)
                continue

            # Get sorted transformations by priority
            sorted_transformations = self._get_prioritized_transformations()

            # Process transformations in priority order
            for (input_type, output_type), transformation in sorted_transformations:
                if self.waste_storage[input_type] > 0:
                    self._process_waste_transformation(input_type, output_type, transformation)

            # Wait for processing time before next cycle
            yield self.env.timeout(self.processing_time)
            
    def _process_waste_transformation(self, input_type, output_type, transformation):
        """Process a single waste transformation"""
        # Skip processing if input type is already a final product
        final_products = {
            OutputType.WOODEN_PACKAGING,
            OutputType.PAPER_PACKAGING,
            OutputType.WOODEN_FURNITURE,
        }
        if input_type in final_products:
            return
            
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        product_demands = {
            OutputType.WOODEN_FURNITURE: state.target_demands['wooden_furniture'] - state.total_products['wooden_furniture'],
            OutputType.WOODEN_PACKAGING: state.target_demands['wooden_packaging'] - state.total_products['wooden_packaging'],
            OutputType.PAPER_PACKAGING: state.target_demands['paper_packaging'] - state.total_products['paper_packaging']
        }

        # Check if this is a furniture-capable input and handle material reservation
        furniture_materials = {WasteType.CONSTRUCTION_WOOD, WasteType.WOOD_CUTTINGS, WasteType.WASTE_WOODEN_PACKAGING}
        furniture_demand = product_demands[OutputType.WOODEN_FURNITURE]
        
        if input_type in furniture_materials and furniture_demand > 0:
            # Calculate material reservation
            reserved_amount = self.waste_storage[input_type] * 0.4  # Reserve 40% for furniture
            
            if output_type != OutputType.WOODEN_FURNITURE:
                # For non-furniture outputs, use appropriate unreserved portion
                available_amount = self.waste_storage[input_type] - reserved_amount
                if available_amount <= 0:
                    return  # Skip processing if all material is reserved
                amount_to_process = min(available_amount, self.processing_capacity)
            else:
                # For furniture production, can use entire amount including reserved
                amount_to_process = min(self.waste_storage[input_type], self.processing_capacity)
        else:
            # Not a furniture material or no furniture demand, process normally
            amount_to_process = min(self.waste_storage[input_type], self.processing_capacity)
        
        # Get transformation efficiency with uncertainty
        efficiency = min(get_transformation_efficiency(self, input_type, transformation), 1.0)
        
        # Calculate output and handle capacity constraints
        amount_to_process, output_amount = calculate_output_amounts(
            self,
            amount_to_process, efficiency
        )
        
        # Update waste storage and tracking
        update_waste_storage(self, input_type, output_type, amount_to_process, output_amount)
        
        # Handle demand fulfillment for final products
        if output_type in final_products:
            fulfill_demand(self, output_type, output_amount)
            # Update product volumes
            if output_type == OutputType.WOODEN_FURNITURE:
                self.product_volumes["wooden_furniture"] += output_amount
            elif output_type == OutputType.WOODEN_PACKAGING:
                self.product_volumes["wooden_packaging"] += output_amount
            elif output_type == OutputType.PAPER_PACKAGING:
                self.product_volumes["paper_packaging"] += output_amount
        
        # Track processing costs
        track_processing_costs(self, amount_to_process, transformation)
        
        # Update utilization metrics
        update_utilization_metrics(self, amount_to_process)
    
    def trigger_collection(self):
        """Request waste collection based on current needs"""
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        product_demands = {
            OutputType.WOODEN_FURNITURE: state.target_demands['wooden_furniture'] - state.total_products['wooden_furniture'],
            OutputType.WOODEN_PACKAGING: state.target_demands['wooden_packaging'] - state.total_products['wooden_packaging'],
            OutputType.PAPER_PACKAGING: state.target_demands['paper_packaging'] - state.total_products['paper_packaging']
        }
        
        # Update self.demand to include all unmet product demands
        self.demand = sum(product_demands.values())
        
        required_waste = calculate_required_waste(self)
        if required_waste <= 0:
            return 0, 0

        # Get input waste types from transformations, prioritizing furniture materials
        input_waste_types = set()
        if product_demands[OutputType.WOODEN_FURNITURE] > 0:
            # First prioritize high-quality materials for furniture
            input_waste_types.add(WasteType.CONSTRUCTION_WOOD)
            input_waste_types.add(WasteType.WOOD_CUTTINGS)
            input_waste_types.add(WasteType.WASTE_WOODEN_PACKAGING)
            
            # Increase the required amount to ensure enough materials for furniture
            required_waste *= 1.2
        
        # Add other input types for remaining products
        input_waste_types.update(key[0] for key in self.transformations.keys())
        
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
            self.data_collector.track_overflow(
                "treatment",
                overflow_amount,
                "landfill",  # Use landfill for collection overflow
                self.env.now
            )
            
        return actually_stored, collection_result.total_collected

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        # Transformation efficiencies from behavior model
        base_transformations = {
            # Primary materials (best for furniture)
            WasteType.CONSTRUCTION_WOOD: (0.98, 0.90),   # High quality, high energy
            WasteType.WOOD_CUTTINGS: (0.92, 0.85),       # Good quality, high energy
            WasteType.WASTE_WOODEN_PACKAGING: (0.88, 0.95), # Good for furniture after processing
            
            # Secondary materials (good for packaging)
            WasteType.SAWDUST: (0.95, 0.50),             # Great for compression molding
            
            # Paper materials
            WasteType.BARK_WASTE: (0.85, 0.70),          # Good for pulping
            WasteType.MIXED_WOOD: (0.88, 0.60),          # Decent for pulping
            WasteType.WASTE_PAPER_PACKAGING: (0.82, 0.65), # Good for recycling
        }

        # Create transformations dictionary
        transformations = {}
        
        # Create furniture transformations first for high-quality materials
        for input_type, (efficiency, energy) in base_transformations.items():
            if input_type in {WasteType.CONSTRUCTION_WOOD, WasteType.WOOD_CUTTINGS, WasteType.WASTE_WOODEN_PACKAGING}:
                key = (input_type, OutputType.WOODEN_FURNITURE)
                transformations[key] = WasteTransformation(
                    input_type=input_type,
                    output_type=OutputType.WOODEN_FURNITURE,
                    conversion_efficiency=efficiency * 1.1,  # Boost efficiency for furniture
                    energy_required=energy,
                )

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            # Primary furniture production - allow all suitable materials
            WasteType.CONSTRUCTION_WOOD: [OutputType.WOODEN_FURNITURE, OutputType.WOODEN_PACKAGING],
            WasteType.WOOD_CUTTINGS: [OutputType.WOODEN_FURNITURE, OutputType.WOODEN_PACKAGING],
            WasteType.WASTE_WOODEN_PACKAGING: [OutputType.WOODEN_FURNITURE, OutputType.WOODEN_PACKAGING],
            WasteType.SAWDUST: [OutputType.WOODEN_PACKAGING],
            
            # Paper production paths
            WasteType.BARK_WASTE: [OutputType.PAPER_PACKAGING],
            WasteType.MIXED_WOOD: [OutputType.PAPER_PACKAGING],
            WasteType.WASTE_PAPER_PACKAGING: [OutputType.PAPER_PACKAGING],
        }

        for input_type, (efficiency, energy) in base_transformations.items():
            for output_type in default_output_mapping[input_type]:
                # Skip if already created (furniture transformations)
                if (input_type, output_type) not in transformations:
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
        if not waste_amounts:
            return 0.0

        allowed_additions, overflow_amount = check_storage_capacity(
            self.waste_storage,
            waste_amounts,
            self.storage_capacity
        )

        if overflow_amount > 0:
            handle_overflow_generic(
                self.data_collector,
                "treatment",
                overflow_amount,
                "landfill",
                self.env.now
            )

        total_added = 0.0
        for waste_type, amount in allowed_additions.items():
            self.waste_storage[waste_type] += amount
            total_added += amount

        return total_added
