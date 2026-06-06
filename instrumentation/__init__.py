"""Instrumentation space: live recorders + the in-memory store.

Top of the four-space stack -- writes raw simulation history. Populated by later
clean-monitoring slices (WasteMonitor-as-recorder and MassBalance move here in
issues 07/09/10); intentionally empty for now.
"""
