import json
from typing import Dict, Any, Optional
from models.state import SimulationState
from utils.helpers import load_json

class OutputFormatter:
    """Handles formatting of production outputs into market-ready formats"""

    def __init__(self):
        """Initialize the formatter with conversion factors"""
        self.conversion_config = load_json("config/product_conversions.json")
        self.state = SimulationState.get_instance()

    def _convert_volume_to_items(self, product_type: str, volume: float) -> Dict[str, Any]:
        """Convert volume to item count based on conversion factors"""
        if product_type not in self.conversion_config:
            raise ValueError(f"Unknown product type: {product_type}")
            
        product_config = self.conversion_config[product_type]
        items = volume * product_config["conversion"]
        
        return {
            "volume": round(volume, 1),
            "volume_unit": "m³",
            "items": round(items),
            "item_unit": product_config["unit"]
        }

    def generate_product_summary(self, product_type: str) -> Dict[str, Any]:
        """Generate summary for a single product type"""
        volume = self.state.total_products.get(product_type, 0.0)
        target = self.state.target_demands.get(product_type, 0.0)
        
        metrics = self._convert_volume_to_items(product_type, volume)
        target_metrics = self._convert_volume_to_items(product_type, target)
        
        return {
            "current": metrics,
            "target": target_metrics,
            "completion_percentage": round((volume / target * 100) if target > 0 else 0, 1)
        }

    def generate_market_report(self, region: Optional[str] = None) -> str:
        """Generate a formatted market report for finished products"""
        report_lines = []
        
        # Add header
        if region:
            report_lines.append(f"{region} Region - Monthly Production:")
        else:
            report_lines.append("National Monthly Production:")
        report_lines.append("")
        
        # Get summaries for each product type
        products = {
            "wooden_furniture": "Wooden Furniture",
            "wooden_packaging": "Wooden Packaging",
            "paper_packaging": "Paper Packaging"
        }
        
        for product_id, product_name in products.items():
            summary = self.generate_product_summary(product_id)
            current = summary["current"]
            target = summary["target"]
            
            # Format the line with proper spacing and newlines
            report_lines.extend([
                f"- {product_name}:",
                f"  Current: {current['volume']} {current['volume_unit']} ({current['items']} {current['item_unit']})",
                f"  Target: {target['volume']} {target['volume_unit']} ({target['items']} {target['item_unit']})",
                f"  Progress: {summary['completion_percentage']}%",
                ""  # Add empty line after each product
            ])
            
        return "\n".join(report_lines)

    def generate_json_report(self, region: Optional[str] = None) -> str:
        """Generate a JSON-formatted report for programmatic use"""
        products = {
            "wooden_furniture": "Wooden Furniture",
            "wooden_packaging": "Wooden Packaging",
            "paper_packaging": "Paper Packaging"
        }
        
        report = {
            "region": region or "national",
            "period": "monthly",
            "products": {}
        }
        
        for product_id in products:
            summary = self.generate_product_summary(product_id)
            # Ensure proper JSON encoding with Unicode cube symbol
            if "current" in summary:
                summary["current"]["volume_unit"] = "m³"
            if "target" in summary:
                summary["target"]["volume_unit"] = "m³"
            report["products"][product_id] = summary
        
        # Use json.dumps to properly encode the Unicode character
        return json.dumps(report, indent=2, ensure_ascii=False)
