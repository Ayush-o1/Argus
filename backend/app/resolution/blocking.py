"""Candidate generation — deciding which pairs are worth scoring at all.

Scoring every pair is quadratic. 20,000 people is 200 million comparisons, and
the answer for essentially all of them is "obviously not". Blocking narrows
that to pairs sharing at least one cheap, coarse key.

Blocking is a **recall** decision, and it is the one place in this pipeline
where a mistake is invisible. A pair that no key brings together is never
scored, never queued, and never appears anywhere as a thing ARGUS declined to
consider — it simply is not in the output. That is why:

  * several independent keys are used rather than one good one, so a missing
    or corrupted attribute costs recall on one key instead of all of them;
  * every candidate records *which* keys produced it, so a merge can state why
    the pair was ever compared;
  * an over-large block is reported rather than silently truncated. A key that
    matches thousands of records is a key that has stopped discriminating, and
    hiding that would make the recall loss undetectable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.resolution.normalize import (
    identifier_key,
    name_tokens,
    parse_date,
    phone_digits,
    phonetic_token,
)
from app.resolution.profile import EntityProfile

# A block larger than this is not narrowing anything. Producing its pairs would
# cost more than the full quadratic scan it exists to avoid, and the pairs it
# produced would be near-worthless. Skipped and *counted*, never silent.
MAX_BLOCK_SIZE = 60

_PHONE_SUFFIX = 8


def _phonetic_key(tokens: list[str]) -> str:
    """Order-independent phonetic signature of a name.

    Sorted so "John Smith" and "Smith John" land in the same block; limited to
    four tokens so a long name does not produce a key so specific it blocks
    with nothing.

    `phonetic_token` rather than `soundex` directly: Soundex returns nothing at
    all for a name in a non-Latin script, which silently excluded those records
    from name blocking entirely.
    """
    codes = sorted({phonetic_token(t) for t in tokens if t})
    return "-".join(c for c in codes[:4] if c)


def blocking_keys(profile: EntityProfile) -> set[str]:
    """Every block this profile belongs to.

    A profile with no usable key returns an empty set and will never be
    compared with anything. That is honest — ARGUS has nothing to go on — and
    `BlockingReport.unblocked` counts them, because a growing population of
    unblockable records is a data quality problem worth seeing.
    """
    keys: set[str] = set()
    entity_type = profile.entity_type

    if entity_type in ("Person", "Organization"):
        kind = "person" if entity_type == "Person" else "organization"
        name = profile.get("name")
        tokens = name_tokens(str(name), kind=kind) if name else []
        phonetic = _phonetic_key(tokens)

        if phonetic:
            keys.add(f"{entity_type}:name_phonetic:{phonetic}")

            # A second, narrower key on the last token plus a discriminator.
            # Catches pairs whose full token sets differ — one source recording
            # a middle name, another not — which the phonetic key above misses
            # because it hashes the whole set.
            last = phonetic_token(tokens[-1]) if tokens else ""
            if last:
                if entity_type == "Person":
                    dob = parse_date(profile.get("date_of_birth"))
                    if dob:
                        keys.add(f"Person:surname_dobyear:{last}-{dob.year}")
                    city = profile.get("city")
                    if city:
                        keys.add(f"Person:surname_city:{last}-{identifier_key(str(city))}")
                else:
                    country = profile.get("country")
                    if country:
                        keys.add(
                            f"Organization:name_country:{last}-{identifier_key(str(country))}"
                        )

    if entity_type == "Person":
        phone = profile.get("phone")
        digits = phone_digits(str(phone)) if phone else ""
        if len(digits) >= _PHONE_SUFFIX:
            keys.add(f"Person:phone_suffix:{digits[-_PHONE_SUFFIX:]}")

    if entity_type == "Vehicle":
        plate = profile.get("plate")
        if plate:
            keys.add(f"Vehicle:plate:{identifier_key(str(plate))}")

    if entity_type == "Device":
        for attribute in ("imei", "mac"):
            value = profile.get(attribute)
            if value:
                keys.add(f"Device:{attribute}:{identifier_key(str(value))}")

    return keys


@dataclass
class BlockingReport:
    """What blocking did, in numbers that make its failures visible."""

    profiles: int = 0
    blocks: int = 0
    pairs: int = 0
    unblocked: list[str] = field(default_factory=list)
    oversized: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "profiles": self.profiles,
            "blocks": self.blocks,
            "pairs": self.pairs,
            "unblocked_count": len(self.unblocked),
            "unblocked_sample": self.unblocked[:20],
            "oversized_blocks": self.oversized,
        }


def candidate_pairs(
    profiles: list[EntityProfile],
) -> tuple[dict[tuple[str, str], set[str]], BlockingReport]:
    """Group profiles into blocks and emit the pairs worth scoring.

    Returns a mapping of canonically-ordered ref pair to the set of blocking
    keys that produced it, plus a report. The key set travels with the
    candidate all the way to the analyst: "these two were compared because they
    share a phone suffix" is a materially different starting point from
    "because their names sound alike".
    """
    report = BlockingReport(profiles=len(profiles))
    by_key: dict[str, list[EntityProfile]] = defaultdict(list)

    for profile in profiles:
        keys = blocking_keys(profile)
        if not keys:
            report.unblocked.append(profile.ref)
            continue
        for key in keys:
            by_key[key].append(profile)

    report.blocks = len(by_key)
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)

    for key, members in by_key.items():
        if len(members) < 2:
            continue
        if len(members) > MAX_BLOCK_SIZE:
            # Recorded, not hidden. An analyst reading the run report sees that
            # this key stopped discriminating, which is actionable — usually it
            # means a source is emitting a placeholder value.
            report.oversized[key] = len(members)
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left, right = members[i], members[j]
                if left.ref == right.ref:
                    continue
                pairs[order_pair(left.ref, right.ref)].add(key)

    report.pairs = len(pairs)
    return dict(pairs), report


def order_pair(left: str, right: str) -> tuple[str, str]:
    """Canonical ordering, so a pair has exactly one identity in the database.

    Without this, (A, B) and (B, A) are two rows, two decisions, and eventually
    two contradicting ones — with nothing in the schema to notice.
    """
    return (left, right) if left <= right else (right, left)
