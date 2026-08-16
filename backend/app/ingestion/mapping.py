"""Turning a source's record into something ARGUS can hold a belief about.

A record arrives as arbitrary JSON. Three questions have to be answered before
it can become an observation: **what is it about**, **when did it happen**, and
**when was it collected**. The mapping is the declarative answer, stored per
connector, so supporting a new feed shape is configuration rather than code.

## Timestamps, and the rule that governs them

The generator writes naive local wall-clock strings with no zone (audit B-17),
and ARGUS read them as if they were UTC — an assumption that is wrong by up to a
day and invisible when it is.

The rule here is the one Phase 2 established: **a timestamp with no stated zone
does not become an instant.** A mapping may declare `timezone`, in which case
naive values are interpreted in it and converted to UTC — a stated convention,
recorded and auditable. Without that declaration a naive value is preserved
verbatim in the payload and the instant is left NULL, because a fabricated
instant is worse than a visible gap.

Offset-aware values are converted to UTC regardless. They carry their own
answer; nothing is being assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.repositories.entity_labels import resolve_label


class MappingError(ValueError):
    """The mapping cannot be applied to this record. Sends it to the DLQ with a
    reason a human can act on."""


class InvalidMapping(ValueError):
    """The mapping itself is unusable, independent of any record."""


@dataclass(frozen=True)
class RecordMapping:
    """How to read one connector's records."""

    content_type: str
    subject_path: str
    occurred_at_path: str | None = None
    collected_at_path: str | None = None
    #: IANA zone used to interpret naive timestamps. None means "unstated", and
    #: unstated means the instant stays unknown rather than being guessed.
    timezone: str | None = None
    required_fields: list[str] = field(default_factory=list)
    #: Optional: profile attribute -> dotted path, e.g. {"name": "subject.full_name"}.
    #: When a record's subject id names no entity ARGUS holds, these let the
    #: matcher ask "is this someone we already know?" instead of dead-lettering
    #: with nothing but an unrecognised id. Keys are the matcher's vocabulary,
    #: and unknown ones are refused at configuration time rather than silently
    #: ignored — a mapping that looks like it is doing something and is not is
    #: worse than one that fails.
    match_attributes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_config(cls, raw: dict[str, Any]) -> RecordMapping:
        content_type = raw.get("content_type")
        subject_path = raw.get("subject_path")
        if not content_type or not subject_path:
            raise InvalidMapping("mapping requires `content_type` and `subject_path`")

        zone = raw.get("timezone")
        if zone is not None:
            try:
                ZoneInfo(str(zone))
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise InvalidMapping(f"unknown timezone {zone!r}: {exc}") from exc

        required = raw.get("required_fields") or []
        if not isinstance(required, list):
            raise InvalidMapping("`required_fields` must be a list")

        match_attributes = raw.get("match_attributes") or {}
        if not isinstance(match_attributes, dict):
            raise InvalidMapping("`match_attributes` must be an object of attribute -> path")
        # Imported here rather than at module scope: `app.resolution` imports
        # nothing from ingestion, and keeping the dependency one-directional and
        # lazy stops a cycle if that ever changes.
        from app.resolution.profile import MATCHABLE_ATTRIBUTES

        unknown = sorted(set(match_attributes) - MATCHABLE_ATTRIBUTES)
        if unknown:
            raise InvalidMapping(
                f"unknown match attribute(s): {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(MATCHABLE_ATTRIBUTES))}"
            )

        return cls(
            content_type=str(content_type),
            subject_path=str(subject_path),
            occurred_at_path=_optional_str(raw.get("occurred_at_path")),
            collected_at_path=_optional_str(raw.get("collected_at_path")),
            timezone=str(zone) if zone is not None else None,
            required_fields=[str(f) for f in required],
            match_attributes={str(k): str(v) for k, v in match_attributes.items()},
        )


def _optional_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


@dataclass(frozen=True)
class MappedRecord:
    subject_ref: str
    subject_type: str
    content_type: str
    occurred_at: datetime | None
    collected_at: datetime | None
    payload: dict[str, Any]
    #: Set when a timestamp was present but could not be turned into an instant.
    #: Carried into the observation's note so the gap is visible on the record
    #: itself, not only in a log nobody reads.
    unresolved_timestamps: tuple[str, ...] = ()
    #: Attribute values pulled out for the matcher, when the mapping declared
    #: any. Empty is the normal case for a feed whose subject ids are reliable.
    match_attributes: dict[str, Any] = field(default_factory=dict)


def dig(payload: dict[str, Any], path: str) -> Any:
    """Read a dotted path. Missing intermediate keys yield None rather than raising."""
    current: Any = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def apply_mapping(payload: dict[str, Any], mapping: RecordMapping) -> MappedRecord:
    """Validate and normalise one record. Raises MappingError on rejection."""
    missing = [f for f in mapping.required_fields if dig(payload, f) in (None, "")]
    if missing:
        raise MappingError(f"missing required field(s): {', '.join(missing)}")

    subject_raw = dig(payload, mapping.subject_path)
    if subject_raw in (None, ""):
        raise MappingError(f"no subject at `{mapping.subject_path}`")

    subject_ref = str(subject_raw).strip()
    info = resolve_label(subject_ref)
    if info is None:
        raise MappingError(
            f"subject {subject_ref!r} does not match any known entity id prefix. "
            "ARGUS records observations about entities that already exist; creating entities "
            "from a feed requires entity resolution, or the same real-world entity reported by "
            "two sources becomes two entities."
        )

    unresolved: list[str] = []
    occurred_at = _timestamp(payload, mapping.occurred_at_path, mapping, unresolved)
    collected_at = _timestamp(payload, mapping.collected_at_path, mapping, unresolved)

    matched = {
        attribute: value
        for attribute, path in mapping.match_attributes.items()
        if (value := dig(payload, path)) not in (None, "", [])
    }

    return MappedRecord(
        subject_ref=subject_ref,
        subject_type=info.label,
        content_type=mapping.content_type,
        occurred_at=occurred_at,
        collected_at=collected_at,
        payload=payload,
        unresolved_timestamps=tuple(unresolved),
        match_attributes=matched,
    )


def _timestamp(
    payload: dict[str, Any],
    path: str | None,
    mapping: RecordMapping,
    unresolved: list[str],
) -> datetime | None:
    if path is None:
        return None
    raw = dig(payload, path)
    if raw in (None, ""):
        return None

    parsed = parse_timestamp(raw)
    if parsed is None:
        unresolved.append(f"{path}: unparseable value {raw!r}")
        return None

    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC)

    if mapping.timezone is None:
        # The decisive line in this module. A naive value with no declared zone
        # is not an instant, and ARGUS will not invent one.
        unresolved.append(
            f"{path}: {raw!r} has no timezone and this source declares none, "
            "so no instant can be derived"
        )
        return None

    return parsed.replace(tzinfo=ZoneInfo(mapping.timezone)).astimezone(UTC)


# Epoch seconds vs milliseconds: anything past this is milliseconds, because a
# seconds value this large is year 33658. Guessing wrong is a 1000x error in the
# one field an investigation orders everything by.
_EPOCH_MS_THRESHOLD = 100_000_000_000

_TRAILING_Z = re.compile(r"[Zz]$")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse the timestamp shapes real feeds actually emit. None if unparseable."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if abs(seconds) >= _EPOCH_MS_THRESHOLD:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    # ISO 8601, including the trailing "Z" that fromisoformat rejects on older
    # Pythons and that many feeds emit.
    try:
        return datetime.fromisoformat(_TRAILING_Z.sub("+00:00", text))
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822, as used by RSS
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    if text.isdigit():
        return parse_timestamp(int(text))
    return None


def field_paths(payload: dict[str, Any], prefix: str = "", depth: int = 0) -> set[str]:
    """Every dotted field path in a record, for schema-drift detection.

    Bounded in depth: a deeply nested or recursive payload should not turn
    drift detection into an unbounded walk.
    """
    if depth > 6:
        return set()
    paths: set[str] = set()
    for key, value in payload.items():
        path = f"{prefix}{key}"
        paths.add(path)
        if isinstance(value, dict):
            paths |= field_paths(value, prefix=f"{path}.", depth=depth + 1)
    return paths
