import numpy as np
from typing import Dict
from models.enums import WasteType
from models.data_classes import WasteStream


class WasteGenerator:
    def __init__(
        self,
        env,
        name,
        waste_streams: Dict[WasteType, float],
        generation_frequency,
        storage_capacity,
        priority_level,
        randomness,
        std_dev,
        environmental_impact,
        region,
    ):
        self.env = env
        self.name = name
        self.waste_streams = {
            waste_type: WasteStream(
                waste_type=waste_type,
                volume=0,
                density=self._get_default_density(waste_type),
                moisture_content=self._get_default_moisture(waste_type),
            )
            for waste_type in waste_streams.keys()
        }
        self.waste_generation_rates = waste_streams
        self.generation_frequency = generation_frequency
        self.storage_capacity = storage_capacity
        self.priority_level = priority_level
        self.randomness = randomness
        self.std_dev = std_dev
        self.environmental_impact = environmental_impact
        self.current_storage = 0
        self.last_collected = env.now
        self.region = region

        # Track total generation (cumulative)
        self.total_generated = {waste_type: 0.0 for waste_type in waste_streams.keys()}

        # Track historical generation with timestamps
        self.generation_history = {
            waste_type: [] for waste_type in waste_streams.keys()
        }

        # Start waste generation process
        self.action = env.process(self.generate_waste())

    def generate_waste(self):
        while True:
            # Print debug info before generation
            # print(f"\nDebug: {self.name} generating waste at time {self.env.now}")
            # print(f"Current storage before generation: {self.current_storage}")

            for waste_type, base_rate in self.waste_generation_rates.items():
                # Apply more realistic waste generation patterns
                if self.randomness:
                    rng = np.random.default_rng()
                    # Base seasonal variation (sine wave with period = 4 time units)
                    seasonal_factor = 1 + 0.2 * np.sin(2 * np.pi * self.env.now / 4)
                    # Daily variation (normal distribution)
                    daily_factor = max(0.7, min(1.3, rng.normal(1, self.std_dev)))
                    # Combine base rate with both variation factors
                    generated_volume = max(
                        0, base_rate * seasonal_factor * daily_factor
                    )
                else:
                    generated_volume = base_rate

                # Check if adding this waste would exceed storage capacity
                if self.current_storage + generated_volume <= self.storage_capacity:
                    # Update waste stream volume
                    self.waste_streams[waste_type].volume += generated_volume

                    # Update current total storage
                    self.current_storage += generated_volume

                    # Update cumulative total
                    self.total_generated[waste_type] += generated_volume

                    # Record in history with timestamp
                    self.generation_history[waste_type].append(
                        {
                            "time": self.env.now,
                            "volume": generated_volume,
                            "total_volume": self.total_generated[waste_type],
                            "current_storage": self.current_storage,
                        }
                    )

                    # print(
                    #     f"{self.env.now}: {self.name} generated {generated_volume:.2f} m³ of {waste_type.value}"
                    # )
                    # print(
                    #     f"Updated storage: {self.current_storage:.2f}/{self.storage_capacity}"
                    # )
                else:
                    print(
                        f"{self.env.now}: {self.name} storage is full! Cannot generate {waste_type.value}"
                    )
                    print(
                        f"Current storage: {self.current_storage:.2f}/{self.storage_capacity}"
                    )

            # Wait for next generation cycle
            yield self.env.timeout(self.generation_frequency)

    def _get_default_density(self, waste_type: WasteType) -> float:
        """Return default density for each waste type in kg/m3"""
        density_map = {
            WasteType.SAWDUST: 250,
            WasteType.WOOD_CUTTINGS: 400,
            WasteType.BARK: 300,
            WasteType.CORK: 240,
            WasteType.SOLID_WOOD: 500,
            WasteType.PAPER_PACKAGING: 100,
            WasteType.WOOD_PACKAGING: 450,
            WasteType.MIXED_WOOD: 350,
        }
        return density_map.get(waste_type, 300)

    def _get_default_moisture(self, waste_type: WasteType) -> float:
        """Return default moisture content for each waste type as percentage"""
        moisture_map = {
            WasteType.SAWDUST: 0.35,
            WasteType.WOOD_CUTTINGS: 0.30,
            WasteType.BARK: 0.45,
            WasteType.CORK: 0.15,
            WasteType.SOLID_WOOD: 0.25,
            WasteType.PAPER_PACKAGING: 0.10,
            WasteType.WOOD_PACKAGING: 0.20,
            WasteType.MIXED_WOOD: 0.30,
        }
        return moisture_map.get(waste_type, 0.30)

    def get_total_generated_volume(self) -> float:
        """Returns total volume across all waste streams"""
        return sum(stream.volume for stream in self.waste_streams.values())

    def get_current_waste_volumes(self) -> Dict[WasteType, float]:
        """Returns dictionary of volumes by waste type"""
        return {
            waste_type: stream.volume
            for waste_type, stream in self.waste_streams.items()
        }

    def get_generation_history_summary(self) -> Dict[str, Dict[WasteType, float]]:
        """Get detailed summary of waste generation"""
        summary = {}
        for waste_type, history in self.generation_history.items():
            total_volume = self.total_generated[waste_type]  # Use tracked total
            num_generations = len(history) if history else 1
            avg_volume = total_volume / num_generations

            summary[waste_type.value] = {
                "total_generated": total_volume,
                "average_per_cycle": avg_volume,
                "current_storage": self.waste_streams[waste_type].volume,
                "generation_rate": self.waste_generation_rates[waste_type],
            }
        return summary

    def adjust_priority(self):
        """Adjust priority level based on storage utilization and time since last collection"""
        utilization_ratio = self.current_storage / self.storage_capacity
        time_since_last_collection = self.env.now - self.last_collected

        # Increase priority as storage utilization nears capacity
        if utilization_ratio > 0.75:
            self.priority_level = min(10, self.priority_level + 1)  # Cap priority at 10
        elif utilization_ratio < 0.25:
            self.priority_level = max(
                1, self.priority_level - 1
            )  # Lower limit for priority

        # Consider time since last collectiosn, ADJUSTABLE
        if time_since_last_collection > 5:
            self.priority_level = min(10, self.priority_level + 1)

    def mark_collected(self):
        self.priority_level = max(1, self.priority_level - 1)
        self.last_collected = self.env.now
        print(
            f"{self.env.now}: {self.name} has been collected.\nPriority reset to {self.priority_level}."
        )
