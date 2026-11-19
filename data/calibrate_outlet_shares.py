"""Write where SURS sends each waste code the processors do not accept (ADR 0036).

Usage: python -m data.calibrate_outlet_shares GREEN_UP_PROJECT_DIR [--write]

For each model waste code, the 2022-2024 SURS treatment quantity is split into
recycling (R_03, R_0302), energy recovery (R_01, R_0101), disposal (D_*) and other
recovery (every other code except R_12/R_13). R_12 and R_13 are left out: they are
pre-treatment and storage, and that waste is counted again where it ends up.
The simulation only reports with these shares; it does not route by them.
"""
import json
import sys
from pathlib import Path

import pandas as pd

from data.calibrate_generation_rates import CALIBRATION_YEARS
from models.enums import WasteType, sorted_by_value

OUTLET_SHARES_PATH = Path(__file__).parent / "outlet_destination_shares.json"
PRE_TREATMENT_PROCESSES = {"R_12", "R_13", "R_12, R_13"}
SHARE_DECIMALS = 4


def destination(process: str) -> str:
    if process in ("R_03", "R_0302"):
        return "recycling"
    if process in ("R_01", "R_0101"):
        return "energy_recovery"
    if process.startswith("D_"):
        return "disposal"
    return "other_recovery"


def destination_shares(green_up_dir: Path) -> dict:
    frames = []
    for year in CALIBRATION_YEARS:
        path = green_up_dir / f"{year} data" / f"{year} filtered" / "treatment" / f"waste_treatment_{str(year)[2:]}.csv"
        frame = pd.read_csv(path, encoding="utf-8-sig").rename(
            columns={"waste_code": "treatment_inlet_waste_code", "waste_quantity_per_treatment": "quantity_treated"}
        )
        frames.append(frame)
    treated = pd.concat(frames)
    treated = treated[~treated.treatment_process.isin(PRE_TREATMENT_PROCESSES)]
    treated = treated.assign(destination=treated.treatment_process.map(destination))
    by_code = treated.groupby(["treatment_inlet_waste_code", "destination"]).quantity_treated.sum()
    shares = {}
    for waste_type in sorted_by_value(WasteType):
        if waste_type.value not in by_code.index.get_level_values(0):
            continue
        code_totals = by_code[waste_type.value]
        shares[waste_type.value] = {
            name: round(float(volume / code_totals.sum()), SHARE_DECIMALS)
            for name, volume in sorted(code_totals.items())
        }
    return shares


def main():
    shares = destination_shares(Path(sys.argv[1]))
    for code, split in shares.items():
        print(code, split)
    if "--write" in sys.argv:
        OUTLET_SHARES_PATH.write_text(json.dumps(shares, indent=4) + "\n")


if __name__ == "__main__":
    main()
