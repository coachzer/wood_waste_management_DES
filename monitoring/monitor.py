import os
from .data_collector import DataCollector
from .metrics_analyzer import MetricsAnalyzer
from .mfa_visualization import create_material_flow_analysis
from .visualizations.storage_plots import StoragePlotter
from .visualizations.efficiency_plots import EfficiencyPlotter
from .visualizations.system_plots import SystemPlotter

class WasteMonitor:
    """Central monitoring system for waste management operations"""

    def __init__(self):
        self.data_collector = DataCollector()
        self.metrics_analyzer = MetricsAnalyzer()

        # Create plots directory if it doesn't exist
        if not os.path.exists("plots"):
            os.makedirs("plots")

    def track_generation(self, generator, timestamp: float) -> None:
        """Track waste generation events with timestamps"""
        self.data_collector.track_generation(generator, timestamp)

    def track_collection(self, collector, timestamp: float) -> None:
        """Track waste collection events"""
        self.data_collector.track_collection(collector, timestamp)

    def track_processing(self, treatment, timestamp: float) -> None:
        """Track treatment facility metrics"""
        self.data_collector.track_processing(treatment, timestamp)

    def plot_temporal_analysis(self, end_time: float) -> None:
        """Create streamlined temporal analysis plots"""
        generation_history = self.data_collector.get_generation_history()
        collection_history = self.data_collector.get_collection_history()
        processing_history = self.data_collector.get_processing_history()

        # Calculate efficiency metrics
        efficiency_metrics = self.metrics_analyzer.calculate_efficiency_metrics(
            generation_history, collection_history, processing_history
        )

        # Core system metrics
        SystemPlotter.plot_system_performance(
            efficiency_metrics,
            collection_history,
            processing_history,
            "plots/system_performance.png",
        )

        # Storage analysis
        StoragePlotter.plot_storage_levels(
            generation_history,
            processing_history,
            collection_history,
            f"plots/storage_t{int(end_time)}.png",
        )

        StoragePlotter.plot_detailed_storage_analysis(
            generation_history,
            processing_history,
            collection_history,
            f"plots/storage_detailed_t{int(end_time)}.png",
        )

        # Efficiency metrics
        EfficiencyPlotter.plot_collection_efficiency(
            collection_history,
            "plots/collector_metrics.png",
        )

        EfficiencyPlotter.plot_treatment_metrics(
            processing_history,
            "plots/treatment_metrics.png",
        )

        # Product analysis plots
        EfficiencyPlotter.plot_demand_metrics(
            processing_history,
            "plots/demand_metrics.png",
        )

        EfficiencyPlotter.plot_product_mix(
            processing_history,
            "plots/product_mix.png",
        )

        # Create material flow analysis plot
        create_material_flow_analysis(
            generation_history,
            collection_history,
            processing_history,
        )

        # Combined analysis
        SystemPlotter.plot_cumulative_analysis(
            generation_history,
            collection_history,
            processing_history,
            "plots/cumulative_analysis.png",
        )

    def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report"""
        return self.metrics_analyzer.generate_summary_report(
            self.data_collector.get_generation_history(),
            self.data_collector.get_collection_history(),
            self.data_collector.get_processing_history(),
        )
