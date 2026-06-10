from typing import Dict, Optional
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


class ProductDataManager:
    """Manager for product specifications"""

    def __init__(self):
        self.product_specifications: Dict[str, ProductSpecification] = {}
        self._initialize_product_specifications()

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
