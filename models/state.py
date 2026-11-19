from typing import Optional


class SimulationState:
    """Holds the state of one simulation run.

    Injected through entity constructors (SimulationManager creates one
    instance per run and passes it to FacilityBuilder, which threads it to
    every entity). Not a singleton -- each run owns an independent instance, so
    two runs can coexist in one process without cross-talk.
    """

    def __init__(self):
        self.generators = []
        self.collectors = []
        self.treatment_operators = []
        self.transport_flows = []
        self.consumption_events = []

    def initialize(self, generators, collectors, treatment_operators):
        self.generators = generators
        self.collectors = collectors
        self.treatment_operators = treatment_operators

    def iter_outbound_vehicles(self):
        """Yield every in-transit vehicle across all collectors' fleets.

        The single point that knows where all transport waste lives mid-flight,
        so a monitor can sum waste in transit by type (each vehicle exposes
        ``current_load_by_type``) for the waste-side mass-balance invariant.
        """
        for collector in self.collectors:
            for vehicle in collector.vehicles:
                if vehicle.in_transit:
                    yield vehicle

    def scheduled_reposition_volume_by_destination(self) -> dict:
        """Repositioning volume on a vehicle, logged as inflow but not yet deposited.

        The collector->collector flow is logged when the transport is scheduled;
        the destination center only receives it on arrival. Keyed by the
        destination collector named in that flow.
        """
        in_flight = {}
        for collector in self.collectors:
            for transport in collector.active_transports:
                target_name = transport["target_name"]
                in_flight[target_name] = in_flight.get(target_name, 0.0) + transport["volume"]
        return in_flight

    def held_transfer_volume_by_collector(self) -> dict:
        """Volume held for queued transfers, by sending collector (ADR 0041).

        It left the sending center at request time and is on no vehicle yet, so neither
        ``current_storage`` nor ``iter_outbound_vehicles`` sees it.
        """
        held = {}
        transport_managers = {}
        for collector in self.collectors:
            transport_manager = getattr(collector, "transport_manager", None)
            if transport_manager is not None:
                transport_managers[id(transport_manager)] = transport_manager
        for transport_manager in transport_managers.values():
            for name, volume in transport_manager.held_volume_by_requester().items():
                held[name] = held.get(name, 0.0) + volume
        return held

    def track_transport_flow(self, source_type: str, source_name: str, 
                           target_type: str, target_name: str, 
                           waste_type, volume: float, timestamp: float,
                           transport_method: str = "vehicle"):
        """Track transport flows between entities"""
        self.transport_flows.append({
            'source_type': source_type,
            'source_name': source_name,
            'target_type': target_type,
            'target_name': target_name,
            'waste_type': waste_type.value if hasattr(waste_type, 'value') else str(waste_type),
            'volume': volume,
            'timestamp': timestamp,
            'transport_method': transport_method
        })

    def record_consumption_event(self, operator_name: str, product: str,
                                 attempted: float, consumed: float,
                                 reason: str = None, timestamp: float = None) -> None:
        """Record a single market consumption event for service-level accounting.

        One event is one (operator, product) attempt at a market tick.
        ``attempted`` is the demand presented; ``consumed`` the portion fulfilled.
        The shortfall is lost sales tagged by ``reason`` -- ``"no_capability"`` (the
        operator cannot produce the product) or ``"stockout"`` (it can but inventory
        was short), recorded only when a shortfall exists.
        """
        lost = max(0.0, attempted - consumed)
        self.consumption_events.append({
            'timestamp': timestamp,
            'operator': operator_name,
            'product': product,
            'attempted': attempted,
            'consumed': consumed,
            'lost': lost,
            'reason': reason if lost > 0 else None,
        })

    @property
    def total_attempted_consumption(self) -> float:
        """Total demand volume presented to operators across all events."""
        return sum(event['attempted'] for event in self.consumption_events)

    @property
    def total_consumed(self) -> float:
        """Total volume fulfilled from finished-goods inventory."""
        return sum(event['consumed'] for event in self.consumption_events)

    @property
    def no_capability_lost(self) -> float:
        """Lost sales from operators structurally unable to make the product."""
        return sum(event['lost'] for event in self.consumption_events
                   if event['reason'] == 'no_capability')

    @property
    def stockout_lost(self) -> float:
        """Lost sales from capable operators whose inventory was insufficient."""
        return sum(event['lost'] for event in self.consumption_events
                   if event['reason'] == 'stockout')

    @property
    def full_service_level(self) -> Optional[float]:
        """Headline service level: total_consumed / total_attempted.

        Includes both no-capability and stockout lost sales. Returns ``None``
        when no consumption has been attempted yet (undefined, not zero).
        """
        attempted = self.total_attempted_consumption
        if attempted <= 0:
            return None
        return self.total_consumed / attempted

    @property
    def operational_service_level(self) -> Optional[float]:
        """Diagnostic service level over operationally-fulfillable demand.

        total_consumed / (total_attempted - no_capability_lost) -- measures
        policy effectiveness on demand the system could actually satisfy.
        Returns ``None`` when no fulfillable demand has been attempted.
        """
        feasible = self.total_attempted_consumption - self.no_capability_lost
        if feasible <= 0:
            return None
        return self.total_consumed / feasible

    def service_level(self, operator_name: str = None, product: str = None,
                      kind: str = "full") -> Optional[float]:
        """Service level filtered by operator and/or product.

        ``kind`` selects ``"full"`` (all lost sales) or ``"operational"``
        (excludes no-capability lost sales from the denominator). Returns
        ``None`` when the filtered slice has no fulfillable demand.
        """
        events = self.consumption_events
        if operator_name is not None:
            events = [event for event in events if event['operator'] == operator_name]
        if product is not None:
            events = [event for event in events if event['product'] == product]

        attempted = sum(event['attempted'] for event in events)
        if kind == "operational":
            attempted -= sum(event['lost'] for event in events
                             if event['reason'] == 'no_capability')
        if attempted <= 0:
            return None
        return sum(event['consumed'] for event in events) / attempted
