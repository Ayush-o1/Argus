"""
Generator configuration: seed, scale parameters, and the fixed reference
data (banks, telecoms, carriers) for the synthetic world. The geography
itself — regions, countries, cities, trade lanes — lives in `geography.py`.
See ARGUS_PLAN.md Phase 4 and Phase 8 for rationale.
"""

from dataclasses import dataclass, field

from geography import CITIES, REGIONS, City  # noqa: F401  (re-exported for generators)

# Every institution here is fictional. Names are grouped by region so that an
# account opened in Rotterdam isn't held at a bank whose name only makes sense
# in Gujarat — regional plausibility is what makes the dataset readable as a
# global picture rather than one country's data with foreign coordinates.
SYNTHETIC_BANKS_BY_REGION: dict[str, list[str]] = {
    "South Asia": ["Surya FinTech Bank", "Narmada Cooperative Bank", "Konkan Trust Bank", "Deccan Mercantile Bank"],
    "Middle East": ["Gulf Meridian Bank", "Al-Nahda Commercial Bank", "Pearl Coast Financial"],
    "Central Asia": ["Steppe Continental Bank", "Caspian Union Bank"],
    "Southeast Asia": ["Straits Anchor Bank", "Mekong Commercial Bank", "Equator Trust Bank"],
    "East Asia": ["Orient Harbour Bank", "Pacific Rim Mercantile", "東 Meridian Trust"],
    "Europe": ["Nordkap Handelsbank", "Meridian Clearing Bank", "Alpine Reserve Bank", "Hansa Union Bank"],
    "Africa": ["Sahel Continental Bank", "Cape Meridian Bank", "Nile Commercial Trust"],
    "North America": ["Atlantic Charter Bank", "Cascadia Federal Trust", "Isthmus Commercial Bank"],
    "South America": ["Andes Mercantile Bank", "Rio Plata Comercial"],
    "Oceania": ["Southern Cross Mutual", "Tasman Reserve Bank"],
}

# Flat list for code paths that just need a plausible institution name.
SYNTHETIC_BANKS = [name for names in SYNTHETIC_BANKS_BY_REGION.values() for name in names]

SYNTHETIC_TELECOMS = [
    "Saffron Mobility",
    "Aether Telecom",
    "NordLink Wireless",
    "Meridian Mobile",
    "Pacific Signal",
    "Sahara Cellular",
]

SYNTHETIC_CARRIERS = [
    "Shakti Logistics Pvt Ltd",
    "Astra Freight Lines",
    "Konkan Port Movers",
    "Ganga Cargo Systems",
    "Meridian Container Lines",
    "Northwind Maritime",
    "Blue Isthmus Shipping",
    "Sable Coast Freight",
    "Orient Anchor Lines",
    "Transverse Bulk Carriers",
]

ORG_INDUSTRIES = [
    "Logistics",
    "FinTech",
    "Manufacturing",
    "Textiles",
    "Healthcare",
    "Energy",
    "Real Estate",
    "Import/Export",
    "IT Services",
    "Agriculture",
    "Maritime Shipping",
    "Commodities Trading",
    "Freight Forwarding",
]

OCCUPATIONS = [
    "Import Merchant",
    "Software Engineer",
    "Chartered Accountant",
    "Logistics Manager",
    "Bank Officer",
    "Government Employee",
    "Textile Trader",
    "Real Estate Broker",
    "Physician",
    "Freight Forwarder",
    "Retail Shop Owner",
    "Consultant",
]

DOCUMENT_TYPES = ["Passport", "ContractFinancial", "Registration", "License", "Invoice"]

STORYLINE_TYPES = [
    "shell_company_ring",
    "money_routing_network",
    "communication_cluster",
    "supply_chain_divergence",
    "document_forgery_ring",
    "identity_overlap",
    "anomalous_transaction_burst",
]


@dataclass(frozen=True)
class ScaleConfig:
    """Entity counts. Defaults match ARGUS_PLAN.md Phase 4's local-first demo scale."""

    person_count: int = 4_000
    org_count: int = 400
    location_count: int = 600
    vehicle_count: int = 900
    device_count: int = 1_500
    account_count: int = 2_800
    transaction_count: int = 40_000
    event_count: int = 6_000
    communication_count: int = 15_000
    shipment_count: int = 1_200
    document_count: int = 2_000
    storyline_count: int = 15


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    scale: ScaleConfig = field(default_factory=ScaleConfig)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "argus_dev_password"
    wipe_existing: bool = False  # opt-in; wiping destroys analyst-created cases (audit B-24)
