"""Hashing what leaves the system, and re-checking it later.

## Where the artifacts come from

ARGUS holds no files. The graph was counted before this phase was designed:

    MATCH (n) WHERE n.file_path IS NOT NULL OR n.content IS NOT NULL
                 OR n.blob IS NOT NULL OR n.sha256 IS NOT NULL
    RETURN count(n)                                              -> 0
    SELECT count(*) FROM raw_records                              -> 0

The 2,000 `Document` nodes are metadata — an id, a type, an issuer, two dates —
with nothing behind them. So the roadmap's "write-once object storage for
artifacts, referenced by SHA-256" would have been a store for zero artifacts.

Export is what creates one. The moment an investigation is rendered for someone
to take away, a byte stream exists that must be identifiable later, and that is
the artifact this module hashes.

## Where the bytes live, and when that should change

In a PostgreSQL `BYTEA` column. A case export is kilobytes; an object store
would be a second system to run, secure and back up for data that fits in a
column, and this project's standard is that a technology must be shown to be
needed before it is added.

**The trigger to move them out**, stated so nobody has to guess: exports that
carry attachments — seized files, images, anything a person did not type — or a
total export volume past roughly a gigabyte. Either makes the row size a
problem for backup and replication, which is the actual reason object storage
exists. Neither is true here.

## Why SHA-256

Not for secrecy — the content is stored beside the hash, so this is not a
commitment scheme and nothing is hidden. It answers one question: are these
bytes the same bytes. A truncated or non-cryptographic hash would answer it
under normal conditions and fail exactly when someone had a reason to make two
different documents agree.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

__all__ = ["Artifact", "digest", "verify"]


@dataclass(frozen=True)
class Artifact:
    content: bytes
    sha256: str
    byte_size: int


def digest(content: bytes) -> Artifact:
    return Artifact(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        byte_size=len(content),
    )


def verify(content: bytes | None, recorded_sha256: str) -> tuple[bool, str]:
    """Re-hash stored content and compare to what was recorded.

    Returns `(ok, explanation)`. Disposed exports have no content, and that is
    reported as a distinct state rather than as a failed verification — an
    artifact destroyed on schedule is not a corrupted one, and conflating them
    would make every routine disposal look like an integrity incident.
    """
    if content is None or len(content) == 0:
        return False, (
            "This export has been disposed of and its content destroyed. The record of "
            "who produced it, when, and what its hash was is retained; the bytes are not, "
            "so integrity cannot be re-checked and there is nothing to check it against."
        )
    actual = hashlib.sha256(content).hexdigest()
    if actual == recorded_sha256:
        return True, f"Content re-hashes to the value recorded at export ({actual[:16]}…)."
    return False, (
        f"Content does not match the hash recorded at export. Recorded "
        f"{recorded_sha256[:16]}…, actual {actual[:16]}…. The stored bytes have changed "
        f"since they were produced."
    )
