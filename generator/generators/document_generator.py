"""Stage 6 (cont'd): Documents — issued between persons and organizations.

Forged / mismatched documents are injected separately by
storyline_generator.py (Stage 8, Document Forgery Ring) so inconsistencies
carry explicit storyline attribution rather than being scattered silently
through otherwise-normal records.
"""

import random
from datetime import date, timedelta

from config import DOCUMENT_TYPES
from generators.common import new_id, new_uuid


def generate_documents(
    rng: random.Random, persons: list[dict], orgs: list[dict], count: int, id_offset: int = 0
) -> list[dict]:
    if not persons:
        return []

    documents: list[dict] = []
    for i in range(id_offset + 1, id_offset + count + 1):
        doc_type = rng.choice(DOCUMENT_TYPES)
        subject = rng.choice(persons)

        if doc_type in ("Passport",):
            issuer_id, issuer_type = None, "Government"
        elif doc_type == "Invoice" and orgs:
            issuer = rng.choice(orgs)
            issuer_id, issuer_type = issuer["id"], "Organization"
        elif orgs and rng.random() < 0.6:
            issuer = rng.choice(orgs)
            issuer_id, issuer_type = issuer["id"], "Organization"
        else:
            issuer = rng.choice(persons)
            issuer_id, issuer_type = issuer["id"], "Person"

        issued = date.today() - timedelta(days=rng.randint(30, 365 * 10))
        expiry = issued + timedelta(days=365 * rng.randint(2, 10))

        documents.append(
            {
                "id": new_uuid(),
                "doc_id": new_id("DOC", i),
                "type": doc_type,
                "issuer_id": issuer_id,
                "issuer_type": issuer_type,
                "subject_id": subject["id"],
                "issued_date": issued.isoformat(),
                "expiry_date": expiry.isoformat(),
                "flagged": False,
                "inconsistency_type": None,
                "storyline_id": None,
            }
        )

    return documents
