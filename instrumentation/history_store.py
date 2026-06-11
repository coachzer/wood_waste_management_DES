"""In-memory store for the raw monitor history.

Owns the six polled history dicts the live recorder writes into and the
serializer reads from: ``generation_``, ``collection_``, ``processing_``,
``environmental_``, ``event_`` and ``entity_status_history``. The roles are
split one each: ``WasteMonitor`` writes data, this store holds it, the
serializer reads it. The store also authors the per-entity *schemas*: the
``ensure_*`` methods own the empty-dict templates that define each history
entry's shape, so the recorder only appends samples and authors no dict
literals.

The getters return a shallow top-level copy (``dict(...)``) so a caller cannot
mutate the store's spine while still sharing the per-entity history nodes, which
is exactly what ``SimulationManager.get_monitor_data`` relies on.

The ``ensure_*`` methods are idempotent guards (init-if-absent); they preserve
the recorder's original insertion order because it calls them in the same
sequence the inline guards used to run. The dict-literal key order is load-bearing
-- it sets insertion order into the raw sidecars -- so the templates moved here
verbatim and must not be reordered.
"""
import os
import json


class HistoryStore:
    """Holds the six raw history dicts and authors their per-entity schemas.

    The recorder writes (appends) into the dicts; the serializer reads them.
    """

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
        self.product_types = self._get_product_types()

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

    def ensure_generation(self, generator_name):
        """Initialize the per-generator history entry if it does not yet exist.

        The only generator cost series is ``holding_costs`` (daily accrual on
        stored waste). The former ``energy_costs`` / ``operational_costs`` /
        ``total_costs`` lists were permanent 0.0 stubs -- ``update_entity_costs``
        was never called for generators -- and stay removed (cleanup #10).
        """
        if generator_name not in self.generation_history:
            self.generation_history[generator_name] = {
                "timestamps": [],
                "volumes": {},
                "efficiency": [],
                "total_generated": {},
                "total_potential_generated": {},
                "storage_utilization": [],
                "status": [],
                "holding_costs": [],
            }

    def ensure_collection(self, collector_name):
        """Initialize the per-collector history entry if it does not yet exist."""
        if collector_name not in self.collection_history:
            self.collection_history[collector_name] = {
                "timestamps": [],
                "collected_volumes": {},
                "efficiency": [],
                "transport_costs": [],
                "storage_utilization": [],
                "status": [],
                "energy_costs": [],
                "operational_costs": [],
                "total_costs": [],
                "holding_costs": [],
            }

    def ensure_processing(self, treatment_name):
        """Initialize the per-treatment history structure if it does not yet exist.

        Only consumed series are recorded (VIZ-REVIEW T7): the per-WasteType
        ``by_type`` breakdowns, ``finished_goods_by_type``, ``products.total``,
        ``products.quality``, and ``operational.energy_consumption`` were
        write-only and are no longer part of the schema.
        """
        if treatment_name not in self.processing_history:
            product_types = self.product_types
            self.processing_history[treatment_name] = {
                "timestamps": [],
                "storage": {
                    "total": [],
                    "utilization": [],
                    "waste_utilization": [],
                    "finished_goods_utilization": [],
                },
                "processed": {
                    "total": [],
                },
                "products": {
                    "by_type": {ptype: [] for ptype in product_types},
                },
                "operational": {
                    "energy_costs": [],
                    "processing_costs": [],
                    "total_costs": [],
                    "holding_costs": [],
                },
                "status": [],
            }

    def ensure_event(self, event_key):
        """Initialize the system-event history entry if it does not yet exist."""
        if event_key not in self.event_history:
            self.event_history[event_key] = {
                "timestamps": [],
                "landfill_usage": [],
                "storage_expansions": [],
                "landfill_costs": [],
                "expansion_costs": [],
                "total_costs": []
            }

    def ensure_environmental(self, entity_name):
        """Initialize the per-entity environmental history entry if it does not yet exist."""
        if entity_name not in self.environmental_history:
            self.environmental_history[entity_name] = {
                "timestamps": [],
                "carbon_emissions": [],
                "transport_emissions": [],
                "landfill_emissions": [],
                "total_impact": [],
            }

    def ensure_entity_status(self, category, entity_name):
        """Initialize the per-entity status-history entry under ``category`` if absent."""
        if entity_name not in self.entity_status_history[category]:
            self.entity_status_history[category][entity_name] = {
                "timestamps": [],
                "status": []
            }

    def _get_product_types(self):
        """Load product types from demand.json"""
        demand_path = os.path.join(os.path.dirname(__file__), '../data/demand.json')
        try:
            with open(demand_path, 'r') as f:
                data = json.load(f)
            return list(data.get('national_demand', {}).keys())
        except Exception:
            return []
