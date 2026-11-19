from typing import Dict, Tuple, List
from .enums import RegionType
import csv
import os

CITY_TO_REGION = {
    "Murska Sobota": RegionType.POMURSKA,
    "Maribor": RegionType.PODRAVSKA,
    "Slovenj Gradec": RegionType.KOROSKA,
    "Celje": RegionType.SAVINJSKA,
    "Trbovlje": RegionType.ZASAVSKA,
    "Krško": RegionType.POSAVSKA,
    "Novo Mesto": RegionType.JUGOVZHODNA_SLOVENIJA,
    "Ljubljana": RegionType.OSREDNJESLOVENSKA,
    "Kranj": RegionType.GORENJSKA,
    "Postojna": RegionType.PRIMORSKONOTRANJSKA,
    "Nova Gorica": RegionType.GORISKA,
    "Koper": RegionType.OBALNO_KRASKA,
}


DISTANCE_MATRIX: Dict[Tuple[RegionType, RegionType], float] = {}

def _load_distance_matrix():
    csv_path = "data/slovenian_cities_distance_matrix_km.csv"
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Distance matrix CSV not found at: {csv_path}")
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)[1:]  
        for row in reader:
            from_city = row[0]
            from_region = CITY_TO_REGION[from_city]
            for to_city, dist in zip(headers, row[1:]):
                to_region = CITY_TO_REGION[to_city]
                DISTANCE_MATRIX[(from_region, to_region)] = float(dist)

_load_distance_matrix()

def get_distance(from_region: RegionType, to_region: RegionType) -> float:
    try:
        return DISTANCE_MATRIX[(from_region, to_region)]
    except KeyError:
        raise ValueError(f"Distance not found for {from_region} to {to_region}")

def get_closest_regions(
    region: RegionType, n: int = 3
) -> List[Tuple[RegionType, float]]:
    distances = []
    for r in RegionType:
        if r == region:
            continue
        distances.append((r, get_distance(region, r)))
    return sorted(distances, key=lambda x: x[1])[:n]
