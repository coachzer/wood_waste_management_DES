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

REGION_TO_CITY = {v: k for k, v in CITY_TO_REGION.items()}

CITY_COORDS = {
    'Murska Sobota': (46.6597, 16.1668),
    'Maribor': (46.55465, 15.645881),
    'Slovenj Gradec': (46.5050, 15.1200),
    'Celje': (46.2276, 15.2672),
    'Trbovlje': (46.1539, 15.0547),
    'Krško': (45.9551, 15.5025),
    'Novo Mesto': (45.8038, 15.1652),
    'Postojna': (45.7783, 14.2161),
    'Ljubljana': (46.056947, 14.505751),
    'Kranj': (46.238108, 14.3556),
    'Nova Gorica': (45.95619, 13.64826),
    'Koper': (45.548264, 13.7301),
}

REGION_COORDINATES: Dict[RegionType, Tuple[float, float]] = {
    region: CITY_COORDS[city]
    for city, region in CITY_TO_REGION.items()
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
        try:
            dist = get_distance(region, r)
            distances.append((r, dist))
        except Exception:
            continue
    return sorted(distances, key=lambda x: x[1])[:n]
