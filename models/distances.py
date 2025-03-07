from typing import Dict, Tuple
from math import sqrt
from .enums import RegionType

# Approximate coordinates (latitude, longitude) for each region's center
REGION_COORDINATES: Dict[RegionType, Tuple[float, float]] = {
    RegionType.POMURSKA: (46.6521, 16.1667),  # Murska Sobota area
    RegionType.PODRAVSKA: (46.5547, 15.6467),  # Maribor area
    RegionType.KOROSKA: (46.5920, 14.9709),  # Slovenj Gradec area
    RegionType.SAVINJSKA: (46.2392, 15.2676),  # Celje area
    RegionType.ZASAVSKA: (46.1103, 15.0024),  # Trbovlje area
    RegionType.POSAVSKA: (45.9588, 15.4925),  # Krško area
    RegionType.JUGOVZHODNA_SLOVENIJA: (45.8033, 15.1695),  # Novo mesto area
    RegionType.OSREDNJESLOVENSKA: (46.0552, 14.5149),  # Ljubljana area
    RegionType.GORENJSKA: (46.3624, 14.1149),  # Kranj area
    RegionType.PRIMORSKONOTRANJSKA: (45.7721, 14.3687),  # Postojna area
    RegionType.GORISKA: (46.0003, 13.6554),  # Nova Gorica area
    RegionType.OBALNO_KRASKA: (45.5480, 13.7315),  # Koper area
}


def euclidean_distance(
    coord1: Tuple[float, float], coord2: Tuple[float, float]
) -> float:
    """
    Calculate Euclidean distance between two geographic coordinates.

    Args:
        coord1: (latitude, longitude) of first point
        coord2: (latitude, longitude) of second point

    Returns:
        Euclidean distance between the points
    """
    # Note: This is a simplified distance calculation.
    # For more accuracy, one could use the Haversine formula for great-circle distance
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    return sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2) * 111  # Rough conversion to km


def get_distance(from_region: RegionType, to_region: RegionType) -> float:
    """
    Get the distance in kilometers between two regions.

    Args:
        from_region: Source region
        to_region: Destination region

    Returns:
        Distance in kilometers between the regions
    """
    coord1 = REGION_COORDINATES[from_region]
    coord2 = REGION_COORDINATES[to_region]
    return euclidean_distance(coord1, coord2)


def get_closest_regions(
    region: RegionType, n: int = 3
) -> list[tuple[RegionType, float]]:
    """
    Get the n closest regions to the specified region, sorted by distance.

    Args:
        region: The reference region
        n: Number of closest regions to return (default 3)

    Returns:
        List of tuples containing (region, distance) pairs, sorted by distance
    """
    distances = [(r, get_distance(region, r)) for r in RegionType if r != region]
    return sorted(distances, key=lambda x: x[1])[:n]
