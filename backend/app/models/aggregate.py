"""A number, plus what it is a number *of*.

The audit found four surfaces presenting sampled or truncated values with the
visual authority of complete findings: the timeline's "N days above 2σ" computed
over a random 800-record sample; an alert's "Spread" computed over an arbitrary
5-entity slice; the dashboard's headline mixing a full population count with a
6-row sample in one sentence; the map's regional reading computed globally
beside a viewport-scoped list.

Fixing those four individually would have left the fifth to be written next
week. The root cause is that a bare `int` carries no information about its own
denominator, so nothing forces the author of a new surface to think about it.

`Aggregate` makes that impossible to omit: constructing one requires stating the
population it was drawn from and how it was computed, and the frontend component
that renders it surfaces those. A count that covers everything says so; a count
that covers part of something says which part.

Use `Aggregate.complete(...)` for a full-population figure and
`Aggregate.sampled(...)` or `Aggregate.truncated(...)` for a partial one. There
is deliberately no bare constructor shortcut.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")


class Basis(StrEnum):
    """How the value relates to the population it describes.

    COMPLETE   — computed over every record. The value *is* the answer.
    SAMPLED    — computed over a random subset. Statistics are estimates and
                 will vary between runs.
    TRUNCATED  — computed over the first N records by some ordering. Not a
                 random sample: systematically biased toward whatever that
                 ordering favours, so it must never be treated as one.
    """

    COMPLETE = "complete"
    SAMPLED = "sampled"
    TRUNCATED = "truncated"


class Aggregate(BaseModel, Generic[T]):
    """A computed value together with its provenance."""

    value: T
    basis: Basis
    # Size of the population the value describes. None only when genuinely
    # unknowable, which should be rare enough to be worth a comment at the call
    # site — an unknown denominator is itself a finding.
    population: int | None = None
    # Records actually examined. Equals `population` when basis is COMPLETE.
    examined: int | None = None
    method: str = Field(description="How the value was derived, e.g. 'count', 'distinct', 'mean+2sigma'")
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _check_consistency(self) -> Aggregate[T]:
        if self.basis is Basis.COMPLETE:
            # A complete aggregate that examined fewer records than exist is a
            # contradiction, and silently allowing it would defeat the point of
            # the type.
            if self.population is not None and self.examined is not None and self.examined != self.population:
                raise ValueError(
                    f"basis=COMPLETE but examined ({self.examined}) != population ({self.population}); "
                    "use SAMPLED or TRUNCATED instead"
                )
            if self.examined is None:
                object.__setattr__(self, "examined", self.population)
        else:
            if self.examined is None or self.population is None:
                raise ValueError(f"basis={self.basis.value} requires both population and examined to be set")
        return self

    @property
    def is_partial(self) -> bool:
        return self.basis is not Basis.COMPLETE

    @property
    def coverage(self) -> float | None:
        """Fraction of the population examined, or None when unknowable."""
        if self.population is None or self.examined is None or self.population == 0:
            return None
        return min(1.0, self.examined / self.population)

    @classmethod
    def complete(cls, value: T, population: int | None = None, method: str = "count") -> Aggregate[T]:
        """A value computed over every record."""
        return cls(value=value, basis=Basis.COMPLETE, population=population, examined=population, method=method)

    @classmethod
    def sampled(cls, value: T, population: int, examined: int, method: str) -> Aggregate[T]:
        """A value computed over a random subset. Callers rendering statistics
        from this must present them as estimates."""
        return cls(value=value, basis=Basis.SAMPLED, population=population, examined=examined, method=method)

    @classmethod
    def truncated(cls, value: T, population: int, examined: int, method: str = "count") -> Aggregate[T]:
        """A value computed over the first N by some ordering — biased by that
        ordering, and never a substitute for a sample."""
        return cls(value=value, basis=Basis.TRUNCATED, population=population, examined=examined, method=method)
