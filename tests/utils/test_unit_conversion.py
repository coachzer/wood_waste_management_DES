"""utils/unit_conversion converts tonnes->m3 with each waste type's density.

``convert_generation_rates_to_volume`` runs at every simulation init, turning each
region's per-WasteType tonne/day rates into m3/day via WASTE_DENSITIES. EWC-code
parsing happens earlier, in ``RegionalFacilities.from_dict``.
"""

import pytest

from config.constants import WASTE_DENSITIES
from models.enums import WasteType
from utils.unit_conversion import convert_generation_rates_to_volume

SAWDUST = WasteType.SAWDUST_SHAVINGS_CUTTINGS_WOOD_03_01_05  # 200 kg/m3
PAPER_PACKAGING = WasteType.PAPER_PACKAGING_15_01_01          # 600 kg/m3


def test_conversion_applies_per_type_density():
    """1 t of sawdust (200 kg/m3) is 1000/200 = 5 m3; 1 t of paper packaging
    (600 kg/m3) is 1000/600 m3. Two densities so a single-value table swap or a
    kg/tonne factor change cannot pass silently."""
    rates = {SAWDUST: 1.0, PAPER_PACKAGING: 1.0}

    volumes = convert_generation_rates_to_volume(rates)

    assert volumes[SAWDUST] == pytest.approx(5.0)
    assert volumes[PAPER_PACKAGING] == pytest.approx(1000.0 / 600.0)


def test_zero_rate_converts_to_zero_volume():
    """A zero generation rate yields a zero-volume entry, not a dropped key: the
    waste type is still present with value 0.0."""
    volumes = convert_generation_rates_to_volume({SAWDUST: 0.0})

    assert volumes == {SAWDUST: 0.0}


def test_every_waste_type_has_a_density():
    """Invariant: WASTE_DENSITIES covers every WasteType, so the live conversion
    never reaches the unknown-type ValueError. Goes red if a WasteType is added
    without a matching density entry."""
    missing = [waste_type for waste_type in WasteType if waste_type not in WASTE_DENSITIES]

    assert missing == []


def test_conversion_raises_for_type_without_density(monkeypatch):
    """The unknown-type ValueError branch, reached through the public seam: with a
    waste type's density removed, conversion refuses rather than guessing a
    density. monkeypatch restores the table afterwards."""
    monkeypatch.delitem(WASTE_DENSITIES, SAWDUST)

    with pytest.raises(ValueError):
        convert_generation_rates_to_volume({SAWDUST: 1.0})
