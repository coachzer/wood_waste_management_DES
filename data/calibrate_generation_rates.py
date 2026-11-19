"""Rebuild generator waste generation rates from SURS ODP data (ADR 0030).

Usage: python -m data.calibrate_generation_rates GREEN_UP_PROJECT_DIR [--write]

Target per region and waste code: the 2022-2024 mean of business generation
(ODP-nastajanje ``generated_in_the_year``) plus municipal waste handed over by
public services (ODP-zbiranje ``total_waste_given_away``), in tonnes per year,
divided by 365 to the t/day the region files hold. Codes SURS does not report
for a region are left out of that region's generator.
"""
import json
import sys
import unicodedata
from pathlib import Path

import pandas as pd

from models.enums import WasteType

CALIBRATION_YEARS = (2022, 2023, 2024)
DAYS_PER_YEAR = 365
RATE_DECIMALS = 3
REGIONS_DIR = Path(__file__).parent / "regions"


def region_key(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return ascii_name.lower().replace("-", "").replace(" ", "_")


def annual_tonnes_by_region_and_code(generation: pd.DataFrame, municipal: pd.DataFrame) -> pd.Series:
    """One year's business generation plus municipal hand-over, by (region, code)."""
    business = generation.assign(region=generation.statistical_region.map(region_key)).groupby(
        ["region", "waste_code"]
    ).generated_in_the_year.sum()
    public = municipal.assign(region=municipal.statistical_region.map(region_key)).groupby(
        ["region", "waste_code"]
    ).total_waste_given_away.sum()
    return business.add(public, fill_value=0.0)


def daily_rates(green_up_dir: Path) -> dict:
    model_codes = {waste_type.value for waste_type in WasteType}
    yearly = []
    for year in CALIBRATION_YEARS:
        suffix = str(year)[2:]
        filtered = green_up_dir / f"{year} data" / f"{year} filtered"
        generation = pd.read_csv(filtered / "generation" / f"generation_{suffix}.csv")
        municipal = pd.read_csv(filtered / "collection" / f"municipal_waste_management_{suffix}.csv")
        yearly.append(annual_tonnes_by_region_and_code(generation, municipal))
    mean_tonnes = pd.concat(yearly, axis=1).fillna(0.0).sum(axis=1) / len(CALIBRATION_YEARS)
    rates = {}
    for (region, code), tonnes in sorted(mean_tonnes.items()):
        rate = round(tonnes / DAYS_PER_YEAR, RATE_DECIMALS)
        if code in model_codes and rate > 0:
            rates.setdefault(region, {})[code] = rate
    return rates


def main():
    rates = daily_rates(Path(sys.argv[1]))
    write = "--write" in sys.argv
    for path in sorted(REGIONS_DIR.glob("*.json")):
        region_data = json.loads(path.read_text())
        region = path.stem.replace("_", "")
        region_rates = next(v for k, v in rates.items() if k.replace("_", "") == region)
        for generator in region_data["generators"]:
            old_total = sum(generator["waste_generation_rates"].values()) * DAYS_PER_YEAR
            generator["waste_generation_rates"] = region_rates
            generator["initial_stock"] = dict.fromkeys(region_rates, 0.0)
            print(f"{path.stem:24s} {old_total:12,.0f} -> {sum(region_rates.values()) * DAYS_PER_YEAR:10,.0f} t/yr")
        if write:
            path.write_bytes((json.dumps(region_data, indent=4, ensure_ascii=False) + "\n").replace("\n", "\r\n").encode())


if __name__ == "__main__":
    main()
