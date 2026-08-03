"""Stage 2: Organizations — synthetic Indian companies, ~10% flagged as shell companies."""

import random
from datetime import date, timedelta

from config import ORG_INDUSTRIES
from generators.common import jittered_point, new_id, new_uuid, weighted_city

NAME_ROOTS = [
    "Shakti", "Surya", "Bharat", "Astra", "Narmada", "Zenith", "Saffron", "Ganga",
    "Konkan", "Deccan", "Himalaya", "Vindhya", "Meridian", "Lotus", "Ashoka",
    "Rajdhani", "Sarovar", "Indus", "Malhar", "Kaveri", "Vayu", "Prakash", "Varun",
]

SUFFIXES_BY_INDUSTRY = {
    "Logistics": ["Logistics Pvt Ltd", "Freight Lines", "Cargo Movers"],
    "FinTech": ["FinTech", "Capital Partners", "Financial Services"],
    "Manufacturing": ["Manufacturing", "Industries", "Works"],
    "Textiles": ["Textiles", "Weaves Pvt Ltd", "Fabrics"],
    "Healthcare": ["Healthcare India", "Medical Systems", "Wellness Group"],
    "Energy": ["Energy Systems", "Power Consortium", "Renewables"],
    "Real Estate": ["Realty", "Estates Pvt Ltd", "Developers"],
    "Import/Export": ["Overseas Trading", "Exports Pvt Ltd", "Global Traders"],
    "IT Services": ["Technologies", "Software Solutions", "Systems Pvt Ltd"],
    "Agriculture": ["AgroTech", "Farms Pvt Ltd", "Agro Industries"],
}

ORG_TYPE_WEIGHTED = [
    ("Corporation", 65),
    ("Shell", 10),
    ("NGO", 10),
    ("Government", 8),
    ("Criminal", 7),
]


def generate_organizations(rng: random.Random, count: int) -> list[dict]:
    orgs: list[dict] = []
    used_names: set[str] = set()
    types, weights = zip(*ORG_TYPE_WEIGHTED)

    for i in range(1, count + 1):
        industry = rng.choice(ORG_INDUSTRIES)
        name = _unique_name(rng, industry, used_names)
        city = weighted_city(rng)
        lat, lng = jittered_point(rng, city)
        org_type = rng.choices(types, weights=weights, k=1)[0]
        reg_date = date.today() - timedelta(days=rng.randint(200, 365 * 25))

        orgs.append(
            {
                "id": new_uuid(),
                "org_id": new_id("ORG", i),
                "name": name,
                "type": org_type,
                "industry": industry,
                "registered_city": city.name,
                "state": city.state,
                "lat": lat,
                "lng": lng,
                "registration_date": reg_date.isoformat(),
                "status": "Active",
                "risk_score": 0.0,
            }
        )
    return orgs


def _unique_name(rng: random.Random, industry: str, used: set[str]) -> str:
    suffixes = SUFFIXES_BY_INDUSTRY[industry]
    for _ in range(20):
        name = f"{rng.choice(NAME_ROOTS)} {rng.choice(suffixes)}"
        if name not in used:
            used.add(name)
            return name
    # Extremely unlikely fallback once the small root pool is exhausted at scale.
    name = f"{rng.choice(NAME_ROOTS)} {rng.choice(suffixes)} {rng.randint(2, 999)}"
    used.add(name)
    return name
