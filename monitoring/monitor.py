import os
from .data_collector import DataCollector
from .metrics_analyzer import MetricsAnalyzer
from .mfa_visualization import create_material_flow_analysis

class WasteMonitor:
    """Central monitoring system for waste management operations"""

    def __init__(self):
        self.data_collector = DataCollector()
        self.metrics_analyzer = MetricsAnalyzer()

        # Create plots directory if it doesn't exist
        if not os.path.exists("plots"):
            os.makedirs("plots")

    def track_generation(self, generator, timestamp: float, region=None) -> None:
        """Track waste generation events with timestamps and region info"""
        self.data_collector.track_generation(generator, timestamp, region=region)

    def track_collection(self, collector, timestamp: float, region=None) -> None:
        """Track waste collection events with region info"""
        self.data_collector.track_collection(collector, timestamp, region=region)

    def track_processing(self, treatment, timestamp: float) -> None:
        """Track treatment facility metrics"""
        self.data_collector.track_processing(treatment, timestamp)

    def track_overflow(self, facility_type: str, volume: float, strategy: str, timestamp: float, region=None) -> None:
        """Track overflow events and their handling strategies, with region info"""
        self.data_collector.track_overflow(facility_type, volume, strategy, timestamp, region=region)

    def plot_temporal_analysis(self, end_time: float) -> None:
        """Create streamlined temporal analysis plots"""
        generation_history = self.data_collector.get_generation_history()
        collection_history = self.data_collector.get_collection_history()
        processing_history = self.data_collector.get_processing_history()

        # Calculate efficiency metrics
        efficiency_metrics = self.metrics_analyzer.calculate_efficiency_metrics(
            generation_history, collection_history, processing_history
        )

        # Create material flow analysis plot
        create_material_flow_analysis(
            generation_history,
            collection_history,
            processing_history,
        )

        print(f"Temporal analysis completed for time {end_time}")
        print(f"Efficiency metrics: {efficiency_metrics}")

    def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report"""
        return self.metrics_analyzer.generate_summary_report(
            self.data_collector.get_generation_history(),
            self.data_collector.get_collection_history(),
            self.data_collector.get_processing_history(),
        )
