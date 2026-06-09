"""Visualization space: all plotting; reads computed results, never raw sim state.

Bottom of the four-space stack. Holds the Plotly comparison suite
(``scenario_comparison`` orchestrating ``temporal_comparison``,
``storage_visualization``, ``summary_visualization``), the MFA Sankey
(``mfa_visualization``), the Pareto parallel-coordinates view
(``pareto_visualization``), the Matplotlib paper figure
(``policy_comparison_figure``), and shared extraction helpers
(``visualization_utils``).
"""
