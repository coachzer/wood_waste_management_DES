from models.enums import WasteType
from models.state import SimulationState
import numpy as np


class CollectorCompany:
    """A company that collects waste from generators"""

    def __init__(
        self,
        env,
        name,
        collection_capacity,
        collection_frequency,
        transport_cost,
        environmental_impact,
        efficiency,
        availability=True,
        strategy="competitive",
        region=None,
    ):
        self.env = env
        self.name = name
        self.collection_capacity = collection_capacity
        self.collection_frequency = collection_frequency
        self.transport_cost = transport_cost
        self.environmental_impact = environmental_impact
        self.efficiency = efficiency
        self.availability = availability
        self.strategy = strategy
        self.region = region

        # Initialize waste tracking
        self.collected_waste = {waste_type: 0.0 for waste_type in WasteType}

        # Initialize RNG for collection adjustments
        self.rng = np.random.default_rng(42)  # For reproducibility

        # Start collection process
        self.process = env.process(self.collect_waste())

    def collect_from_generator(self, generator):
        """Collect waste from a generator, handling multiple waste types"""
        total_collected = 0
        remaining_capacity = self.collection_capacity * self.efficiency

        # Pre-filter active waste streams
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0
        }

        for waste_type, waste_stream in active_streams.items():
            collectable_amount = min(waste_stream.volume, remaining_capacity)

            if collectable_amount > 0:
                # Update generator's waste stream
                waste_stream.volume -= collectable_amount
                generator.current_storage -= collectable_amount

                # Update collector's tracking
                self.collected_waste[waste_type] += collectable_amount
                remaining_capacity -= collectable_amount
                total_collected += collectable_amount

                print(
                    f"{self.env.now}: {self.name} collected {collectable_amount:.2f} m³ of {waste_type.value} from {generator.name}"
                )

        if total_collected > 0:
            generator.mark_collected()
            return self.transport_cost + (0.1 * total_collected)
        return 0

    def collect_with_collaboration(self, generator, other_collectors):
        """Collaborative collection handling multiple waste types"""
        remaining_capacity = {
            collector.name: collector.collection_capacity * collector.efficiency
            for collector in [self] + other_collectors
        }

        # Pre-filter active waste streams
        active_streams = {
            waste_type: stream
            for waste_type, stream in generator.waste_streams.items()
            if stream.volume > 0
        }

        for waste_type, waste_stream in active_streams.items():
            remaining_volume = waste_stream.volume

            # Try collection with other collectors first
            for collector in other_collectors:
                if remaining_volume <= 0 or remaining_capacity[collector.name] <= 0:
                    continue

                collectable_amount = min(
                    remaining_volume, remaining_capacity[collector.name]
                )

                if collectable_amount > 0:
                    # Update generator
                    waste_stream.volume -= collectable_amount
                    generator.current_storage -= collectable_amount

                    # Update collector
                    collector.collected_waste[waste_type] += collectable_amount
                    remaining_capacity[collector.name] -= collectable_amount
                    remaining_volume -= collectable_amount

                    print(
                        f"{self.env.now}: {collector.name} collaboratively collected {collectable_amount:.2f} m³ of {waste_type.value}"
                    )

            # Process with this collector if there's remaining waste
            if remaining_volume > 0 and remaining_capacity[self.name] > 0:
                collectable_amount = min(
                    remaining_volume, remaining_capacity[self.name]
                )

                if collectable_amount > 0:
                    # Update generator
                    waste_stream.volume -= collectable_amount
                    generator.current_storage -= collectable_amount

                    # Update collector
                    self.collected_waste[waste_type] += collectable_amount
                    remaining_capacity[self.name] -= collectable_amount

                    print(
                        f"{self.env.now}: {self.name} collected remaining {collectable_amount:.2f} m³ of {waste_type.value}"
                    )

    def collect_waste_for_demand(self, required_amount):
        """Collect waste based on treatment plant demand with storage-based adjustments"""
        collected_amounts = {waste_type: 0.0 for waste_type in WasteType}
        total_collected = 0
        state = SimulationState.get_instance()

        # Get storage levels from generators to adjust collection amount
        generators_storage = [
            (g, g.current_storage / g.storage_capacity)
            for g in state.generators
            if g.region == self.region and g.current_storage > 0
        ]

        # Adjust required amount based on average storage levels
        if generators_storage:
            avg_storage = sum(ratio for _, ratio in generators_storage) / len(
                generators_storage
            )
            if avg_storage < 0.3:
                required_amount = required_amount * self.rng.uniform(
                    1.0, 1.2
                )  # Increase collection
            elif avg_storage > 0.7:
                required_amount = required_amount * self.rng.uniform(
                    0.6, 0.8
                )  # Reduce collection

        # Sort generators by storage level (prioritize those with higher storage)
        generators_storage.sort(key=lambda x: x[1], reverse=True)
        eligible_generators = [g for g, _ in generators_storage]

        print(f"Eligible generators: {[g.name for g in eligible_generators]}")

        for generator in eligible_generators:
            # Pre-filter active waste streams that we can collect
            active_streams = {
                waste_type: stream
                for waste_type, stream in generator.waste_streams.items()
                if stream.volume > 0 and total_collected < required_amount
            }

            for waste_type, stream in active_streams.items():
                collectable_amount = min(
                    stream.volume,
                    required_amount - total_collected,
                    self.collection_capacity * self.efficiency,
                )

                if collectable_amount > 0:
                    # Update generator
                    stream.volume -= collectable_amount
                    generator.current_storage -= collectable_amount

                    # Update tracking
                    collected_amounts[waste_type] += collectable_amount
                    total_collected += collectable_amount

                    print(
                        f"{self.env.now}: {self.name} collected {collectable_amount:.2f} m³ of {waste_type.value} from {generator.name}"
                    )

                if total_collected >= required_amount:
                    print(f"{self.name} collected enough waste for demand")
                    break

            if total_collected >= required_amount:
                break

        return collected_amounts

    def get_collection_summary(self):
        """Get summary of all collected waste by type"""
        capacity_with_efficiency = self.collection_capacity * self.efficiency
        return {
            waste_type: {
                "total_collected": amount,
                "collection_capacity_utilization": amount / capacity_with_efficiency,
            }
            for waste_type, amount in self.collected_waste.items()
            if amount > 0
        }

    def _get_prioritized_generators(self):
        """Get generators sorted by priority and filtered by region"""
        state = SimulationState.get_instance()
        regional_generators = [
            g
            for g in state.generators
            if g.current_storage > 0 and g.region == self.region
        ]

        if not regional_generators:
            regional_generators = [g for g in state.generators if g.current_storage > 0]

        regional_generators.sort(key=lambda x: x.priority_level, reverse=True)
        return regional_generators

    def _handle_competitive_collection(self, prioritized_generators):
        """Handle competitive collection strategy"""
        if prioritized_generators and self.availability:
            return self.collect_from_generator(prioritized_generators[0])
        return 0

    def _handle_collaborative_collection(self, prioritized_generators):
        """Handle collaborative collection strategy"""
        if not self.availability:
            return

        state = SimulationState.get_instance()
        other_collectors = [
            c
            for c in state.collectors
            if c != self and c.availability and c.region == self.region
        ]

        total_collection_cost = 0
        for generator in prioritized_generators:
            if generator.current_storage <= 0:
                continue
            self.collect_with_collaboration(generator, other_collectors)
            total_collection_cost += self.transport_cost
        return total_collection_cost

    def collect_waste(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            # Update collection parameters based on optimization
            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            yield self.env.timeout(self.collection_frequency)

            if not self.availability:
                continue

            prioritized_generators = self._get_prioritized_generators()

            collection_cost = 0
            if self.strategy == "competitive":
                collection_cost = self._handle_competitive_collection(
                    prioritized_generators
                )
            elif self.strategy == "collaborative":
                collection_cost = self._handle_collaborative_collection(
                    prioritized_generators
                )

            if collection_cost > 0:
                print(
                    f"{self.env.now}: {self.name} collection operation cost: {collection_cost:.2f}"
                )
