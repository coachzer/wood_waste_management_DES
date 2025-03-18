from typing import Dict, Any, List, Optional, Tuple
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from ..visualizations.plot_utils import (
    DEFAULT_FIGURE_SIZE,
    save_plot,
)

class BasePlotter:
    """Base class for all plotters with common functionality"""
    
    def __init__(self):
        self.window = 5  # Default window size for moving averages
        
    def get_timestamps(self, history: Dict[str, Any]) -> List[float]:
        """Extract timestamps from history data"""
        return next(iter(history.values()))["timestamps"]
        
    def setup_figure(self, rows: int = 1, cols: int = 1, figsize: Optional[Tuple[float, float]] = None) -> Tuple[plt.Figure, List[plt.Axes]]:
        """Create figure and axes with specified layout"""
        fig = plt.figure(figsize=figsize or DEFAULT_FIGURE_SIZE)
        gs = GridSpec(rows, cols, figure=fig)
        axes = [fig.add_subplot(gs[i]) for i in range(rows * cols)]
        return fig, axes
        
    def save_figure(self, fig: plt.Figure, save_path: Optional[str]) -> None:
        """Save figure if path is provided"""
        plt.tight_layout()
        save_plot(fig, save_path)
