"""Stage 1: World Foundation — locations distributed across real Indian cities."""

import random

from config import CITIES
from generators.common import jittered_point, new_id, new_uuid, weighted_city

LOCATION_TYPES_WEIGHTED = [
    ("Building", 55),
    ("Warehouse", 20),
    ("District", 10),
    ("Port", 5),
    ("Airport", 5),
    ("SafeHouse", 5),
]

# Ensures every major city has at least one canonical port/airport so
# shipment and travel-event generators have something realistic to point at.
PORT_CITIES = {"Mumbai", "Chennai"}
AIRPORT_CITIES = {"Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai"}


def generate_locations(rng: random.Random, count: int) -> list[dict]:
    locations: list[dict] = []
    counter = 0

    for city in CITIES:
        if city.name in PORT_CITIES:
            counter += 1
            lat, lng = jittered_point(rng, city)
            locations.append(_location(counter, f"{city.name} Port Authority", "Port", city.name, city.state, lat, lng))
        if city.name in AIRPORT_CITIES:
            counter += 1
            lat, lng = jittered_point(rng, city)
            locations.append(
                _location(counter, f"{city.name} International Cargo Terminal", "Airport", city.name, city.state, lat, lng)
            )

    types, weights = zip(*LOCATION_TYPES_WEIGHTED)
    while len(locations) < count:
        counter += 1
        city = weighted_city(rng)
        loc_type = rng.choices(types, weights=weights, k=1)[0]
        lat, lng = jittered_point(rng, city)
        name = _generic_name(rng, loc_type, city.name)
        locations.append(_location(counter, name, loc_type, city.name, city.state, lat, lng))

    return locations


def _generic_name(rng: random.Random, loc_type: str, city: str) -> str:
    suffixes = {
        "Building": ["Business Tower", "Corporate Plaza", "Trade Centre", "Annexe"],
        "Warehouse": ["Logistics Park Warehouse", "Freight Depot", "Storage Yard"],
        "District": ["Industrial Area", "Commercial District", "Old Quarter"],
        "Port": ["Port Authority"],
        "Airport": ["Cargo Terminal"],
        "SafeHouse": ["Residential Block", "Guest House"],
    }
    return f"{city} {rng.choice(suffixes[loc_type])} {rng.randint(1, 40)}"


def _location(counter: int, name: str, loc_type: str, city: str, state: str, lat: float, lng: float) -> dict:
    return {
        "id": new_uuid(),
        "location_id": new_id("LOC", counter),
        "name": name,
        "type": loc_type,
        "city": city,
        "state": state,
        "lat": lat,
        "lng": lng,
        "capacity": 0,
        "risk_score": 0.0,
    }
