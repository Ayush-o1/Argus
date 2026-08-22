"""Where activity is actually concentrated, computed from coordinates.

`get_region_rollup` groups entities by `n.region` and `get_country_rollup` by
`n.country`. Those are string aggregations wearing a map's clothes, and they
mislead in two specific directions:

  - **A concentration that straddles a border disappears.** Three hundred
    subjects packed into fifty kilometres either side of a frontier are split
    into two unremarkable country totals.
  - **A large country looks like a hotspot for being large.** The count is
    driven by how many entities the country holds, not by how tightly they sit
    together, so the biggest region is always at the top of the list.

Neither is fixed by better shading. They are fixed by computing over positions.

## Why DBSCAN

Density-based, so a cluster is defined by points being close to each other
rather than by a shape imposed in advance. Two consequences that matter here:
it finds concentrations of arbitrary outline — a cluster along a coastline or a
corridor is still one cluster — and it labels sparse points as **noise** rather
than forcing every entity into some cluster. k-means would have to assign every
point to one of k groups and would need k chosen up front, which is a decision
nobody has grounds to make.

Distance is haversine on radians, so `eps` is a real distance on the sphere
rather than a number of degrees. A degree of longitude is 111 km at the equator
and 79 km at 45°N; clustering in degrees would silently use a different radius
at every latitude.

## Why not PostGIS

The audit recommended it. At the scale this instance runs — 4,418 located
entities — a full haversine DBSCAN is milliseconds, and PostGIS's contribution
would be a GiST index on a set small enough to scan. Adding a datastore
extension buys nothing measurable here and costs a new image, a new extension, a
new migration and a second query surface.

**The trigger for revisiting is stated rather than left to taste:** when the
located-entity count passes roughly 10^6, or when a query needs polygon
containment (an area of interest, a jurisdiction boundary, a corridor buffer)
rather than point proximity. Neither is true today.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN

from app.geometry import EARTH_RADIUS_KM, centroid, haversine_km

__all__ = [
    "DEFAULT_EPS_KM",
    "DEFAULT_MIN_SAMPLES",
    "SpatialCluster",
    "cluster_points",
]

# Radius within which points count as neighbours. 75 km is roughly a metropolitan
# area plus its hinterland: close enough that co-location is worth remarking on,
# wide enough that two districts of one city do not become two clusters.
DEFAULT_EPS_KM = 75.0

# A cluster needs this many points. Below five, "concentration" is a coincidence
# — any two people are within 75 km of each other somewhere.
DEFAULT_MIN_SAMPLES = 5


@dataclass(frozen=True)
class SpatialCluster:
    cluster_id: int
    size: int
    lat: float
    lng: float
    """Spherical centroid — not a mean of degrees."""
    radius_km: float
    """Distance from the centroid to the furthest member."""
    mean_distance_km: float
    members: tuple[str, ...]
    countries: tuple[str, ...]
    elevated: int
    assessed: int

    @property
    def crosses_border(self) -> bool:
        """The finding string grouping cannot produce."""
        return len(self.countries) > 1

    @property
    def density_per_1000km2(self) -> float:
        area = math.pi * max(self.radius_km, 1.0) ** 2
        return self.size / (area / 1000.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "size": self.size,
            "lat": self.lat,
            "lng": self.lng,
            "radius_km": round(self.radius_km, 2),
            "mean_distance_km": round(self.mean_distance_km, 2),
            "density_per_1000km2": round(self.density_per_1000km2, 4),
            "countries": list(self.countries),
            "crosses_border": self.crosses_border,
            "elevated": self.elevated,
            "assessed": self.assessed,
            "members": list(self.members[:25]),
            "members_total": self.size,
        }


def cluster_points(
    points: list[dict[str, Any]],
    *,
    eps_km: float = DEFAULT_EPS_KM,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> tuple[list[SpatialCluster], int]:
    """DBSCAN over (lat, lng), returning clusters and the count left as noise.

    Each point is a dict with at least `ref`, `lat`, `lng`; `country` and `band`
    are used where present. The noise count is returned rather than discarded:
    "1,900 of 4,418 entities are in no concentration at all" is a finding about
    the map, and a view that showed only clusters would imply the world is
    entirely made of them.
    """
    located = [p for p in points if p.get("lat") is not None and p.get("lng") is not None]
    if len(located) < min_samples:
        return [], len(located)

    coords = np.radians(np.array([[float(p["lat"]), float(p["lng"])] for p in located]))
    labels = DBSCAN(
        eps=eps_km / EARTH_RADIUS_KM,  # radians, because the metric is haversine
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
    ).fit_predict(coords)

    clusters: list[SpatialCluster] = []
    noise = int((labels == -1).sum())

    for label in sorted({int(x) for x in labels if x != -1}):
        members = [located[i] for i in range(len(located)) if labels[i] == label]
        positions = [(float(m["lat"]), float(m["lng"])) for m in members]
        centre = centroid(positions)
        if centre is None:  # pragma: no cover - needs antipodal members
            continue
        distances = [haversine_km(centre[0], centre[1], lat, lng) for lat, lng in positions]
        countries = sorted({m["country"] for m in members if m.get("country")})
        clusters.append(
            SpatialCluster(
                cluster_id=label,
                size=len(members),
                lat=centre[0],
                lng=centre[1],
                radius_km=max(distances),
                mean_distance_km=sum(distances) / len(distances),
                members=tuple(sorted(str(m["ref"]) for m in members)),
                countries=tuple(countries),
                elevated=sum(1 for m in members if m.get("band") == "elevated"),
                assessed=sum(
                    1
                    for m in members
                    if m.get("band") not in (None, "insufficient_evidence")
                ),
            )
        )

    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters, noise
