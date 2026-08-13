"""
Global geography reference for the synthetic world.

ARGUS models a *global* operating picture: an analyst should be able to move
World -> Region -> Country -> City -> Entity without the dataset quietly
collapsing into one country. Real place names and coordinates are used purely
to ground synthetic entities in plausible geography (see README's ethics note);
every person, organization, shipment and event placed at these coordinates is
procedurally generated and fictional.

South Asia (and India within it) is deliberately the heaviest-weighted region:
it is the product's declared *area of interest*, not the whole world model.
Weights are activity weights, not population — they only need to produce a
distribution where regional differences are legible on a map.
"""

from dataclasses import dataclass, field


# Faker locale per region. Names should look like they belong to the place the
# entity is registered in; a world where every synthetic person in Rotterdam
# and Busan has an Indian name reads as a bug, not as a global dataset.
REGION_LOCALES: dict[str, list[str]] = {
    "South Asia": ["en_IN"],
    "Middle East": ["ar_SA", "ar_AA", "fa_IR"],
    "Central Asia": ["ru_RU", "tr_TR"],
    "Southeast Asia": ["id_ID", "th_TH", "en_PH", "vi_VN"],
    "East Asia": ["zh_CN", "ja_JP", "ko_KR"],
    "Europe": ["en_GB", "de_DE", "nl_NL", "it_IT", "el_GR", "tr_TR"],
    "Africa": ["ar_EG", "fr_FR", "en_US"],
    "North America": ["en_US", "es_MX"],
    "South America": ["pt_BR", "es_ES"],
    "Oceania": ["en_AU"],
}

# Representative centroid + default zoom for each region, used by the map's
# region rollup so "fly to region" lands somewhere meaningful rather than on
# the arithmetic mean of its cities (which for Europe sits in a field).
REGION_CENTERS: dict[str, tuple[float, float, float]] = {
    "South Asia": (21.0, 78.0, 4.0),
    "Middle East": (25.0, 51.0, 4.4),
    "Central Asia": (41.5, 63.0, 4.2),
    "Southeast Asia": (5.0, 108.0, 4.0),
    "East Asia": (28.0, 122.0, 4.0),
    "Europe": (48.5, 10.0, 3.8),
    "Africa": (5.0, 20.0, 3.2),
    "North America": (35.0, -90.0, 3.4),
    "South America": (-20.0, -60.0, 3.4),
    "Oceania": (-33.0, 148.0, 4.0),
}


@dataclass(frozen=True)
class City:
    name: str
    state: str  # state / province / emirate — the sub-national admin area
    country: str
    country_code: str
    region: str
    lat: float
    lng: float
    weight: float
    # Functional roles. "port" makes a city eligible as a shipment endpoint;
    # "financial" and "hub" drive where organizations and accounts cluster.
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_port(self) -> bool:
        return "port" in self.tags


# fmt: off
CITIES: list[City] = [
    # --- South Asia (area of interest — heaviest weighting) -------------------
    City("Mumbai",      "Maharashtra",   "India",       "IN", "South Asia", 19.0760,  72.8777, 20, ("port", "financial", "hub")),
    City("Delhi",       "Delhi",         "India",       "IN", "South Asia", 28.7041,  77.1025, 18, ("hub",)),
    City("Bengaluru",   "Karnataka",     "India",       "IN", "South Asia", 12.9716,  77.5946, 14, ("hub",)),
    City("Chennai",     "Tamil Nadu",    "India",       "IN", "South Asia", 13.0827,  80.2707, 12, ("port", "hub")),
    City("Hyderabad",   "Telangana",     "India",       "IN", "South Asia", 17.3850,  78.4867, 10, ()),
    City("Kolkata",     "West Bengal",   "India",       "IN", "South Asia", 22.5726,  88.3639,  9, ("port",)),
    City("Pune",        "Maharashtra",   "India",       "IN", "South Asia", 18.5204,  73.8567,  8, ()),
    City("Ahmedabad",   "Gujarat",       "India",       "IN", "South Asia", 23.0225,  72.5714,  7, ()),
    City("Kochi",       "Kerala",        "India",       "IN", "South Asia",  9.9312,  76.2673,  5, ("port",)),
    City("Mundra",      "Gujarat",       "India",       "IN", "South Asia", 22.8394,  69.7219,  4, ("port",)),
    City("Karachi",     "Sindh",         "Pakistan",    "PK", "South Asia", 24.8607,  67.0011,  8, ("port", "hub")),
    City("Colombo",     "Western",       "Sri Lanka",   "LK", "South Asia",  6.9271,  79.8612,  7, ("port", "hub")),
    City("Dhaka",       "Dhaka",         "Bangladesh",  "BD", "South Asia", 23.8103,  90.4125,  6, ("hub",)),
    City("Chattogram",  "Chattogram",    "Bangladesh",  "BD", "South Asia", 22.3569,  91.7832,  5, ("port",)),
    City("Kathmandu",   "Bagmati",       "Nepal",       "NP", "South Asia", 27.7172,  85.3240,  3, ()),
    City("Male",        "Kaafu",         "Maldives",    "MV", "South Asia",  4.1755,  73.5093,  2, ("port",)),

    # --- Middle East ---------------------------------------------------------
    City("Dubai",       "Dubai",         "UAE",         "AE", "Middle East", 25.2048, 55.2708, 14, ("port", "financial", "hub")),
    City("Abu Dhabi",   "Abu Dhabi",     "UAE",         "AE", "Middle East", 24.4539, 54.3773,  7, ("port",)),
    City("Doha",        "Ad Dawhah",     "Qatar",       "QA", "Middle East", 25.2854, 51.5310,  6, ("port", "financial")),
    City("Riyadh",      "Riyadh",        "Saudi Arabia","SA", "Middle East", 24.7136, 46.6753,  7, ("financial",)),
    City("Jeddah",      "Makkah",        "Saudi Arabia","SA", "Middle East", 21.4858, 39.1925,  6, ("port", "hub")),
    City("Muscat",      "Muscat",        "Oman",        "OM", "Middle East", 23.5880, 58.3829,  4, ("port",)),
    City("Manama",      "Capital",       "Bahrain",     "BH", "Middle East", 26.2285, 50.5860,  4, ("financial",)),
    City("Bandar Abbas","Hormozgan",     "Iran",        "IR", "Middle East", 27.1865, 56.2808,  4, ("port",)),

    # --- Central Asia --------------------------------------------------------
    City("Tashkent",    "Tashkent",      "Uzbekistan",  "UZ", "Central Asia", 41.2995, 69.2401, 4, ("hub",)),
    City("Almaty",      "Almaty",        "Kazakhstan",  "KZ", "Central Asia", 43.2220, 76.8512, 4, ("hub",)),
    City("Baku",        "Baku",          "Azerbaijan",  "AZ", "Central Asia", 40.4093, 49.8671, 4, ("port",)),
    City("Ashgabat",    "Ahal",          "Turkmenistan","TM", "Central Asia", 37.9601, 58.3261, 2, ()),

    # --- Southeast Asia ------------------------------------------------------
    City("Singapore",   "Singapore",     "Singapore",   "SG", "Southeast Asia",  1.3521, 103.8198, 15, ("port", "financial", "hub")),
    City("Bangkok",     "Bangkok",       "Thailand",    "TH", "Southeast Asia", 13.7563, 100.5018,  8, ("port", "hub")),
    City("Jakarta",     "Jakarta",       "Indonesia",   "ID", "Southeast Asia", -6.2088, 106.8456,  8, ("port",)),
    City("Ho Chi Minh City", "Ho Chi Minh", "Vietnam",  "VN", "Southeast Asia", 10.8231, 106.6297,  7, ("port",)),
    City("Kuala Lumpur","Selangor",      "Malaysia",    "MY", "Southeast Asia",  3.1390, 101.6869,  6, ("financial",)),
    City("Port Klang",  "Selangor",      "Malaysia",    "MY", "Southeast Asia",  3.0000, 101.4000,  5, ("port",)),
    City("Manila",      "Metro Manila",  "Philippines", "PH", "Southeast Asia", 14.5995, 120.9842,  6, ("port",)),

    # --- East Asia -----------------------------------------------------------
    City("Hong Kong",   "Hong Kong",     "Hong Kong",   "HK", "East Asia", 22.3193, 114.1694, 12, ("port", "financial", "hub")),
    City("Shanghai",    "Shanghai",      "China",       "CN", "East Asia", 31.2304, 121.4737, 13, ("port", "hub")),
    City("Shenzhen",    "Guangdong",     "China",       "CN", "East Asia", 22.5431, 114.0579, 10, ("port",)),
    City("Busan",       "Busan",         "South Korea", "KR", "East Asia", 35.1796, 129.0756,  7, ("port",)),
    City("Tokyo",       "Tokyo",         "Japan",       "JP", "East Asia", 35.6762, 139.6503,  9, ("financial", "hub")),
    City("Kaohsiung",   "Kaohsiung",     "Taiwan",      "TW", "East Asia", 22.6273, 120.3014,  5, ("port",)),

    # --- Europe --------------------------------------------------------------
    City("Rotterdam",   "South Holland", "Netherlands", "NL", "Europe", 51.9244,  4.4777, 11, ("port", "hub")),
    City("Hamburg",     "Hamburg",       "Germany",     "DE", "Europe", 53.5511,  9.9937,  8, ("port",)),
    City("Antwerp",     "Flanders",      "Belgium",     "BE", "Europe", 51.2194,  4.4025,  7, ("port",)),
    City("London",      "England",       "United Kingdom","GB","Europe", 51.5074, -0.1278, 12, ("financial", "hub")),
    City("Zurich",      "Zurich",        "Switzerland", "CH", "Europe", 47.3769,  8.5417,  6, ("financial",)),
    City("Frankfurt",   "Hesse",         "Germany",     "DE", "Europe", 50.1109,  8.6821,  6, ("financial",)),
    City("Piraeus",     "Attica",        "Greece",      "GR", "Europe", 37.9420, 23.6465,  5, ("port",)),
    City("Istanbul",    "Istanbul",      "Turkey",      "TR", "Europe", 41.0082, 28.9784,  8, ("port", "hub")),
    City("Valletta",    "South Eastern", "Malta",       "MT", "Europe", 35.8989, 14.5146,  3, ("port",)),
    City("Limassol",    "Limassol",      "Cyprus",      "CY", "Europe", 34.7071, 33.0226,  3, ("financial", "port")),

    # --- Africa --------------------------------------------------------------
    City("Durban",      "KwaZulu-Natal", "South Africa","ZA", "Africa", -29.8587, 31.0218, 6, ("port",)),
    City("Lagos",       "Lagos",         "Nigeria",     "NG", "Africa",   6.5244,  3.3792, 7, ("port", "hub")),
    City("Mombasa",     "Mombasa",       "Kenya",       "KE", "Africa",  -4.0435, 39.6682, 5, ("port",)),
    City("Djibouti",    "Djibouti",      "Djibouti",    "DJ", "Africa",  11.5721, 43.1456, 4, ("port",)),
    City("Alexandria",  "Alexandria",    "Egypt",       "EG", "Africa",  31.2001, 29.9187, 5, ("port",)),
    City("Casablanca",  "Casablanca",    "Morocco",     "MA", "Africa",  33.5731, -7.5898, 4, ("port",)),
    City("Tangier",     "Tanger",        "Morocco",     "MA", "Africa",  35.7595, -5.8340, 4, ("port",)),

    # --- North America -------------------------------------------------------
    City("New York",    "New York",      "United States","US","North America", 40.7128, -74.0060, 12, ("port", "financial", "hub")),
    City("Los Angeles", "California",    "United States","US","North America", 33.7405,-118.2760,  9, ("port",)),
    City("Houston",     "Texas",         "United States","US","North America", 29.7604, -95.3698,  7, ("port",)),
    City("Toronto",     "Ontario",       "Canada",      "CA", "North America", 43.6532, -79.3832,  6, ("financial",)),
    City("Panama City", "Panama",        "Panama",      "PA", "North America",  8.9824, -79.5199,  5, ("port", "hub")),
    City("Colon",       "Colon",         "Panama",      "PA", "North America",  9.3592, -79.9014,  3, ("port",)),

    # --- South America -------------------------------------------------------
    City("Santos",      "Sao Paulo",     "Brazil",      "BR", "South America", -23.9608, -46.3336, 6, ("port",)),
    City("Buenos Aires","Buenos Aires",  "Argentina",   "AR", "South America", -34.6037, -58.3816, 5, ("port", "financial")),
    City("Callao",      "Callao",        "Peru",        "PE", "South America", -12.0508, -77.1181, 4, ("port",)),
    City("Cartagena",   "Bolivar",       "Colombia",    "CO", "South America",  10.3910, -75.4794, 4, ("port",)),

    # --- Oceania -------------------------------------------------------------
    City("Sydney",      "New South Wales","Australia",  "AU", "Oceania", -33.8688, 151.2093, 6, ("financial", "port")),
    City("Melbourne",   "Victoria",      "Australia",   "AU", "Oceania", -37.8136, 144.9631, 5, ("port",)),
]
# fmt: on


REGIONS: list[str] = list(REGION_CENTERS.keys())

# Faker's phone_number provider isn't implemented for every locale used here
# (ar_AA and several others raise AttributeError), and its output wouldn't carry
# a country code anyway. Synthesising from the real dialing code gives every
# person a number that is consistent with where they're registered.
CALLING_CODES: dict[str, str] = {
    "IN": "+91", "PK": "+92", "BD": "+880", "LK": "+94", "NP": "+977", "MV": "+960",
    "AE": "+971", "QA": "+974", "SA": "+966", "OM": "+968", "BH": "+973", "IR": "+98",
    "UZ": "+998", "KZ": "+7", "AZ": "+994", "TM": "+993",
    "SG": "+65", "TH": "+66", "ID": "+62", "VN": "+84", "MY": "+60", "PH": "+63",
    "HK": "+852", "CN": "+86", "KR": "+82", "JP": "+81", "TW": "+886",
    "NL": "+31", "DE": "+49", "BE": "+32", "GB": "+44", "CH": "+41", "GR": "+30",
    "TR": "+90", "MT": "+356", "CY": "+357",
    "ZA": "+27", "NG": "+234", "KE": "+254", "DJ": "+253", "EG": "+20", "MA": "+212",
    "US": "+1", "CA": "+1", "PA": "+507",
    "BR": "+55", "AR": "+54", "PE": "+51", "CO": "+57",
    "AU": "+61",
}

PORT_CITIES: list[City] = [c for c in CITIES if c.is_port]
FINANCIAL_CITIES: list[City] = [c for c in CITIES if "financial" in c.tags]


def cities_in_region(region: str) -> list[City]:
    return [c for c in CITIES if c.region == region]


# --- Trade lanes -------------------------------------------------------------
# Shipments follow weighted *lanes* rather than connecting two random ports.
# A uniformly random origin/destination pairing produces a hairball with no
# structure, so nothing on the map can be "anomalous" in any meaningful sense —
# every route is equally arbitrary. Weighting plausible corridors gives the
# dataset a baseline for off-lane routing to actually deviate from.
TRADE_LANES: list[tuple[str, str, float]] = [
    ("East Asia", "Europe", 14),
    ("East Asia", "North America", 12),
    ("East Asia", "South Asia", 10),
    ("Southeast Asia", "Europe", 9),
    ("Southeast Asia", "South Asia", 8),
    ("Southeast Asia", "East Asia", 8),
    ("South Asia", "Middle East", 12),
    ("South Asia", "Europe", 9),
    ("South Asia", "Africa", 6),
    ("South Asia", "North America", 6),
    ("Middle East", "Europe", 8),
    ("Middle East", "Africa", 6),
    ("Middle East", "East Asia", 7),
    ("Europe", "North America", 8),
    ("Europe", "Africa", 6),
    ("Africa", "East Asia", 5),
    ("South America", "North America", 5),
    ("South America", "Europe", 4),
    ("South America", "East Asia", 3),
    ("Oceania", "East Asia", 4),
    ("Oceania", "Southeast Asia", 3),
    ("Central Asia", "East Asia", 3),
    ("Central Asia", "Europe", 3),
    ("Central Asia", "South Asia", 2),
]

# Region pairs with essentially no direct maritime freight relationship. A
# shipment routed along one of these is what "off-lane" means in this dataset —
# it is defined against the baseline above rather than asserted by a flag.
IMPLAUSIBLE_LANES: set[frozenset[str]] = {
    frozenset({"South America", "Central Asia"}),
    frozenset({"Oceania", "Central Asia"}),
    frozenset({"Oceania", "South America"}),
    frozenset({"Africa", "Central Asia"}),
    frozenset({"North America", "Central Asia"}),
}
