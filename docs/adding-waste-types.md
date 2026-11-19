# Adding new waste types or products

1. Add the enum to `models/enums.py::WasteType` (EWC format) or `OutputType`.
2. Add the efficiency/energy row to `TRANSFORMATION_CATALOGUE` and the output pathways to `WASTE_TO_OUTPUT_TYPES` in `models/transformations.py`.
3. For a new output, update `data/demand.json` and the product specifications in `models/products.py`. Treatment's volumetric yield uses the midpoint of the product's density range (decision 0043).
4. In `config/constants.py`, add a new waste type's bulk density to `WASTE_DENSITIES` (mass conversion, landfill cost and transport emissions read it). For a new output, add its credit to `AVOIDED_EMISSIONS_PER_M3_BY_PRODUCT`.
5. Rerun `python -m data.calibrate_generation_rates <green-up-project dir> --write` to pick up SURS rates for the new code.
