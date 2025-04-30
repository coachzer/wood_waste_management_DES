"""Example script demonstrating the use of OutputFormatter for market-ready reports"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from monitoring.output_formatter import OutputFormatter

def main():
    """Generate and display example market reports"""
    formatter = OutputFormatter()
    
    # Generate national report
    print("=== National Report ===")
    print(formatter.generate_market_report())
    print("\n")
    
    # Generate report for specific region
    print("=== Regional Report ===")
    print(formatter.generate_market_report(region="Podravska"))
    print("\n")
    
    # Generate JSON report for programmatic use
    print("=== JSON Report ===")
    print(formatter.generate_json_report())

if __name__ == "__main__":
    main()
