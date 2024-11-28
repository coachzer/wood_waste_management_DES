from models.enums import WasteType
from models.state import SimulationState


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

        self.collected_waste = {waste_type: 0.0 for waste_type in WasteType}
        self.process = env.process(self.collect_waste())

    def collect_from_generator(self, generator):
        """Collect waste from a generator, handling multiple waste types"""
        total_collected = 0
        collection_details = {}
        remaining_capacity = self.collection_capacity * self.efficiency

        # Collect from each waste stream based on priority/availability
        for waste_type, waste_stream in generator.waste_streams.items():
            if waste_stream.volume > 0 and remaining_capacity > 0:
                collectable_amount = min(waste_stream.volume, remaining_capacity)

                if collectable_amount > 0:
                    # Update generator's waste stream
                    generator.waste_streams[waste_type].volume -= collectable_amount
                    generator.current_storage -= collectable_amount

                    # Update collector's tracking
                    self.collected_waste[waste_type] += collectable_amount
                    remaining_capacity -= collectable_amount
                    total_collected += collectable_amount
                    collection_details[waste_type] = collectable_amount

        if total_collected > 0:
            generator.mark_collected()
            collection_cost = self.transport_cost + (0.1 * total_collected)

            # Print detailed collection report
            print(
                f"\n{self.env.now}: {self.name} (Region: {self.region}) collection report:"
            )
            for waste_type, amount in collection_details.items():
                print(f"- Collected {amount:.2f} m³ of {waste_type.value}")
            print(f"Total cost: {collection_cost:.2f}")
            print(
                f"{generator.name} remaining storage: {generator.current_storage:.2f}/{generator.storage_capacity}"
            )

    def collect_with_collaboration(self, generator, other_collectors):
        """Collaborative collection handling multiple waste types"""
        collection_details = {
            collector.name: {} for collector in [self] + other_collectors
        }
        remaining_capacity = {
            collector.name: collector.collection_capacity * collector.efficiency
            for collector in [self] + other_collectors
        }

        # Process each waste type
        for waste_type, waste_stream in generator.waste_streams.items():
            remaining_volume = waste_stream.volume

            if remaining_volume > 0:
                # Try collection with other collectors first
                for collector in other_collectors:
                    if remaining_volume > 0 and remaining_capacity[collector.name] > 0:
                        collectable_amount = min(
                            remaining_volume, remaining_capacity[collector.name]
                        )

                        if collectable_amount > 0:
                            # Update generator
                            generator.waste_streams[
                                waste_type
                            ].volume -= collectable_amount
                            generator.current_storage -= collectable_amount

                            # Update collector
                            collector.collected_waste[waste_type] += collectable_amount
                            remaining_capacity[collector.name] -= collectable_amount
                            remaining_volume -= collectable_amount

                            # Track details
                            if waste_type not in collection_details[collector.name]:
                                collection_details[collector.name][waste_type] = 0
                            collection_details[collector.name][
                                waste_type
                            ] += collectable_amount

                # Finally collect with this collector if there's remaining waste
                if remaining_volume > 0 and remaining_capacity[self.name] > 0:
                    collectable_amount = min(
                        remaining_volume, remaining_capacity[self.name]
                    )

                    if collectable_amount > 0:
                        # Update generator
                        generator.waste_streams[waste_type].volume -= collectable_amount
                        generator.current_storage -= collectable_amount

                        # Update collector
                        self.collected_waste[waste_type] += collectable_amount
                        remaining_capacity[self.name] -= collectable_amount

                        # Track details
                        if waste_type not in collection_details[self.name]:
                            collection_details[self.name][waste_type] = 0
                        collection_details[self.name][waste_type] += collectable_amount

        # Print collaborative collection report if any waste was collected
        if any(details for details in collection_details.values()):
            print(
                f"\n{self.env.now}: Collaborative collection report for {generator.name}:"
            )
            for collector_name, waste_types in collection_details.items():
                if waste_types:
                    print(f"\n{collector_name} collected:")
                    for waste_type, amount in waste_types.items():
                        print(f"- {amount:.2f} m³ of {waste_type.value}")
            print(
                f"Generator remaining storage: {generator.current_storage:.2f}/{generator.storage_capacity}"
            )

    def collect_waste_for_demand(self, required_amount):
        """Collect waste based on treatment plant demand"""
        collected_amounts = {waste_type: 0.0 for waste_type in WasteType}
        total_collected = 0

        state = SimulationState.get_instance()

        for generator in state.generators:
            if generator.region == self.region and generator.current_storage > 0:
                for waste_type, waste_stream in generator.waste_streams.items():
                    if total_collected < required_amount and waste_stream.volume > 0:
                        collectable_amount = min(
                            waste_stream.volume,
                            required_amount - total_collected,
                            self.collection_capacity * self.efficiency,
                        )

                        if collectable_amount > 0:
                            # Update generator
                            generator.waste_streams[
                                waste_type
                            ].volume -= collectable_amount
                            generator.current_storage -= collectable_amount

                            # Update tracking
                            collected_amounts[waste_type] += collectable_amount
                            total_collected += collectable_amount

                            print(
                                f"{self.env.now}: {self.name} collected {collectable_amount:.2f} m³ of {waste_type.value} from {generator.name}"
                            )

                if total_collected >= required_amount:
                    break

        return collected_amounts

    def get_collection_summary(self):
        """Get summary of all collected waste by type"""
        return {
            waste_type: {
                "total_collected": amount,
                "collection_capacity_utilization": amount
                / (self.collection_capacity * self.efficiency),
            }
            for waste_type, amount in self.collected_waste.items()
            if amount > 0
        }

    def _get_prioritized_generators(self):
        state = SimulationState.get_instance()
        regional_generators = [
            g
            for g in state.generators
            if g.current_storage > 0 and g.region == self.region
        ]

        if not regional_generators:
            regional_generators = [g for g in state.generators if g.current_storage > 0]

        return sorted(regional_generators, key=lambda x: x.priority_level, reverse=True)

    def _handle_competitive_collection(self, prioritized_generators):
        if prioritized_generators and self.availability:
            self.collect_from_generator(prioritized_generators[0])

    def _handle_collaborative_collection(self, prioritized_generators):
        state = SimulationState.get_instance()
        for generator in prioritized_generators:
            if generator.current_storage > 0 and self.availability:
                other_collectors = [
                    c
                    for c in state.collectors
                    if c != self and c.availability and c.region == self.region
                ]
                self.collect_with_collaboration(generator, other_collectors)

    def collect_waste(self):
        """Periodically collect waste from generators based on strategy"""
        while True:
            # Update collection parameters based on optimization
            self.collection_capacity = max(
                10, self.collection_capacity * self.efficiency
            )
            self.transport_cost = min(100, self.transport_cost * (2 - self.efficiency))

            yield self.env.timeout(self.collection_frequency)
            prioritized_generators = self._get_prioritized_generators()

            if self.strategy == "competitive":
                self._handle_competitive_collection(prioritized_generators)
            elif self.strategy == "collaborative":
                self._handle_collaborative_collection(prioritized_generators)
