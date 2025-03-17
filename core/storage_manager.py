from typing import Dict, Optional
from models.enums import WasteType
from core.overflow import OverflowTracker

class StorageManager:
    """Dedicated class for managing storage operations following SRP"""
    
    def __init__(
        self,
        name: str,
        storage_capacity: float,
        initial_stock: Optional[Dict[WasteType, float]] = None,
        facility_type: str = "generator",
        final_products: Optional[set[WasteType]] = None
    ):
        self.name = name
        self.storage_capacity = storage_capacity
        self.overflow_tracker = OverflowTracker()
        
        # Validate and initialize storage
        if initial_stock:
            total_initial = sum(initial_stock.values())
            if total_initial > storage_capacity:
                raise ValueError(
                    f"Initial stock ({total_initial}) exceeds storage capacity ({storage_capacity})"
                )
        
        self.facility_type = facility_type
        self.final_products = final_products or set()
        
        # Initialize storage based on facility type
        self.current_storage = 0.0
        self.waste_volumes = {}
        self.product_volumes = {product: 0.0 for product in self.final_products} if facility_type == "treatment" else {}
        
        # Initialize waste volumes
        if initial_stock:
            for waste_type, volume in initial_stock.items():
                if facility_type == "treatment" and waste_type in self.final_products:
                    self.product_volumes[waste_type] = max(0.0, volume)
                else:
                    self.waste_volumes[waste_type] = max(0.0, volume)
            self.current_storage = max(0.0, sum(initial_stock.values()))

    def add_waste(self, waste_type: WasteType, volume: float, is_product: bool = False) -> float:
        """
        Add waste/product to storage, returns actual amount added
        """
        if volume < 0:
            return 0.0
            
        available_capacity = max(0.0, self.storage_capacity - self.current_storage)
        amount_to_add = min(volume, available_capacity)
        
        if amount_to_add > 0:
            if is_product and self.facility_type == "treatment" and waste_type in self.final_products:
                self.product_volumes[waste_type] = self.product_volumes.get(waste_type, 0.0) + amount_to_add
            else:
                self.waste_volumes[waste_type] = self.waste_volumes.get(waste_type, 0.0) + amount_to_add
            self.current_storage = min(self.storage_capacity, self.current_storage + amount_to_add)
            
        return amount_to_add

    def remove_waste(self, waste_type: WasteType, volume: float, is_product: bool = False) -> float:
        """
        Remove waste from storage, returns actual amount removed
        """
        if volume < 0:
            return 0.0
            
        if is_product and self.facility_type == "treatment" and waste_type in self.final_products:
            available_volume = self.product_volumes.get(waste_type, 0.0)
        else:
            available_volume = self.waste_volumes.get(waste_type, 0.0)
        amount_to_remove = min(volume, available_volume)
        
        if amount_to_remove > 0:
            if is_product and self.facility_type == "treatment" and waste_type in self.final_products:
                self.product_volumes[waste_type] = max(0.0, self.product_volumes[waste_type] - amount_to_remove)
            else:
                self.waste_volumes[waste_type] = max(0.0, self.waste_volumes[waste_type] - amount_to_remove)
            self.current_storage = max(0.0, self.current_storage - amount_to_remove)
            
        return amount_to_remove

    def get_available_capacity(self) -> float:
        """Get remaining storage capacity"""
        return max(0.0, self.storage_capacity - self.current_storage)

    def get_waste_volume(self, waste_type: WasteType, is_product: bool = False) -> float:
        """Get current volume for specific waste type or product"""
        if is_product and self.facility_type == "treatment" and waste_type in self.final_products:
            return max(0.0, self.product_volumes.get(waste_type, 0.0))
        return max(0.0, self.waste_volumes.get(waste_type, 0.0))

    @property
    def total_storage(self) -> float:
        """Get total storage including both waste and products"""
        waste_total = sum(self.waste_volumes.values())
        product_total = sum(self.product_volumes.values()) if self.facility_type == "treatment" else 0.0
        return max(0.0, waste_total + product_total)

    def handle_overflow(self, env, environmental_impact: float = 1.0):
        """Handle storage overflow situation"""
        if self.current_storage <= self.storage_capacity:
            return
            
        overflow_volume = self.current_storage - self.storage_capacity
        
        # Determine severity
        if self.current_storage / self.storage_capacity > 0.95:
            severity = "emergency"
        elif self.current_storage / self.storage_capacity > 0.90:
            severity = "critical"
        else:
            severity = "warning"
            
        # Track overflow
        print(f"{env.now}: Overflow detected at {self.name}: {overflow_volume:.2f} m³")
        self.overflow_tracker.track_overflow(
            facility_type="storage",
            volume=overflow_volume
        )
        
        # Apply penalty considering environmental impact
        penalty = self.overflow_tracker.calculate_penalty(
            facility_type="storage",
            severity=severity,
            volume=overflow_volume * (1 + environmental_impact/10)
        )
        print(f"Overflow penalty applied to {self.name}: {penalty:.2f}")
        
        # Reset to capacity
        reduction_factor = self.storage_capacity / self.current_storage
        for waste_type in self.waste_volumes:
            self.waste_volumes[waste_type] *= reduction_factor
        self.current_storage = self.storage_capacity
