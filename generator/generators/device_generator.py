"""Stage 3 (cont'd): Devices, 1-3 per person, used as communication endpoints."""

import random

from config import SYNTHETIC_TELECOMS
from generators.common import new_id, new_uuid

DEVICE_TYPE_WEIGHTED = [("Phone", 55), ("SIM", 25), ("Laptop", 15), ("Router", 5)]


def generate_devices(rng: random.Random, persons: list[dict], target_count: int) -> list[dict]:
    devices: list[dict] = []
    counter = 0
    types, weights = zip(*DEVICE_TYPE_WEIGHTED)

    persons_shuffled = persons[:]
    rng.shuffle(persons_shuffled)

    for person in persons_shuffled:
        if len(devices) >= target_count:
            break
        num_devices = rng.randint(1, 3)
        for _ in range(num_devices):
            if len(devices) >= target_count:
                break
            counter += 1
            devices.append(
                {
                    "id": new_uuid(),
                    "device_id": new_id("DEV", counter),
                    "type": rng.choices(types, weights=weights, k=1)[0],
                    "imei": _synthetic_imei(rng),
                    "mac": _synthetic_mac(rng),
                    "owner_id": person["id"],
                    "carrier": rng.choice(SYNTHETIC_TELECOMS),
                    "risk_score": 0.0,
                }
            )

    return devices


def _synthetic_imei(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(15))


def _synthetic_mac(rng: random.Random) -> str:
    return ":".join(f"{rng.randint(0, 255):02X}" for _ in range(6))
