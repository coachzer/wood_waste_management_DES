"""Post-hoc analysis space: ``extract_kpis`` + the metric families it composes.

Reads persisted run/raw data and computes KPIs (bullwhip, flow times, avoided
emissions, biogenic carbon) plus the post-hoc comparators (paired/CRN, stochastic
dominance, pareto). Kept free of eager submodule re-exports so ``python -m
analysis.<module>`` resolves without dragging in the visualization stack.
"""
