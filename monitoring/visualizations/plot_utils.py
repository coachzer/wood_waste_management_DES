import os
from typing import List, Optional, Dict
from matplotlib import pyplot as plt

# Constants for plot styling
VOLUME_LABEL = "Volume (m³)"
STORAGE_UTIL_LABEL = "Storage Utilization (%)"
YEAR_1_2_LABEL = "Year 1-2"
YEAR_2_3_LABEL = "Year 2-3"
DEFAULT_FIGURE_SIZE = (15, 10)
GRID_ALPHA = 0.7
LEGEND_FONTSIZE = 8


def setup_plot_directory():
    """Ensure the plots directory exists"""
    if not os.path.exists("plots"):
        os.makedirs("plots")


def add_year_demarcations(ax: plt.Axes, labels: bool = True) -> None:
    """Add vertical lines for year transitions"""
    ax.axvline(
        x=100,
        color="gray",
        linestyle="--",
        alpha=0.5,
        label=YEAR_1_2_LABEL if labels else None,
    )
    ax.axvline(
        x=200,
        color="gray",
        linestyle="--",
        alpha=0.5,
        label=YEAR_2_3_LABEL if labels else None,
    )


def save_plot(fig: plt.Figure, save_path: Optional[str], dpi: int = 300) -> None:
    """Save the plot if a path is provided"""
    if save_path:
        setup_plot_directory()
        fig.savefig(save_path, bbox_inches="tight", dpi=dpi)
        print(f"Plot saved to: {save_path}")
    plt.close()


def create_entity_groups(
    data_dict: dict, metric_key: str, show_top_n: int = 5, group_threshold: float = 5.0
) -> tuple:
    """
    Group entities based on their average metric values.

    Args:
        data_dict: Dictionary containing entity data
        metric_key: Key to access the metric values
        show_top_n: Number of top entities to show individually
        group_threshold: Threshold for grouping entities

    Returns:
        tuple: (top_entities, remaining_entities, grouped_entities)
    """
    # Calculate average values
    avg_values = {}
    for name, data in data_dict.items():
        values = _extract_metric_values(data, metric_key)
        if values:
            avg_values[name] = sum(values) / len(values)

    # Sort entities by average value
    sorted_entities = sorted(avg_values.items(), key=lambda x: x[1], reverse=True)

    # Separate into groups
    top_entities = sorted_entities[:show_top_n]
    other_entities = sorted_entities[show_top_n:]
    grouped_entities = [x for x in other_entities if x[1] < group_threshold]
    remaining_entities = [x for x in other_entities if x[1] >= group_threshold]

    return top_entities, remaining_entities, grouped_entities


def _extract_metric_values(data: dict, metric_key: str) -> List[float]:
    """Extract metric values from nested dictionary structure"""
    if isinstance(metric_key, str):
        keys = metric_key.split(".")
    else:
        keys = [metric_key]

    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return []

    if isinstance(current, list):
        return current
    return []


def setup_axis_labels(
    ax: plt.Axes,
    title: str,
    xlabel: str = "Time",
    ylabel: str = None,
    title_fontsize: int = 12,
    title_pad: int = 10,
) -> None:
    """Set up common axis labels and styling"""
    ax.set_title(title, fontsize=title_fontsize, pad=title_pad)
    ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=GRID_ALPHA)


def create_grouped_plot(
    ax: plt.Axes,
    data_dict: dict,
    metric_key: str,
    show_top_n: int = 5,
    group_threshold: float = 5.0,
    marker: str = "o",
    markersize: int = 4,
    alpha: float = 0.5,
) -> None:
    """Create a plot with grouped entities based on their importance"""
    top_entities, remaining_entities, grouped_entities = create_entity_groups(
        data_dict, metric_key, show_top_n, group_threshold
    )

    # Plot top entities
    for name, avg_value in top_entities:
        values = _extract_metric_values(data_dict[name], metric_key)
        timestamps = data_dict[name].get("timestamps", range(len(values)))
        ax.plot(
            timestamps,
            values,
            label=f"{name} ({avg_value:.1f}%)",
            marker=marker,
            markersize=markersize,
            linestyle="-",
            linewidth=2,
        )

    # Plot remaining individual entities
    for name, avg_value in remaining_entities:
        values = _extract_metric_values(data_dict[name], metric_key)
        timestamps = data_dict[name].get("timestamps", range(len(values)))
        ax.plot(
            timestamps,
            values,
            label=f"{name} ({avg_value:.1f}%)",
            alpha=alpha,
            linewidth=1,
        )

    # Plot grouped entities if any
    if grouped_entities:
        _plot_grouped_entities(
            ax, data_dict, grouped_entities, metric_key, group_threshold
        )


def calculate_moving_average(data: List[float], window: int = 5) -> List[float]:
    """Calculate moving average of a time series.
    
    Args:
        data: List of values to calculate moving average for
        window: Window size for the moving average calculation
        
    Returns:
        List of moving average values
    """
    return [
        sum(data[max(0, i - window) : min(len(data), i + window + 1)])
        / (min(len(data), i + window + 1) - max(0, i - window))
        for i in range(len(data))
    ]

def add_moving_average_plot(
    ax: plt.Axes,
    timestamps: List[float],
    data: List[float],
    label: str,
    color: str,
    window: int = 5,
    alpha: float = 0.2
) -> None:
    """Add raw data and moving average plots to axes.
    
    Args:
        ax: Matplotlib axes to plot on
        timestamps: List of timestamp values
        data: List of data values
        label: Label for the plot legend
        color: Color for the plot lines
        window: Window size for moving average calculation
        alpha: Alpha value for raw data plot
    """
    # Plot raw data
    ax.plot(
        timestamps,
        data,
        alpha=alpha,
        color=color,
        label=f"{label} (Raw)",
    )
    
    # Calculate and plot moving average
    ma = calculate_moving_average(data, window)
    ax.plot(
        timestamps,
        ma,
        color=color,
        linewidth=2,
        label=f"{label} (MA)"
    )

def plot_multi_series(
    ax: plt.Axes,
    timestamps: List[float],
    series_data: Dict[str, List[float]],
    colors: Dict[str, str],
    title: str,
    ylabel: str,
    window: int = 5,
    alpha: float = 0.2
) -> None:
    """Plot multiple time series with moving averages.
    
    Args:
        ax: Matplotlib axes to plot on
        timestamps: List of timestamp values
        series_data: Dictionary mapping series names to data values
        colors: Dictionary mapping series names to colors
        title: Title for the plot
        ylabel: Label for y-axis
        window: Window size for moving average calculation
        alpha: Alpha value for raw data plots
    """
    for name, data in series_data.items():
        add_moving_average_plot(
            ax=ax,
            timestamps=timestamps,
            data=data,
            label=name,
            color=colors[name],
            window=window,
            alpha=alpha
        )
    
    setup_axis_labels(ax, title, ylabel=ylabel)
    ax.legend()
    ax.grid(True, linestyle="--", alpha=GRID_ALPHA)

def _plot_grouped_entities(
    ax: plt.Axes,
    data_dict: dict,
    grouped_entities: List[tuple],
    metric_key: str,
    group_threshold: float,
) -> None:
    """Plot the average of grouped entities"""
    # Get reference timestamps from first entity
    first_entity = next(iter(data_dict.values()))
    reference_timestamps = first_entity.get("timestamps", [])

    if not reference_timestamps:
        return

    # Calculate average values for each timestamp
    grouped_data = []
    for t_idx in range(len(reference_timestamps)):
        values = []
        for name, _ in grouped_entities:
            metric_values = _extract_metric_values(data_dict[name], metric_key)
            if t_idx < len(metric_values):
                values.append(metric_values[t_idx])
        grouped_data.append(sum(values) / len(values) if values else 0)

    # Plot grouped data
    ax.plot(
        reference_timestamps,
        grouped_data,
        label=f"Others (<{group_threshold}% avg) [{len(grouped_entities)} entities]",
        color="gray",
        alpha=0.5,
        linestyle="--",
    )
