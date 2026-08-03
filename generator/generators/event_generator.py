"""Stage 6: Events — meetings, travel, and document-signing events."""

import random

from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

EVENT_TYPE_WEIGHTED = [("Meeting", 55), ("Travel", 30), ("DocumentSigned", 15)]


def generate_events(rng: random.Random, persons: list[dict], locations: list[dict], target_count: int) -> list[dict]:
    if not persons or not locations:
        return []

    events: list[dict] = []
    types, weights = zip(*EVENT_TYPE_WEIGHTED)

    for i in range(1, target_count + 1):
        event_type = rng.choices(types, weights=weights, k=1)[0]
        location = rng.choice(locations)
        participant_count = 1 if event_type == "Travel" else rng.randint(2, 5)
        participants = rng.sample(persons, k=min(participant_count, len(persons)))

        events.append(
            {
                "id": new_uuid(),
                "event_id": new_id("EVT", i),
                "type": event_type,
                "timestamp": random_datetime_between(rng, WORLD_START, WORLD_END).isoformat(),
                "location_id": location["id"],
                "participant_ids": [p["id"] for p in participants],
                "risk_score": 0.0,
                "storyline_id": None,
            }
        )

    return events
