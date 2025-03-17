from .regional_tracker import RegionalWasteTracker


class SimulationState:
    """Singleton class to store the state of the simulation environment."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Initialize waste tracker first
            cls._instance.waste_tracker = RegionalWasteTracker()
            # Then initialize component lists
            cls._instance.generators = []
            cls._instance.collectors = []
            cls._instance.treatment_operators = []
            # Initialize product tracking
            cls._instance.total_products = {
                'wooden_packaging': 0,
                'paper_packaging': 0,
                'wooden_furniture': 0
            }
            cls._instance.target_demands = {
                'wooden_packaging': 600,  # from MONTHLY_DEMAND
                'paper_packaging': 500,
                'wooden_furniture': 200
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
            
    def track_product_production(self, product_type: str, amount: float) -> None:
        """Track production of final products"""
        if product_type in self.total_products:
            self.total_products[product_type] += amount
            print(f"Production tracked: {product_type} - {amount:.2f} m³ (Total: {self.total_products[product_type]:.2f} m³)")
            
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
