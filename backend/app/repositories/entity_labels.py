"""Maps a human-readable ID prefix to its Neo4j label, ID field, and display-name
field. Mirrors the generator's ID scheme (see generator/config.py naming) —
duplicated rather than shared, since the generator and backend are separate
deployables by design (ARGUS_PLAN.md Phase 14)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntityLabelInfo:
    label: str
    id_field: str
    name_field: str


ENTITY_LABELS: dict[str, EntityLabelInfo] = {
    "PRS": EntityLabelInfo("Person", "person_id", "name"),
    "ORG": EntityLabelInfo("Organization", "org_id", "name"),
    "ACC": EntityLabelInfo("Account", "account_id", "account_id"),
    "DEV": EntityLabelInfo("Device", "device_id", "device_id"),
    "VEH": EntityLabelInfo("Vehicle", "vehicle_id", "plate"),
    "DOC": EntityLabelInfo("Document", "doc_id", "doc_id"),
    "SHP": EntityLabelInfo("Shipment", "shipment_id", "shipment_id"),
    "EVT": EntityLabelInfo("Event", "event_id", "type"),
    "LOC": EntityLabelInfo("Location", "location_id", "name"),
    "CASE": EntityLabelInfo("Case", "case_id", "title"),
    "INC": EntityLabelInfo("Incident", "incident_id", "type"),
    "STL": EntityLabelInfo("Storyline", "storyline_id", "type"),
}


def resolve_label(human_id: str) -> EntityLabelInfo | None:
    prefix = human_id.split("-")[0]
    return ENTITY_LABELS.get(prefix)
