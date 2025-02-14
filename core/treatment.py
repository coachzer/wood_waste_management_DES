from typing import Dict, Optional
from models.data_classes import WasteTransformation
from models.enums import WasteType
from models.state import SimulationState
import random


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
    ):
        self.env = env
        self.name = name
        self.processing_capacity = storage_capacity * 0.75
        self.processing_time = processing_time
        self.initial_storage_capacity = storage_capacity
        self.storage_capacity = storage_capacity
        self.energy_consumption = energy_consumption
        self.environmental_impact = environmental_impact
        self.conversion_rate = conversion_rate
        self.operational_costs = operational_costs
        self.region = region
        self.demand = 0

        # Track total products created
        self.total_products_created = 0.0

        # Add tracking for storage utilization history
        self.utilization_history = []
        self.utilization_window = 10  # Track last 10 periods
        self.demand_history = []
        self.production_history = []
        self.high_utilization_threshold = 0.85
        self.low_utilization_threshold = 0.3
        self.max_expansion_multiplier = 2.0  # Maximum 2x initial capacity
        self.min_capacity_multiplier = 0.75  # Minimum 75% of initial capacity

        # Single source of truth for storage
        self.waste_storage = {waste_type: 0.0 for waste_type in WasteType}

        # Track cumulative processed volumes
        self.processed_volumes = {waste_type: 0.0 for waste_type in WasteType}

        # Start the demand-driven processing loop
        self.process = env.process(self.create_demand())
        self.transformations = transformations or self._default_transformations()

    @property
    def current_storage(self) -> float:
        """Calculate current total storage from waste_storage"""
        total = sum(self.waste_storage.values())
        # print("DEBUG - Current storage calculation:")
        # print("Individual storage amounts:")
        # for waste_type, amount in self.waste_storage.items():
        #     if amount > 0:
        #         print(f"- {waste_type.value}: {amount:.2f}")
        # print(f"Total: {total:.2f}")
        return total

    @property
    def storage_utilization(self) -> float:
        """Calculate storage utilization percentage with bounds checking"""
        if self.storage_capacity <= 0:
            print("WARNING: Storage capacity is 0 or negative")
            return 0

        utilization = self.current_storage / self.storage_capacity * 100
        utilization = min(100, max(0, utilization))  # Ensure between 0 and 100

        print("DEBUG - Storage utilization calculation:")
        print(f"Current storage: {self.current_storage:.2f}")
        print(f"Storage capacity: {self.storage_capacity}")
        print(f"Utilization: {utilization:.2f}%")

        return utilization

    def adjust_storage_capacity(self):
        """Dynamically adjust storage capacity based on utilization patterns"""
        current_utilization = (
            self.storage_utilization / 100
        )  # Convert percentage to decimal
        self.utilization_history.append(current_utilization)

        # Keep only recent history
        if len(self.utilization_history) > self.utilization_window:
            self.utilization_history.pop(0)

        # Calculate average utilization over recent periods
        avg_utilization = sum(self.utilization_history) / len(self.utilization_history)

        # Adjust capacity based on sustained utilization patterns
        if avg_utilization > self.high_utilization_threshold:
            # Expand capacity by 20% if consistently near capacity
            new_capacity = self.storage_capacity * 1.2
            # But don't exceed maximum allowed expansion
            max_allowed = self.initial_storage_capacity * self.max_expansion_multiplier
            self.storage_capacity = min(new_capacity, max_allowed)
            print(f"\n{self.env.now}: {self.name} expanding storage capacity:")
            print(f"- Previous capacity: {self.storage_capacity / 1.2:.2f}")
            print(f"- New capacity: {self.storage_capacity:.2f}")
            print(f"- Average utilization: {avg_utilization:.2%}")

        elif avg_utilization < self.low_utilization_threshold:
            # Contract capacity by 10% if consistently underutilized
            new_capacity = self.storage_capacity * 0.9
            # But don't go below minimum allowed capacity
            min_allowed = self.initial_storage_capacity * self.min_capacity_multiplier
            self.storage_capacity = max(new_capacity, min_allowed)
            print(f"\n{self.env.now}: {self.name} reducing storage capacity:")
            print(f"- Previous capacity: {self.storage_capacity / 0.9:.2f}")
            print(f"- New capacity: {self.storage_capacity:.2f}")
            print(f"- Average utilization: {avg_utilization:.2%}")

    def _default_transformations(self) -> Dict[WasteType, WasteTransformation]:
        """Define default transformation pathways for all waste types"""
        return {
            WasteType.SAWDUST: WasteTransformation(
                input_type=WasteType.SAWDUST,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.95,
                energy_required=0.5,
            ),
            WasteType.WOOD_CUTTINGS: WasteTransformation(
                input_type=WasteType.WOOD_CUTTINGS,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.90,
                energy_required=0.8,
            ),
            WasteType.BARK: WasteTransformation(
                input_type=WasteType.BARK,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.85,
                energy_required=0.7,
            ),
            WasteType.CORK: WasteTransformation(
                input_type=WasteType.CORK,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.92,
                energy_required=0.6,
            ),
            WasteType.SOLID_WOOD: WasteTransformation(
                input_type=WasteType.SOLID_WOOD,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.98,
                energy_required=0.9,
            ),
            WasteType.PAPER_PACKAGING: WasteTransformation(
                input_type=WasteType.PAPER_PACKAGING,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.80,
                energy_required=0.4,
            ),
            WasteType.WOOD_PACKAGING: WasteTransformation(
                input_type=WasteType.WOOD_PACKAGING,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=0.88,
                energy_required=0.7,
            ),
            WasteType.MIXED_WOOD: WasteTransformation(
                input_type=WasteType.MIXED_WOOD,
                output_type=WasteType.MIXED_WOOD,
                conversion_efficiency=1.0,
                energy_required=0.3,
            ),
        }

    def create_demand(self):
        """Generate demand based on facility capacity and current storage levels"""
        while True:

            self.adjust_storage_capacity()

            # Evolve parameters over time based on optimization
            if self.current_storage > 0.8 * self.storage_capacity:
                self.processing_capacity *= (
                    1.1  # Increase capacity when storage is high
                )
            elif self.current_storage < 0.2 * self.storage_capacity:
                self.processing_capacity *= 0.9  # Decrease capacity when storage is low

            # Calculate base demand considering processing capacity and storage
            storage_factor = min(
                1.0, self.current_storage / (self.storage_capacity * 0.8)
            )
            capacity_based_demand = self.processing_capacity * self.conversion_rate

            # Adjust demand based on current storage levels
            if storage_factor < 0.3:  # Low storage - increase demand
                demand_multiplier = random.uniform(1.0, 1.2)
            elif storage_factor > 0.7:  # High storage - decrease demand
                demand_multiplier = random.uniform(0.6, 0.8)
            else:  # Normal storage levels
                demand_multiplier = random.uniform(0.8, 1.2)

            # Calculate final demand with some randomness
            self.demand = max(
                10,
                min(
                    capacity_based_demand * demand_multiplier,
                    self.storage_capacity
                    * 0.5,  # Cap demand at 50% of storage capacity
                ),
            )

            self.demand_history.append(self.demand)
            print(f"\n{self.env.now}: {self.name} creating demand:")
            print(f"- Storage factor: {storage_factor:.2f}")
            print(f"- Capacity-based demand: {capacity_based_demand:.2f}")
            print(f"- Demand multiplier: {demand_multiplier:.2f}")
            print(f"- Final demand: {self.demand:.2f} units")
            print(
                f"- Current storage: {self.current_storage:.2f}/{self.storage_capacity}"
            )
            print(f"- Storage utilization: {self.storage_utilization:.2f}%")

            # Trigger collection process
            self.trigger_collection()

            # Dynamic processing time based on storage levels
            if storage_factor > 0.8:  # Very high storage
                processing_time = max(1, self.processing_time * 0.7)  # Process faster
            elif storage_factor < 0.2:  # Very low storage
                processing_time = self.processing_time * 1.3  # Process slower
            else:
                processing_time = self.processing_time

            yield self.env.timeout(processing_time)

    def process_waste_to_product(self) -> float:
        """Process waste into product with gradual processing"""
        total_output = 0.0
        total_energy_used = 0.0

        print(f"\n{self.env.now}: {self.name} processing waste:")

        # Calculate maximum processable amount per cycle
        max_process_per_cycle = min(
            self.processing_capacity,
            self.current_storage * 0.4,  # Process only 40% of current storage per cycle
        )

        if max_process_per_cycle <= 0:
            print("No waste available for processing")
            return 0.0

        # Process a portion of each waste type
        for waste_type, amount in list(self.waste_storage.items()):
            if amount <= 0:
                continue

            transformation = self.transformations.get(waste_type)
            if transformation:
                # Calculate processable amount for this waste type
                waste_fraction = amount / self.current_storage
                processable_amount = min(amount, max_process_per_cycle * waste_fraction)

                # Process the waste
                output = processable_amount * transformation.conversion_efficiency
                energy_used = processable_amount * transformation.energy_required

                # Update storage and processing records
                self.waste_storage[waste_type] -= processable_amount
                self.processed_volumes[waste_type] += processable_amount

                # Accumulate outputs
                total_output += output
                total_energy_used += energy_used

                print(f"- Processed {processable_amount:.2f} m³ of {waste_type.value}")
                print(f"  Output: {output:.2f} m³")
                print(f"  Energy used: {energy_used:.2f} kWh")

        # Update total products created
        self.total_products_created += total_output

        self.production_history.append(total_output)
        print(f"Total output: {total_output:.2f} m³")
        print(f"Total products created to date: {self.total_products_created:.2f} m³")
        print(f"Total energy used: {total_energy_used:.2f} kWh")
        print(f"Remaining storage utilization: {self.storage_utilization:.2f}%")

        return total_output

    def _collect_from_single_generator(self, generator, needed_amount):
        collected = 0
        collected_by_type = {}

        for waste_type, waste_stream in generator.waste_streams.items():
            if waste_stream.volume <= 0:
                continue

            amount = min(waste_stream.volume, needed_amount - collected)
            if amount > 0:
                waste_stream.volume -= amount
                generator.current_storage -= amount
                collected_by_type[waste_type] = amount
                collected += amount

        return collected, collected_by_type

    def _collect_using_collector(self, collector, needed_amount):
        """Debug version of collection process"""
        collected = 0
        collected_amounts = {waste_type: 0.0 for waste_type in WasteType}

        max_collectable = min(
            needed_amount, collector.collection_capacity * collector.efficiency
        )

        # print("\nDEBUG: Collection Details")
        # print(f"Needed amount: {needed_amount:.2f}")
        # print(f"Collector capacity: {collector.collection_capacity}")
        # print(f"Collector efficiency: {collector.efficiency}")
        # print(f"Max collectable: {max_collectable:.2f}")

        state = SimulationState.get_instance()
        for generator in state.generators:
            # Debug generator state
            print(f"\nChecking {generator.name}")
            print(f"Current storage: {generator.current_storage}")
            print("Available waste types:")
            for waste_type, amount in generator.waste_streams.items():
                print(f"- {waste_type.value}: {amount.volume}")

            if generator.current_storage <= 0:
                print("Generator has no waste to collect")
                continue

            # Try collection
            amount, by_type = self._collect_from_single_generator(
                generator, max_collectable - collected
            )

            print(f"Collected from generator: {amount:.2f}")
            print("By waste type:")
            for waste_type, type_amount in by_type.items():
                if type_amount > 0:
                    print(f"- {waste_type.value}: {type_amount:.2f}")
                    collected_amounts[waste_type] += type_amount
            collected += amount

            if collected >= max_collectable:
                print("Reached maximum collection capacity")
                break

        # print("\nTotal collection results:")
        # print(f"Total collected: {collected:.2f}")
        # print("By waste type:")
        # for waste_type, amount in collected_amounts.items():
        #     if amount > 0:
        #         print(f"- {waste_type.value}: {amount:.2f}")

        return collected, collected_amounts

    def _report_results(self, collected, produced):
        print(f"Total collected: {collected:.2f} m³")
        print(f"Total produced: {produced:.2f} m³")

        if produced >= self.demand:
            print(f"{self.name} SATISFIED demand of {self.demand:.2f} units")
        else:
            shortage = self.demand - produced
            print(f"{self.name} FAILED to meet demand. Shortage: {shortage:.2f} units")

    def _add_to_storage(self, collected_amounts: Dict[WasteType, float]) -> float:
        """
        Add collected waste to storage with bounds checking.
        Returns total amount actually stored.
        """
        total_added = 0
        available_space = self.storage_capacity - self.current_storage

        if available_space <= 0:
            return 0

        for waste_type, amount in collected_amounts.items():
            if amount <= 0:
                continue

            # Calculate how much we can actually store
            storable_amount = min(amount, available_space)
            if storable_amount > 0:
                self.waste_storage[waste_type] += storable_amount
                total_added += storable_amount
                available_space -= storable_amount

                print(f"Added {storable_amount:.2f} m³ of {waste_type.value}")
                if available_space <= 0:
                    break

        print(
            f"Storage after addition: {self.current_storage:.2f}/{self.storage_capacity} m³"
        )
        print(f"Storage utilization: {self.storage_utilization:.2f}%")

        return total_added

    def trigger_collection(self):
        """Trigger waste collection based on storage-aware demand"""
        available_storage = self.storage_capacity - self.current_storage
        required_waste = min(
            self.demand / self.conversion_rate, available_storage * 0.8
        )

        # print(f"\n{self.env.now}: {self.name} triggering collection")
        # print(f"Available storage: {available_storage:.2f} m³")
        # print(f"Required waste: {required_waste:.2f} m³")
        # print(f"Current storage before collection: {self.current_storage:.2f} m³")
        # print(f"Current storage utilization: {self.storage_utilization:.2f}%")

        state = SimulationState.get_instance()
        total_collected = 0
        total_by_type = {waste_type: 0.0 for waste_type in WasteType}

        # Collect from available collectors
        for collector in state.collectors:
            if collector.region != self.region and not collector.availability:
                print(f"Collector {collector.name} not available or in wrong region")
                continue

            remaining_need = required_waste - total_collected
            if remaining_need <= 0:
                break

            print(f"\nTrying collection with {collector.name}")
            collected, by_type = self._collect_using_collector(
                collector, remaining_need
            )

            for waste_type, amount in by_type.items():
                total_by_type[waste_type] += amount
            total_collected += collected

        print(f"\nTotal collected across all collectors: {total_collected:.2f} m³")

        # Add to storage and track how much was actually stored
        actually_stored = self._add_to_storage(total_by_type)
        if actually_stored < total_collected:
            print(
                f"Warning: Could only store {actually_stored:.2f} m³ out of {total_collected:.2f} m³ collected"
            )
            print(f"Storage efficiency: {(actually_stored/total_collected*100):.1f}%")

        # Process waste
        produced_amount = self.process_waste_to_product()

        # Report comprehensive results
        collection_efficiency = (
            (total_collected / required_waste * 100) if required_waste > 0 else 0
        )
        storage_efficiency = (
            (actually_stored / total_collected * 100) if total_collected > 0 else 0
        )
        demand_satisfaction = (
            (produced_amount / self.demand * 100) if self.demand > 0 else 0
        )

        # print("\nOperation Summary:")
        # print(f"- Collection efficiency: {collection_efficiency:.1f}%")
        # print(f"- Storage efficiency: {storage_efficiency:.1f}%")
        # print(f"- Demand satisfaction: {demand_satisfaction:.1f}%")
        # print(f"- Demand satisfaction: {demand_satisfaction:.1f}%")

        if produced_amount >= self.demand:
            print(
                f"{self.name} met demand of {self.demand:.2f} units. Produced: {produced_amount:.2f} units"
            )
        else:
            shortage = self.demand - produced_amount
            print(f"{self.name} failed to meet demand. Shortage: {shortage:.2f} units")
