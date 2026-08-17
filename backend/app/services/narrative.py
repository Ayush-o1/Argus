"""Deterministic template-based narrative generation (ARGUS_PLAN.md Phase 10,
Local Feature 2). Every clause maps 1:1 to a queried fact. No LLM, no network
call, no dependency beyond stdlib.

The risk clause used to read the generator's `risk_score` and `risk_factors`
and render them as prose — "Risk score: 87/100 (critical). The risk assessment
cites: linked to money routing network." That was the answer key, restated in
the confident voice of an analyst's summary, which is the most misleading form
it could take. It now describes ARGUS's own assessment, and says plainly when
there is not one."""

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


# Phrasing per band. Deliberately not adjectives about the subject: ARGUS
# assesses evidence, and "critical person" is a claim it cannot support.
BAND_PHRASING = {
    "elevated": "ARGUS assessed this as warranting review",
    "notable": "ARGUS found something worth noting",
    "routine": "ARGUS examined the available evidence and found nothing of note",
    "insufficient_evidence": "ARGUS does not have enough evidence to assess this",
}


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


def _assessment_sentence(properties: dict) -> str:
    """One sentence about ARGUS's assessment, including its absence.

    The coverage is stated alongside the score wherever there is one, because a
    score without its denominator is the number this module used to print.
    """
    band = properties.get("argus_band")
    if band is None:
        return (
            "ARGUS has published no risk assessment for this entity — either its type is not "
            "assessed or no assessment run has covered it yet."
        )
    phrasing = BAND_PHRASING.get(band, f"ARGUS assessed this as {band}")
    score = properties.get("argus_score")
    coverage = properties.get("argus_coverage")
    if score is None:
        return f"{phrasing}; no score is published where the evidence does not support one."
    coverage_clause = (
        f", over the {coverage * 100:.0f}% of its model it could evaluate" if coverage else ""
    )
    return f"{phrasing} (score {score:.0f} of 100{coverage_clause})."


def compose_entity_narrative(label: str, name: str, properties: dict, connections: dict[str, int]) -> str:
    sentences = [_bio_sentence(label, name, properties)]

    sentences.append(_assessment_sentence(properties))

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
