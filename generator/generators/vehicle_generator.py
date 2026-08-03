"""Stage 3 (cont'd): Vehicles, registered to persons or organizations."""

import random

from generators.common import new_id, new_uuid

VEHICLE_TYPE_WEIGHTED = [("Car", 55), ("Truck", 30), ("Boat", 8), ("Aircraft", 2), ("Motorcycle", 5)]
MAKES_MODELS = [
    ("Tata", "Nexon"), ("Tata", "Ace"), ("Mahindra", "Bolero"), ("Mahindra", "Scorpio"),
    ("Maruti Suzuki", "Swift"), ("Maruti Suzuki", "Eeco"), ("Ashok Leyland", "Dost"),
    ("Hyundai", "Creta"), ("Force Motors", "Traveller"), ("Bajaj", "Pulsar"),
]
COLORS = ["White", "Silver", "Black", "Grey", "Red", "Blue"]


def generate_vehicles(rng: random.Random, persons: list[dict], orgs: list[dict], target_count: int) -> list[dict]:
    vehicles: list[dict] = []
    owners = [(p["id"], "Person") for p in persons] + [(o["id"], "Organization") for o in orgs]
    rng.shuffle(owners)

    types, weights = zip(*VEHICLE_TYPE_WEIGHTED)

    for i, (owner_id, owner_type) in enumerate(owners, start=1):
        if len(vehicles) >= target_count:
            break
        # Not everyone owns a vehicle — roughly 1 in 3 owners get one.
        if rng.random() > 0.33:
            continue
        make, model = rng.choice(MAKES_MODELS)
        vehicles.append(
            {
                "id": new_uuid(),
                "vehicle_id": new_id("VEH", i),
                "plate": _synthetic_plate(rng),
                "type": rng.choices(types, weights=weights, k=1)[0],
                "make": make,
                "model": model,
                "color": rng.choice(COLORS),
                "registered_to": owner_id,
                "owner_type": owner_type,
                "risk_score": 0.0,
            }
        )

    return vehicles


def _synthetic_plate(rng: random.Random) -> str:
    state_codes = ["MH", "DL", "KA", "TG", "TN", "GJ", "RJ", "UP", "BR"]
    return f"{rng.choice(state_codes)}{rng.randint(1, 99):02d}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}{rng.randint(1000, 9999)}"
