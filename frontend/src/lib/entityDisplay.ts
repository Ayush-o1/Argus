/** Mirrors backend/app/repositories/entity_labels.py — resolves the human-readable
 * id and display name out of a raw {label, properties} entity reference (as
 * returned by Case.linked_entities / Incident.involved_entities), which carry
 * the node's native properties rather than a normalized GraphNode shape. */

const FIELD_BY_LABEL: Record<string, { id: string; name: string }> = {
  Person: { id: "person_id", name: "name" },
  Organization: { id: "org_id", name: "name" },
  Account: { id: "account_id", name: "account_id" },
  Device: { id: "device_id", name: "device_id" },
  Vehicle: { id: "vehicle_id", name: "plate" },
  Document: { id: "doc_id", name: "doc_id" },
  Shipment: { id: "shipment_id", name: "shipment_id" },
  Event: { id: "event_id", name: "type" },
  Location: { id: "location_id", name: "name" },
  Case: { id: "case_id", name: "title" },
  Incident: { id: "incident_id", name: "type" },
  Storyline: { id: "storyline_id", name: "type" },
};

export function entityId(label: string, properties: Record<string, unknown>): string | null {
  const field = FIELD_BY_LABEL[label];
  if (!field) return null;
  const value = properties[field.id];
  return typeof value === "string" ? value : null;
}

export function entityName(label: string, properties: Record<string, unknown>): string {
  const field = FIELD_BY_LABEL[label];
  const value = field ? properties[field.name] : undefined;
  return typeof value === "string" ? value : (entityId(label, properties) ?? label);
}
