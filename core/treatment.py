from typing import Dict, Optional
from models.data_classes import WasteTransformation, OperationalEntity
from models.enums import RegionType, WasteType, EntityStatus
from models.state import SimulationState
from optimization.stochastic import UncertaintySet
from monitoring.data_collector import DataCollector
from core.collection_coordinator import CollectionCoordinator
import numpy as np

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

        self.waste_storage = {waste_type: 0.0 for waste_type in WasteType}
        self.processed_volumes = {waste_type: 0.0 for waste_type in WasteType}

        # Capacity management state
        self.last_capacity_check = env.now
        self.capacity_check_interval = 1.0  # Check every time unit

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
            current_time = self.env.now
            
            # Check for failures if uncertainty set is available
            if self.uncertainty_set and hasattr(self.uncertainty_set, 'treatment_failure'):
                self.check_failure(current_time, self.uncertainty_set.treatment_failure.probability)
            
            # Skip processing if failed
            if self.status == EntityStatus.FAILED:
                print(f"{current_time}: Treatment operator {self.name} is currently failed, skipping processing")
                yield self.env.timeout(self.processing_time)
                continue
                
            # Check for recovery
            if (self.status == EntityStatus.FAILED and 
                current_time >= self.recovery_time):
                print(f"{current_time}: Treatment operator {self.name} has recovered from failure")
                self.status = EntityStatus.OPERATIONAL
                self.failure_time = None
                self.recovery_time = None

            # Get current demands and sort transformations by priority
            state = SimulationState.get_instance()
            product_demands = {
                WasteType.WOODEN_FURNITURE: state.target_demands['wooden_furniture'] - state.total_products['wooden_furniture'],
                WasteType.WOODEN_PACKAGING: state.target_demands['wooden_packaging'] - state.total_products['wooden_packaging'],
                WasteType.PAPER_PACKAGING: state.target_demands['paper_packaging'] - state.total_products['paper_packaging']
            }

            # Define a function to get furniture material quality
            def get_furniture_material_quality(waste_type):
                if waste_type == WasteType.CONSTRUCTION_WOOD:
                    return 1.0
                elif waste_type == WasteType.WOOD_CUTTINGS:
                    return 0.9
                else:
                    return 0.8

            # Sort transformations by demand priority and furniture preference
            sorted_transformations = sorted(
                self.transformations.items(),
                key=lambda x, demands=product_demands, get_quality=get_furniture_material_quality: (
                    # Primary sort: furniture with demand gets highest priority
                    (x[0][1] == WasteType.WOODEN_FURNITURE and demands[WasteType.WOODEN_FURNITURE] > 0),
                    # Secondary sort: remaining demand amount
                    demands.get(x[0][1], 0),
                    # Tertiary sort: efficiency for non-furniture, or highest quality for furniture
                    -self._get_transformation_efficiency(x[0][0], x[1]) if x[0][1] != WasteType.WOODEN_FURNITURE
                    else get_quality(x[0][0]),  # Prioritize best materials for furniture
                ),
                reverse=True
            )

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
            WasteType.WOODEN_PACKAGING,
            WasteType.PAPER_PACKAGING,
            WasteType.WOODEN_FURNITURE,
        }
        if input_type in final_products:
            return
            
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        product_demands = {
            WasteType.WOODEN_FURNITURE: state.target_demands['wooden_furniture'] - state.total_products['wooden_furniture'],
            WasteType.WOODEN_PACKAGING: state.target_demands['wooden_packaging'] - state.total_products['wooden_packaging'],
            WasteType.PAPER_PACKAGING: state.target_demands['paper_packaging'] - state.total_products['paper_packaging']
        }

        # Check if this is a furniture-capable input and handle material reservation
        furniture_materials = {WasteType.CONSTRUCTION_WOOD, WasteType.WOOD_CUTTINGS, WasteType.WASTE_WOODEN_PACKAGING}
        furniture_demand = product_demands[WasteType.WOODEN_FURNITURE]
        
        if input_type in furniture_materials and furniture_demand > 0:
            # Calculate material reservation
            reserved_amount = self.waste_storage[input_type] * 0.4  # Reserve 40% for furniture
            
            if output_type != WasteType.WOODEN_FURNITURE:
                # For non-furniture outputs, only use unreserved portion
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
        # Get current unmet demand for this specific product type
        state = SimulationState.get_instance()
        product_type = output_type.value.lower()
        unmet_demand = state.target_demands[product_type] - state.total_products[product_type]
        
        # Use the actual unmet demand instead of self.demand
        fulfilled_amount = min(output_amount, unmet_demand)
        if fulfilled_amount > 0:
            self.waste_storage[output_type] -= fulfilled_amount
            self.demand -= fulfilled_amount

            # Report production to simulation state
            state.track_product_production(product_type, fulfilled_amount)

            print(
                f"{self.env.now}: Fulfilled {fulfilled_amount:.12f} m³ of {output_type.value} demand (Total: {state.total_products[product_type]:.2f})"
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
        # Get current demands from simulation state
        state = SimulationState.get_instance()
        product_demands = {
            WasteType.WOODEN_FURNITURE: state.target_demands['wooden_furniture'] - state.total_products['wooden_furniture'],
            WasteType.WOODEN_PACKAGING: state.target_demands['wooden_packaging'] - state.total_products['wooden_packaging'],
            WasteType.PAPER_PACKAGING: state.target_demands['paper_packaging'] - state.total_products['paper_packaging']
        }
        
        # Update self.demand to include all unmet product demands
        self.demand = sum(product_demands.values())
        
        required_waste = self._calculate_required_waste()
        if required_waste <= 0:
            return 0, 0

        # Get input waste types from transformations, prioritizing furniture materials
        input_waste_types = set()
        if product_demands[WasteType.WOODEN_FURNITURE] > 0:
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
            self.data_collector.track_overflow("treatment", overflow_amount)
            
        return actually_stored, collection_result.total_collected

    MIN_REQUIRED_WASTE = 0.01  # Minimum waste volume to request

    def _calculate_required_waste(self):
        """Calculate how much waste needs to be collected"""
        if self.demand < self.MIN_REQUIRED_WASTE:
            return 0.0
            
        available_storage = self.storage_capacity - self.current_storage
        if available_storage <= 0:
            return 0.0
            
        # Calculate required waste considering conversion rate
        required_waste = self.demand / self.conversion_rate
        
        # Ensure we don't request too little
        if required_waste < self.MIN_REQUIRED_WASTE:
            return 0.0
            
        # Limit by available storage with buffer
        return min(required_waste, available_storage * 0.8)

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
                key = (input_type, WasteType.WOODEN_FURNITURE)
                transformations[key] = WasteTransformation(
                    input_type=input_type,
                    output_type=WasteType.WOODEN_FURNITURE,
                    conversion_efficiency=efficiency * 1.1,  # Boost efficiency for furniture
                    energy_required=energy,
                )

        # Define transformation paths (raw materials to final products only)
        default_output_mapping = {
            # Primary furniture production - allow all suitable materials
            WasteType.CONSTRUCTION_WOOD: [WasteType.WOODEN_FURNITURE, WasteType.WOODEN_PACKAGING],
            WasteType.WOOD_CUTTINGS: [WasteType.WOODEN_FURNITURE, WasteType.WOODEN_PACKAGING],
            WasteType.WASTE_WOODEN_PACKAGING: [WasteType.WOODEN_FURNITURE, WasteType.WOODEN_PACKAGING],
            WasteType.SAWDUST: [WasteType.WOODEN_PACKAGING],
            
            # Paper production paths
            WasteType.BARK_WASTE: [WasteType.PAPER_PACKAGING],
            WasteType.MIXED_WOOD: [WasteType.PAPER_PACKAGING],
            WasteType.WASTE_PAPER_PACKAGING: [WasteType.PAPER_PACKAGING],
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
