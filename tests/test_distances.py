import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models.distances import get_distance, get_closest_regions
from models.enums import RegionType

def test_get_distance_known_pair():
    # Murska Sobota to Maribor should be 41.5 km (from CSV)
    dist = get_distance(RegionType.POMURSKA, RegionType.PODRAVSKA)
    assert abs(dist - 41.5) < 0.1

def test_get_distance_self():
    # Distance to self should be 0.0
    dist = get_distance(RegionType.POMURSKA, RegionType.POMURSKA)
    assert abs(dist - 0.0) < 0.1

def test_get_distance_invalid():
    # Should raise ValueError for invalid region pair
    with pytest.raises(ValueError):
        get_distance("not_a_region", RegionType.POMURSKA)

def test_get_closest_regions():
    # For Murska Sobota, the closest should be Maribor, Slovenj Gradec, Celje
    closest = get_closest_regions(RegionType.POMURSKA, n=3)
    closest_regions = [r for r, d in closest]
    assert RegionType.PODRAVSKA in closest_regions
    assert RegionType.KOROSKA in closest_regions
    assert RegionType.SAVINJSKA in closest_regions
    # Distances should be sorted ascending
    distances = [d for r, d in closest]
    assert distances == sorted(distances)
