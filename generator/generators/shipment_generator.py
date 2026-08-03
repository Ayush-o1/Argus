"""Stage 7: Shipments — synthetic freight movements between locations, ~3% route anomalies."""

import random
from datetime import timedelta

from config import SYNTHETIC_CARRIERS
from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

MANIFEST_GOODS = [
    "Textile rolls",
    "Electronics components",
    "Pharmaceutical supplies",
    "Machine parts",
    "Agricultural produce",
    "Construction materials",
    "Consumer electronics",
    "Packaged foods",
]

ROUTE_ANOMALY_RATE = 0.03


def generate_shipments(rng: random.Random, locations: list[dict], count: int, id_offset: int = 0) -> list[dict]:
    ports_and_warehouses = [loc for loc in locations if loc["type"] in ("Port", "Airport", "Warehouse")]
    if len(ports_and_warehouses) < 2:
        ports_and_warehouses = locations
    if len(ports_and_warehouses) < 2:
        return []

    shipments: list[dict] = []
    for i in range(id_offset + 1, id_offset + count + 1):
        origin, destination = rng.sample(ports_and_warehouses, k=2)
        departure = random_datetime_between(rng, WORLD_START, WORLD_END)
        transit_days = rng.randint(1, 14)
        arrival = departure + timedelta(days=transit_days)
        has_route_anomaly = rng.random() < ROUTE_ANOMALY_RATE

        shipments.append(
            {
                "id": new_uuid(),
                "shipment_id": new_id("SHP", i),
                "origin_id": origin["id"],
                "destination_id": destination["id"],
                "carrier": rng.choice(SYNTHETIC_CARRIERS),
                "manifest": rng.sample(MANIFEST_GOODS, k=rng.randint(1, 3)),
                "departure": departure.isoformat(),
                "arrival": arrival.isoformat(),
                "status": "Delivered" if arrival < WORLD_END else "InTransit",
                "route_anomaly": has_route_anomaly,
                "risk_score": 15.0 if has_route_anomaly else 0.0,
            }
        )

    return shipments
