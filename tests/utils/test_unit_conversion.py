"""utils/unit_conversion converts tonnes->m3 correctly and handles unmapped codes.

``convert_generation_rates_to_volume`` runs at every simulation init, turning each
region's EWC->tonne/day rates into per-WasteType m3/day rates via WASTE_DENSITIES.
These tests pin the parts a future edit to the density table or the EWC mapping
could silently corrupt:

  1. the tonnes->m3 arithmetic at two distinct densities (a density swap or a
     kg/tonne factor change would move the result);
  2. an unmapped EWC code is dropped, not crashed, on the live path;
  3. EWC suffix-matching resolves a code to its enum member and skips non-matches;
  4. the invariant that every WasteType carries a density -- which is exactly what
     keeps the unknown-type ValueError unreachable on the live path -- plus that
     ValueError firing when the invariant is (artificially) broken.

Each assertion is mutation-verified non-vacuous; see the commit / per-test notes.
"""

import pytest

from models.enums import WasteType
from utils.unit_conversion import (
    WASTE_DENSITIES,
    _create_waste_type_mapping,
    convert_generation_rates_to_volume,
)

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05  # 200 kg/m3
PAPER_PACKAGING = WasteType.PAPER_PACKAGING_15_01_01          # 600 kg/m3


def test_conversion_applies_per_type_density():
    """1 t of sawdust (200 kg/m3) is 1000/200 = 5 m3; 1 t of paper packaging
    (600 kg/m3) is 1000/600 m3. Two densities so a single-value table swap or a
    kg/tonne factor change cannot pass silently."""
    rates = {"03 01 05": 1.0, "15 01 01": 1.0}

    volumes = convert_generation_rates_to_volume(rates)

    assert volumes[SAWDUST] == pytest.approx(5.0)
    assert volumes[PAPER_PACKAGING] == pytest.approx(1000.0 / 600.0)


def test_zero_rate_converts_to_zero_volume():
    """A zero generation rate yields a zero-volume entry, not a dropped key: the
    mapped waste type is still present with value 0.0."""
    volumes = convert_generation_rates_to_volume({"03 01 05": 0.0})

    assert volumes == {SAWDUST: 0.0}


def test_unmapped_ewc_code_is_dropped_not_raised():
    """Documented live-path fallback: an EWC code matching no WasteType is skipped
    (warning printed) and absent from the result, while mapped codes still
    convert. The result is keyed only by WasteType, never by the raw string."""
    volumes = convert_generation_rates_to_volume({"99 99 99": 1.0, "03 01 05": 1.0})

    assert volumes == {SAWDUST: pytest.approx(5.0)}


def test_create_mapping_resolves_and_skips():
    """EWC suffix-matching maps a real code to its enum member and omits an
    unmatched code from the mapping entirely."""
    mapping = _create_waste_type_mapping({"03 01 05": 1.0, "99 99 99": 1.0})

    assert mapping == {"03 01 05": SAWDUST}


def test_every_waste_type_has_a_density():
    """Invariant: WASTE_DENSITIES covers every WasteType, so the live conversion
    never reaches the unknown-type ValueError. Goes red if a WasteType is added
    without a matching density entry."""
    missing = [waste_type for waste_type in WasteType if waste_type not in WASTE_DENSITIES]

    assert missing == []


def test_conversion_raises_for_type_without_density(monkeypatch):
    """The unknown-type ValueError branch, reached through the public seam: with a
    mapped code's density removed, conversion refuses rather than guessing a
    density. monkeypatch restores the table afterwards."""
    monkeypatch.delitem(WASTE_DENSITIES, SAWDUST)

    with pytest.raises(ValueError):
        convert_generation_rates_to_volume({"03 01 05": 1.0})
