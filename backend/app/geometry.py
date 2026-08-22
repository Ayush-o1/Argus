"""Spherical geometry, shared by every package that reasons about position.

Promoted out of `app/correlation/measures.py` for the reason `app/integrity.py`
was promoted out of the assessment package: correlation was the first consumer,
not the only one. Resolution already imported `haversine_km` across a package
boundary to compare two records' locations, and Phase 8's spatial statistics
need both functions. Two copies of a distance formula eventually disagree, and
the copy that was forgotten is the one guarding the newer code.

Nothing here touches a database or a model. Every function is checkable against
a worked example by hand, which is the only real defence for a number that later
becomes evidence.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = ["EARTH_RADIUS_KM", "centroid", "haversine_km"]

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    """Great-circle distance in kilometres.

    Used rather than a projected-plane approximation because the world spans
    ~30 degrees of latitude, where a flat approximation is wrong by several
    percent — small in absolute terms, but distance becomes evidence here, and
    evidence should not carry an error nobody accounted for.
    """
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lng_b - lng_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """The mean position of a set of (lat, lng) points, or None if there are none.

    Computed in three dimensions and projected back, rather than by averaging
    degrees. Averaging longitude degrees is wrong across the antimeridian, and
    while this world does not span it, a centroid helper that is quietly wrong
    in one hemisphere is the kind of thing that survives until it matters.

    `map_repo` averaged `n.lat` and `n.lng` in Cypher to place a country marker,
    which has exactly that defect and is why this is now used there instead.
    """
    if not points:
        return None

    x = y = z = 0.0
    for lat, lng in points:
        phi, lam = math.radians(lat), math.radians(lng)
        x += math.cos(phi) * math.cos(lam)
        y += math.cos(phi) * math.sin(lam)
        z += math.sin(phi)

    count = len(points)
    x, y, z = x / count, y / count, z / count
    if abs(x) < 1e-12 and abs(y) < 1e-12 and abs(z) < 1e-12:
        return None

    lng = math.degrees(math.atan2(y, x))
    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
    return lat, lng
