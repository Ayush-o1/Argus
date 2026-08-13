"""Stage 7: Shipments — freight movements along weighted global trade lanes.

The baseline is what makes anomalies legible. Earlier versions picked two
locations uniformly at random, which meant no route could be more surprising
than any other — "anomalous" was a flag with nothing behind it. Here, ~97% of
shipments follow the weighted corridors in `geography.TRADE_LANES`, and the
remainder deviate from that baseline in one of three specific, inspectable ways.
"""

import random
from collections import defaultdict
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from config import SYNTHETIC_CARRIERS
from geography import IMPLAUSIBLE_LANES, TRADE_LANES
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
    "Industrial chemicals",
    "Refined metals",
    "Automotive parts",
    "Cold-chain perishables",
]

ROUTE_ANOMALY_RATE = 0.03

# Each flavour is a different analytic question, which is why they're modelled
# separately rather than as one opaque `route_anomaly` boolean:
#   off_lane      — these two regions have no freight relationship at all
#   circuitous    — plausible endpoints, implausible detour between them
#   manifest_shift— cargo declared at origin doesn't match what arrived
ANOMALY_KINDS_WEIGHTED = [("off_lane", 40), ("circuitous", 35), ("manifest_shift", 25)]

ANOMALY_RISK = {"off_lane": 45.0, "circuitous": 35.0, "manifest_shift": 30.0}


def generate_shipments(rng: random.Random, locations: list[dict], count: int, id_offset: int = 0) -> list[dict]:
    ports = [loc for loc in locations if loc["type"] in ("Port", "Airport")]
    if len(ports) < 2:
        ports = [loc for loc in locations if loc["type"] == "Warehouse"] or locations
    if len(ports) < 2:
        return []

    by_region: dict[str, list[dict]] = defaultdict(list)
    for port in ports:
        by_region[port.get("region", "South Asia")].append(port)

    # Only lanes whose both endpoints actually exist in this world are usable.
    lanes = [(a, b, w) for a, b, w in TRADE_LANES if by_region.get(a) and by_region.get(b)]
    if not lanes:
        lanes = [(r, r, 1.0) for r in by_region]
    lane_weights = [w for _, _, w in lanes]

    regions_present = sorted(by_region)

    shipments: list[dict] = []
    for i in range(id_offset + 1, id_offset + count + 1):
        anomaly_kind: str | None = None
        if rng.random() < ROUTE_ANOMALY_RATE:
            kinds, weights = zip(*ANOMALY_KINDS_WEIGHTED)
            anomaly_kind = rng.choices(kinds, weights=weights, k=1)[0]

        if anomaly_kind == "off_lane":
            pair = _pick_implausible_pair(rng, regions_present, by_region)
            if pair is None:  # world too small to contain an implausible pair
                anomaly_kind = "circuitous"
                origin_region, dest_region, _ = _weighted_lane(rng, lanes, lane_weights)
            else:
                origin_region, dest_region = pair
        else:
            origin_region, dest_region, _ = _weighted_lane(rng, lanes, lane_weights)

        origin = rng.choice(by_region[origin_region])
        destination = _distinct_port(rng, by_region[dest_region], origin)
        if destination is None:
            continue

        # A circuitous route calls at a port in a third region that sits well
        # off the direct path — the signal an analyst is meant to notice.
        via = None
        if anomaly_kind == "circuitous":
            via = _pick_detour(rng, by_region, origin, destination, regions_present)
            if via is None:
                anomaly_kind = "manifest_shift"

        direct_km = _haversine_km(origin["lat"], origin["lng"], destination["lat"], destination["lng"])
        routed_km = direct_km
        if via is not None:
            routed_km = _haversine_km(origin["lat"], origin["lng"], via["lat"], via["lng"]) + _haversine_km(
                via["lat"], via["lng"], destination["lat"], destination["lng"]
            )

        departure = random_datetime_between(rng, WORLD_START, WORLD_END)
        # Transit scales with distance (~500 km/day of effective progress) so
        # arrival dates stay consistent with the route actually drawn.
        transit_days = max(2, round(routed_km / 500) + rng.randint(-1, 3))
        arrival = departure + timedelta(days=transit_days)

        manifest = rng.sample(MANIFEST_GOODS, k=rng.randint(1, 3))
        declared_manifest = manifest
        if anomaly_kind == "manifest_shift":
            declared_manifest = rng.sample([g for g in MANIFEST_GOODS if g not in manifest], k=len(manifest))

        shipments.append(
            {
                "id": new_uuid(),
                "shipment_id": new_id("SHP", i),
                "origin_id": origin["id"],
                "destination_id": destination["id"],
                "via_id": via["id"] if via else None,
                "origin_region": origin_region,
                "destination_region": dest_region,
                "lane": f"{origin_region} → {dest_region}",
                "carrier": rng.choice(SYNTHETIC_CARRIERS),
                "manifest": manifest,
                "declared_manifest": declared_manifest,
                "departure": departure.isoformat(),
                "arrival": arrival.isoformat(),
                "status": "Delivered" if arrival < WORLD_END else "InTransit",
                "distance_km": round(routed_km),
                "detour_ratio": round(routed_km / direct_km, 2) if direct_km > 1 else 1.0,
                "route_anomaly": anomaly_kind is not None,
                "anomaly_kind": anomaly_kind,
                "risk_score": ANOMALY_RISK.get(anomaly_kind or "", 0.0),
            }
        )

    return shipments


def _weighted_lane(rng, lanes, weights):
    lane = rng.choices(lanes, weights=weights, k=1)[0]
    # Lanes are undirected trade relationships; direction is chosen per shipment.
    a, b, w = lane
    return (a, b, w) if rng.random() < 0.5 else (b, a, w)


def _distinct_port(rng: random.Random, pool: list[dict], origin: dict) -> dict | None:
    candidates = [p for p in pool if p["id"] != origin["id"]]
    return rng.choice(candidates) if candidates else None


def _pick_implausible_pair(rng, regions_present, by_region) -> tuple[str, str] | None:
    usable = [
        tuple(pair) for pair in IMPLAUSIBLE_LANES
        if all(r in regions_present and by_region[r] for r in pair)
    ]
    if not usable:
        return None
    a, b = rng.choice(usable)
    return (a, b) if rng.random() < 0.5 else (b, a)


def _pick_detour(rng, by_region, origin, destination, regions_present) -> dict | None:
    """A port in a third region at least 1.4x off the direct path."""
    direct = _haversine_km(origin["lat"], origin["lng"], destination["lat"], destination["lng"])
    others = [r for r in regions_present if r not in (origin.get("region"), destination.get("region"))]
    rng.shuffle(others)
    for region in others:
        for candidate in rng.sample(by_region[region], k=min(4, len(by_region[region]))):
            routed = _haversine_km(origin["lat"], origin["lng"], candidate["lat"], candidate["lng"]) + _haversine_km(
                candidate["lat"], candidate["lng"], destination["lat"], destination["lng"]
            )
            if direct > 1 and routed / direct >= 1.4:
                return candidate
    return None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))
