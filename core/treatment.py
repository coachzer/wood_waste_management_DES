import numpy as np
from typing import Dict, Iterable, Optional
from models.data_classes import WasteTransformation, OperationalEntity, ProductStorage
from models.enums import OutputType, RegionType, WasteType, EntityStatus
from models.state import SimulationState
from monitoring.data_collector import DataCollector
from core.kanban_manager import KanbanManager
from models.enums import InventoryPolicy
from core.collection_coordinator import CollectionCoordinator
from core.treatment_utils import (
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
        uncertainty_set = None,
        data_collector: Optional['DataCollector'] = None,
        inventory_policy: InventoryPolicy = InventoryPolicy.PUSH,
        kanban_manager: KanbanManager = None,
        product_storage_capacity: float = 0.0,
    ):
        super().__init__()
        # Initialize monitoring
        if data_collector is None:
            raise ValueError("data_collector is required for TreatmentOperator")
        self.data_collector = data_collector
        self.inventory_policy = inventory_policy
        self.kanban_manager = kanban_manager or KanbanManager()
        
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

        self._waste_storage = StorageDict(self, dict.fromkeys(WasteType, 0.0))
        self.processed_volumes = dict.fromkeys(WasteType, 0.0)
        self.product_volumes = {
            "mdf_fibreboard": 0.0,
            "particle_board": 0.0,
            "osb_waferboard": 0.0
        }

        # Initialize product storage for finished products
        self.product_storage_capacity = product_storage_capacity
        self.product_storage = ProductStorage(
            capacity=product_storage_capacity,
            current_storage=dict.fromkeys(OutputType, 0.0)
        )

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
        """Process to periodically trigger collection based on demand or Kanban"""
        while True:
            if self.inventory_policy == InventoryPolicy.PUSH:
                # Periodic review: forecast demand, calculate order-up-to, trigger collection
                forecast = np.mean([d for _, d in self.demand_history[-4:]]) if self.demand_history else 0
                safety_stock = 1.65 * np.std([d for _, d in self.demand_history[-4:]]) if self.demand_history else 0
                order_up_to = forecast + safety_stock
                
                # If no demand history, use current demand as initial trigger
                if len(self.demand_history) == 0 and self.demand > 0:
                    order_up_to = self.demand
                
                if order_up_to > 0:
                    self.demand = order_up_to
                    self.trigger_collection()
                yield self.env.timeout(7)  # Weekly review
            elif self.inventory_policy == InventoryPolicy.PULL:
                # Kanban container management: check if any waste type drops below threshold
                for waste_type, volume in self.waste_storage.items():
                    # Example: trigger Kanban signal if below 1 container (customize as needed)
                    if volume < 1.0:
                        self.kanban_manager.add_signal(
                            waste_type=waste_type,
                            priority=1,  # Could be weighted by biogenic value
                            timestamp=self.env.now
                        )
                yield self.env.timeout(self.processing_time)

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
                OutputType.MDF_FIBREBOARD: unmet_demands.get('mdf_fibreboard', 0),
                OutputType.PARTICLE_BOARD: unmet_demands.get('particle_board', 0),
                OutputType.OSB_WAFERBOARD: unmet_demands.get('osb_waferboard', 0)
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
                    get_transformation_efficiency(self, x[1])
                ),
                reverse=True
            )
        else:
            # All demands met - sort based on transformation efficiency
            return sorted(
                self.transformations.items(),
                key=lambda x: get_transformation_efficiency(self, x[1]),
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
        print(f"[PROCESS DEBUG] Starting transformation {input_type.name} -> {output_type.name}")
        print(f"[PROCESS DEBUG] Available waste: {self.waste_storage[input_type]:.2f} m³")
        
        # Skip processing if input type is already a final product
        final_products = {
            OutputType.MDF_FIBREBOARD,
            OutputType.PARTICLE_BOARD,
            OutputType.OSB_WAFERBOARD,
            OutputType.WOODEN_PACKAGING,
            OutputType.PAPER_PACKAGING
        }
        if input_type in final_products:
            print("[PROCESS DEBUG] Skipping - input is already a final product")
            return
            
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        product_demands = {
            OutputType.MDF_FIBREBOARD: state.target_demands['mdf_fibreboard'] - state.total_products['mdf_fibreboard'],
            OutputType.PARTICLE_BOARD: state.target_demands['particle_board'] - state.total_products['particle_board'],
            OutputType.OSB_WAFERBOARD: state.target_demands['osb_waferboard'] - state.total_products['osb_waferboard']
        }
        print(f"[PROCESS DEBUG] Current unmet demand for {output_type.name}: {product_demands.get(output_type, 'N/A')}")

        # Process normally since we don't handle furniture anymore
        amount_to_process = min(self.waste_storage[input_type], self.processing_capacity)
        print(f"[PROCESS DEBUG] Amount to process: {amount_to_process:.2f} m³ (capacity: {self.processing_capacity})")
        
        if amount_to_process <= 0:
            print("[PROCESS DEBUG] No waste to process")
            return
        
        # Get transformation efficiency with uncertainty
        efficiency = min(get_transformation_efficiency(self, transformation), 1.0)
        print(f"[PROCESS DEBUG] Efficiency: {efficiency:.3f}")
        
        # Calculate output and handle capacity constraints
        amount_to_process, output_amount = calculate_output_amounts(
            self,
            amount_to_process, efficiency
        )
        print(f"[PROCESS DEBUG] Final processing: {amount_to_process:.2f} m³ -> {output_amount:.2f} m³")
        
        # Update waste storage and tracking
        update_waste_storage(self, input_type, output_type, amount_to_process, output_amount)
        
        # Handle demand fulfillment for final products
        if output_type in final_products:
            print("[PROCESS DEBUG] Output is final product, proceeding with fulfillment")
            # Store finished product in product storage (shared capacity)
            total_stored = sum(self.product_storage.current_storage.values())
            capacity = self.product_storage.capacity
            addable = min(output_amount, capacity - total_stored)
            overflow = output_amount - addable
            self.product_storage.current_storage[output_type] += addable

            # On overflow, simulate buying more inventory (increase capacity)
            if overflow > 0:
                # Log purchase event - increase capacity by overflow amount
                self.product_storage.capacity += overflow # Increase capacity by overflow amount
                self.product_storage.current_storage[output_type] += overflow # Add overflow to storage

            # Update product volumes (legacy tracking)
            if output_type == OutputType.MDF_FIBREBOARD:
                self.product_volumes["mdf_fibreboard"] += output_amount
            elif output_type == OutputType.PARTICLE_BOARD:
                self.product_volumes["particle_board"] += output_amount
            elif output_type == OutputType.OSB_WAFERBOARD:
                self.product_volumes["osb_waferboard"] += output_amount
            
            # Fulfill demand and track in simulation state
            print(f"[PROCESS DEBUG] About to call fulfill_demand with {output_amount:.2f} m³")
            fulfill_demand(self, output_type, output_amount)
        else:
            print("[PROCESS DEBUG] Output is not final product, skipping fulfillment")
        
        # Track processing costs
        track_processing_costs(self, amount_to_process, transformation)
        
        # Update utilization metrics
        update_utilization_metrics(self, amount_to_process)
    
    def trigger_collection(self):
        """Request waste collection based on current needs"""
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        
        # Use the actual product types that exist in the state
        product_demands = {}
        for product_type in [OutputType.MDF_FIBREBOARD, OutputType.PARTICLE_BOARD, OutputType.OSB_WAFERBOARD]:
            key = product_type.value.lower().replace('_', '_')  # mdf_fibreboard, particle_board, osb_waferboard
            if key in state.target_demands and key in state.total_products:
                unmet_demand = state.target_demands[key] - state.total_products[key]
                if unmet_demand > 0:
                    product_demands[product_type] = unmet_demand
        
        # Update self.demand to include all unmet product demands
        self.demand = sum(product_demands.values())
        
        required_waste = calculate_required_waste(self)
        if required_waste <= 0:
            return 0, 0

        # Get all input types from transformations
        input_waste_types = {key[0] for key in self.transformations.keys()}
        
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
            # Construction and wood materials
            WasteType.CONSTRUCTION_WOOD_17_02_01: (0.98, 0.90),   # High quality wood
            WasteType.WOODEN_PACKAGING_15_01_03: (0.88, 0.95),     # Good for recycling
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (0.95, 0.50),  # Great for compression molding
            
            # Processing materials
            WasteType.BARK_WASTE_03_01_01: (0.85, 0.70),          # Good for boards
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: (0.88, 0.60),  # General recycling
            WasteType.PAPER_PACKAGING_15_01_01: (0.82, 0.65),      # Paper recycling
        }

        # Initialize empty transformations dictionary
        transformations = {}

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            # Construction wood waste (17 02 01) - Primary reuse pathways
            WasteType.CONSTRUCTION_WOOD_17_02_01: [
                OutputType.PARTICLE_BOARD,    # Downcycling pathway
            ],
            
            # Sawdust, shavings, cuttings (03 01 05) - Primary particleboard feedstock
            WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: [
                OutputType.PARTICLE_BOARD,    # Primary pathway - supported by research
                OutputType.MDF_FIBREBOARD,    # Secondary pathway
            ],
            
            # Wooden packaging waste (15 01 03) - Cascading use
            WasteType.WOODEN_PACKAGING_15_01_03: [
                OutputType.PARTICLE_BOARD,    # Recycling pathway
            ],
            
            # Bark waste (03 01 01) - Limited applications
            WasteType.BARK_WASTE_03_01_01: [
                OutputType.MDF_FIBREBOARD,    # Can incorporate bark content
                OutputType.PARTICLE_BOARD,    # Lower percentage incorporation
            ],
            
            # Non-hazardous wood (20 01 38) - Municipal waste stream
            WasteType.NON_HAZARDOUS_WOOD_20_01_38: [
                OutputType.PARTICLE_BOARD,    # Primary recycling pathway
                OutputType.MDF_FIBREBOARD,    # Secondary pathway
            ],
            
            # Paper packaging (15 01 01) - Paper cycle
            WasteType.PAPER_PACKAGING_15_01_01: [
                OutputType.MDF_FIBREBOARD,    # Can incorporate recycled paper
            ],
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
