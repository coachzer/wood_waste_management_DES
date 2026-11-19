"""Generation rates come from SURS business generation plus municipal hand-over (ADR 0030)."""
import pandas as pd
import pytest

from data.calibrate_generation_rates import daily_rates


def _write_year(root, year, business_tonnes, municipal_tonnes):
    filtered = root / f"{year} data" / f"{year} filtered"
    (filtered / "generation").mkdir(parents=True)
    (filtered / "collection").mkdir(parents=True)
    suffix = str(year)[2:]
    pd.DataFrame([
        {"statistical_region": "OBALNO-KRAŠKA", "waste_code": "15 01 03", "generated_in_the_year": business_tonnes},
        {"statistical_region": "OBALNO-KRAŠKA", "waste_code": "99 99 99", "generated_in_the_year": 1_000.0},
        {"statistical_region": "OBALNO-KRAŠKA", "waste_code": "17 02 01", "generated_in_the_year": 0.0},
    ]).to_csv(filtered / "generation" / f"generation_{suffix}.csv", index=False)
    pd.DataFrame([
        {"statistical_region": "OBALNO-KRAŠKA", "waste_code": "15 01 03", "total_waste_given_away": municipal_tonnes},
    ]).to_csv(filtered / "collection" / f"municipal_waste_management_{suffix}.csv", index=False)


def test_rate_is_the_three_year_mean_of_business_plus_municipal_per_day(tmp_path):
    """Mutation check (red): drop the municipal term, or divide by one year instead of three."""
    _write_year(tmp_path, 2022, business_tonnes=300.0, municipal_tonnes=65.0)
    _write_year(tmp_path, 2023, business_tonnes=600.0, municipal_tonnes=130.0)
    _write_year(tmp_path, 2024, business_tonnes=900.0, municipal_tonnes=195.0)

    rates = daily_rates(tmp_path)

    assert rates == {"obalnokraska": {"15 01 03": pytest.approx((600.0 + 130.0) / 365, abs=1e-3)}}
