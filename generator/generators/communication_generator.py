"""Stage 5: Communications — a social-network model of device-to-device contact.

Most persons have 5-15 regular contacts; communications are generated along
those edges. Storyline-specific dense clusters are layered on top separately
by storyline_generator.py (Stage 8) so they carry storyline attribution.
"""

import random

from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

COMM_TYPE_WEIGHTED = [("Call", 45), ("SMS", 40), ("Encrypted", 5), ("Email", 10)]
CONTACTS_PER_PERSON = (5, 15)


def generate_communications(
    rng: random.Random, persons: list[dict], devices: list[dict], target_count: int
) -> list[dict]:
    devices_by_owner: dict[str, list[str]] = {}
    for device in devices:
        devices_by_owner.setdefault(device["owner_id"], []).append(device["id"])

    connected_persons = [p["id"] for p in persons if p["id"] in devices_by_owner]
    if len(connected_persons) < 2:
        return []

    # Build a contact graph first (who knows whom), then generate traffic
    # along those edges — this is what makes the resulting graph look like a
    # real social network instead of uniform random noise.
    contact_edges: list[tuple[str, str]] = []
    for person_id in connected_persons:
        num_contacts = rng.randint(*CONTACTS_PER_PERSON)
        candidates = [p for p in connected_persons if p != person_id]
        contacts = rng.sample(candidates, k=min(num_contacts, len(candidates)))
        for contact_id in contacts:
            contact_edges.append((person_id, contact_id))

    rng.shuffle(contact_edges)

    communications: list[dict] = []
    counter = 0
    types, weights = zip(*COMM_TYPE_WEIGHTED)

    edge_index = 0
    while len(communications) < target_count and contact_edges:
        person_a, person_b = contact_edges[edge_index % len(contact_edges)]
        edge_index += 1

        device_a = rng.choice(devices_by_owner[person_a])
        device_b = rng.choice(devices_by_owner[person_b])
        counter += 1

        communications.append(
            {
                "id": new_uuid(),
                "comm_id": new_id("COM", counter),
                "from_device": device_a,
                "to_device": device_b,
                "type": rng.choices(types, weights=weights, k=1)[0],
                "timestamp": random_datetime_between(rng, WORLD_START, WORLD_END).isoformat(),
                "duration_seconds": rng.randint(0, 1800),
                "flagged": False,
                "storyline_id": None,
            }
        )

        if edge_index >= len(contact_edges) * 8:
            # Safety valve: even with max contacts-per-person, don't loop forever
            # if target_count is set unrealistically high for this population.
            break

    return communications
