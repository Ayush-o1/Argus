"""Stage 3: Persons — synthetic individuals with Indian-context naming (Faker en_IN)."""

import random
from datetime import date

from faker import Faker

from config import OCCUPATIONS
from generators.common import jittered_point, new_id, new_uuid, weighted_city


def generate_persons(rng: random.Random, faker: Faker, count: int) -> list[dict]:
    persons: list[dict] = []
    for i in range(1, count + 1):
        gender = rng.choice(["Male", "Female"])
        name = faker.name_male() if gender == "Male" else faker.name_female()
        city = weighted_city(rng)
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
                "nationality": "Indian",
                "occupation": rng.choice(OCCUPATIONS),
                "city": city.name,
                "state": city.state,
                "lat": lat,
                "lng": lng,
                "phone": faker.phone_number(),
                "status": "Active",
                "risk_score": 0.0,
                "risk_factors": [],
                "community_ids": [],
                "flags": [],
            }
        )
    return persons


def _random_dob(rng: random.Random) -> date:
    today = date.today()
    age_years = rng.randint(18, 75)
    birth_year = today.year - age_years
    # Clamp day-of-month to 28 to sidestep invalid Feb-29-on-non-leap-year dates.
    return date(birth_year, rng.randint(1, 12), rng.randint(1, 28))
