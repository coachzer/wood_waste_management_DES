import json
import os

# Calculate monthly generation for each waste type across all regions
monthly_totals = {
    "bark_waste": 0,
    "sawdust": 0,
    "wood_cuttings": 0,
    "construction_wood": 0,
    "mixed_wood": 0,
    "waste_wooden_packaging": 0,
    "waste_paper_packaging": 0
}

# Read all region files
region_files = [f for f in os.listdir('data/regions') if f.endswith('.json')]
for file in region_files:
    with open(f'data/regions/{file}', 'r') as f:
        data = json.load(f)
        for generator in data['generators']:
            rates = generator['waste_generation_rates']
            # Multiply daily rates by 30 to get monthly
            for waste_type, rate in rates.items():
                monthly_totals[waste_type] += rate * 30

print("Monthly generation totals across all regions:")
for waste_type, total in monthly_totals.items():
    print(f"{waste_type}: {total:.1f}")
