"""Stage 3: Persons — synthetic individuals placed across the global city set.

Naming follows the region a person is registered in (see
`common.faker_for_region`), so the dataset reads as a global population rather
than one country's names scattered over foreign coordinates.
"""

import random
from datetime import date

from faker import Faker

from config import OCCUPATIONS
from geography import CALLING_CODES
from generators.common import faker_for_region, jittered_point, new_id, new_uuid, weighted_city

# A small share of people are resident somewhere other than their country of
# citizenship. Cross-border investigations are the product's whole point, and a
# world where nationality is a pure function of location can't express them.
EXPATRIATE_RATE = 0.12


def generate_persons(rng: random.Random, faker: Faker, count: int, all_cities: list | None = None) -> list[dict]:
    persons: list[dict] = []
    for i in range(1, count + 1):
        city = weighted_city(rng)

        # Expatriates keep their origin country's nationality while living at
        # the resident city's coordinates. The *name* has to follow the origin
        # too — deriving it from the city of residence produced people like a
        # "Jorn Strik" holding Indian nationality, where the name silently
        # contradicts the only field an analyst would filter on.
        origin = weighted_city(rng) if rng.random() < EXPATRIATE_RATE else city
        nationality = origin.country

        name_faker = faker_for_region(rng, origin.region)
        gender = rng.choice(["Male", "Female"])
        name = name_faker.name_male() if gender == "Male" else name_faker.name_female()
        lat, lng = jittered_point(rng, city)
        dob = _random_dob(rng)

        persons.append(
            {
                "id": new_uuid(),
                "person_id": new_id("PRS", i),
                "name": name,
                "alias": [],
                "dob": dob.isoformat(),
                "gender": gender,
                "nationality": nationality,
                "occupation": rng.choice(OCCUPATIONS),
                "city": city.name,
                "state": city.state,
                "country": city.country,
                "country_code": city.country_code,
                "region": city.region,
                "lat": lat,
                "lng": lng,
                "phone": _phone_for(rng, city.country_code),
                "status": "Active",
                "risk_score": 0.0,
                "risk_factors": [],
                "community_ids": [],
                "flags": [],
            }
        )
    return persons


def _phone_for(rng: random.Random, country_code: str) -> str:
    """A synthetic subscriber number under the country's real dialing code."""
    prefix = CALLING_CODES.get(country_code, "+1")
    return f"{prefix} {rng.randint(60, 99)}{rng.randint(1000000, 9999999)}"


def _random_dob(rng: random.Random) -> date:
    today = date.today()
    age_years = rng.randint(18, 75)
    birth_year = today.year - age_years
    # Clamp day-of-month to 28 to sidestep invalid Feb-29-on-non-leap-year dates.
    return date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
