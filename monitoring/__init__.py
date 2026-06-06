"""Monitoring, analysis, and visualization package.

Intentionally empty of re-exports: importers must reach for the concrete
submodule (``from monitoring.serialization import jsonify``) rather than
the package root. Keeping ``__init__`` free of eager submodule imports is what
lets ``python -m monitoring.<module>`` resolve without dragging in the heavy
(plotly-backed) visualization modules and reopening the import cycle.
"""
