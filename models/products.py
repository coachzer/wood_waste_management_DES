from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ProductSpecification:
    """Product specifications including density, wood content, and biogenic stock"""
    product_type: str
    density_min: float  # kg/m³
    density_max: float  # kg/m³
    wood_content_percent: float  # percentage of wood content
    biogenic_carbon_stock: float  # total biogenic stock for 1 m³ of product
    description: str
    
    @property
    def wood_density_min(self) -> float:
        """Calculate minimum wood content density (kg/m³)"""
        return self.density_min * (self.wood_content_percent / 100)
    
    @property
    def wood_density_max(self) -> float:
        """Calculate maximum wood content density (kg/m³)"""
        return self.density_max * (self.wood_content_percent / 100)
    
    @property
    def wood_density_avg(self) -> float:
        """Calculate average wood content density (kg/m³)"""
        return (self.wood_density_min + self.wood_density_max) / 2
    
    @property
    def biogenic_stock_per_kg_wood(self) -> float:
        """Calculate biogenic stock per kg of wood waste invested"""
        return self.biogenic_carbon_stock / self.wood_density_avg


@dataclass
class WasteMapping:
    """Maps EWC codes to processing categories"""
    ewc_code: str
    waste_name: str
    processing_category: str  # e.g., "wood_chips", "wood_fibers", "sawdust"
    preparation_required: bool = False
    processing_difficulty: float = 1.0  # 1.0 = standard, >1.0 = more difficult


class ProductDataManager:
    """Manager for product specifications and waste mappings"""

    def __init__(self):
        self.product_specifications: Dict[str, ProductSpecification] = {}
        self.waste_mappings: Dict[str, WasteMapping] = {}
        self._initialize_waste_mappings()
        self._initialize_product_specifications()
    
    def _initialize_waste_mappings(self):
        """Map EWC codes to processing categories"""
        self.waste_mappings = {
            "02 01 07": WasteMapping("02 01 07", "Forestry waste", "wood_chips"),
            "03 01 01": WasteMapping("03 01 01", "Bark waste", "bark_chips"),
            "03 01 05": WasteMapping("03 01 05", "Sawdust, shavings, cuttings", "sawdust"),
            "03 01 99": WasteMapping("03 01 99", "Other wood waste", "wood_chips"),
            "03 03 01": WasteMapping("03 03 01", "Bark and wood waste", "wood_chips"),
            "03 03 08": WasteMapping("03 03 08", "Paper/cardboard sorting waste", "paper_fibers"),
            "15 01 01": WasteMapping("15 01 01", "Paper packaging", "paper_fibers"),
            "15 01 03": WasteMapping("15 01 03", "Wooden packaging", "wood_strands"),
            "17 02 01": WasteMapping("17 02 01", "Construction wood", "wood_strands", True, 1.2),
            "19 12 01": WasteMapping("19 12 01", "Paper and cardboard", "paper_fibers"),
            "19 12 07": WasteMapping("19 12 07", "Wood", "wood_chips"),
            "20 01 01": WasteMapping("20 01 01", "Paper and cardboard", "paper_fibers"),
            "20 01 38": WasteMapping("20 01 38", "Non-hazardous wood", "wood_chips"),
            "20 03 07": WasteMapping("20 03 07", "Bulky waste", "mixed_wood", True, 1.5),
        }
    
    def _initialize_product_specifications(self):
        """Initialize product specifications"""
        self.product_specifications = {
            "particle_board": ProductSpecification(
                product_type="particle_board",
                density_min=600.0,
                density_max=800.0,
                wood_content_percent=92.5,
                biogenic_carbon_stock=-585.31,
                description="Particle board made from wood particles and resin binders"
            ),
            "osb": ProductSpecification(
                product_type="osb",
                density_min=600.0,
                density_max=680.0,
                wood_content_percent=95.0,
                biogenic_carbon_stock=-1213.60,
                description="Oriented Strand Board made from wood strands and adhesive resins"
            ),
            "mdf": ProductSpecification(
                product_type="mdf",
                density_min=500.0,
                density_max=1000.0,
                wood_content_percent=82.0,
                biogenic_carbon_stock=-516.0,
                description="Medium Density Fiberboard made from wood fibers and resin glue"
            )
        }
    
    # Access methods
    def get_product_specification(self, product_type: str) -> Optional[ProductSpecification]:
        return self.product_specifications.get(product_type)

    def get_waste_mapping(self, ewc_code: str) -> Optional[WasteMapping]:
        return self.waste_mappings.get(ewc_code)

    def get_products_by_biogenic_priority(self) -> List[tuple[str, float]]:
        """Get products ranked by biogenic stock efficiency"""
        products_with_efficiency = [
            (product_type, spec.biogenic_stock_per_kg_wood)
            for product_type, spec in self.product_specifications.items()
        ]
        return sorted(products_with_efficiency, key=lambda x: x[1])
