"""Temporal and spatial analysis endpoints.

Read-only and computed on request. There is no `POST /run` and no job here,
because unlike assessment, correlation and alerting these produce no durable
claim for anything else to attach to — and because the whole analysis is a few
hundred milliseconds, so queueing it would add more latency than it removes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope
from app.security.roles import Permission
from app.services import patterns
from app.spatial.clustering import DEFAULT_EPS_KM, DEFAULT_MIN_SAMPLES
from app.spatial.hotspots import DEFAULT_BAND_KM
from app.temporal.significance import DEFAULT_ALPHA
from app.temporal.trend import MIN_PER_WEEKDAY, MIN_TREND_POINTS

router = APIRouter(
    prefix="/api/patterns",
    tags=["patterns"],
    # Reading where activity concentrates, and whether it changed, is reading
    # intelligence. It travels with the rest of the read set, so an
    # administrator does not get it.
    dependencies=[Depends(require_permission(Permission.ANALYTICS_READ))],
)


@router.get("/model")
async def pattern_model() -> Envelope[dict]:
    """Which test answers which question, and where each declines to answer.

    Published for the same reason the risk, correlation and alert models are: a
    statistic with no stated method is a number asking to be believed. The
    previous statistical claim in this product — "N days above 2σ of flagged
    volume" — was uncheckable precisely because nothing said what it measured
    against.
    """
    return Envelope(
        data={
            "alpha": DEFAULT_ALPHA,
            "tests": [
                {
                    "question": "Is this increase significant?",
                    "test": "Exact conditional Poisson rate ratio",
                    "returns": "rate ratio, 95% confidence interval, two-sided p-value",
                    "why": (
                        "Counts are not normally distributed, and at the volumes an "
                        "analyst asks about — nine events last week against four the "
                        "week before — a normal approximation calls ordinary variation "
                        "significant."
                    ),
                    "declines_when": "Neither window contains an event; there is no ratio to report.",
                },
                {
                    "question": "Is it going anywhere?",
                    "test": "Mann-Kendall with Sen's slope",
                    "returns": "S statistic, z-score, p-value, slope per day and per week",
                    "why": (
                        "Non-parametric, so it holds for skewed integer counts where a "
                        "regression's standard error would be computed under assumptions "
                        "the data does not meet. Sen's slope is a median of pairwise "
                        "slopes, so one spike cannot set the trend."
                    ),
                    "declines_when": (
                        f"Fewer than {MIN_TREND_POINTS} buckets, or every value identical."
                    ),
                },
                {
                    "question": "Did it change course?",
                    "test": "Maximum mean-shift split, permutation-tested",
                    "returns": "split index, p-value, mean before and after",
                    "why": (
                        "Describes where the series divides most sharply, tested against "
                        "the null that the ordering carries no information."
                    ),
                    "declines_when": f"Fewer than {MIN_TREND_POINTS} buckets, or a flat series.",
                    "caveat": (
                        "It says nothing about cause. A change in collection looks "
                        "identical to a change in the world."
                    ),
                },
                {
                    "question": "Is there a weekly rhythm?",
                    "test": "Chi-square goodness-of-fit against an even week",
                    "returns": "chi-square statistic, p-value, busiest and quietest day",
                    "why": (
                        "Tests whether activity concentrates on particular weekdays "
                        "rather than being spread as chance would spread it."
                    ),
                    "declines_when": (
                        f"Fewer than about {MIN_PER_WEEKDAY * 7} events, where the "
                        "approximation is unreliable."
                    ),
                },
                {
                    "question": "Where is activity concentrated?",
                    "test": "DBSCAN on great-circle distance",
                    "returns": "clusters with a spherical centroid, radius, member list and the count left as noise",
                    "why": (
                        "Density-based, so a concentration keeps its real outline and "
                        "sparse points stay noise instead of being forced into a group. "
                        "Distance is haversine, so the radius is a real distance rather "
                        "than a number of degrees that means something different at "
                        "every latitude."
                    ),
                    "declines_when": "Fewer located points than the minimum cluster size.",
                },
                {
                    "question": "Is that concentration more than the map being dense there?",
                    "test": "Getis-Ord Gi*, Benjamini-Hochberg corrected",
                    "returns": "z-score and p-value per location, before and after correction",
                    "why": (
                        "A cluster says points are close together; Gi* says whether the "
                        "value at them is unusual against their neighbourhood. The "
                        "correction matters: testing 200 locations at alpha 0.05 yields "
                        "about ten hotspots when nothing is happening."
                    ),
                    "declines_when": "Fewer than 8 locations, or every location holding the same value.",
                    "caveat": (
                        "Gi* cannot distinguish a place where more happens from a place "
                        "where more is collected."
                    ),
                },
            ],
            "not_implemented": [
                {
                    "item": "PostGIS-backed spatial querying",
                    "reason": (
                        "At this scale a full haversine scan is milliseconds and a "
                        "spatial index would have nothing to accelerate. The trigger for "
                        "revisiting is roughly a million located entities, or a query "
                        "needing polygon containment rather than point proximity."
                    ),
                },
            ],
        }
    )


@router.get("/temporal")
async def temporal(
    window_days: int = Query(patterns.DEFAULT_WINDOW_DAYS, ge=1, le=patterns.MAX_WINDOW_DAYS),
    baseline_days: int = Query(patterns.DEFAULT_BASELINE_DAYS, ge=1, le=patterns.MAX_BASELINE_DAYS),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[dict]:
    try:
        return Envelope(data=await patterns.analyse_temporal(
            driver, window_days=window_days, baseline_days=baseline_days
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/spatial")
async def spatial(
    eps_km: float = Query(DEFAULT_EPS_KM, ge=1.0, le=2000.0),
    min_samples: int = Query(DEFAULT_MIN_SAMPLES, ge=2, le=500),
    band_km: float = Query(DEFAULT_BAND_KM, ge=10.0, le=5000.0),
    value: str = Query("elevated_count", pattern="^(elevated_count|entity_count|assessed_count)$"),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[dict]:
    try:
        return Envelope(data=await patterns.analyse_spatial(
            driver, eps_km=eps_km, min_samples=min_samples, band_km=band_km, value=value
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
