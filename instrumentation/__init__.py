"""Instrumentation space: live recorders + the in-memory store.

Top of the four-space stack -- writes raw simulation history. Holds the
``WasteMonitor`` recorder (polls entities and appends samples), the
``HistoryStore`` container (owns the raw history dicts and their per-entity
schemas), and the ``mass_balance`` invariant checks.
"""
