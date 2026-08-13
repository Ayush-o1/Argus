"""Stage 1: World Foundation — locations distributed across the global city set.

Every city tagged `port` in `geography.py` gets a canonical Port node, and every
regional hub gets a cargo airport. Shipments draw their endpoints from these, so
the trade-lane model in `shipment_generator` has real infrastructure to connect
rather than arbitrary buildings.
"""

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

# Port naming varies by whether the city is primarily a container terminal or a
# broader harbour; this only needs to read plausibly to an analyst.
PORT_NAME_FORMS = ["{city} Port Authority", "Port of {city}", "{city} Container Terminal"]


def generate_locations(rng: random.Random, count: int) -> list[dict]:
    locations: list[dict] = []
    counter = 0

    # Anchor infrastructure first: one canonical port per port city, one cargo
    # airport per hub. These are the endpoints trade lanes are drawn between.
    for city in CITIES:
        if city.is_port:
            counter += 1
            lat, lng = jittered_point(rng, city)
            name = rng.choice(PORT_NAME_FORMS).format(city=city.name)
            locations.append(_location(counter, name, "Port", city, lat, lng))
        if "hub" in city.tags:
            counter += 1
            lat, lng = jittered_point(rng, city)
            locations.append(
                _location(counter, f"{city.name} International Cargo Terminal", "Airport", city, lat, lng)
            )

    types, weights = zip(*LOCATION_TYPES_WEIGHTED)
    while len(locations) < count:
        counter += 1
        city = weighted_city(rng)
        loc_type = rng.choices(types, weights=weights, k=1)[0]
        lat, lng = jittered_point(rng, city)
        name = _generic_name(rng, loc_type, city.name)
        locations.append(_location(counter, name, loc_type, city, lat, lng))

    return locations


def _generic_name(rng: random.Random, loc_type: str, city: str) -> str:
    suffixes = {
        "Building": ["Business Tower", "Corporate Plaza", "Trade Centre", "Annexe"],
        "Warehouse": ["Logistics Park Warehouse", "Freight Depot", "Storage Yard"],
        "District": ["Industrial Area", "Commercial District", "Old Quarter"],
        "Port": ["Wharf", "Dockyard"],
        "Airport": ["Cargo Terminal"],
        "SafeHouse": ["Residential Block", "Guest House"],
    }
    return f"{city} {rng.choice(suffixes[loc_type])} {rng.randint(1, 40)}"


def _location(counter: int, name: str, loc_type: str, city, lat: float, lng: float) -> dict:
    return {
        "id": new_uuid(),
        "location_id": new_id("LOC", counter),
        "name": name,
        "type": loc_type,
        "city": city.name,
        "state": city.state,
        "country": city.country,
        "country_code": city.country_code,
        "region": city.region,
        "lat": lat,
        "lng": lng,
        "capacity": 0,
        "risk_score": 0.0,
    }
