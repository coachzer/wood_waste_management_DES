"""In-memory store for the raw monitor history.

Owns the polled history dicts the live recorder writes into and the
serializer reads from: ``generation_``, ``collection_``, ``processing_``,
``environmental_``, ``landfill_``, ``event_`` and ``entity_status_history``.
The roles are split one each: ``WasteMonitor`` writes data, this store holds
it, the serializer reads it. The store also authors the per-entity *schemas*:
the ``ensure_*`` methods own the empty-dict templates that define each history
entry's shape, so the recorder only appends samples and authors no dict
literals.

Two of the histories are *ledgers* the store writes itself, because they are
the single record of a physical fate and have two independent readers:

- ``landfill_history`` (``record_landfill``): every landfill resolved by
  ``handle_storage_event``, attributed to the dumping entity. Read by the
  mass-balance monitor (the raw-waste discard term, ADR 0009) and by
  ``extract_kpis`` (``landfill_volume_m3`` / ``landfill_cost``) through the
  same module-level readers, so the two can never diverge.
- ``environmental_history`` (``record_emission``): every operational
  emission, by entity and kind. Read by ``extract_kpis``
  (``total_emissions_kgco2e``) and the environmental plots.

Landfill used to be written three times per event (an entity attribute, a
per-name counter on ``SimulationState``, and an entity-less monitor bucket)
with the invariant reading one copy and the KPI another; one ledger, one
writer, shared readers closes that hole.

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
from typing import Any, Dict

# The emission kinds the ledger accepts; each is a per-tick series column in
# the per-entity environmental_history entry, beside their ``total_impact`` sum.
EMISSION_KINDS = ("carbon_emissions", "transport_emissions", "landfill_emissions")


# --- Ledger readers ----------------------------------------------------------
# Pure functions over the plain history dicts, so the live monitor (reading the
# store) and the post-hoc KPI layer (reading the exported / deserialized copy)
# compute the same totals from the same code path.


def landfilled_volume_by_entity(landfill_history: Dict[str, Any]) -> Dict[str, float]:
    """Total raw waste landfilled per entity (m3), from the landfill ledger."""
    return {
        entity_name: float(sum(entry.get("volumes", []) or []))
        for entity_name, entry in landfill_history.items()
    }


def total_landfilled_volume(landfill_history: Dict[str, Any]) -> float:
    """System-wide raw waste landfilled (m3)."""
    return float(sum(landfilled_volume_by_entity(landfill_history).values()))


def total_landfill_cost(landfill_history: Dict[str, Any]) -> float:
    """System-wide landfill gate cost, summed over every landfill event."""
    return float(
        sum(
            sum(entry.get("costs", []) or [])
            for entry in landfill_history.values()
        )
    )


def total_emissions_kgco2e(environmental_history: Dict[str, Any]) -> float:
    """System-wide operational emissions (kg CO2e), all kinds and entities.

    ``total_impact`` is a per-timestamp series (``record_emission`` opens a
    fresh slot per new timestamp), so the run total is the sum, not the last
    element -- unlike the cumulative processed/generated series.
    """
    total = 0.0
    for entry in environmental_history.values():
        series = entry.get("total_impact", [])
        if isinstance(series, list) and series:
            total += float(sum(series))
    return total


class HistoryStore:
    """Holds the raw history dicts and authors their per-entity schemas.

    The recorder writes (appends) into the dicts; the serializer reads them.
    The two ledgers (``record_landfill`` / ``record_emission``) are written
    through the store directly.
    """

    def __init__(self):
        self.generation_history = {}
        self.collection_history = {}
        self.processing_history = {}
        self.environmental_history = {}
        self.landfill_history = {}
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
    def get_landfill_history(self):
        return dict(self.landfill_history)

    @property
    def get_event_history(self):
        return dict(self.event_history)

    # --- Ledgers -------------------------------------------------------------

    def record_landfill(self, entity_name, composition, cost, timestamp):
        """Append one landfill event to the dumping entity's ledger entry.

        ``composition`` is the per-WasteType breakdown of the landfilled volume
        (m3); its total is the mass-balance discard term (ADR 0009) and the
        per-type split is kept so the density-weighted cost (ADR 0013) stays
        auditable. Snapshotted with ``dict()`` so a caller reusing its dict
        cannot mutate the ledger afterwards.
        """
        self.ensure_landfill(entity_name)
        entry = self.landfill_history[entity_name]
        entry["timestamps"].append(timestamp)
        entry["volumes"].append(float(sum(composition.values())))
        entry["costs"].append(cost)
        entry["compositions"].append(dict(composition))

    def record_emission(self, entity_name, kind, kgco2e, timestamp):
        """Accrue ``kgco2e`` of ``kind`` to the entity's per-timestamp slot.

        A new slot (one zeroed value per kind plus ``total_impact``) is opened
        when ``timestamp`` advances past the last recorded one; same-timestamp
        emissions accumulate into the open slot. ``kind`` must be one of
        ``EMISSION_KINDS`` -- an unknown kind is a programming error, not a
        warning.
        """
        if kind not in EMISSION_KINDS:
            raise ValueError(
                f"Unknown emission kind {kind!r}; expected one of {EMISSION_KINDS}"
            )
        self.ensure_environmental(entity_name)
        entry = self.environmental_history[entity_name]
        if not entry["timestamps"] or timestamp > entry["timestamps"][-1]:
            entry["timestamps"].append(timestamp)
            for emission_kind in EMISSION_KINDS:
                entry[emission_kind].append(0.0)
            entry["total_impact"].append(0.0)
        entry[kind][-1] += kgco2e
        entry["total_impact"][-1] += kgco2e

    def landfilled_volume_by_entity(self):
        """Live view of the landfill ledger totals per entity (m3)."""
        return landfilled_volume_by_entity(self.landfill_history)

    def total_landfilled_volume(self):
        """Live system-wide landfilled volume (m3)."""
        return total_landfilled_volume(self.landfill_history)

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
                "total_uncollected": {},
                "total_outlet": {},
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
        """Initialize the system-event history entry if it does not yet exist.

        Carries storage expansions only; landfills live in ``landfill_history``
        (the ``record_landfill`` ledger). ``total_costs`` mirrors
        ``expansion_costs`` and is kept for the event-cost timeline readers.
        """
        if event_key not in self.event_history:
            self.event_history[event_key] = {
                "timestamps": [],
                "storage_expansions": [],
                "expansion_costs": [],
                "total_costs": []
            }

    def ensure_environmental(self, entity_name):
        """Initialize the per-entity environmental history entry if it does not yet exist."""
        if entity_name not in self.environmental_history:
            entry = {"timestamps": []}
            for emission_kind in EMISSION_KINDS:
                entry[emission_kind] = []
            entry["total_impact"] = []
            self.environmental_history[entity_name] = entry

    def ensure_landfill(self, entity_name):
        """Initialize the per-entity landfill ledger entry if it does not yet exist."""
        if entity_name not in self.landfill_history:
            self.landfill_history[entity_name] = {
                "timestamps": [],
                "volumes": [],
                "costs": [],
                "compositions": [],
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
