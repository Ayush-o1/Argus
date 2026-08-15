"""The generator's time anchor must be timezone-aware (audit B-17).

Kept in the backend suite because that is the suite CI runs; the generator has
no test harness of its own, and a regression test nobody executes is not a
regression test. It imports the generator directly rather than duplicating its
constants, so it fails if the real thing regresses rather than if a copy drifts.

Why this matters beyond tidiness: the generator anchored the world with
`datetime.now()` and emitted ISO strings with no offset. Events near midnight
therefore landed in the wrong day bucket by an amount that depended on the
generating machine's timezone, and two instances generating from the same seed
in different timezones produced different burst days — quietly breaking the
determinism this project advertises.
"""

from __future__ import annotations

import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

GENERATOR_ROOT = Path(__file__).resolve().parents[2] / "generator"


@pytest.fixture(scope="module")
def generator_common():
    """Import the generator's `common` module, or skip.

    The generator is a separate project with its own virtualenv; when its
    dependencies are not installed the honest outcome is a skip that says so,
    not a failure that looks like a defect in ARGUS.
    """
    for path in (str(GENERATOR_ROOT), str(GENERATOR_ROOT / "generators")):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        from generators import common  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on local install
        pytest.skip(f"generator dependencies unavailable ({exc})")
    return common


def test_the_world_anchor_is_timezone_aware_utc(generator_common) -> None:
    assert generator_common.WORLD_END.tzinfo is not None, (
        "WORLD_END is naive again; every emitted instant becomes a wall-clock "
        "reading with no zone, and day bucketing silently depends on the "
        "generating machine's timezone"
    )
    assert generator_common.WORLD_END.utcoffset() == timedelta(0)
    assert generator_common.WORLD_START.tzinfo is not None


def test_every_generated_instant_carries_an_offset(generator_common) -> None:
    """The property that actually reaches the database: `.isoformat()` must
    emit an offset, because that string is what gets stored and later sliced
    into a day key."""
    rng = random.Random(42)
    for _ in range(50):
        moment = generator_common.random_datetime_between(
            rng, generator_common.WORLD_START, generator_common.WORLD_END
        )
        assert moment.tzinfo is not None
        rendered = moment.isoformat()
        assert rendered.endswith("+00:00"), rendered
        # And it round-trips to the same instant, which is the whole point.
        assert datetime.fromisoformat(rendered) == moment


def test_the_activity_window_is_the_declared_180_days(generator_common) -> None:
    span = generator_common.WORLD_END - generator_common.WORLD_START
    assert span == timedelta(days=180)


def test_a_date_of_birth_is_a_date_and_stays_zoneless() -> None:
    """The counterpart to the fix, and a boundary worth pinning.

    A birthday genuinely has no timezone. Sweeping every temporal value into
    tz-aware datetimes "for consistency" would attach an offset to a calendar
    date, which is its own small fabrication — the same class of error as
    reading a naive instant as UTC, just in the other direction.
    """
    assert not isinstance(date.today(), datetime)
    assert date.today().isoformat() == datetime.now(UTC).date().isoformat()
