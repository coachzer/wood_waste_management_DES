"""Visualization space: all plotting.

Bottom of the four-space stack. Holds the Plotly grid-mode comparison suite
(``scenario_comparison`` drawing ``temporal_comparison``,
``storage_visualization`` and ``summary_visualization``), the MFA Sankey
(``mfa_visualization``, which also reads the live simulation state), the
Matplotlib baseline figures (``policy_comparison_figure``,
``pareto_visualization``, ``kpi_family_figures``) and shared extraction
helpers (``visualization_utils``).
"""
