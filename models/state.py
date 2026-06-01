from typing import Optional
from utils.helpers import load_json
from models import regional_tracker

# Load demand data
_demand_data = load_json("data/demand.json")


class SimulationState:
    """Singleton class to store the state of the simulation environment."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.generators = []
            cls._instance.collectors = []
            cls._instance.treatment_operators = []
            # Initialize transport flows
            cls._instance.transport_flows = []
            # Initialize regional waste tracker
            cls._instance.waste_tracker = regional_tracker.RegionalWasteTracker()
            # Initialize product tracking with values from demand.json
            demand = _demand_data["national_demand"]
            cls._instance.total_products = {
                'mdf': 0,
                'particle_board': 0,
                'osb': 0
            }
            # Finished goods removed from inventory without consumption (mass-balance
            # discard term, ADR 0002 Phase E.5). Zero by construction -- the
            # partial-batch headroom clamp leaves no discard path; the counter
            # exists so the mass-balance identity is explicit and as a guard.
            cls._instance.production_discarded = {
                'mdf': 0.0,
                'particle_board': 0.0,
                'osb': 0.0
            }
            cls._instance.target_demands = {
                'mdf': demand["mdf"],
                'particle_board': demand["particle_board"],
                'osb': demand["osb"]
            }
            # Track when each demand was met
            cls._instance.demand_met_times = {
                'mdf': None,
                'particle_board': None,
                'osb': None
            }
            # Market consumption event log (demand-as-consumption model, ADR 0002)
            cls._instance.consumption_events = []
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls() if cls._instance is None else cls._instance

    def initialize(self, generators, collectors, treatment_operators):
        self.generators = generators
        self.collectors = collectors
        self.treatment_operators = treatment_operators

    def track_add_waste(self, region, waste_type, amount):
        """Track waste generation in a specific region"""
        if not region:
            return
        try:
            self.waste_tracker.add_waste(region, waste_type, amount)
        except KeyError as e:
            print(f"Warning: Could not track waste generation - {str(e)}")

    def track_remove_waste(self, region, waste_type, amount):
        """Track waste removal from a specific region"""
        if not region:
            return 0
        try:
            return self.waste_tracker.remove_waste(region, waste_type, amount)
        except KeyError as e:
            print(f"Warning: Could not track waste removal - {str(e)}")
            return 0
        
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

    def get_regional_waste_stats(self, region):
        """Get waste statistics for a specific region"""
        if not region:
            return {}
        try:
            return self.waste_tracker.get_regional_stats(region)
        except KeyError as e:
            print(f"Warning: Could not get regional stats - {str(e)}")
            return {}
            
    def track_product_production(self, product_type: str, amount: float, current_time: float = None) -> None:
        """Track production of final products"""
        if product_type in self.total_products:
            self.total_products[product_type] += amount
            target = self.target_demands[product_type]
            print(f"- {product_type}: {self.total_products[product_type]:.2f}/{target:.2f} m³")
            
            # Check if this production met the demand
            if current_time is not None and self.demand_met_times[product_type] is None:
                if self.total_products[product_type] >= self.target_demands[product_type]:
                    self.demand_met_times[product_type] = current_time
            
    def check_all_demands_met(self) -> bool:
        """Check if all product demands have been met"""
        return all(
            self.total_products[product] >= demand 
            for product, demand in self.target_demands.items()
        )
        
    def get_unmet_demands(self) -> dict:
        """Get dictionary of unmet demands for each product"""
        return {
            product: max(0, demand - self.total_products[product])
            for product, demand in self.target_demands.items()
        }

    def record_consumption_event(self, operator_name: str, product: str,
                                 attempted: float, consumed: float,
                                 reason: str = None, timestamp: float = None) -> None:
        """Record a single market consumption event for service-level accounting.

        One event is one (operator, product) consumption attempt at a market
        tick. ``attempted`` is the demand volume presented to the operator;
        ``consumed`` is the portion fulfilled from finished-goods inventory.
        The shortfall ``attempted - consumed`` is lost sales tagged by
        ``reason`` -- ``"no_capability"`` when the operator cannot produce the
        product at all, ``"stockout"`` when it can but inventory was
        insufficient. ``reason`` is recorded only when a shortfall exists.
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

    def reset(self):
        """Reset simulation state to initial values"""
        self.generators = []
        self.collectors = []
        self.treatment_operators = []
        self.transport_flows = []
        self.waste_tracker = regional_tracker.RegionalWasteTracker()
        demand = _demand_data["national_demand"]
        self.total_products = {
            'mdf': 0,
            'particle_board': 0,
            'osb': 0
        }
        self.production_discarded = {
            'mdf': 0.0,
            'particle_board': 0.0,
            'osb': 0.0
        }
        self.target_demands = {
            'mdf': demand["mdf"],
            'particle_board': demand["particle_board"],
            'osb': demand["osb"]
        }
        # Reset demand met times
        self.demand_met_times = {
            'mdf': None,
            'particle_board': None,
            'osb': None
        }
        # Reset market consumption event log
        self.consumption_events = []

    def get_transport_flow_summary(self):
        """Get summary of transport flows for debugging"""
        if not self.transport_flows:
            return "No transport flows recorded"
        
        summary = []
        summary.append(f"Total transport flows: {len(self.transport_flows)}")
        
        flow_types = {}
        for flow in self.transport_flows:
            key = f"{flow['source_type']} → {flow['target_type']}"
            if key not in flow_types:
                flow_types[key] = {"count": 0, "volume": 0}
            flow_types[key]["count"] += 1
            flow_types[key]["volume"] += flow['volume']
        
        summary.append("\nFlow types:")
        for flow_type, stats in flow_types.items():
            summary.append(f"  {flow_type}: {stats['count']} flows, {stats['volume']:.1f} m³ total")
        
        summary.append("\nRecent flows (last 50):")
        for flow in self.transport_flows[-50:]:
            summary.append(f"  {flow['source_name']} → {flow['target_name']}: "
                        f"{flow['volume']:.1f} m³ {flow['waste_type']}")
        
        return "\n".join(summary)
