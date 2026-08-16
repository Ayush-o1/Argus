"""The view of an entity that the matcher is allowed to see.

An `EntityProfile` is a deliberately narrow projection. The graph node has more
on it than this — a risk score, community ids, flags — and the matcher is
denied all of it.

That denial is the point. Those properties are either analytic output or
generator ground truth, and a matcher that reads them would be resolving
identity partly from conclusions ARGUS itself drew, which is the same
circularity the audit found in risk scoring (G-08). Two records are the same
person because their *observable attributes* say so, or they are not.

The allowlist below is therefore a security boundary as much as a schema, and
`tests/test_resolution_isolation.py` fails if it grows a field that carries a
conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Properties the matcher may read, per entity type, mapped to the profile key
# the scoring model names. Anything not listed is invisible to matching.
#
# Explicitly NOT here, and never to be added: risk_score, risk_factors, flags,
# community_ids, storyline_id, flagged. Those are conclusions, not observations.
_ATTRIBUTE_MAP: dict[str, dict[str, str]] = {
    "Person": {
        "name": "name",
        "alias": "aliases",
        "dob": "date_of_birth",
        "phone": "phone",
        "nationality": "nationality",
        "occupation": "occupation",
        "city": "city",
        "state": "state",
        "country": "country",
        "gender": "gender",
    },
    "Organization": {
        "name": "name",
        "industry": "industry",
        "type": "org_type",
        "registration_date": "registration_date",
        "registered_city": "city",
        "state": "state",
        "country": "country",
    },
    "Vehicle": {
        "plate": "plate",
        "make": "make",
        "model": "model",
        "color": "color",
        "type": "vehicle_type",
    },
    "Device": {
        "imei": "imei",
        "mac": "mac",
        "carrier": "carrier",
        "type": "device_type",
    },
}

# Entity types the matcher understands. A type absent from here is not
# "unmatched" by accident — it has no declared attributes to match on, and
# guessing would be worse than declining.
SUPPORTED_TYPES: frozenset[str] = frozenset(_ATTRIBUTE_MAP)

# Every attribute name the matcher understands, across all types. A connector
# mapping is validated against this, so a feed declaring `email` — which
# nothing scores — is refused at configuration time rather than contributing
# nothing at match time and looking as though it did.
MATCHABLE_ATTRIBUTES: frozenset[str] = frozenset(
    key for mapping in _ATTRIBUTE_MAP.values() for key in mapping.values()
) | {"lat", "lng"}

ID_FIELDS = {
    "Person": "person_id",
    "Organization": "org_id",
    "Vehicle": "vehicle_id",
    "Device": "device_id",
}

# Coordinates are read for the geo comparator; they are observations of where a
# record places the entity, not a conclusion ARGUS drew.
_GEO_KEYS = ("lat", "lng")


def allowed_source_keys(entity_type: str) -> tuple[str, ...]:
    """Graph properties the matcher may read for a type, id and geo included.

    Used to build the Cypher projection, so forbidden properties are never read
    out of the database at all rather than being read and then discarded. A
    filter applied after the fetch is a convention; a projection that never
    names the column is a boundary.
    """
    mapping = _ATTRIBUTE_MAP.get(entity_type)
    if mapping is None:
        return ()
    return (ID_FIELDS[entity_type], *sorted(mapping), *_GEO_KEYS)


@dataclass(frozen=True)
class EntityProfile:
    """Everything the matcher knows about one record.

    `ref` is the human-readable id (`PRS-0002001`) rather than the internal
    uuid, because it is what every other ARGUS surface — provenance subjects,
    case links, the audit log — uses to name an entity. A merge decision has to
    be legible in the audit log without a database to hand.
    """

    ref: str
    entity_type: str
    attributes: dict[str, Any] = field(default_factory=dict)
    coordinates: tuple[float, float] | None = None
    # Where this profile came from: "graph" for a node already in ARGUS,
    # or a source id for a record arriving from a feed that has not been
    # resolved to anything yet.
    origin: str = "graph"

    def get(self, key: str) -> Any:
        return self.attributes.get(key)

    @property
    def display_name(self) -> str:
        for key in ("name", "plate", "imei"):
            value = self.attributes.get(key)
            if value:
                return str(value)
        return self.ref


def profile_from_node(entity_type: str, node: dict[str, Any]) -> EntityProfile | None:
    """Project a Neo4j node onto the matcher's allowed view.

    Returns None for an unsupported type or a node with no id, rather than a
    profile with an empty ref — a profile that cannot be named cannot be merged
    into anything, and carrying one around invites it being compared anyway.
    """
    mapping = _ATTRIBUTE_MAP.get(entity_type)
    if mapping is None:
        return None

    ref = node.get(ID_FIELDS.get(entity_type, ""))
    if not ref:
        return None

    attributes: dict[str, Any] = {}
    for source_key, profile_key in mapping.items():
        value = node.get(source_key)
        if value is None or value == "" or value == []:
            continue
        attributes[profile_key] = value

    coordinates = None
    lat, lng = node.get("lat"), node.get("lng")
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        coordinates = (float(lat), float(lng))

    return EntityProfile(
        ref=str(ref), entity_type=entity_type, attributes=attributes, coordinates=coordinates
    )


def profile_from_record(
    ref: str, entity_type: str, values: dict[str, Any], *, origin: str
) -> EntityProfile | None:
    """Build a profile from an inbound feed record.

    Keys are the *profile* keys (`date_of_birth`, not `dob`), because a feed's
    mapping already translates into ARGUS's vocabulary at ingest. Unknown keys
    are dropped rather than passed through: an attribute nothing scores is
    weight the model does not have, and letting a feed introduce one silently
    would let the feed change how matching behaves.
    """
    mapping = _ATTRIBUTE_MAP.get(entity_type)
    if mapping is None:
        return None

    allowed = set(mapping.values())
    attributes = {
        key: value
        for key, value in values.items()
        if key in allowed and value not in (None, "", [])
    }

    coordinates = None
    lat, lng = values.get("lat"), values.get("lng")
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        coordinates = (float(lat), float(lng))

    return EntityProfile(
        ref=ref,
        entity_type=entity_type,
        attributes=attributes,
        coordinates=coordinates,
        origin=origin,
    )
