"""
Deprecated: This module is maintained for backwards compatibility.
New code should use the optimization.uncertainty package instead.
"""
import warnings
from optimization.uncertainty import (
    UncertaintySet,
    create_default_uncertainty_set,
    ScenarioGenerator,
    ScenarioGenerationError,
    StochasticOptimizer
)

# Emit deprecation warning
warnings.warn(
    "The optimization.stochastic module is deprecated. "
    "Use optimization.uncertainty instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export for backwards compatibility
__all__ = [
    'UncertaintySet',
    'create_default_uncertainty_set',
    'ScenarioGenerator',
    'TwoStageOptimizer'  # Legacy name
]

# Alias for backwards compatibility
class TwoStageOptimizer(StochasticOptimizer):
    """
    Deprecated: Use StochasticOptimizer from optimization.uncertainty instead.
    
    This class is maintained for backwards compatibility only.
    """
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "TwoStageOptimizer is deprecated. Use StochasticOptimizer instead.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init__(*args, **kwargs)

    def optimize(self, *args, **kwargs):
        """
        Deprecated: Use StochasticOptimizer.optimize instead.
        """
        warnings.warn(
            "This method is deprecated. Use StochasticOptimizer.optimize instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return super().optimize(*args, **kwargs)
