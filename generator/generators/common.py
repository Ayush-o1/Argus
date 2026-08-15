"""Shared helpers used across every generator module."""

import random
import uuid
from datetime import UTC, datetime, timedelta

from faker import Faker

from config import CITIES, City
from geography import REGION_LOCALES

# ~0.15 degrees of jitter around a city center keeps every generated point
# plausibly "in the city" without pretending to be a real street address.
CITY_JITTER_DEGREES = 0.15

_CITY_WEIGHTS = [c.weight for c in CITIES]

# One Faker per locale, built lazily and cached. Constructing a Faker is
# comparatively expensive, and generating 4,000 persons would otherwise build
# one per person; they're seeded centrally by `seed_locale_fakers`.
_FAKER_CACHE: dict[str, Faker] = {}


def new_id(prefix: str, counter: int) -> str:
    """e.g. new_id('PRS', 442) -> 'PRS-0000442'."""
    return f"{prefix}-{counter:07d}"


def new_uuid() -> str:
    return str(uuid.uuid4())


def weighted_city(rng: random.Random) -> City:
    return rng.choices(CITIES, weights=_CITY_WEIGHTS, k=1)[0]


def faker_for_region(rng: random.Random, region: str) -> Faker:
    """A Faker whose locale suits `region`, so synthetic names match their place."""
    locales = REGION_LOCALES.get(region) or ["en_US"]
    locale = rng.choice(locales)
    if locale not in _FAKER_CACHE:
        _FAKER_CACHE[locale] = Faker(locale)
    return _FAKER_CACHE[locale]


def seed_locale_fakers(seed: int) -> None:
    """Seed every locale Faker so a given --seed reproduces the same world.

    Faker.seed() is a classmethod seeding the shared generator, so this must be
    called after the cache is warm to cover locales instantiated later; it is
    cheap enough to call once per run before generation begins.
    """
    Faker.seed(seed)
    for locale in {loc for locs in REGION_LOCALES.values() for loc in locs}:
        if locale not in _FAKER_CACHE:
            _FAKER_CACHE[locale] = Faker(locale)


def jittered_point(rng: random.Random, city: City) -> tuple[float, float]:
    lat = city.lat + rng.uniform(-CITY_JITTER_DEGREES, CITY_JITTER_DEGREES)
    lng = city.lng + rng.uniform(-CITY_JITTER_DEGREES, CITY_JITTER_DEGREES)
    return round(lat, 6), round(lng, 6)


def random_datetime_between(rng: random.Random, start: datetime, end: datetime) -> datetime:
    delta = end - start
    seconds = rng.uniform(0, delta.total_seconds())
    return start + timedelta(seconds=seconds)


# The generated world's activity window: the last 180 days, ending "now" —
# computed at generation time so the world always feels current on regeneration.
#
# Timezone-aware UTC, not `datetime.now()` (audit B-17). Naive local time meant
# every emitted instant was a wall-clock reading with no zone attached, so:
#
#   * the frontend bucketed by date and then treated that date as UTC, putting
#     events near midnight in the wrong day by an amount that depended on the
#     generating machine's timezone; and
#   * two instances generating from the same seed in different timezones
#     produced different burst days, which quietly broke the determinism this
#     project advertises.
#
# Calendar values elsewhere — a date of birth, a registration date — stay plain
# `date` objects. A birthday genuinely has no timezone, and giving one an offset
# would be its own small lie.
WORLD_END = datetime.now(UTC)
WORLD_START = WORLD_END - timedelta(days=180)
