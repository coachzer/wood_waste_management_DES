from typing import Dict, Optional
from models.data_classes import WasteTransformation
from models.enums import WasteType
from models.state import SimulationState
from optimization.stochastic import UncertaintySet
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
        region,
        transformations: Optional[Dict[WasteType, WasteTransformation]] = None,
        uncertainty_set: Optional[UncertaintySet] = None,
    ):
        # Track utilization history for dynamic capacity management
        self.utilization_history = []
        self.utilization_window = 10  # Rolling window size
        self.env = env
        self.name = name
        self.processing_capacity = (
            storage_capacity * 0.1
        )  # Start with 10% of storage capacity
        self.processing_time = processing_time
        self.initial_storage_capacity = storage_capacity
        self.storage_capacity = storage_capacity
        self.energy_consumption = energy_consumption
        self.environmental_impact = environmental_impact
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs
        self.region = region
        self.demand = 0

        self.initial_storage_capacity = storage_capacity
        self.storage_capacity = storage_capacity
        self.min_capacity = storage_capacity * 0.75  # Minimum 75% of initial
        self.max_capacity = storage_capacity * 2.0  # Maximum 200% of initial

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

        return {
            waste_type: WasteTransformation(
                input_type=waste_type,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=efficiency,
                energy_required=energy,
            )
            for waste_type, (efficiency, energy) in base_transformations.items()
        }

    def collect_and_process(self):
        """Main collection and processing cycle"""
        # Calculate storage-based demand
        storage_factor = min(1.0, self.current_storage / (self.storage_capacity * 0.8))
        base_demand = self.processing_capacity * self.conversion_rate

        # Use stochastic market demand if available
        if self.uncertainty_set:
            waste_type = next(iter(self.waste_storage.keys()))  # Get first waste type
            mean, std = self.uncertainty_set.market_demand.get(waste_type, (1.0, 0.2))
            demand_factor = np.clip(self.rng.normal(mean, std), 0.6, 1.4)
            self.demand = base_demand * demand_factor
            print(f"Market demand factor: {demand_factor:.2f}")
        else:
            # Fallback to deterministic demand adjustments
            if storage_factor < 0.3:
                self.demand = base_demand * self.rng.uniform(1.0, 1.2)  # High demand
            elif storage_factor > 0.7:
                self.demand = base_demand * self.rng.uniform(0.6, 0.8)  # Low demand
            else:
                self.demand = base_demand * self.rng.uniform(0.8, 1.2)  # Normal demand

        # Cap demand at 50% of storage capacity
        self.demand = min(self.demand, self.storage_capacity * 0.5)
        self.demand = max(10, self.demand)  # Ensure minimum demand

        print(f"\n{self.env.now}: {self.name} operating cycle:")
        print(
            f"Current storage: {self.current_storage:.2f}/{self.storage_capacity:.2f} m³"
        )
        print(f"Demand: {self.demand:.2f} m³")

        # Collect waste if needed
        if self.current_storage < self.storage_capacity * 0.8:
            actually_stored, total_collected = self.trigger_collection()
            if actually_stored > 0:
                print(f"Collected and stored: {actually_stored:.2f} m³")
                print(f"Total collected: {total_collected:.2f} m³")

        # Process stored waste with equipment failure consideration
        if self.current_storage > 0:
            # Check for equipment failure if uncertainty set is available
            equipment_operational = True
            if self.uncertainty_set:
                equipment_operational = (
                    self.rng.random() > self.uncertainty_set.equipment_failure_rate
                )
                if not equipment_operational:
                    print(f"{self.env.now}: Equipment failure at {self.name}")
                    return False

            processed = self.process_waste_to_product()
            if processed > 0:
                print(f"Products created: {processed:.2f} m³")
                return True

        return False

    def check_overflow_risk(self) -> bool:
        """Early Warning System for overflow risk"""
        if len(self.utilization_history) <= self.utilization_window:
            return False

        # Analyze recent utilization trend
        recent_utilization = self.utilization_history[-self.utilization_window :]
        trend = np.polyfit(range(len(recent_utilization)), recent_utilization, 1)[0]
        current_util = recent_utilization[-1]

        # High risk if:
        # 1. Current utilization is high (>80%)
        # 2. Trend is positive (increasing storage)
        # 3. Rate of increase is significant
        return current_util > 80 and trend > 0.5

    def handle_overflow_risk(self):
        """Implement overflow prevention measures"""
        if self.check_overflow_risk():
            print(f"\n{self.env.now}: OVERFLOW RISK DETECTED at {self.name}")
            print(f"Current utilization: {self.storage_utilization:.2f}%")

            # Emergency Protocol 1: Rapid processing activation
            self.processing_capacity *= 1.5
            print("Emergency Protocol: Increased processing capacity by 50%")

            # Emergency Protocol 2: Collection suspension
            # (implemented via very low demand)
            self.demand *= 0.2
            print("Emergency Protocol: Reduced collection demand by 80%")

            return True
        return False

    def manage_storage_capacity(self):
        """Dynamic capacity management based on utilization"""
        if self.env.now - self.last_capacity_check < self.capacity_check_interval:
            return

        # First check for overflow risk
        if self.handle_overflow_risk():
            self.last_capacity_check = self.env.now
            return

        # Regular capacity management
        if len(self.utilization_history) > self.utilization_window:
            recent_utilization = np.mean(
                self.utilization_history[-self.utilization_window :]
            )

            # Expand capacity if utilization > 85%
            if recent_utilization > 85:
                new_capacity = min(self.max_capacity, self.storage_capacity * 1.1)
                if new_capacity > self.storage_capacity:
                    print(
                        f"{self.env.now}: Expanding storage capacity from {self.storage_capacity:.2f} to {new_capacity:.2f}"
                    )
                    self.storage_capacity = new_capacity

            # Contract capacity if utilization < 30%
            elif recent_utilization < 30:
                new_capacity = max(self.min_capacity, self.storage_capacity * 0.9)
                if new_capacity < self.storage_capacity:
                    print(
                        f"{self.env.now}: Contracting storage capacity from {self.storage_capacity:.2f} to {new_capacity:.2f}"
                    )
                    self.storage_capacity = new_capacity

        # Update check time
        self.last_capacity_check = self.env.now

        # Record current utilization
        self.utilization_history.append(self.storage_utilization)

    def run_facility(self):
        """Main facility operation loop"""
        while True:
            # Check and adjust storage capacity
            self.manage_storage_capacity()

            # Adjust operations based on inventory state
            state_message = self.adjust_operations_for_state()
            print(f"\n{self.env.now}: Inventory State - {state_message}")

            success = self.collect_and_process()

            # Adjust processing time based on success and stochastic factors
            base_adjustment = 1.0
            if self.uncertainty_set:
                mean, std = self.uncertainty_set.transportation_time
                base_adjustment = np.clip(self.rng.normal(mean, std), 0.5, 2.0)

            if success and self.current_storage > 0.8 * self.storage_capacity:
                processing_time = max(
                    1, self.processing_time * 0.7 * base_adjustment
                )  # Process faster when storage is high
            elif not success or self.current_storage < 0.2 * self.storage_capacity:
                processing_time = (
                    self.processing_time * 1.3 * base_adjustment
                )  # Process slower when storage is low
            else:
                processing_time = self.processing_time * base_adjustment

            yield self.env.timeout(processing_time)

    def process_waste_to_product(self) -> float:
        """Process waste into products"""
        if self.current_storage <= 0:
            return 0.0

        total_output = 0.0
        total_energy_used = 0.0

        # Calculate maximum processable amount
        max_process_per_cycle = min(
            self.processing_capacity,
            self.current_storage * 0.4,  # Process up to 40% of current storage
        )

        # Pre-filter active waste streams
        active_storage = {wt: amt for wt, amt in self.waste_storage.items() if amt > 0}

        print(f"\n{self.env.now}: {self.name} processing waste:")
        for waste_type, amount in active_storage.items():
            transformation = self.transformations.get(waste_type)
            if not transformation:
                continue

            # Determine processing state and adjust rate
            storage_ratio = self.current_storage / self.storage_capacity
            if storage_ratio > 0.8:  # High-Volume Processing
                processing_multiplier = 1.3  # 30% faster
                energy_multiplier = 1.3  # Higher energy consumption
            elif storage_ratio < 0.2:  # Low-Volume Processing
                processing_multiplier = 0.7  # 30% slower
                energy_multiplier = 0.7  # Energy conservation
            else:  # Standard Processing
                processing_multiplier = 1.0  # Normal rate
                energy_multiplier = 1.0  # Standard energy usage

            # Calculate processable amount for this waste type with state-based adjustment
            waste_fraction = amount / self.current_storage
            processable_amount = min(
                amount, max_process_per_cycle * waste_fraction * processing_multiplier
            )

            if processable_amount > 0:
                # Apply stochastic conversion rate if available
                if self.uncertainty_set:
                    mean, std = self.uncertainty_set.treatment_conversion.get(
                        waste_type, (transformation.conversion_efficiency, 0.05)
                    )
                    conversion_rate = np.clip(self.rng.normal(mean, std), 0.5, 1.0)
                    output = processable_amount * conversion_rate
                else:
                    output = processable_amount * transformation.conversion_efficiency

                energy_used = (
                    processable_amount
                    * transformation.energy_required
                    * energy_multiplier
                )

                # Update storage and records
                self.waste_storage[waste_type] -= processable_amount
                self.processed_volumes[waste_type] += processable_amount
                total_output += output
                total_energy_used += energy_used

                print(f"- Processed {processable_amount:.2f} m³ of {waste_type.value}")
                print(f"  Output: {output:.2f} m³")
                print(f"  Energy used: {energy_used:.2f} kWh")

        if total_output > 0:
            self.total_products_created += total_output
            self.production_history.append(total_output)

            print(f"Total output: {total_output:.2f} m³")
            print(
                f"Total products created to date: {self.total_products_created:.2f} m³"
            )
            print(f"Total energy used: {total_energy_used:.2f} kWh")
            print(f"Storage utilization: {self.storage_utilization:.2f}%")

        return total_output

    def trigger_collection(self):
        """Request waste collection based on current needs"""
        available_storage = self.storage_capacity - self.current_storage
        required_waste = min(
            self.demand / self.conversion_rate, available_storage * 0.8
        )

        if required_waste <= 0:
            return 0, 0

        state = SimulationState.get_instance()
        total_collected = 0
        total_by_type = {waste_type: 0.0 for waste_type in WasteType}

        print(
            f"\n{self.env.now}: {self.name} requesting collection of {required_waste:.2f} m³"
        )

        # Get available collectors in the region
        available_collectors = [
            c for c in state.collectors if c.region == self.region and c.availability
        ]

        for collector in available_collectors:
            remaining_need = required_waste - total_collected
            if remaining_need <= 0:
                break

            # Request collection
            collected_amounts = collector.collect_waste_for_demand(remaining_need)

            # Process collected amounts
            for waste_type, amount in collected_amounts.items():
                if amount > 0:
                    total_by_type[waste_type] += amount
                    total_collected += amount
                    print(
                        f"Collected {amount:.2f} m³ of {waste_type.value} from {collector.name}"
                    )

        if total_collected > 0:
            print(f"Total waste collected: {total_collected:.2f} m³")
            # Add to storage
            actually_stored = self._add_to_storage(total_by_type)
            if actually_stored < total_collected:
                print(
                    f"Could only store {actually_stored:.2f} m³ due to capacity constraints"
                )
            return actually_stored, total_collected

        return 0, 0

    def _add_to_storage(self, waste_amounts: Dict[WasteType, float]) -> float:
        """Add collected waste to storage"""
        available_space = self.storage_capacity - self.current_storage
        if available_space <= 0:
            return 0

        total_added = 0
        for waste_type, amount in waste_amounts.items():
            if amount <= 0:
                continue

            storable_amount = min(amount, available_space)
            if storable_amount > 0:
                self.waste_storage[waste_type] += storable_amount
                total_added += storable_amount
                available_space -= storable_amount
                print(
                    f"Added {storable_amount:.2f} m³ of {waste_type.value} to storage"
                )

            if available_space <= 0:
                break

        return total_added

    @property
    def current_storage(self) -> float:
        """Calculate current total storage"""
        return sum(self.waste_storage.values())

    def get_inventory_state(self) -> str:
        """Determine current inventory state based on storage utilization"""
        utilization = self.storage_utilization

        if 40 <= utilization <= 60:
            return "OPTIMAL"
        elif 20 <= utilization < 40 or 60 < utilization <= 80:
            return "BUFFER"
        else:
            return "CRITICAL"

    def adjust_operations_for_state(self):
        """Adjust operations based on inventory state"""
        state = self.get_inventory_state()
        utilization = self.storage_utilization

        if state == "OPTIMAL":
            # Standard operations, no adjustments needed
            self.processing_capacity = self.initial_storage_capacity * 0.1
            return "Standard operations in optimal zone"

        elif state == "BUFFER":
            # Adjust operations based on which buffer zone we're in
            if utilization < 40:  # Lower buffer
                self.processing_capacity *= 0.9  # Slightly reduce processing
                return "Adjusted operations for lower buffer zone"
            else:  # Upper buffer
                self.processing_capacity *= 1.1  # Slightly increase processing
                return "Adjusted operations for upper buffer zone"

        else:  # CRITICAL
            if utilization < 20:  # Critical low
                self.processing_capacity *= 0.7  # Significantly reduce processing
                return "Emergency measures for critically low storage"
            else:  # Critical high
                self.processing_capacity *= 1.3  # Significantly increase processing
                return "Emergency measures for critically high storage"

    @property
    def storage_utilization(self) -> float:
        """Calculate storage utilization percentage"""
        if self.storage_capacity <= 0:
            return 0
        return min(100, max(0, (self.current_storage / self.storage_capacity * 100)))
