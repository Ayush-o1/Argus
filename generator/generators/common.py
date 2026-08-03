"""Shared helpers used across every generator module."""

import random
import uuid
from datetime import datetime, timedelta

from config import CITIES, City

# ~0.15 degrees of jitter around a city center keeps every generated point
# plausibly "in the city" without pretending to be a real street address.
CITY_JITTER_DEGREES = 0.15


def new_id(prefix: str, counter: int) -> str:
    """e.g. new_id('PRS', 442) -> 'PRS-0000442'."""
    return f"{prefix}-{counter:07d}"


def new_uuid() -> str:
    return str(uuid.uuid4())


def weighted_city(rng: random.Random) -> City:
    return rng.choices(CITIES, weights=[c.weight for c in CITIES], k=1)[0]


def jittered_point(rng: random.Random, city: City) -> tuple[float, float]:
    lat = city.lat + rng.uniform(-CITY_JITTER_DEGREES, CITY_JITTER_DEGREES)
    lng = city.lng + rng.uniform(-CITY_JITTER_DEGREES, CITY_JITTER_DEGREES)
    return round(lat, 6), round(lng, 6)


def random_datetime_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    delta = end - start
    seconds = rng.uniform(0, delta.total_seconds())
    return start + timedelta(seconds=seconds)


# The generated world's activity window: the last 180 days, ending "today" —
# computed at generation time so the world always feels current on regeneration.
WORLD_END = datetime.now()
WORLD_START = WORLD_END - timedelta(days=180)
