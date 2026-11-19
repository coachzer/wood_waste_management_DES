"""Plot styling shared by every figure script.

Two encodings coexist on purpose:

- The Matplotlib paper figures (policy comparison, Pareto, KPI families) use
  marker shape per inventory policy and colour per stock strategy (the caption
  convention). Bars cannot carry a marker, so they hatch PULL instead.
- The Plotly comparison suite uses colour per inventory policy and marker symbol
  per stock strategy.

The dicts are keyed by enum ``.value`` strings because the figures read policy
and strategy back from combo labels and CSV rows. A new ``StockStrategy`` member
with no entry here makes a figure's style lookup raise ``KeyError`` rather than
plot unstyled.
"""
from datetime import datetime

from models.enums import StockStrategy

# Matplotlib paper figures.
POLICY_MARKERS = {"push": "o", "pull": "^"}
STRATEGY_COLORS = {
    "on_demand": "#1f77b4",
    "reorder_50": "#ff7f0e",
    "reorder_90": "#2ca02c",
}
STRATEGY_LABELS = {strategy.value: strategy.name for strategy in StockStrategy}
PULL_HATCH = "//"

# Single-column journal figure size in inches.
FIGURE_SIZE_INCHES = (7, 5)

# Fixed PDF dates so re-rendering the same data gives a byte-identical file.
REPRODUCIBLE_PDF_METADATA = {
    "CreationDate": datetime(1970, 1, 1, 0, 0, 0),
    "ModDate": datetime(1970, 1, 1, 0, 0, 0),
}

# Emissions are scaled to kilotonnes for a readable axis (raw values run ~1e6-2e7
# kg CO2e). The divisor is exact, so it shifts only the axis label, not the data.
KG_PER_KILOTONNE = 1_000_000.0

# Plotly comparison suite.
POLICY_COLORS = {"push": "#1f77b4", "pull": "#ff7f0e"}
STRATEGY_SYMBOLS = {"on_demand": "circle", "reorder_50": "square", "reorder_90": "diamond"}
