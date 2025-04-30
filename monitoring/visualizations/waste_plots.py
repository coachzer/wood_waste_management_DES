import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, Set
from models.enums import WasteType
from ..visualizations.plot_utils import (
    VOLUME_LABEL,
    GRID_ALPHA,
    setup_axis_labels,
    add_moving_average_plot,
)
from .base_plotter import BasePlotter

class WastePlotter(BasePlotter):
    """Handles plotting of waste-related metrics"""

    INPUT_WASTE_TYPES = {
        WasteType.CONSTRUCTION_WOOD,
        WasteType.WOOD_CUTTINGS,
        WasteType.WASTE_WOODEN_PACKAGING,
        WasteType.SAWDUST,
        WasteType.BARK_WASTE,
        WasteType.MIXED_WOOD,
        WasteType.WASTE_PAPER_PACKAGING
    }

    def plot_waste_mix(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot waste mix analysis"""
        fig, axes = self.setup_figure(2, 1)
        
        # Plot aggregated waste mix
        self._plot_aggregated_waste_mix(
            axes[0], 
            processing_history,
            self.INPUT_WASTE_TYPES,
            "Input Waste Mix Over Time"
        )
        
        # Plot waste summary
        self._plot_waste_summary(
            axes[1], 
            processing_history,
            self.INPUT_WASTE_TYPES,
            "Input Waste Distribution"
        )
        
        self.save_figure(fig, save_path)

    def _plot_aggregated_waste_mix(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any],
        waste_types_filter: Set[WasteType],
        title: str
    ) -> None:
        """Plot waste mix across facilities"""
        timestamps = self.get_timestamps(processing_history)
        
        colors = plt.cm.tab10(np.linspace(0, 1, len(waste_types_filter)))
        
        for waste_type, color in zip(waste_types_filter, colors):
            totals = []
            for t_idx in range(len(timestamps)):
                total = sum(
                    history["storage"]["by_type"][waste_type][t_idx]
                    for history in processing_history.values()
                    if waste_type in history["storage"]["by_type"]
                    and len(history["storage"]["by_type"][waste_type]) > t_idx
                )
                totals.append(total)
            
            add_moving_average_plot(
                ax=ax,
                timestamps=timestamps,
                data=totals,
                label=waste_type.value,
                color=color
            )

        setup_axis_labels(ax, title, ylabel=VOLUME_LABEL)
        ax.legend(bbox_to_anchor=(1.05, 1))
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

    def _plot_waste_summary(
        self,
        ax: plt.Axes,
        processing_history: Dict[str, Any],
        waste_types_filter: Set[WasteType],
        title: str
    ) -> None:
        """Plot waste mix distribution summary"""
        ax.axis("off")

        summary_data = []
        for waste_type in waste_types_filter:
            final_volume = 0.0
            for history in processing_history.values():
                if waste_type in history["storage"]["by_type"]:
                    volumes = history["storage"]["by_type"][waste_type]
                    if volumes:
                        final_volume += volumes[-1]
            summary_data.append([waste_type.value, f"{final_volume:.1f}"])

        # Sort by volume
        summary_data.sort(key=lambda x: float(x[1]), reverse=True)

        # Create table
        table = ax.table(
            cellText=summary_data,
            colLabels=["Waste Type", "Final Volume (m³)"],
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.5)

        # Style header
        for j in range(2):
            table[(0, j)].set_facecolor("#E6E6E6")

        ax.set_title(title, pad=20)
