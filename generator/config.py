"""
Generator configuration: seed, scale parameters, and the fixed reference
data (cities, banks, telecoms, carriers) that grounds ARGUS in real Indian
geography. See ARGUS_PLAN.md Phase 4 and Phase 8 for rationale.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class City:
    name: str
    state: str
    lat: float
    lng: float
    weight: float  # relative population/activity weight for sampling


# Real coordinates. Weights are illustrative (roughly population-order), not
# census-accurate — they only need to produce a plausible distribution.
CITIES: list[City] = [
    City("Mumbai", "Maharashtra", 19.0760, 72.8777, 20),
    City("Delhi", "Delhi", 28.7041, 77.1025, 20),
    City("Bengaluru", "Karnataka", 12.9716, 77.5946, 16),
    City("Hyderabad", "Telangana", 17.3850, 78.4867, 12),
    City("Chennai", "Tamil Nadu", 13.0827, 80.2707, 12),
    City("Pune", "Maharashtra", 18.5204, 73.8567, 10),
    City("Ahmedabad", "Gujarat", 23.0225, 72.5714, 8),
    City("Jaipur", "Rajasthan", 26.9124, 75.7873, 6),
    City("Lucknow", "Uttar Pradesh", 26.8467, 80.9462, 5),
    City("Patna", "Bihar", 25.5941, 85.1376, 4),
]

SYNTHETIC_BANKS = [
    "Surya FinTech Bank",
    "Narmada Cooperative Bank",
    "Reserve Nexus Bank",
    "Konkan Trust Bank",
    "Deccan Mercantile Bank",
    "Himalaya Savings Bank",
]

SYNTHETIC_TELECOMS = ["Saffron Mobility", "Aether Telecom", "NordLink Wireless"]

SYNTHETIC_CARRIERS = [
    "Shakti Logistics Pvt Ltd",
    "Astra Freight Lines",
    "Konkan Port Movers",
    "Ganga Cargo Systems",
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
    wipe_existing: bool = True
