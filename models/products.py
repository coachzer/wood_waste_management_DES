from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class ProductRecipe:
    """Recipe defining how to produce a product from wood waste inputs"""
    product_type: str
    input_mappings: Dict[str, List[str]]  # waste_category -> list of EWC codes
    processing_time: float  # hours per m³ of product
    energy_consumption: float  # kWh per m³ of product
    conversion_efficiency: float  # percentage (0-100) of input that becomes product
    description: str
    
    def get_material_requirements(self) -> Dict[str, float]:
        """Get material requirements in kg per m³ based on industry data"""
        if self.product_type == "mdf_fibreboard":
            return {
                "03 01 01": 462.0,  # wood chips (70% of 660kg wood residue)
                "03 01 05": 198.0   # sawdust (30% of 660kg wood residue)
            }
        elif self.product_type == "particle_board":
            return {
                "03 01 01": 396.0,  # wood chips (60% of 660kg panel)
                "03 01 05": 132.0,  # sawdust (20% of 660kg panel)
                "03 01 99": 132.0   # shavings (20% of 660kg panel)
            }
        elif self.product_type == "osb_waferboard":
            return {
                "02 01 07": 416.0,  # forestry chips (70% of 594kg wood strands)
                "03 01 01": 178.0   # processing chips (30% of 594kg wood strands)
            }
        else:
            return {}


@dataclass
class ProductSpecification:
    """Product specifications including density, wood content, and biogenic stock"""
    product_type: str
    density_min: float  # kg/m³
    density_max: float  # kg/m³
    wood_content_percent: float  # percentage of wood content
    biogenic_stock_total: float  # total biogenic stock for 1 m³ of product
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
        return self.biogenic_stock_total / self.wood_density_avg


@dataclass
class WasteMapping:
    """Maps EWC codes to processing categories"""
    ewc_code: str
    waste_name: str
    processing_category: str  # e.g., "wood_chips", "wood_fibers", "sawdust"
    preparation_required: bool = False
    processing_difficulty: float = 1.0  # 1.0 = standard, >1.0 = more difficult


class ProductDataManager:
    """Manager for product specifications, recipes, and waste mappings"""
    
    def __init__(self):
        self.product_specifications: Dict[str, ProductSpecification] = {}
        self.product_recipes: Dict[str, ProductRecipe] = {}
        self.waste_mappings: Dict[str, WasteMapping] = {}
        self._initialize_waste_mappings()
        self._initialize_product_specifications()
        self._initialize_product_recipes()
    
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
                biogenic_stock_total=-585.31,
                description="Particle board made from wood particles and resin binders"
            ),
            "osb_waferboard": ProductSpecification(
                product_type="osb_waferboard",
                density_min=600.0,
                density_max=680.0,
                wood_content_percent=95.0,
                biogenic_stock_total=-1213.60,
                description="Oriented Strand Board made from wood strands and adhesive resins"
            ),
            "mdf_fibreboard": ProductSpecification(
                product_type="mdf_fibreboard",
                density_min=500.0,
                density_max=1000.0,
                wood_content_percent=82.0,
                biogenic_stock_total=-516.0,
                description="Medium Density Fiberboard made from wood fibers and resin glue"
            )
        }
    
    def _initialize_product_recipes(self):
        """Initialize production recipes with EWC code mappings based on industry data"""
        self.product_recipes = {
            "mdf_fibreboard": ProductRecipe(
                product_type="mdf_fibreboard",
                input_mappings={
                    "wood_chips": ["03 01 01"],      # 462 kg (70% of wood residue)
                    "sawdust": ["03 01 05"]          # 198 kg (30% of wood residue)
                },
                processing_time=3.0,
                energy_consumption=120.0,
                conversion_efficiency=89.0,  # 660kg wood / 741kg total = 89%
                description="MDF: 462kg chips (03 01 01) + 198kg sawdust (03 01 05) per m³"
            ),
            "particle_board": ProductRecipe(
                product_type="particle_board",
                input_mappings={
                    "wood_chips": ["03 01 01"],      # 396 kg (60% of panel)
                    "sawdust": ["03 01 05", "03 01 99"]  # 264 kg (40% - sawdust + shavings)
                },
                processing_time=2.0,
                energy_consumption=80.0,
                conversion_efficiency=100.0,  # Most efficient conversion
                description="Particleboard: 396kg chips (03 01 01) + 264kg sawdust/shavings (03 01 05/99) per m³"
            ),
            "osb_waferboard": ProductRecipe(
                product_type="osb_waferboard",
                input_mappings={
                    "forestry_chips": ["02 01 07"],  # 416 kg (70% of wood strands)
                    "wood_chips": ["03 01 01"]       # 178 kg (30% of wood strands)
                },
                processing_time=2.5,
                energy_consumption=90.0,
                conversion_efficiency=95.8,  # 594kg wood / 620kg total = 95.8%
                description="OSB: 416kg forestry chips (02 01 07) + 178kg processing chips (03 01 01) per m³"
            )
        }
    
    # Access methods
    def get_product_specification(self, product_type: str) -> Optional[ProductSpecification]:
        return self.product_specifications.get(product_type)
    
    def get_product_recipe(self, product_type: str) -> Optional[ProductRecipe]:
        return self.product_recipes.get(product_type)
    
    def get_waste_mapping(self, ewc_code: str) -> Optional[WasteMapping]:
        return self.waste_mappings.get(ewc_code)
    
    def can_produce_from_waste(self, product_type: str, ewc_codes: List[str]) -> bool:
        """Check if a product can be made from available waste types"""
        recipe = self.get_product_recipe(product_type)
        if not recipe:
            return False
        
        # Check if any of the input categories can be satisfied
        for category, required_codes in recipe.input_mappings.items():
            if any(code in ewc_codes for code in required_codes):
                return True
        return False
    
    def get_products_by_biogenic_priority(self) -> List[tuple[str, float]]:
        """Get products ranked by biogenic stock efficiency"""
        products_with_efficiency = [
            (product_type, spec.biogenic_stock_per_kg_wood)
            for product_type, spec in self.product_specifications.items()
        ]
        return sorted(products_with_efficiency, key=lambda x: x[1])
    
    def get_material_requirements(self, product_type: str, volume_m3: float) -> Optional[Dict[str, float]]:
        """Calculate exact material requirements in kg for producing given volume"""
        recipe = self.get_product_recipe(product_type)
        if not recipe:
            return None
        
        requirements = recipe.get_material_requirements()
        return {
            ewc_code: amount * volume_m3
            for ewc_code, amount in requirements.items()
        }
    
    def can_fulfill_production(self, product_type: str, volume_m3: float, available_waste: Dict[str, float]) -> bool:
        """Check if production can be fulfilled with available waste"""
        requirements = self.get_material_requirements(product_type, volume_m3)
        if not requirements:
            return False
        
        for ewc_code, needed_amount in requirements.items():
            if available_waste.get(ewc_code, 0) < needed_amount:
                return False
        return True
