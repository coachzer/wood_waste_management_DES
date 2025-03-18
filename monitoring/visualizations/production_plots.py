from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import matplotlib.pyplot as plt
from models.enums import OutputType, WasteType
from models.state import SimulationState
from utils.helpers import load_json
from ..visualizations.plot_utils import (
    VOLUME_LABEL,
    DEFAULT_FIGURE_SIZE,
    GRID_ALPHA,
    setup_axis_labels,
)
from .base_plotter import BasePlotter

class ProductionPlotter(BasePlotter):
    """Handles plotting of production-related metrics"""

    def plot_accumulated_products(
        self,
        processing_history: Dict[str, Any],
        save_path: str = None,
    ) -> None:
        """Plot accumulated products over time with demand targets"""
        # Create figure with extra width for legend
        wider_figsize = (DEFAULT_FIGURE_SIZE[0] * 1.3, DEFAULT_FIGURE_SIZE[1])
        fig, [ax] = self.setup_figure(figsize=wider_figsize)
        plt.subplots_adjust(right=0.85)  # Adjust for legend

        timestamps = self.get_timestamps(processing_history)
        state = SimulationState.get_instance()
        demand_data = load_json("data/demand.json")

        # Define product mapping
        product_mapping = {
            OutputType.WOODEN_FURNITURE: "wooden_furniture",
            OutputType.WOODEN_PACKAGING: "wooden_packaging",
            OutputType.PAPER_PACKAGING: "paper_packaging"
        }

        # Calculate y-axis limits
        max_target = max(demand_data['national_demand'].values())
        max_current = max(state.total_products.values())
        y_max = max(max_target, max_current) * 1.2

        # Plot each product type
        colors = plt.cm.tab10(np.linspace(0, 1, len(product_mapping)))
        linestyles = ['-', '--', ':']
        self._plot_product_lines(ax, timestamps, product_mapping, state, demand_data, colors, linestyles)

        # Format axes and legend
        self._format_production_plot(ax, timestamps, y_max, product_mapping, state, demand_data)
        self.save_figure(fig, save_path)

    def _plot_product_lines(
        self,
        ax: plt.Axes,
        timestamps: List[float],
        product_mapping: Dict[OutputType, str],
        state: SimulationState,
        demand_data: Dict[str, Any],
        colors: np.ndarray,
        linestyles: List[str]
    ) -> None:
        """Plot production lines for each product type"""
        # Initialize product histories with accurate cumulative production
        product_histories = {}
        
        # For each product type, calculate cumulative production at each timestamp
        for _, state_key in product_mapping.items():
            product_histories[state_key] = []
            cumulative_production = 0
            
            # Get the demand met time for this product
            demand_met_time = state.demand_met_times[state_key]
            target_demand = demand_data['national_demand'][state_key]
            
            for t in timestamps:
                # If we've passed the demand met time, we know we reached the target
                if demand_met_time is not None and t >= demand_met_time:
                    cumulative_production = target_demand
                # Otherwise interpolate based on final production and demand met time
                else:
                    final_production = state.total_products[state_key]
                    if demand_met_time is not None:
                        # Linear interpolation up to demand met time
                        progress = min(t / demand_met_time, 1.0)
                        cumulative_production = target_demand * progress
                    else:
                        # Linear interpolation over entire simulation
                        progress = t / timestamps[-1]
                        cumulative_production = final_production * progress
                
                product_histories[state_key].append(cumulative_production)
                            
        for (product_type, state_key), color, style in zip(product_mapping.items(), colors, linestyles):
            target_demand = demand_data['national_demand'][state_key]
            current_production = state.total_products[state_key]
            
            # Get product-specific history
            product_history = product_histories.get(state_key, [])
            if not product_history:
                # Fallback to linear if no history
                product_history = [current_production * (i / len(timestamps)) for i in range(len(timestamps))]
            
            # Plot production line
            self._plot_single_product(ax, timestamps, product_history, target_demand, product_type, color, style)
            
            # Add annotations with product type
            self._add_product_annotations(ax, timestamps, current_production, target_demand, color, product_type)

    def _plot_single_product(
        self,
        ax: plt.Axes,
        timestamps: List[float],
        accumulated: List[float],
        target_demand: float,
        product_type: OutputType,
        color: np.ndarray,
        style: str,
    ) -> None:
        """Plot production line and target for a single product"""
        # Plot accumulation line
        ax.plot(
            timestamps,
            accumulated,
            color=color,
            linestyle=style,
            linewidth=2,
            label=f"Current: {product_type.value}"
        )
        
        # Plot target line
        ax.axhline(
            y=target_demand,
            color=color,
            linestyle=':',
            alpha=0.5,
            linewidth=1,
            label=f"Target: {product_type.value}"
        )
        
        # Add shaded areas
        self._add_shaded_areas(ax, timestamps, accumulated, target_demand, color)

    def _add_shaded_areas(
        self,
        ax: plt.Axes,
        timestamps: List[float],
        accumulated: List[float],
        target_demand: float,
        color: np.ndarray,
    ) -> None:
        """Add shaded areas for under/over production"""
        # Under target
        ax.fill_between(
            timestamps,
            accumulated,
            [target_demand] * len(timestamps),
            where=[x < target_demand for x in accumulated],
            color=color,
            alpha=0.1
        )
        # Over target
        ax.fill_between(
            timestamps,
            [target_demand] * len(timestamps),
            accumulated,
            where=[x > target_demand for x in accumulated],
            color='red',
            alpha=0.1
        )

    def _add_product_annotations(
        self,
        ax: plt.Axes,
        timestamps: List[float],
        current_production: float,
        target_demand: float,
        color: np.ndarray,
        product_type: OutputType,
    ) -> None:
        """Add annotations for final production and fulfillment time"""
        # Final production annotation
        ax.text(
            timestamps[-1] + 1,
            current_production,
            f"Final: {current_production:.1f} m³",
            color=color,
            verticalalignment='bottom'
        )
        
        # Get demand met time from simulation state
        state = SimulationState.get_instance()
        state_key = product_type.value.lower()
        
        # Add fulfillment time annotation if demand was met
        met_time = state.demand_met_times.get(state_key)
        if met_time is not None:
            ax.axvline(x=met_time, color=color, linestyle='--', alpha=0.3)
            ax.text(
                met_time,
                target_demand * 1.05,
                f"Met at t={met_time:.0f}",
                color=color,
                rotation=90,
                verticalalignment='bottom'
            )

    def _format_production_plot(
        self,
        ax: plt.Axes,
        timestamps: List[float],
        y_max: float,
        product_mapping: Dict[OutputType, str],
        state: SimulationState,
        demand_data: Dict[str, Any],
    ) -> None:
        """Format axes and legend for production plot"""
        setup_axis_labels(
            ax,
            "Product Production vs Targets",
            ylabel=f"Volume ({VOLUME_LABEL})"
        )
        
        ax.set_xlim(timestamps[0], timestamps[-1])
        ax.set_ylim(0, y_max)
        
        # Create legend entries
        legend_entries = []
        for pt, sk in product_mapping.items():
            current = f"Current: {pt.value} ({state.total_products[sk]:.1f} m³, {(state.total_products[sk]/demand_data['national_demand'][sk]*100):.1f}%)"
            target = f"Target: {pt.value} ({demand_data['national_demand'][sk]:.1f} m³)"
            legend_entries.extend([current, target])
            
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        ax.grid(True, linestyle="--", alpha=GRID_ALPHA)
