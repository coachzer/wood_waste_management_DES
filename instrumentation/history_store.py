"""In-memory store for the raw monitor history.

Owns the six polled history dicts the live recorder writes into and the
serializer reads from: ``generation_``, ``collection_``, ``processing_``,
``environmental_``, ``event_`` and ``entity_status_history``. Splitting the
container out of ``WasteMonitor`` (clean-monitoring issue 09) leaves the recorder
writing data, this store holding it, and the serializer reading it -- one role
each.

The getters return a shallow top-level copy (``dict(...)``) so a caller cannot
mutate the store's spine while still sharing the per-entity history nodes, which
is exactly what ``SimulationManager.get_monitor_data`` relies on.
"""


class HistoryStore:
    """Holds the six raw history dicts; the recorder writes, the serializer reads."""

    def __init__(self):
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}
        self.environmental_history = {}
        self.event_history = {}
        self.entity_status_history = {
            "generators": {},
            "collectors": {},
            "treatments": {}
        }

    @property
    def get_generation_history(self):
        return dict(self.generation_history)

    @property
    def get_collection_history(self):
        return dict(self.collection_history)

    @property
    def get_processing_history(self):
        return dict(self.processing_history)

    @property
    def get_environmental_history(self):
        return dict(self.environmental_history)

    @property
    def get_event_history(self):
        return dict(self.event_history)

    @property
    def get_entity_status_history(self):
        return dict(self.entity_status_history)
