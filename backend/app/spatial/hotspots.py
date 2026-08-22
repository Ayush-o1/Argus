"""Is this concentration more than the map is dense here anyway?

A cluster says points are close together. It does not say the *value* at those
points is unusual — and those are different questions. Fifty subjects in one
city is not a hotspot if the city holds fifty thousand people; twelve is, if its
neighbours hold one each.

## Getis-Ord Gi*

The standard statistic for exactly this. For each location it compares the sum
of values in its neighbourhood against what the neighbourhood would hold if the
same total were spread evenly, and expresses the difference in standard
deviations. The result is a z-score, so it is directly interpretable and comes
with a p-value.

`Gi*` includes the location itself in its own neighbourhood — the starred
variant — because the question is whether *this place and around it* is hot, not
whether its surroundings are hot while it is quiet.

## The correction that stops this being a lie

Testing 200 locations at alpha 0.05 yields about ten "significant" hotspots when
nothing whatever is happening. A map that highlights ten arbitrary places is
worse than a map that highlights none, because it looks like a finding and an
analyst will go and look. Every p-value here goes through Benjamini-Hochberg
before anything is called a hotspot, and both the raw and the corrected verdict
are returned so the correction is visible rather than assumed.

## What it cannot tell you

Gi* describes the distribution of a value over space. It has no opinion about
why, and in particular it cannot distinguish a place where more happens from a
place where more is *collected*. A region with one diligent feed and neighbours
with none will light up. That caveat travels with the result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

from app.geometry import haversine_km
from app.temporal.significance import DEFAULT_ALPHA, fdr_adjust

__all__ = ["Hotspot", "HotspotReport", "getis_ord"]

# Neighbourhood radius. Locations within this distance of each other are treated
# as neighbours with equal weight — a binary weights matrix, which is the
# conventional choice for Gi* and the one that needs no further justification
# than the band itself.
DEFAULT_BAND_KM = 250.0

# Fewer locations than this and the normal approximation behind Gi* is not
# trustworthy; the statistic is defined but its p-value is not meaningful.
MIN_LOCATIONS = 8


@dataclass(frozen=True)
class Hotspot:
    key: str
    lat: float
    lng: float
    value: float
    neighbours: int
    z_score: float
    p_value: float
    significant_raw: bool
    significant_corrected: bool
    """Survives Benjamini-Hochberg across every location tested. This is the
    one a map should colour."""

    @property
    def kind(self) -> str:
        if not self.significant_corrected:
            return "none"
        return "hot" if self.z_score > 0 else "cold"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "lat": self.lat,
            "lng": self.lng,
            "value": self.value,
            "neighbours": self.neighbours,
            "z_score": round(self.z_score, 4),
            "p_value": self.p_value,
            "significant_raw": self.significant_raw,
            "significant": self.significant_corrected,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class HotspotReport:
    locations: list[Hotspot]
    band_km: float
    alpha: float
    evaluable: bool
    reason: str | None = None

    @property
    def hot(self) -> list[Hotspot]:
        return [h for h in self.locations if h.kind == "hot"]

    @property
    def cold(self) -> list[Hotspot]:
        return [h for h in self.locations if h.kind == "cold"]

    def as_dict(self) -> dict[str, Any]:
        raw = sum(1 for h in self.locations if h.significant_raw)
        return {
            "evaluable": self.evaluable,
            "reason": self.reason,
            "band_km": self.band_km,
            "alpha": self.alpha,
            "locations_tested": len(self.locations),
            "hot": [h.as_dict() for h in self.hot],
            "cold": [h.as_dict() for h in self.cold],
            "all": [h.as_dict() for h in self.locations],
            "significant_before_correction": raw,
            "significant_after_correction": len(self.hot) + len(self.cold),
            "test": "Getis-Ord Gi* with a binary distance band, Benjamini-Hochberg corrected",
            "caveat": (
                "Gi* describes where a value concentrates, not why. It cannot "
                "distinguish a place where more happens from a place where more is "
                "collected: a region with one active feed beside regions with none "
                "will register as hot."
            ),
        }


def getis_ord(
    locations: list[dict[str, Any]],
    *,
    band_km: float = DEFAULT_BAND_KM,
    alpha: float = DEFAULT_ALPHA,
) -> HotspotReport:
    """Gi* over locations carrying `key`, `lat`, `lng` and `value`."""
    usable = [
        loc
        for loc in locations
        if loc.get("lat") is not None and loc.get("lng") is not None and loc.get("value") is not None
    ]
    n = len(usable)
    if n < MIN_LOCATIONS:
        return HotspotReport(
            locations=[], band_km=band_km, alpha=alpha, evaluable=False,
            reason=(
                f"Gi* needs at least {MIN_LOCATIONS} locations for its normal "
                f"approximation to mean anything; {n} were supplied."
            ),
        )

    values = np.array([float(loc["value"]) for loc in usable], dtype=float)
    mean = float(values.mean())
    # Population standard deviation, which is what Gi* is defined with.
    s = float(math.sqrt(max(0.0, (values**2).mean() - mean**2)))

    if s == 0.0:
        return HotspotReport(
            locations=[], band_km=band_km, alpha=alpha, evaluable=False,
            reason="Every location holds the same value; there is no concentration to find.",
        )

    coords = [(float(loc["lat"]), float(loc["lng"])) for loc in usable]

    # Binary weights: 1 inside the band, 0 outside, and 1 for the location
    # itself — the star in Gi*.
    weights = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i == j or haversine_km(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) <= band_km:
                weights[i, j] = 1.0

    z_scores: list[float] = []
    p_values: list[float] = []
    for i in range(n):
        w = weights[i]
        w_sum = float(w.sum())
        w_sq_sum = float((w**2).sum())
        numerator = float((w * values).sum()) - mean * w_sum
        denominator = s * math.sqrt(max(1e-12, (n * w_sq_sum - w_sum**2) / (n - 1)))
        z = numerator / denominator if denominator > 0 else 0.0
        z_scores.append(z)
        p_values.append(float(2 * stats.norm.sf(abs(z))))

    corrected = fdr_adjust(p_values, alpha)

    hotspots = [
        Hotspot(
            key=str(usable[i].get("key", i)),
            lat=coords[i][0],
            lng=coords[i][1],
            value=float(values[i]),
            neighbours=int(weights[i].sum()) - 1,
            z_score=z_scores[i],
            p_value=p_values[i],
            significant_raw=p_values[i] < alpha,
            significant_corrected=corrected[i],
        )
        for i in range(n)
    ]
    hotspots.sort(key=lambda h: h.z_score, reverse=True)
    return HotspotReport(locations=hotspots, band_km=band_km, alpha=alpha, evaluable=True)
