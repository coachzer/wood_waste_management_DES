# Waste Generation Data Flow - Clarified

## Problem Identified

The original system had **two competing sources** for waste generation rates, causing confusion:

1. **Regional JSON files** (e.g., `gorenjska.json`) with specific rates per region
2. **Uncertainty Set** from `base_config.py` with global default rates

**Result**: The uncertainty set rates were generated but **never used**!

## Simplified Solution (KISS Applied)

### **New Data Flow**

```
Regional JSON Files (gorenjska.json)
     ↓
  BASE RATES (e.g., "03 01 05": 15.0)
     ↓
Uncertainty Set provides VARIABILITY ONLY
     ↓
Final Generation = BASE_RATE × SEASONAL × VARIABILITY
```

### **1. Regional JSON Files (Primary Source)**
```json
// data/regions/gorenjska.json
{
  "generators": [{
    "waste_generation_rates": {
      "03 01 05": 15.0,    // ← ACTUAL base rate used
      "03 01 01": 8.0,     // ← ACTUAL base rate used
      // ... per region, per waste type
    }
  }]
}
```

### **2. Uncertainty Set (Variability Only)**
```python
// config/base_config.py
@dataclass
class UncertaintySet:
    waste_generation_variability: float = 0.2  # ±20% variation on regional rates
    collection_efficiency: Tuple[float, float]
    treatment_conversion: Tuple[float, float]
    # ... other parameters
```

### **3. Actual Generation Formula**
```python
// In generator_utils.py
potential_volume = base_rate × seasonal_factor × daily_factor

Where:
- base_rate: From regional JSON (e.g., 15.0 from gorenjska.json)
- seasonal_factor: Calculated seasonality (1.0 ± seasonal variation)
- daily_factor: Random factor based on uncertainty_set.waste_generation_variability
```

## **What Changed**

### **Before (Confusing)**
```python
# uncertainty_set had unused waste_generation rates
waste_generation = {
    WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05: (4320, 864)  # IGNORED!
}

# Regional JSON provided the real rates
"waste_generation_rates": {
    "03 01 05": 15.0  # ACTUALLY USED
}
```

### **After (Clear)**
```python
# uncertainty_set only provides variability
waste_generation_variability = 0.2  # ±20% uncertainty

# Regional JSON remains the source of truth for base rates
"waste_generation_rates": {
    "03 01 05": 15.0  # Base rate
}

# Final generation: 15.0 × seasonal × (1.0 ± 0.2)
```

## **Benefits of This Approach**

1. **Single Source of Truth**: Regional JSON files for actual rates
2. **Clear Separation**: Uncertainty set only for variability/uncertainty
3. **Realistic Regional Differences**: Gorenjska vs Pomurska can have different rates
4. **Scenario Flexibility**: Different scenarios = different uncertainty levels
5. **No Redundancy**: Eliminated unused waste_generation dictionary

## **Example: Gorenjska Region Generation**

```python
# From gorenjska.json
base_rate = 15.0  # tonnes per day for "03 01 05"

# From uncertainty set (Baseline scenario)
variability = 0.2  # ±20%

# Daily calculation
seasonal_factor = 1.1  # 10% more in this season
random_factor = 0.85   # Random day: 15% below average

final_generation = 15.0 × 1.1 × 0.85 = 14.025 tonnes
```

## **How to Use**

### **To Change Base Rates**: Edit regional JSON files
```json
// To increase gorenjska sawdust generation:
"waste_generation_rates": {
    "03 01 05": 20.0  // Changed from 15.0
}
```

### **To Change Uncertainty**: Edit scenarios in base_config.py
```python
# For more uncertainty
"High Uncertainty": ScenarioConfig(
    waste_gen=(1.0, 0.4),  # 40% variability instead of 20%
    ...
)
```

### **To Add New Regions**: Create new JSON file
```json
// data/regions/new_region.json
{
  "generators": [{
    "waste_generation_rates": {
      "03 01 05": 25.0,  // Higher generation in new region
      // ...
    }
  }]
}
```

This approach maintains regional accuracy while allowing for scenario-based uncertainty modeling.
