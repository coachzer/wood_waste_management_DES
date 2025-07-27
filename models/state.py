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
        return cls._instance

    @classmethod
    def get_instance(cls):
        return cls() if cls._instance is None else cls._instance

    def initialize(self, generators, collectors, treatment_operators):
        self.generators = generators
        self.collectors = collectors
        self.treatment_operators = treatment_operators

    def track_waste_generation(self, region, waste_type, amount):
        """Track waste generation in a specific region"""
        if not region:
            return
        try:
            self.waste_tracker.add_waste(region, waste_type, amount)
        except KeyError as e:
            print(f"Warning: Could not track waste generation - {str(e)}")

    def track_waste_collection(self, region, waste_type, amount):
        """Track waste collection from a specific region"""
        if not region:
            return 0
        try:
            return self.waste_tracker.remove_waste(region, waste_type, amount)
        except KeyError as e:
            print(f"Warning: Could not track waste collection - {str(e)}")
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
        
        # print(f"[FLOW TRACKED] {source_type}:{source_name} → {target_type}:{target_name} "
        #       f"({volume:.1f} m³ {waste_type})")

    def get_regional_waste_stats(self, region):
        """Get waste statistics for a specific region"""
        if not region:
            return {}
        try:
            return self.waste_tracker.get_regional_stats(region)
        except KeyError as e:
            print(f"Warning: Could not get regional stats - {str(e)}")
            return {}

    def get_waste_type_distribution(self, waste_type):
        """Get distribution of a specific waste type across regions"""
        try:
            return self.waste_tracker.get_waste_type_stats(waste_type)
        except Exception as e:
            print(f"Warning: Could not get waste type distribution - {str(e)}")
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
        
    def reset(self):
        """Reset simulation state to initial values"""
        # Reset component lists
        self.generators = []
        self.collectors = []
        self.treatment_operators = []
        # Reset transport flows
        self.transport_flows = []
        # Reset regional waste tracker
        self.waste_tracker = regional_tracker.RegionalWasteTracker()
        # Reset product tracking with values from demand.json
        demand = _demand_data["national_demand"]
        self.total_products = {
            'mdf': 0,
            'particle_board': 0,
            'osb': 0
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

    def get_transport_flow_summary(self):
        """Get summary of transport flows for debugging"""
        if not self.transport_flows:
            return "No transport flows recorded"
        
        summary = []
        summary.append(f"Total transport flows: {len(self.transport_flows)}")
        
        # Group by flow type
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
        
        # Show recent flows
        summary.append(f"\nRecent flows (last 50):")
        for flow in self.transport_flows[-50:]:
            summary.append(f"  {flow['source_name']} → {flow['target_name']}: "
                        f"{flow['volume']:.1f} m³ {flow['waste_type']}")
        
        return "\n".join(summary)
