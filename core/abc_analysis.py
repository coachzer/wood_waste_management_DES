# python -m core.abc_analysis
import json
from typing import Dict, List
from dataclasses import dataclass
from models.products import ProductDataManager

@dataclass
class ABCClassification:
    """ABC classification result for a product"""
    product_type: str
    biogenic_carbon_per_unit: float  # kg CO₂eq/m³
    demand_volume: float  # m³
    total_biogenic_impact: float  # Total kg CO₂eq
    abc_class: str
    cumulative_percentage: float
    priority_weight: float

class BiogenicCarbonABCAnalyzer:
    """ABC Analysis based on biogenic carbon stock values"""
    
    def __init__(self, demand_config_path: str = "demand.json"):
        self.product_manager = ProductDataManager()
        self.demand_config_path = demand_config_path
        self.demand_data = self._load_demand_data()
        
    def _load_demand_data(self) -> Dict:
        """Load demand configuration from JSON file"""
        try:
            with open(self.demand_config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: {self.demand_config_path} not found, using default values")
            return {
                "national_demand": {
                    "particle_board": 40000,
                    "osb": 30000,
                    "mdf": 30000
                }
            }
    
    def calculate_biogenic_impact_analysis(self) -> List[ABCClassification]:
        """Calculate total biogenic carbon impact for each product"""
        results = []
        
        for product_type, demand_volume in self.demand_data["national_demand"].items():
            product_spec = self.product_manager.get_product_specification(product_type)
            
            if not product_spec:
                print(f"Warning: No specification found for {product_type}")
                continue
        
            total_impact = demand_volume * product_spec.biogenic_carbon_stock
            
            results.append({
                'product_type': product_type,
                'biogenic_carbon_per_unit': product_spec.biogenic_carbon_stock,
                'demand_volume': demand_volume,
                'total_biogenic_impact': total_impact,
                'wood_content_kg_per_m3': product_spec.wood_density_avg
            })
        
        return results
    
    def perform_abc_classification(self, 
                                 a_threshold: float = 70.0,
                                 b_threshold: float = 95.0) -> List[ABCClassification]:
        """
        Perform ABC classification based on total biogenic carbon storage
        
        Args:
            a_threshold: Cumulative percentage for Class A (default 70%)
            b_threshold: Cumulative percentage for Class B cutoff (default 95%)
        """
        impact_data = self.calculate_biogenic_impact_analysis()
        impact_data.sort(key=lambda x: abs(x['total_biogenic_impact']), reverse=True)

        total_absolute_impact = sum(abs(item['total_biogenic_impact']) for item in impact_data)
        
        classifications = []
        cumulative_impact = 0.0
        
        for item in impact_data:
            cumulative_impact += abs(item['total_biogenic_impact'])
            cumulative_percentage = (cumulative_impact / total_absolute_impact) * 100
            
            # Determine ABC class
            if cumulative_percentage <= a_threshold:
                abc_class = 'A'
                priority_weight = 1.0  # Highest priority
            elif cumulative_percentage <= b_threshold:
                abc_class = 'B'
                priority_weight = 0.7  # Medium priority
            else:
                abc_class = 'C'
                priority_weight = 0.4  # Lower priority
            
            classifications.append(ABCClassification(
                product_type=item['product_type'],
                biogenic_carbon_per_unit=item['biogenic_carbon_per_unit'],
                demand_volume=item['demand_volume'],
                total_biogenic_impact=item['total_biogenic_impact'],
                abc_class=abc_class,
                cumulative_percentage=cumulative_percentage,
                priority_weight=priority_weight
            ))
        
        return classifications
    
    def generate_abc_report(self) -> str:
        """Generate comprehensive ABC analysis report"""
        classifications = self.perform_abc_classification()
        
        report = []
        report.append("=" * 80)
        report.append("BIOGENIC CARBON STOCK ABC ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")
        
        # Summary section
        report.append("EXECUTIVE SUMMARY")
        report.append("-" * 40)
        
        class_summary = {'A': [], 'B': [], 'C': []}
        for item in classifications:
            class_summary[item.abc_class].append(item)
        
        total_carbon_storage = sum(abs(item.total_biogenic_impact) for item in classifications)
        
        report.append(f"Total Biogenic Carbon Storage Potential: {total_carbon_storage:,.0f} kg CO₂eq")
        report.append(f"Analysis based on national demand volumes from {self.demand_config_path}")
        report.append("")
        
        for class_name in ['A', 'B', 'C']:
            items = class_summary[class_name]
            if items:
                class_storage = sum(abs(item.total_biogenic_impact) for item in items)
                class_percentage = (class_storage / total_carbon_storage) * 100
                report.append(f"Class {class_name}: {len(items)} products, "
                            f"{class_storage:,.0f} kg CO₂eq ({class_percentage:.1f}%)")
        
        report.append("")
        report.append("DETAILED CLASSIFICATION")
        report.append("-" * 40)
        report.append(f"{'Product':<15} {'Class':<5} {'Demand':<10} {'Carbon/m³':<12} "
                     f"{'Total Impact':<15} {'Cumulative%':<12} {'Priority':<8}")
        report.append("-" * 80)
        
        for item in classifications:
            report.append(f"{item.product_type:<15} {item.abc_class:<5} "
                         f"{item.demand_volume:<10,.0f} {item.biogenic_carbon_per_unit:<12.1f} "
                         f"{item.total_biogenic_impact:<15,.0f} {item.cumulative_percentage:<12.1f}% "
                         f"{item.priority_weight:<8.1f}")
        
        report.append("")
        report.append("STRATEGIC RECOMMENDATIONS")
        report.append("-" * 40)
        
        # Class A recommendations
        class_a_products = [item.product_type for item in classifications if item.abc_class == 'A']
        if class_a_products:
            report.append(f"CLASS A (High Priority): {', '.join(class_a_products)}")
            report.append("• Focus production capacity and resources on these products")
            report.append("• Ensure reliable supply chains for required waste streams")
            report.append("• Monitor production efficiency closely")
            report.append("• These products provide the highest biogenic carbon storage impact")
            report.append("")
        
        # Class B recommendations  
        class_b_products = [item.product_type for item in classifications if item.abc_class == 'B']
        if class_b_products:
            report.append(f"CLASS B (Medium Priority): {', '.join(class_b_products)}")
            report.append("• Maintain steady production to meet demand")
            report.append("• Optimize processing efficiency where possible")
            report.append("• Consider as backup capacity when Class A demand is met")
            report.append("")
        
        # Class C recommendations
        class_c_products = [item.product_type for item in classifications if item.abc_class == 'C']
        if class_c_products:
            report.append(f"CLASS C (Lower Priority): {', '.join(class_c_products)}")
            report.append("• Produce only when excess capacity is available")
            report.append("• Consider cost optimization strategies")
            report.append("• Monitor for potential demand changes")
            report.append("")
        
        # Carbon storage insights
        report.append("BIOGENIC CARBON INSIGHTS")
        report.append("-" * 40)
        
        best_performer = max(classifications, key=lambda x: abs(x.biogenic_carbon_per_unit))
        report.append(f"Highest carbon storage per m³: {best_performer.product_type} "
                     f"({best_performer.biogenic_carbon_per_unit:.1f} kg CO₂eq/m³)")
        
        most_impact = max(classifications, key=lambda x: abs(x.total_biogenic_impact))
        report.append(f"Highest total impact: {most_impact.product_type} "
                     f"({most_impact.total_biogenic_impact:,.0f} kg CO₂eq total)")
        
        report.append("")
        report.append("Note: Negative values indicate carbon storage (removal from atmosphere)")
        report.append("Higher absolute values indicate better climate impact")
        
        return "\n".join(report)
    
    def update_demand_config_with_priorities(self, output_path: str = "demand_with_abc.json"):
        """Update demand configuration with ABC priority information"""
        classifications = self.perform_abc_classification()
        
        updated_config = {
            "national_demand": self.demand_data["national_demand"].copy(),
            "abc_analysis": {
                "analysis_date": "2025-08-05",
                "methodology": "Biogenic carbon stock based ABC classification",
                "thresholds": {
                    "class_a_percentage": 70.0,
                    "class_b_percentage": 95.0
                },
                "products": {}
            }
        }
        
        for item in classifications:
            updated_config["abc_analysis"]["products"][item.product_type] = {
                "abc_class": item.abc_class,
                "priority_weight": item.priority_weight,
                "biogenic_carbon_per_unit": item.biogenic_carbon_per_unit,
                "total_biogenic_impact": item.total_biogenic_impact,
                "cumulative_percentage": item.cumulative_percentage,
                "demand_volume": item.demand_volume
            }
        
        with open(output_path, 'w') as f:
            json.dump(updated_config, f, indent=2)
        
        print(f"Updated demand configuration saved to {output_path}")
        return updated_config

if __name__ == "__main__":
    analyzer = BiogenicCarbonABCAnalyzer("demand.json")
    
    report = analyzer.generate_abc_report()
    print(report)
    
    analyzer.update_demand_config_with_priorities()
    
    classifications = analyzer.perform_abc_classification()
    
    print("\nABC Classification Results:")
    for item in classifications:
        print(f"{item.product_type}: Class {item.abc_class} "
              f"(Priority: {item.priority_weight}, "
              f"Impact: {item.total_biogenic_impact:,.0f} kg CO₂eq)")