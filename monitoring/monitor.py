import os
from matplotlib import pyplot as plt

from core.collector import CollectorCompany
from core.generator import WasteGenerator
from core.treatment import TreatmentOperator
from models.enums import WasteType
from monitoring.mfa_visualization import (
    create_material_flow_analysis,
    plot_generation_trends,
    plot_collection_efficiency,
    plot_processing_volume,
    plot_system_efficiency,
    plot_cumulative_analysis,
    plot_production_analysis,
)


class WasteMonitor:
    def __init__(self):
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}
        self.efficiency_metrics = {}

        # Create directory for plots if it doesn't exist
        if not os.path.exists("plots"):
            os.makedirs("plots")

    def track_generation(self, generator: WasteGenerator, timestamp: float):
        """Track waste generation events with timestamps"""
        if generator.name not in self.generation_history:
            self.generation_history[generator.name] = {
                "timestamps": [],
                "volumes": {},
                "total_generated": {},
                "storage_utilization": [],
            }

        history = self.generation_history[generator.name]
        history["timestamps"].append(timestamp)

        # Track volumes by waste type
        for waste_type, stream in generator.waste_streams.items():
            if waste_type not in history["volumes"]:
                history["volumes"][waste_type] = []
                history["total_generated"][waste_type] = []

            history["volumes"][waste_type].append(stream.volume)
            history["total_generated"][waste_type].append(
                generator.total_generated[waste_type]
            )

        # Track storage utilization
        utilization = (generator.current_storage / generator.storage_capacity) * 100
        history["storage_utilization"].append(utilization)

    def track_collection(self, collector: CollectorCompany, timestamp: float):
        """Track waste collection events"""
        if collector.name not in self.collection_history:
            self.collection_history[collector.name] = {
                "timestamps": [],
                "collected_volumes": {},
                "efficiency": [],
                "transport_costs": [],
            }

        history = self.collection_history[collector.name]
        history["timestamps"].append(timestamp)

        # Track collected volumes by waste type
        for waste_type, amount in collector.collected_waste.items():
            if waste_type not in history["collected_volumes"]:
                history["collected_volumes"][waste_type] = []
            history["collected_volumes"][waste_type].append(amount)

        # Track efficiency metrics
        history["efficiency"].append(collector.efficiency)
        history["transport_costs"].append(collector.transport_cost)

    def track_processing(self, treatment: TreatmentOperator, timestamp: float):
        """Track treatment facility metrics"""
        if treatment.name not in self.processing_history:
            self.processing_history[treatment.name] = {
                "timestamps": [],
                "storage": {
                    "total": [],
                    "by_type": {waste_type: [] for waste_type in WasteType},
                    "utilization": [],
                },
                "processed": {
                    "total": [],
                    "by_type": {waste_type: [] for waste_type in WasteType},
                },
                "operational": {
                    "energy_consumption": [],
                    "conversion_rate": [],
                    "demand": [],
                    "demand_satisfaction": [],
                },
            }

        history = self.processing_history[treatment.name]

        # Only record if this is a new timestamp
        if not history["timestamps"] or timestamp > history["timestamps"][-1]:
            history["timestamps"].append(timestamp)

            # Storage metrics
            history["storage"]["total"].append(treatment.current_storage)
            history["storage"]["utilization"].append(treatment.storage_utilization)
            for waste_type in WasteType:
                history["storage"]["by_type"][waste_type].append(
                    treatment.waste_storage[waste_type]
                )

            # Processing metrics
            total_processed = sum(treatment.processed_volumes.values())
            history["processed"]["total"].append(total_processed)
            for waste_type in WasteType:
                history["processed"]["by_type"][waste_type].append(
                    treatment.processed_volumes[waste_type]
                )

            # Operational metrics
            history["operational"]["energy_consumption"].append(
                treatment.energy_consumption
            )
            history["operational"]["conversion_rate"].append(treatment.conversion_rate)
            history["operational"]["demand"].append(treatment.demand)
            history["operational"]["demand_satisfaction"].append(
                total_processed >= treatment.demand if treatment.demand > 0 else 1.0
            )

    def calculate_efficiency_metrics(self):
        """Calculate system-wide efficiency metrics"""
        total_generated = self._sum_totals(self.generation_history, "total_generated")
        total_collected = self._sum_totals(self.collection_history, "collected_volumes")
        total_processed = self._sum_totals(self.processing_history, "processed_volumes")

        # Calculate efficiency metrics
        self.efficiency_metrics = {
            "collection_rate": (
                total_collected / total_generated * 100 if total_generated > 0 else 0
            ),
            "processing_rate": (
                total_processed / total_collected * 100 if total_collected > 0 else 0
            ),
            "overall_efficiency": (
                total_processed / total_generated * 100 if total_generated > 0 else 0
            ),
        }

    def plot_generation_trends(self, save_path=None):
        """Plot waste generation trends over time"""
        plt.figure(figsize=(15, 10))

        # Plot total generation by waste type
        plt.subplot(2, 1, 1)
        for generator_name, history in self.generation_history.items():
            for waste_type, volumes in history["total_generated"].items():
                plt.plot(
                    history["timestamps"],
                    volumes,
                    label=f"{generator_name} - {waste_type.value}",
                )

        plt.title("Cumulative Waste Generation Over Time")
        plt.xlabel("Time")
        plt.ylabel("Volume (m³)")
        plt.legend()
        plt.grid(True)

        # Plot storage utilization
        plt.subplot(2, 1, 2)
        for generator_name, history in self.generation_history.items():
            plt.plot(
                history["timestamps"],
                history["storage_utilization"],
                label=f"{generator_name} Storage Utilization",
            )

        plt.title("Storage Utilization Over Time")
        plt.xlabel("Time")
        plt.ylabel("Utilization (%)")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path)

        plt.close()

    def plot_collection_efficiency(self, save_path=None):
        """Plot collection efficiency metrics"""
        plt.figure(figsize=(12, 6))

        for collector_name, history in self.collection_history.items():
            plt.plot(
                history["timestamps"],
                history["efficiency"],
                label=f"{collector_name} Efficiency",
            )

        plt.title("Collection Efficiency Over Time")
        plt.xlabel("Time")
        plt.ylabel("Efficiency")
        plt.legend()
        plt.grid(True)

        if save_path:
            plt.savefig(save_path)
            print(f"Collection efficiency plot saved to: {save_path}")

        plt.close()

    def plot_storage_levels(self, save_path=None):
        """
        Plot comprehensive storage levels across the system.
        Shows storage utilization for generators, treatment facilities,
        and collectors over time with improved error handling.
        """
        plt.figure(figsize=(15, 12))

        self._plot_generators_storage()
        self._plot_treatment_storage()
        self._plot_collectors_storage()

        # Adjust layout to prevent overlap
        plt.tight_layout()

        # Save if path provided
        if save_path:
            plt.savefig(save_path, bbox_inches="tight", dpi=300)
            print(f"Storage levels plot saved to: {save_path}")

        plt.close()

    def _plot_generators_storage(self):
        """Helper method to plot generators storage utilization"""
        plt.subplot(3, 1, 1)
        for name, history in self.generation_history.items():
            if len(history["timestamps"]) == len(history["storage_utilization"]):
                plt.plot(
                    history["timestamps"],
                    history["storage_utilization"],
                    label=f"{name}",
                    marker="o",
                    markersize=4,
                    linestyle="-",
                    linewidth=2,
                )
            else:
                print(f"Warning: Data mismatch for generator {name}. Skipping plot.")

        plt.title("Generator Storage Utilization", fontsize=12, pad=10)
        plt.ylabel("Storage Utilization (%)")
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.ylim(0, 100)

    def _plot_treatment_storage(self):
        """Helper method to plot treatment facility storage utilization"""
        plt.subplot(3, 1, 2)
        for name, history in self.processing_history.items():
            if len(history["timestamps"]) == len(history["storage"]["utilization"]):
                plt.plot(
                    history["timestamps"],
                    history["storage"]["utilization"],
                    label=f"{name}",
                    marker="s",
                    markersize=4,
                    linestyle="-",
                    linewidth=2,
                )
        plt.title("Treatment Facility Storage Utilization", fontsize=12, pad=10)
        plt.ylabel("Storage Utilization (%)")
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.ylim(0, 100)

    def _plot_collectors_storage(self):
        """Helper method to plot collectors' storage utilization"""
        plt.subplot(3, 1, 3)
        for name, history in self.collection_history.items():
            if len(history["timestamps"]) > 0:
                try:
                    # Calculate storage utilization as percentage of total collected volume
                    total_volumes = []
                    timestamps = history["timestamps"]

                    for t_idx in range(len(timestamps)):
                        total = sum(
                            volumes[t_idx]
                            for volumes in history["collected_volumes"].values()
                            if len(volumes) > t_idx
                        )
                        total_volumes.append(total)

                    # Normalize to percentage (0-100%)
                    max_volume = max(total_volumes) if total_volumes else 1
                    storage_utilization = [v / max_volume * 100 for v in total_volumes]

                    if len(timestamps) == len(storage_utilization):
                        plt.plot(
                            timestamps,
                            storage_utilization,
                            label=f"{name}",
                            marker="^",
                            markersize=4,
                            linestyle="-",
                            linewidth=2,
                        )
                    else:
                        print(
                            f"Warning: Data mismatch for collector {name}. Skipping plot."
                        )
                except Exception as e:
                    print(f"Error plotting collector {name}: {str(e)}")

        plt.title("Collector Storage Utilization", fontsize=12, pad=10)
        plt.xlabel("Simulation Time")
        plt.ylabel("Storage Utilization (%)")
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True, linestyle="--", alpha=0.7)
        plt.ylim(0, 100)

    def plot_detailed_storage_analysis(self, save_path=None):
        """Create a detailed analysis of storage patterns with additional metrics"""
        fig = plt.figure(figsize=(15, 10))
        gs = plt.GridSpec(2, 2, figure=fig)

        # Storage Utilization Heatmap - Top left
        ax1 = fig.add_subplot(gs[0, 0])
        self._plot_storage_heatmap(ax1)

        # Average Storage Utilization - Top right
        ax2 = fig.add_subplot(gs[0, 1])
        self._plot_average_storage(ax2)

        # Storage Fluctuation Analysis - Bottom spanning both columns
        ax3 = fig.add_subplot(gs[1, :])
        self._plot_storage_fluctuations(ax3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, bbox_inches="tight", dpi=300)
            print(f"Detailed storage analysis saved to: {save_path}")

        plt.close()

    def _plot_storage_heatmap(self, ax):
        """Helper method to create storage utilization heatmap"""
        storage_data = []
        labels = []

        # Get generator data
        for name, history in self.generation_history.items():
            if "storage_utilization" in history and history["storage_utilization"]:
                storage_data.append(history["storage_utilization"])
                labels.append(f"Gen: {name}")

        # Get treatment facility data with new structure
        for name, history in self.processing_history.items():
            if "storage" in history and "utilization" in history["storage"]:
                storage_data.append(history["storage"]["utilization"])
                labels.append(f"Proc: {name}")

        if storage_data:
            im = ax.imshow(storage_data, aspect="auto", cmap="YlOrRd")
            ax.set_yticks(range(len(labels)))
            ax.set_yticklabels(labels)
            ax.set_xlabel("Time Steps")
            ax.set_title("Storage Utilization Heatmap")
            plt.colorbar(im, ax=ax, label="Utilization %")

    def _plot_average_storage(self, ax):
        """Helper method to plot average storage utilization"""
        generator_avgs = {}
        processor_avgs = {}

        # Calculate generator averages
        for name, history in self.generation_history.items():
            if "storage_utilization" in history and history["storage_utilization"]:
                generator_avgs[name] = sum(history["storage_utilization"]) / len(
                    history["storage_utilization"]
                )

        # Calculate processor averages with new structure
        for name, history in self.processing_history.items():
            if "storage" in history and "utilization" in history["storage"]:
                processor_avgs[name] = sum(history["storage"]["utilization"]) / len(
                    history["storage"]["utilization"]
                )

        labels = list(generator_avgs.keys()) + list(processor_avgs.keys())
        values = list(generator_avgs.values()) + list(processor_avgs.values())

        if values:
            bars = ax.bar(range(len(values)), values)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=45, ha="right")
            ax.set_ylabel("Average Storage Utilization (%)")
            ax.set_title("Average Storage Utilization by Entity")

            # Add value labels on top of bars
            for bar in bars:
                height = bar.get_height()
                ax.text(
                    bar.get_x() + bar.get_width() / 2.0,
                    height,
                    f"{height:.1f}%",
                    ha="center",
                    va="bottom",
                )

    def _plot_storage_fluctuations(self, ax):
        """Helper method to plot storage level fluctuations"""
        # Plot generator fluctuations
        for name, history in self.generation_history.items():
            if "storage_utilization" in history and history["storage_utilization"]:
                ax.plot(
                    history["timestamps"],
                    history["storage_utilization"],
                    label=f"Gen: {name}",
                    alpha=0.7,
                )

        # Plot treatment facility fluctuations with new structure
        for name, history in self.processing_history.items():
            if "storage" in history and "utilization" in history["storage"]:
                ax.plot(
                    history["timestamps"],
                    history["storage"]["utilization"],
                    label=f"Proc: {name}",
                    alpha=0.7,
                )

        ax.set_xlabel("Simulation Time")
        ax.set_ylabel("Storage Utilization (%)")
        ax.set_title("Storage Level Fluctuations Over Time")
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")

    def generate_summary_report(self):
        """Generate a comprehensive summary report"""
        self.calculate_efficiency_metrics()

        print("\n=== Waste Management System Summary Report ===\n")

        self._print_generation_summary()
        self._print_collection_summary()
        self._print_processing_metrics()
        self._print_efficiency_metrics()

    def _print_generation_summary(self):
        """Print generation summary"""
        print("Generation Summary:")
        for generator_name, history in self.generation_history.items():
            print(f"\n{generator_name}:")
            for waste_type in history["total_generated"]:
                if history["total_generated"][waste_type]:
                    total = history["total_generated"][waste_type][-1]
                    print(f"- Total {waste_type.value} generated: {total:.2f} m³")
            if history["storage_utilization"]:
                print(
                    f"- Current storage utilization: {history['storage_utilization'][-1]:.1f}%"
                )

    def _print_collection_summary(self):
        """Print collection summary"""
        print("\nCollection Summary:")
        for collector_name, history in self.collection_history.items():
            print(f"\n{collector_name}:")
            for waste_type in history["collected_volumes"]:
                if history["collected_volumes"][waste_type]:
                    total = history["collected_volumes"][waste_type][-1]
                    print(f"- Total {waste_type.value} collected: {total:.2f} m³")
            if history["efficiency"]:
                print(f"- Current efficiency: {history['efficiency'][-1]:.2f}")

    def _print_processing_metrics(self):
        """Print system processing metrics"""
        print("\nProcessing Summary:")
        for facility_name, history in self.processing_history.items():
            print(f"\n{facility_name}:")
            if history["processed"]["total"]:
                total_processed = history["processed"]["total"][-1]
                print(f"- Total waste processed: {total_processed:.2f} m³")
            if history["storage"]["utilization"]:
                print(
                    f"- Current storage utilization: {history['storage']['utilization'][-1]:.1f}%"
                )
            if history["operational"]["demand_satisfaction"]:
                satisfaction_rate = (
                    history["operational"]["demand_satisfaction"][-1] * 100
                )
                print(f"- Current demand satisfaction rate: {satisfaction_rate:.1f}%")

    def _print_efficiency_metrics(self):
        # System Efficiency Metrics
        print("\nSystem Efficiency Metrics:")
        print(
            f"- Overall collection rate: {self.efficiency_metrics['collection_rate']:.1f}%"
        )
        print(
            f"- Overall processing rate: {self.efficiency_metrics['processing_rate']:.1f}%"
        )
        print(
            f"- System-wide efficiency: {self.efficiency_metrics['overall_efficiency']:.1f}%"
        )

    def calculate_efficiency_metrics(self):
        """Calculate system-wide efficiency metrics with updated data structure"""
        total_generated = self._sum_totals(self.generation_history, "total_generated")
        total_collected = self._sum_totals(self.collection_history, "collected_volumes")

        # Handle the new processing history structure
        total_processed = 0
        for history in self.processing_history.values():
            if history["processed"]["total"]:
                total_processed += history["processed"]["total"][-1]

        # Calculate efficiency metrics
        self.efficiency_metrics = {
            "collection_rate": (
                (total_collected / total_generated * 100) if total_generated > 0 else 0
            ),
            "processing_rate": (
                (total_processed / total_collected * 100) if total_collected > 0 else 0
            ),
            "overall_efficiency": (
                (total_processed / total_generated * 100) if total_generated > 0 else 0
            ),
        }

    def _sum_totals(self, history_dict, key):
        """Helper function to sum totals across all entities with structure handling"""
        total = 0
        for history in history_dict.values():
            if key not in history:
                continue

            # Handle different data structures
            if isinstance(history[key], dict):
                # For nested dictionary structure
                for values in history[key].values():
                    if values and isinstance(values, list):
                        total += values[-1]
            elif isinstance(history[key], list):
                # For direct list structure
                if history[key]:
                    total += history[key][-1]

        return total

    def plot_temporal_analysis(self):
        """Create streamlined temporal analysis plots"""
        # Core system metrics
        self.plot_system_performance()  # Combined system efficiency metrics
        self.plot_product_metrics()  # Production and demand analysis

        # Create material flow analysis plot (key visualization)
        create_material_flow_analysis(
            self.generation_history,
            self.collection_history,
            self.processing_history,
        )

        # Combined analysis plots
        plot_cumulative_analysis(
            self.generation_history,
            self.collection_history,
            self.processing_history,
            "plots/cumulative_analysis.png",
        )

    def plot_generator_metrics(self):
        """Plot detailed generator performance metrics"""
        plt.figure(figsize=(15, 10))

        # Generation rates
        plt.subplot(2, 2, 1)
        for name, history in self.generation_history.items():
            for waste_type, volumes in history["total_generated"].items():
                plt.plot(
                    history["timestamps"],
                    [v / max(1, t) for v, t in zip(volumes, history["timestamps"])],
                    label=f"{name}-{waste_type.value}",
                )
        plt.title("Waste Generation Rates")
        plt.xlabel("Time")
        plt.ylabel("Generation Rate (m³/time)")
        plt.legend(bbox_to_anchor=(1.05, 1))
        plt.grid(True)

        # Storage dynamics
        plt.subplot(2, 2, 2)
        for name, history in self.generation_history.items():
            plt.plot(history["timestamps"], history["storage_utilization"], label=name)
        plt.title("Storage Utilization Dynamics")
        plt.xlabel("Time")
        plt.ylabel("Storage Utilization (%)")
        plt.legend()
        plt.grid(True)

        # Waste composition
        plt.subplot(2, 2, 3)
        latest_composition = {}
        for name, history in self.generation_history.items():
            for waste_type, volumes in history["total_generated"].items():
                if volumes:
                    latest_composition[waste_type.value] = (
                        latest_composition.get(waste_type.value, 0) + volumes[-1]
                    )

        plt.pie(
            latest_composition.values(),
            labels=latest_composition.keys(),
            autopct="%1.1f%%",
        )
        plt.title("Waste Composition Distribution")

        plt.tight_layout()
        plt.savefig("plots/generator_metrics.png")
        plt.close()

    def plot_collector_metrics(self):
        """Plot detailed collector performance metrics"""
        plt.figure(figsize=(15, 10))

        # Collection efficiency over time
        plt.subplot(2, 2, 1)
        for name, history in self.collection_history.items():
            plt.plot(
                history["timestamps"], history["efficiency"], label=name, marker="o"
            )
        plt.title("Collection Efficiency Trends")
        plt.xlabel("Time")
        plt.ylabel("Efficiency")
        plt.legend()
        plt.grid(True)

        # Transport costs
        plt.subplot(2, 2, 2)
        for name, history in self.collection_history.items():
            plt.plot(history["timestamps"], history["transport_costs"], label=name)
        plt.title("Transport Cost Evolution")
        plt.xlabel("Time")
        plt.ylabel("Cost")
        plt.legend()
        plt.grid(True)

        # Collection volumes by type
        plt.subplot(2, 2, 3)
        for name, history in self.collection_history.items():
            volumes = []
            for waste_type, vol in history["collected_volumes"].items():
                if vol:
                    plt.plot(
                        history["timestamps"], vol, label=f"{name}-{waste_type.value}"
                    )
        plt.title("Collection Volumes by Waste Type")
        plt.xlabel("Time")
        plt.ylabel("Volume (m³)")
        plt.legend(bbox_to_anchor=(1.05, 1))
        plt.grid(True)

        plt.tight_layout()
        plt.savefig("plots/collector_metrics.png")
        plt.close()

    def plot_treatment_metrics(self):
        """Plot detailed treatment facility metrics"""
        plt.figure(figsize=(15, 10))

        # Processing efficiency
        plt.subplot(2, 2, 1)
        for name, history in self.processing_history.items():
            plt.plot(
                history["timestamps"],
                history["operational"]["conversion_rate"],
                label=name,
            )
        plt.title("Processing Efficiency")
        plt.xlabel("Time")
        plt.ylabel("Conversion Rate")
        plt.legend()
        plt.grid(True)

        # Demand satisfaction
        plt.subplot(2, 2, 2)
        for name, history in self.processing_history.items():
            satisfaction = history["operational"]["demand_satisfaction"]
            plt.plot(history["timestamps"], [s * 100 for s in satisfaction], label=name)
        plt.title("Demand Satisfaction Rate")
        plt.xlabel("Time")
        plt.ylabel("Satisfaction Rate (%)")
        plt.legend()
        plt.grid(True)

        # Energy consumption
        plt.subplot(2, 2, 3)
        for name, history in self.processing_history.items():
            plt.plot(
                history["timestamps"],
                history["operational"]["energy_consumption"],
                label=name,
            )
        plt.title("Energy Consumption Trends")
        plt.xlabel("Time")
        plt.ylabel("Energy Consumption")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.savefig("plots/treatment_metrics.png")
        plt.close()

    def plot_treatment_detailed(self):
        """Plot detailed treatment metrics from treatment.py"""
        plt.figure(figsize=(15, 10))

        # Energy consumption correlation
        plt.subplot(2, 2, 1)
        for name, history in self.processing_history.items():
            plt.scatter(
                history["processed"]["total"],
                history["operational"]["energy_consumption"],
                alpha=0.6,
                label=name,
            )
        plt.title("Energy Consumption vs Processing Volume")
        plt.xlabel("Processed Volume (m³)")
        plt.ylabel("Energy Consumption")
        plt.legend()
        plt.grid(True)

        # Processing capacity evolution
        plt.subplot(2, 2, 2)
        for name, history in self.processing_history.items():
            plt.plot(
                history["timestamps"],
                [
                    e * v
                    for e, v in zip(
                        history["operational"]["energy_consumption"],
                        history["processed"]["total"],
                    )
                ],
                label=name,
            )
        plt.title("Energy Efficiency Over Time")
        plt.xlabel("Time")
        plt.ylabel("Energy per Volume")
        plt.legend()
        plt.grid(True)

        # Storage vs Processing
        plt.subplot(2, 2, 3)
        for name, history in self.processing_history.items():
            plt.plot(
                history["timestamps"],
                [
                    p / s if s > 0 else 0
                    for p, s in zip(
                        history["processed"]["total"], history["storage"]["total"]
                    )
                ],
                label=name,
            )
        plt.title("Processing/Storage Ratio")
        plt.xlabel("Time")
        plt.ylabel("Ratio")
        plt.legend()
        plt.grid(True)

        plt.tight_layout()
        plt.savefig("plots/treatment_detailed.png")
        plt.close()

    def plot_product_metrics(self):
        """Plot product creation and demand metrics with demand satisfaction table"""
        fig = plt.figure(figsize=(15, 12))
        gs = plt.GridSpec(3, 2, figure=fig)

        self._plot_processing_vs_demand(fig, gs)
        self._plot_conversion_efficiency(fig, gs)
        self._plot_product_mix(fig, gs)
        self._plot_demand_satisfaction_table(fig, gs)

        plt.tight_layout()
        plt.savefig("plots/product_metrics.png")
        plt.close()

    def _plot_processing_vs_demand(self, fig, gs):
        """Helper method to plot processing vs. demand"""
        ax1 = fig.add_subplot(gs[0, 0])
        for name, history in self.processing_history.items():
            plt.plot(
                history["timestamps"],
                history["processed"]["total"],
                label=f"{name} - Processed",
            )
            plt.plot(
                history["timestamps"],
                [history["operational"]["demand"][-1]] * len(history["timestamps"]),
                label=f"{name} - Demand",
                linestyle="--",
            )
        ax1.set_title("Processed vs. Demand Volumes")
        ax1.set_xlabel("Time")
        ax1.set_ylabel("Volume (m³)")
        ax1.legend()
        ax1.grid(True)

    def _plot_conversion_efficiency(self, fig, gs):
        """Helper method to plot conversion efficiency"""
        ax2 = fig.add_subplot(gs[0, 1])
        for name, history in self.processing_history.items():
            efficiency = [
                p / d if d > 0 else 0
                for p, d in zip(
                    history["processed"]["total"], history["operational"]["demand"]
                )
            ]
            plt.plot(history["timestamps"], efficiency, label=name)
        ax2.set_title("Processing Efficiency")
        ax2.set_xlabel("Time")
        ax2.set_ylabel("Efficiency Ratio")
        ax2.legend()
        ax2.grid(True)

    def _plot_product_mix(self, fig, gs):
        """Helper method to plot product mix"""
        ax3 = fig.add_subplot(gs[1, 0])
        for name, history in self.processing_history.items():
            for waste_type, volumes in history["processed"]["by_type"].items():
                if volumes:
                    plt.plot(
                        history["timestamps"],
                        volumes,
                        label=f"{name}-{waste_type.value}",
                    )
        ax3.set_title("Product Mix Over Time")
        ax3.set_xlabel("Time")
        ax3.set_ylabel("Volume (m³)")
        ax3.legend(bbox_to_anchor=(1.05, 1))
        ax3.grid(True)

    def _plot_demand_satisfaction_table(self, fig, gs):
        """Helper method to plot demand satisfaction table"""
        ax4 = fig.add_subplot(gs[1:, 1])
        ax4.axis("off")

        facility_stats = []
        for name, history in self.processing_history.items():
            demands = history["operational"]["demand"]
            processed = history["processed"]["total"]
            if demands and processed:
                total_demands = sum(demands)
                total_processed = sum(processed)
                success_count = sum(1 for p, d in zip(processed, demands) if p >= d)
                total_periods = len(demands)

                stats = {
                    "Facility": name,
                    "Success Rate": f"{(success_count/total_periods)*100:.1f}%",
                    "Total Demand": f"{total_demands:.1f}",
                    "Total Produced": f"{total_processed:.1f}",
                    "Satisfaction Rate": (
                        f"{(total_processed/total_demands)*100:.1f}%"
                        if total_demands > 0
                        else "N/A"
                    ),
                }
                facility_stats.append(stats)

        table_data = [
            [
                stats[key]
                for key in [
                    "Facility",
                    "Success Rate",
                    "Total Demand",
                    "Total Produced",
                    "Satisfaction Rate",
                ]
            ]
            for stats in facility_stats
        ]
        headers = [
            "Facility",
            "Success Rate",
            "Total Demand",
            "Total Produced",
            "Satisfaction Rate",
        ]

        table = ax4.table(
            cellText=table_data, colLabels=headers, loc="center", cellLoc="center"
        )

        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)

        for j in range(len(headers)):
            table[(0, j)].set_facecolor("#E6E6E6")

        plt.title("Demand Satisfaction Statistics", pad=20)

    def plot_system_performance(self):
        """Plot overall system performance metrics"""
        plt.figure(figsize=(15, 10))

        # System efficiency metrics
        self.calculate_efficiency_metrics()
        metrics = ["collection_rate", "processing_rate", "overall_efficiency"]
        values = [self.efficiency_metrics[m] for m in metrics]

        plt.subplot(2, 2, 1)
        plt.bar(metrics, values)
        plt.title("System Efficiency Metrics")
        plt.ylabel("Percentage (%)")
        plt.xticks(rotation=45)

        # Collection rates
        collection_rates = []
        for name, history in self.collection_history.items():
            if history["collected_volumes"]:
                total_collected = sum(history["collected_volumes"].values(), [])
                collection_rates.append((name, total_collected[-1]))

        collection_rates.sort(key=lambda x: x[1], reverse=True)
        names, values = zip(*collection_rates)

        plt.subplot(2, 2, 2)
        plt.bar(names, values)
        plt.title("Total Collection Volumes")
        plt.ylabel("Volume (m³)")
        plt.xticks(rotation=45)

        # Processing rates
        processing_rates = []
        for name, history in self.processing_history.items():
            if history["processed"]["total"]:
                total_processed = history["processed"]["total"][-1]
                processing_rates.append((name, total_processed))

        processing_rates.sort(key=lambda x: x[1], reverse=True)
        names, values = zip(*processing_rates)

        plt.subplot(2, 2, 3)
        plt.bar(names, values)
        plt.title("Total Processing Volumes")
        plt.ylabel("Volume (m³)")
        plt.xticks(rotation=45)

        plt.tight_layout()
        plt.savefig("plots/system_performance.png")
        plt.close()
