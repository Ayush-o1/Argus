"""Stage 2: Organizations — synthetic companies worldwide, ~10% flagged as shells.

Names are composed from a regional root, an industry suffix, and the legal form
used where the company is registered ("Pte Ltd" in Singapore, "GmbH" in
Germany). Every company here is fictional; the naming conventions are real only
so that a corporate network reads plausibly to an analyst.
"""

import random
from datetime import date, timedelta

from config import ORG_INDUSTRIES
from generators.common import jittered_point, new_id, new_uuid, weighted_city

NAME_ROOTS_BY_REGION: dict[str, list[str]] = {
    "South Asia": ["Shakti", "Surya", "Bharat", "Narmada", "Saffron", "Ganga", "Konkan",
                   "Deccan", "Himalaya", "Vindhya", "Ashoka", "Indus", "Kaveri", "Varun"],
    "Middle East": ["Al-Nahda", "Rimal", "Qasr", "Falcon Bay", "Sahil", "Zafar",
                    "Dune Gate", "Pearl Coast", "Najm", "Harbour Crescent"],
    "Central Asia": ["Steppe", "Altyn", "Caspian", "Silk Meridian", "Tien Shan", "Oxus"],
    "Southeast Asia": ["Straits", "Mekong", "Equator", "Nusantara", "Selat", "Bayan",
                       "Coral Gate", "Andaman"],
    "East Asia": ["Orient Harbour", "Jinhai", "Pacific Rim", "Sakura Line", "Hanseong",
                  "Dragonfly", "Nanpu", "Kaiyo"],
    "Europe": ["Nordkap", "Hansa", "Alpine", "Meridian", "Vantage", "Adriatic",
               "Kestrel", "Blackfriars", "Zenith", "Aurelian"],
    "Africa": ["Sahel", "Cape Meridian", "Nile Gate", "Serengeti", "Atlas Coast",
               "Baobab", "Zambezi"],
    "North America": ["Atlantic Charter", "Cascadia", "Isthmus", "Redwood", "Gulfline",
                      "Northstar", "Bayard"],
    "South America": ["Andes", "Rio Plata", "Amazonia", "Pampas", "Corcovado"],
    "Oceania": ["Southern Cross", "Tasman", "Coral Sea", "Kanga Freight"],
}

# Real legal forms, applied to fictional companies.
LEGAL_FORM_BY_COUNTRY: dict[str, str] = {
    "India": "Pvt Ltd", "Pakistan": "Pvt Ltd", "Bangladesh": "Ltd", "Sri Lanka": "PLC",
    "Nepal": "Pvt Ltd", "Maldives": "Pvt Ltd",
    "UAE": "FZE", "Qatar": "WLL", "Saudi Arabia": "LLC", "Oman": "LLC",
    "Bahrain": "WLL", "Iran": "Co",
    "Uzbekistan": "MChJ", "Kazakhstan": "TOO", "Azerbaijan": "MMC", "Turkmenistan": "HJ",
    "Singapore": "Pte Ltd", "Thailand": "Co Ltd", "Indonesia": "PT", "Vietnam": "JSC",
    "Malaysia": "Sdn Bhd", "Philippines": "Inc",
    "Hong Kong": "Ltd", "China": "Co Ltd", "South Korea": "Co Ltd", "Japan": "K.K.",
    "Taiwan": "Co Ltd",
    "Netherlands": "B.V.", "Germany": "GmbH", "Belgium": "NV", "United Kingdom": "Ltd",
    "Switzerland": "AG", "Greece": "S.A.", "Turkey": "A.S.", "Malta": "Ltd", "Cyprus": "Ltd",
    "South Africa": "Pty Ltd", "Nigeria": "Ltd", "Kenya": "Ltd", "Djibouti": "SARL",
    "Egypt": "S.A.E.", "Morocco": "SARL",
    "United States": "Inc", "Canada": "Inc", "Panama": "S.A.",
    "Brazil": "Ltda", "Argentina": "S.A.", "Peru": "S.A.C.", "Colombia": "S.A.S.",
    "Australia": "Pty Ltd",
}

SUFFIXES_BY_INDUSTRY = {
    "Logistics": ["Logistics", "Freight Lines", "Cargo Movers"],
    "FinTech": ["FinTech", "Capital Partners", "Financial Services"],
    "Manufacturing": ["Manufacturing", "Industries", "Works"],
    "Textiles": ["Textiles", "Weaves", "Fabrics"],
    "Healthcare": ["Healthcare", "Medical Systems", "Wellness Group"],
    "Energy": ["Energy Systems", "Power Consortium", "Renewables"],
    "Real Estate": ["Realty", "Estates", "Developers"],
    "Import/Export": ["Overseas Trading", "Exports", "Global Traders"],
    "IT Services": ["Technologies", "Software Solutions", "Systems"],
    "Agriculture": ["AgroTech", "Farms", "Agro Industries"],
    "Maritime Shipping": ["Maritime", "Shipping Lines", "Container Services"],
    "Commodities Trading": ["Commodities", "Resources Trading", "Bulk Trading"],
    "Freight Forwarding": ["Freight Forwarding", "Customs & Clearing", "Transit Services"],
}

ORG_TYPE_WEIGHTED = [
    ("Corporation", 65),
    ("Shell", 10),
    ("NGO", 10),
    ("Government", 8),
    ("Criminal", 7),
]


def generate_organizations(rng: random.Random, count: int, id_offset: int = 0) -> list[dict]:
    orgs: list[dict] = []
    used_names: set[str] = set()
    types, weights = zip(*ORG_TYPE_WEIGHTED)

    for i in range(id_offset + 1, id_offset + count + 1):
        industry = rng.choice(ORG_INDUSTRIES)
        city = weighted_city(rng)
        name = _unique_name(rng, industry, city, used_names)
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
                "country": city.country,
                "country_code": city.country_code,
                "region": city.region,
                "lat": lat,
                "lng": lng,
                "registration_date": reg_date.isoformat(),
                "status": "Active",
                "risk_score": 0.0,
            }
        )
    return orgs


def _unique_name(rng: random.Random, industry: str, city, used: set[str]) -> str:
    roots = NAME_ROOTS_BY_REGION.get(city.region) or NAME_ROOTS_BY_REGION["Europe"]
    suffixes = SUFFIXES_BY_INDUSTRY[industry]
    legal = LEGAL_FORM_BY_COUNTRY.get(city.country, "Ltd")
    for _ in range(24):
        name = f"{rng.choice(roots)} {rng.choice(suffixes)} {legal}"
        if name not in used:
            used.add(name)
            return name
    # Fallback once a region's root pool is exhausted at scale.
    name = f"{rng.choice(roots)} {rng.choice(suffixes)} {legal} {rng.randint(2, 999)}"
    used.add(name)
    return name
