"""Stage 2 (cont'd) / Stage 3 (cont'd): DIRECTS and EMPLOYED_BY edges between persons and orgs."""

import random
from datetime import date, timedelta

DIRECTOR_ROLES = ["Managing Director", "Director", "Chairperson", "Company Secretary"]
EMPLOYEE_ROLES = ["Manager", "Analyst", "Officer", "Executive", "Associate", "Consultant"]

EMPLOYMENT_RATE = 0.35  # fraction of persons who are EMPLOYED_BY some organization


def assign_directors(rng: random.Random, persons: list[dict], orgs: list[dict]) -> list[dict]:
    """Every organization gets 1-3 directors drawn from the person pool."""
    edges: list[dict] = []
    if not persons:
        return edges

    for org in orgs:
        num_directors = rng.randint(1, 3)
        directors = rng.sample(persons, k=min(num_directors, len(persons)))
        for person in directors:
            since = date.today() - timedelta(days=rng.randint(100, 365 * 12))
            edges.append(
                {
                    "person_id": person["id"],
                    "org_id": org["id"],
                    "role": rng.choice(DIRECTOR_ROLES),
                    "since": since.isoformat(),
                }
            )
    return edges


def assign_employment(rng: random.Random, persons: list[dict], orgs: list[dict]) -> list[dict]:
    """A subset of persons are EMPLOYED_BY an organization (independent of directorship)."""
    edges: list[dict] = []
    if not orgs:
        return edges

    employed = rng.sample(persons, k=int(len(persons) * EMPLOYMENT_RATE))
    for person in employed:
        org = rng.choice(orgs)
        start = date.today() - timedelta(days=rng.randint(30, 365 * 10))
        edges.append(
            {
                "person_id": person["id"],
                "org_id": org["id"],
                "role": rng.choice(EMPLOYEE_ROLES),
                "start_date": start.isoformat(),
            }
        )
    return edges
