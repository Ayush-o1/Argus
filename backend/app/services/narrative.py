"""Deterministic template-based narrative generation (ARGUS_PLAN.md Phase 10,
Local Feature 2). Every clause maps 1:1 to a queried fact — properties, risk
factors already computed by the generator's rule-based scorer, and direct
connection counts. No LLM, no network call, no dependency beyond stdlib."""

from datetime import UTC, date, datetime

CONNECTION_LABEL_NOUNS = {
    "Account": ("account", "accounts"),
    "Device": ("device", "devices"),
    "Vehicle": ("vehicle", "vehicles"),
    "Organization": ("organization", "organizations"),
    "Person": ("person", "people"),
    "Event": ("event", "events"),
    "Document": ("document", "documents"),
    "Shipment": ("shipment", "shipments"),
    "Location": ("location", "locations"),
}


def _age(dob_iso: str) -> int:
    dob = date.fromisoformat(dob_iso)
    today = datetime.now(UTC).date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _risk_band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "moderate"
    return "low"


def _bio_sentence(label: str, name: str, properties: dict) -> str:
    if label == "Person":
        age = _age(properties["dob"]) if properties.get("dob") else None
        age_clause = f"a {age}-year-old " if age is not None else ""
        occupation = properties.get("occupation", "individual").lower()
        city = properties.get("city")
        state = properties.get("state")
        location = f" based in {city}, {state}" if city and state else ""
        return f"{name} is {age_clause}{occupation}{location}."
    if label == "Organization":
        industry = properties.get("industry", "")
        city = properties.get("registered_city")
        state = properties.get("state")
        location = f" registered in {city}, {state}" if city and state else ""
        industry_clause = f" operating in {industry}" if industry else ""
        return f"{name} is an organization{industry_clause}{location}."
    return f"{name} is a {label.lower()} entity in the ARGUS graph."


def _connections_sentence(name: str, connections: dict[str, int]) -> str | None:
    if not connections:
        return None
    parts = []
    for label, count in sorted(connections.items(), key=lambda kv: kv[1], reverse=True):
        singular, plural = CONNECTION_LABEL_NOUNS.get(label, (label.lower(), label.lower() + "s"))
        parts.append(f"{count} {singular if count == 1 else plural}")
    if len(parts) == 1:
        joined = parts[0]
    else:
        joined = ", ".join(parts[:-1]) + f", and {parts[-1]}"
    return f"{name} is directly connected to {joined}."


def compose_entity_narrative(label: str, name: str, properties: dict, connections: dict[str, int]) -> str:
    sentences = [_bio_sentence(label, name, properties)]

    risk_score = properties.get("risk_score", 0)
    band = _risk_band(risk_score)
    sentences.append(f"Risk score: {risk_score:.0f}/100 ({band}).")

    risk_factors: list[str] = properties.get("risk_factors") or []
    if risk_factors:
        if len(risk_factors) == 1:
            sentences.append(f"The risk assessment cites: {risk_factors[0].lower()}")
        else:
            cited = "; ".join(f.lower() for f in risk_factors[:4])
            sentences.append(f"The risk assessment cites {len(risk_factors)} factors: {cited}.")

    connections_sentence = _connections_sentence(name, connections)
    if connections_sentence:
        sentences.append(connections_sentence)

    return " ".join(sentences)


def compose_case_narrative(case: dict, linked_entities: list[dict]) -> str:
    title = case.get("title", "This case")
    status = case.get("status", "Draft")
    priority = case.get("priority", "Medium")
    sentences = [f'"{title}" is currently {status.lower()} with {priority.lower()} priority.']

    if linked_entities:
        by_label: dict[str, int] = {}
        for entity in linked_entities:
            by_label[entity["label"]] = by_label.get(entity["label"], 0) + 1
        parts = []
        for label, count in by_label.items():
            singular, plural = CONNECTION_LABEL_NOUNS.get(label, (label.lower(), label.lower() + "s"))
            parts.append(f"{count} {singular if count == 1 else plural}")
        sentences.append(f"The evidence board links {', '.join(parts)}.")
    else:
        sentences.append("No entities have been linked to the evidence board yet.")

    notes = case.get("notes", "").strip()
    if notes:
        sentences.append(f"Analyst notes: {notes}")

    return " ".join(sentences)
