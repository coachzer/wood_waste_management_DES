from typing import Dict, Any


class MetricsAnalyzer:
    """Analyzes collected data to generate system metrics and insights"""

    def __init__(self):
        self.efficiency_metrics = {}

    def calculate_efficiency_metrics(
        self,
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> Dict[str, float]:
        """Calculate system-wide efficiency metrics"""
        total_generated = self._sum_totals(generation_history, "total_generated")
        total_collected = self._sum_totals(collection_history, "collected_volumes")

        # Handle the processing history structure
        total_processed = 0
        for history in processing_history.values():
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

        return self.efficiency_metrics

    def generate_summary_report(
        self,
        generation_history: Dict[str, Any],
        collection_history: Dict[str, Any],
        processing_history: Dict[str, Any],
    ) -> str:
        """Generate a comprehensive summary report"""
        self.calculate_efficiency_metrics(
            generation_history, collection_history, processing_history
        )

        report = []
        report.append("\n=== Waste Management System Summary Report ===\n")

        # Add each section
        self._add_generation_summary(report, generation_history)
        self._add_collection_summary(report, collection_history)
        self._add_processing_summary(report, processing_history)
        self._add_efficiency_metrics(report)

        return "\n".join(report)
        
    def _add_generation_summary(self, report: list, generation_history: Dict[str, Any]) -> None:
        """Add generation summary to the report"""
        report.append("Generation Summary:")
        for generator_name, history in generation_history.items():
            report.append(f"\n{generator_name}:")
            for waste_type in history["total_generated"]:
                if history["total_generated"][waste_type]:
                    total = history["total_generated"][waste_type][-1]
                    report.append(
                        f"- Total {waste_type} generated: {total:.2f} m³"
                    )
            if history["storage_utilization"]:
                report.append(
                    f"- Current storage utilization: {history['storage_utilization'][-1]:.1f}%"
                )

    def _add_collection_summary(self, report: list, collection_history: Dict[str, Any]) -> None:
        """Add collection summary to the report"""
        report.append("\nCollection Summary:")
        for collector_name, history in collection_history.items():
            report.append(f"\n{collector_name}:")
            for waste_type in history["collected_volumes"]:
                if history["collected_volumes"][waste_type]:
                    total = history["collected_volumes"][waste_type][-1]
                    report.append(
                        f"- Total {waste_type} collected: {total:.2f} m³"
                    )
            if history["efficiency"]:
                report.append(f"- Current efficiency: {history['efficiency'][-1]:.2f}")

    def _add_processing_summary(self, report: list, processing_history: Dict[str, Any]) -> None:
        """Add processing summary to the report"""
        report.append("\nProcessing Summary:")
        for facility_name, history in processing_history.items():
            report.append(f"\n{facility_name}:")
            if history["processed"]["total"]:
                total_processed = history["processed"]["total"][-1]
                report.append(f"- Total waste processed: {total_processed:.2f} m³")
            if history["storage"]["utilization"]:
                report.append(
                    f"- Current storage utilization: {history['storage']['utilization'][-1]:.1f}%"
                )
            if history["operational"]["demand_satisfaction"]:
                satisfaction_rate = (
                    history["operational"]["demand_satisfaction"][-1] * 100
                )
                report.append(
                    f"- Current demand satisfaction rate: {satisfaction_rate:.1f}%"
                )

    def _add_efficiency_metrics(self, report: list) -> None:
        """Add efficiency metrics to the report"""
        report.append("\nSystem Efficiency Metrics:")
        report.append(
            f"- Overall collection rate: {self.efficiency_metrics['collection_rate']:.1f}%"
        )
        report.append(
            f"- Overall processing rate: {self.efficiency_metrics['processing_rate']:.1f}%"
        )
        report.append(
            f"- System-wide efficiency: {self.efficiency_metrics['overall_efficiency']:.1f}%"
        )

    def _sum_totals(self, history_dict: Dict[str, Any], key: str) -> float:
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
