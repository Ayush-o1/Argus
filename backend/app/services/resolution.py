"""Entity resolution orchestration — runs, decisions, clusters, subject lookup.

Every database call in the resolution feature lives here. The decision logic
itself is pure and sits in `app/resolution/`, which is what makes a merge
re-derivable from the record alone.

Three guarantees this module is responsible for holding:

  **A merge never destroys either record.** Nothing here writes to an entity
  node. A merge writes a row to the append-only ledger and projects a `SAME_AS`
  edge; reversal writes another row and deletes the edge. Both original records
  are byte-for-byte unchanged throughout, which is why reversal needs no backup
  and loses no history.

  **Automatic merges are the narrow case, not the default.** The matcher acts
  on its own only where an identifier matched exactly, nothing disagreed, and
  enough of the model was comparable to mean anything (see
  `scoring.MatchModel`). Everything else is queued for a person. The roadmap
  asked for "auto-merge above a high threshold"; a high threshold alone is not
  a sufficient condition and this deliberately does not implement it that way.

  **A contradiction is surfaced, never settled.** See `clustering`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.database.neo4j import get_driver
from app.database.postgres import acquire
from app.repositories import resolution_graph_repo as graph_repo
from app.repositories import resolution_repo as repo
from app.repositories.entity_labels import resolve_label
from app.resolution.blocking import blocking_keys, candidate_pairs, order_pair
from app.resolution.clustering import build_clusters
from app.resolution.profile import SUPPORTED_TYPES, EntityProfile
from app.resolution.scoring import (
    BAND_AUTO,
    BAND_REVIEW,
    DEFAULT_MODEL,
    MatchModel,
    MatchResult,
    compare,
)
from app.services import audit, queue

logger = logging.getLogger(__name__)

MATCH_JOB_KIND = "resolution.match_run"

# The matcher acts under its own name, never a person's. An automatic merge in
# the audit log that appears to have been made by whoever last logged in would
# be a lie about who decided.
MATCHER_ACTOR = "argus.matcher"

# Ceiling on how many entities one run loads per type. Beyond this the run
# reports that it was truncated rather than presenting a partial sweep as a
# complete one.
MAX_PROFILES_PER_TYPE = 20_000


@dataclass
class RunOutcome:
    run_id: int
    entity_types: list[str]
    profiles_examined: int = 0
    pairs_scored: int = 0
    bands: dict[str, int] = field(default_factory=dict)
    auto_merged: int = 0
    auto_skipped_existing: int = 0
    withdrawn: int = 0
    blocking: dict[str, Any] = field(default_factory=dict)
    truncated: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "entity_types": self.entity_types,
            "profiles_examined": self.profiles_examined,
            "pairs_scored": self.pairs_scored,
            "bands": self.bands,
            "auto_merged": self.auto_merged,
            "auto_skipped_existing": self.auto_skipped_existing,
            "withdrawn": self.withdrawn,
            "blocking": self.blocking,
            "truncated": self.truncated,
        }


# ── Matcher runs ─────────────────────────────────────────────────────────────


async def run_matcher(
    entity_types: list[str] | None = None,
    *,
    triggered_by: str = MATCHER_ACTOR,
    model: MatchModel = DEFAULT_MODEL,
    apply_auto: bool = True,
) -> RunOutcome:
    """Score the population and record every candidate above the noise floor.

    `apply_auto=False` scores without merging anything — the mode to use when
    changing weights, so the effect can be inspected in the queue before it is
    allowed to act.
    """
    types = [t for t in (entity_types or sorted(SUPPORTED_TYPES)) if t in SUPPORTED_TYPES]
    if not types:
        raise ValueError(f"no supported entity types among {entity_types!r}")

    run_id = await repo.start_run(
        entity_types=types,
        model_version=model.version,
        model_fingerprint=model.fingerprint(),
        triggered_by=triggered_by,
    )
    outcome = RunOutcome(run_id=run_id, entity_types=types)
    driver = get_driver()

    try:
        for entity_type in types:
            total = await graph_repo.count_entities(driver, entity_type)
            profiles = await graph_repo.fetch_profiles(
                driver, entity_type, limit=MAX_PROFILES_PER_TYPE
            )
            complete = total <= len(profiles)
            if not complete:
                outcome.truncated.append(
                    f"{entity_type}: examined {len(profiles)} of {total}"
                )
            outcome.profiles_examined += len(profiles)

            await _index_blocks(entity_type, profiles)

            pairs, report = candidate_pairs(profiles)
            outcome.blocking[entity_type] = report.as_dict()
            by_ref = {p.ref: p for p in profiles}

            for (left_ref, right_ref), keys in pairs.items():
                result = compare(
                    by_ref[left_ref], by_ref[right_ref], model=model, blocking_keys=sorted(keys)
                )
                outcome.pairs_scored += 1
                outcome.bands[result.band] = outcome.bands.get(result.band, 0) + 1
                await _persist_candidate(run_id, result, apply_auto, outcome)

            # Anything still open from an earlier run that this complete sweep
            # did not re-produce is no longer a candidate under the current
            # model. Leaving it would keep a pair in the queue scored by a
            # model that no longer exists — found when a fix to organisation
            # name handling stopped producing a pair, and the pair stayed in
            # the queue with its old score anyway.
            if complete:
                async with acquire() as conn, conn.transaction():
                    outcome.withdrawn += await repo.withdraw_stale_candidates(
                        conn,
                        entity_type=entity_type,
                        run_id=run_id,
                        reason=(
                            f"Not produced by run {run_id} under model "
                            f"{model.version} ({model.fingerprint()}). The current model "
                            "either no longer compares these two records or no longer "
                            "scores them as related."
                        ),
                    )

        await repo.finish_run(
            run_id,
            status="complete",
            profiles_examined=outcome.profiles_examined,
            pairs_scored=outcome.pairs_scored,
            bands=outcome.bands,
            blocking_report={**outcome.blocking, "truncated": outcome.truncated},
        )
    except Exception as exc:
        await repo.finish_run(
            run_id,
            status="failed",
            profiles_examined=outcome.profiles_examined,
            pairs_scored=outcome.pairs_scored,
            bands=outcome.bands,
            blocking_report=outcome.blocking,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    if outcome.auto_merged:
        await rebuild_clusters()
    return outcome


async def _persist_candidate(
    run_id: int, result: MatchResult, apply_auto: bool, outcome: RunOutcome
) -> None:
    async with acquire() as conn, conn.transaction():
        candidate_id = await repo.upsert_candidate(conn, run_id, result)

    if result.band != BAND_AUTO or not apply_auto:
        return
    if candidate_id is None:
        # The pair already has a decision. A later run must not quietly re-merge
        # something a person un-merged: that would make reversal temporary,
        # which is the same as not supporting it.
        outcome.auto_skipped_existing += 1
        return

    existing = await repo.current_decision(result.left_ref, result.right_ref)
    if existing is not None:
        outcome.auto_skipped_existing += 1
        return

    await decide(
        left_ref=result.left_ref,
        right_ref=result.right_ref,
        verdict="same",
        actor=MATCHER_ACTOR,
        actor_kind="matcher",
        rationale=result.band_reason,
        candidate_id=candidate_id,
        entity_type=result.entity_type,
        score=result.score,
        evidence_weight=result.evidence_weight,
        model_version=result.model_version,
        model_fingerprint=result.model_fingerprint,
        rebuild=False,
        audit_actor=None,
    )
    outcome.auto_merged += 1


async def _index_blocks(entity_type: str, profiles: list[EntityProfile]) -> None:
    rows = [(p.ref, key) for p in profiles for key in blocking_keys(p)]
    async with acquire() as conn, conn.transaction():
        await repo.replace_blocking_index(conn, entity_type, rows)


# ── Decisions ────────────────────────────────────────────────────────────────


class DecisionRefused(RuntimeError):
    """Raised when a decision cannot be recorded as asked."""


async def decide(
    *,
    left_ref: str,
    right_ref: str,
    verdict: str,
    actor: str,
    actor_kind: str,
    rationale: str,
    entity_type: str | None = None,
    candidate_id: int | None = None,
    score: float | None = None,
    evidence_weight: float | None = None,
    model_version: str | None = None,
    model_fingerprint: str | None = None,
    reverses_decision_id: int | None = None,
    rebuild: bool = True,
    audit_actor: Any | None = None,
    label_origin: str | None = "analyst",
) -> dict[str, Any]:
    """Record a decision about a pair, and project it.

    Order matters and is deliberate: the ledger row and the audit record commit
    in one transaction, and only then is the graph projection touched. If the
    projection write fails, the decision still stands and `rebuild_projection`
    can re-derive it — the reverse order would allow a merged graph with no
    record of who merged it.
    """
    if verdict not in ("same", "different"):
        raise DecisionRefused(f"verdict must be 'same' or 'different', not {verdict!r}")
    if left_ref == right_ref:
        raise DecisionRefused("a record cannot be resolved against itself")
    if not rationale.strip():
        raise DecisionRefused("a decision must state its reason")

    left, right = order_pair(left_ref, right_ref)
    resolved_type = entity_type or _entity_type_for(left)
    if resolved_type is None or resolved_type not in SUPPORTED_TYPES:
        raise DecisionRefused(f"{left} is not a type ARGUS resolves identity for")
    if _entity_type_for(right) != resolved_type:
        raise DecisionRefused(
            f"{left} and {right} are different entity types — identity is resolved "
            "within a type, never across one"
        )

    async with acquire() as conn, conn.transaction():
        decision_id = await repo.record_decision(
            conn,
            entity_type=resolved_type,
            left_ref=left,
            right_ref=right,
            verdict=verdict,
            decided_by=actor,
            decided_by_kind=actor_kind,
            rationale=rationale,
            score=score,
            evidence_weight=evidence_weight,
            model_version=model_version,
            model_fingerprint=model_fingerprint,
            candidate_id=candidate_id,
            reverses_decision_id=reverses_decision_id,
        )
        if candidate_id is not None:
            await repo.close_candidate(conn, candidate_id)

        # An analyst's decision is the only ground truth ARGUS ever gets about
        # its own population, so every one becomes a label. This is what turns
        # the evaluation report from a measurement against constructed data
        # into a measurement against the real thing, over time.
        if label_origin is not None:
            await repo.add_label(
                conn,
                entity_type=resolved_type,
                left_ref=left,
                right_ref=right,
                is_same=(verdict == "same"),
                origin=label_origin,
                note=rationale[:500],
            )

        if audit_actor is not None:
            await audit.record(
                audit.AuditEvent(
                    action=(
                        "resolution.merge" if verdict == "same" else "resolution.separate"
                    ),
                    outcome="success",
                    actor_id=getattr(audit_actor, "id", None),
                    actor_username=getattr(audit_actor, "username", None),
                    actor_role=getattr(audit_actor, "role", None),
                    resource_type=resolved_type,
                    resource_id=f"{left}|{right}",
                    after_state={
                        "decision_id": decision_id,
                        "verdict": verdict,
                        "score": score,
                        "evidence_weight": evidence_weight,
                        "rationale": rationale,
                        "reverses_decision_id": reverses_decision_id,
                    },
                ),
                conn,
            )
        else:
            await audit.record(
                audit.AuditEvent(
                    action=(
                        "resolution.merge" if verdict == "same" else "resolution.separate"
                    ),
                    outcome="success",
                    actor_username=actor,
                    actor_role="matcher",
                    resource_type=resolved_type,
                    resource_id=f"{left}|{right}",
                    detail=rationale,
                    after_state={
                        "decision_id": decision_id,
                        "verdict": verdict,
                        "score": score,
                        "model_fingerprint": model_fingerprint,
                    },
                ),
                conn,
            )

    driver = get_driver()
    projected: bool
    if verdict == "same":
        projected = await graph_repo.project_same_as(
            driver,
            entity_type=resolved_type,
            left_ref=left,
            right_ref=right,
            decision_id=decision_id,
            decided_by=actor,
            score=score,
        )
    else:
        projected = await graph_repo.remove_same_as(
            driver, entity_type=resolved_type, left_ref=left, right_ref=right
        )

    if rebuild:
        await rebuild_clusters()

    return {
        "decision_id": decision_id,
        "left_ref": left,
        "right_ref": right,
        "verdict": verdict,
        "entity_type": resolved_type,
        "projected": projected,
    }


async def reverse_decision(
    decision_id: int, *, actor: str, actor_kind: str, rationale: str, audit_actor: Any = None
) -> dict[str, Any]:
    """Undo a decision by recording its opposite.

    The original row is not touched. "Merged on Tuesday, un-merged on Thursday
    by a supervisor who disagreed" is a materially different record from "never
    merged", and only the append-only form can tell them apart.
    """
    original = await repo.get_decision(decision_id)
    if original is None:
        raise DecisionRefused(f"no decision {decision_id}")

    current = await repo.current_decision(original.left_ref, original.right_ref)
    if current is None or current.decision_id != decision_id:
        raise DecisionRefused(
            f"decision {decision_id} is no longer the current decision for "
            f"{original.left_ref} / {original.right_ref} — reverse the current one "
            f"({current.decision_id if current else 'none'}) instead"
        )

    opposite = "different" if original.verdict == "same" else "same"
    return await decide(
        left_ref=original.left_ref,
        right_ref=original.right_ref,
        verdict=opposite,
        actor=actor,
        actor_kind=actor_kind,
        rationale=rationale,
        entity_type=original.entity_type,
        reverses_decision_id=decision_id,
        audit_actor=audit_actor,
        # A reversal is a statement about a decision, not fresh ground truth
        # about the pair, so it does not overwrite the label the original wrote.
        # The append-only labels table would refuse anyway; being explicit here
        # keeps the reason visible.
        label_origin=None,
    )


def _entity_type_for(ref: str) -> str | None:
    info = resolve_label(ref)
    return info.label if info else None


# ── Clusters ─────────────────────────────────────────────────────────────────


async def rebuild_clusters() -> dict[str, Any]:
    """Re-derive the cluster projection from the decision ledger.

    Cheap enough to run after every decision at this scale, and running it
    eagerly is what keeps "what ARGUS currently believes" from drifting away
    from "what ARGUS was told".
    """
    same_pairs = await repo.active_same_pairs()
    different_pairs = await repo.active_different_pairs()
    refs = sorted({ref for _, left, right in same_pairs for ref in (left, right)})
    counts = await repo.observation_counts(refs)
    pins = await repo.pinned_canonicals()

    clusters = build_clusters(
        same_pairs, different_pairs, observation_counts=counts, pinned=pins
    )
    payload = [
        {
            "cluster_key": c.cluster_key,
            "entity_type": c.entity_type,
            "canonical_ref": c.canonical_ref,
            "canonical_basis": c.canonical_basis,
            "members": c.members,
            "contested": c.contested,
            "contested_reason": c.contested_reason,
        }
        for c in clusters
    ]
    async with acquire() as conn, conn.transaction():
        await repo.replace_clusters(conn, payload)

    return {
        "clusters": len(clusters),
        "members": sum(len(c.members) for c in clusters),
        "contested": sum(1 for c in clusters if c.contested),
    }


async def rebuild_projection() -> dict[str, int]:
    """Rewrite every SAME_AS edge from the ledger.

    A repair tool, and a proof: if the graph ever disagrees with Postgres about
    what has been merged, this makes Postgres win. It exists so "the graph is a
    projection" is a testable claim rather than a description of intent.
    """
    same_pairs = await repo.active_same_pairs()
    pairs = []
    for entity_type, left, right in same_pairs:
        decision = await repo.current_decision(left, right)
        pairs.append(
            (
                entity_type,
                left,
                right,
                decision.decision_id if decision else 0,
                decision.decided_by if decision else MATCHER_ACTOR,
                decision.score if decision else None,
            )
        )
    result = await graph_repo.rebuild_same_as(get_driver(), pairs)
    await rebuild_clusters()
    return result


# ── Subject resolution: the path that closes Phase 3's boundary ──────────────


@dataclass(frozen=True)
class SubjectResolution:
    """What happened when ARGUS tried to work out who a record is about."""

    status: str  # 'known' | 'matched' | 'ambiguous' | 'unknown' | 'unsupported'
    ref: str | None
    detail: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    searched: int = 0
    search_truncated: bool = False

    @property
    def resolved(self) -> bool:
        return self.status in ("known", "matched")


async def resolve_subject(
    subject_ref: str,
    *,
    attributes: dict[str, Any] | None = None,
    origin: str = "feed",
    model: MatchModel = DEFAULT_MODEL,
) -> SubjectResolution:
    """Work out which existing entity an inbound record is about.

    Phase 3 checked only that a subject id had a recognised *prefix*, which
    meant a feed could record observations against `PRS-9999999` — a person who
    does not exist — and nothing anywhere would say so. The observation landed,
    no error was raised, and it would never appear on any entity page. That is
    exactly the silent-loss failure the ingestion phase was built to prevent,
    and it survived because prefix validation looks like existence validation.

    So: the id is checked against the graph. If it is not there and the record
    carries attributes, the matcher is asked whether this is someone ARGUS
    already knows. An unambiguous auto-band match resolves; anything less
    returns the candidates and lets the caller dead-letter the record with them
    named, which is a far more useful dead-letter entry than "unknown subject".
    """
    driver = get_driver()
    if await graph_repo.entity_exists(driver, subject_ref):
        return SubjectResolution("known", subject_ref, "Subject id exists in the graph.")

    entity_type = _entity_type_for(subject_ref)
    if entity_type is None:
        return SubjectResolution(
            "unsupported", None, f"{subject_ref!r} has no recognised entity id prefix."
        )
    if entity_type not in SUPPORTED_TYPES or not attributes:
        return SubjectResolution(
            "unknown",
            None,
            f"No {entity_type} with id {subject_ref} exists, and "
            + (
                "the record carries no attributes to match on."
                if not attributes
                else f"ARGUS does not resolve identity for {entity_type}."
            ),
        )

    from app.resolution.profile import profile_from_record

    probe = profile_from_record(subject_ref, entity_type, attributes, origin=origin)
    if probe is None or not probe.attributes:
        return SubjectResolution(
            "unknown", None, f"No {entity_type} with id {subject_ref}, and no usable attributes."
        )

    keys = sorted(blocking_keys(probe))
    if not keys:
        return SubjectResolution(
            "unknown",
            None,
            "No blocking key could be derived from the record's attributes, so ARGUS "
            "has no way to look for a match without scanning every record.",
        )

    refs = await repo.refs_for_block_keys(keys)
    truncated = len(refs) >= 200

    existing = await graph_repo.fetch_profiles_by_refs(
        driver, entity_type, [ref for ref in refs if ref != subject_ref]
    )
    scored: list[MatchResult] = [
        compare(probe, profile, model=model, blocking_keys=keys)
        for profile in existing.values()
    ]

    scored.sort(key=lambda r: (r.score or 0.0), reverse=True)
    auto = [r for r in scored if r.band == BAND_AUTO]
    review = [r for r in scored if r.band == BAND_REVIEW]

    if len(auto) == 1:
        match = auto[0]
        other = match.right_ref if match.left_ref == subject_ref else match.left_ref
        return SubjectResolution(
            "matched",
            other,
            f"Resolved to {other}: {match.band_reason}",
            candidates=[_candidate_summary(r, subject_ref) for r in scored[:5]],
            searched=len(scored),
            search_truncated=truncated,
        )

    if len(auto) > 1:
        # Several strong matches are only ambiguous if they are different
        # entities. When they are all members of one cluster, ARGUS has already
        # decided they are the same thing, and refusing to resolve would be
        # contradicting its own conclusion — and dead-lettering a record it has
        # everything it needs to place. Found in runtime verification, where a
        # feed matched both halves of a pair the matcher had merged minutes
        # earlier.
        matched_refs = [
            r.right_ref if r.left_ref == subject_ref else r.left_ref for r in auto
        ]
        cluster = await repo.cluster_for_ref(matched_refs[0])
        if cluster is not None and set(matched_refs) <= set(cluster["members"]):
            canonical = cluster["canonical_ref"]
            return SubjectResolution(
                "matched",
                canonical,
                f"Resolved to {canonical}: matched {len(matched_refs)} records "
                f"({', '.join(sorted(matched_refs))}) that ARGUS has already resolved to a "
                f"single entity, so the canonical record was used — {cluster['canonical_basis']}.",
                candidates=[_candidate_summary(r, subject_ref) for r in auto[:5]],
                searched=len(scored),
                search_truncated=truncated,
            )
        return SubjectResolution(
            "ambiguous",
            None,
            f"{len(auto)} existing records match this one strongly enough to merge "
            "automatically, and they are not known to be the same entity. When more than "
            "one does, none of them is a safe answer.",
            candidates=[_candidate_summary(r, subject_ref) for r in auto[:5]],
            searched=len(scored),
            search_truncated=truncated,
        )

    if review:
        return SubjectResolution(
            "ambiguous",
            None,
            f"{len(review)} possible match(es) found, none strong enough to act on "
            "without a person.",
            candidates=[_candidate_summary(r, subject_ref) for r in review[:5]],
            searched=len(scored),
            search_truncated=truncated,
        )

    detail = (
        f"No {entity_type} with id {subject_ref}, and no existing record shares even a "
        "blocking key with it — on the attributes supplied, this looks like someone ARGUS "
        "has never seen."
        if not scored
        else (
            f"No {entity_type} with id {subject_ref}, and none of the {len(scored)} "
            "record(s) sharing a blocking key is a plausible match."
        )
    )
    return SubjectResolution(
        "unknown", None, detail, searched=len(scored), search_truncated=truncated
    )


def _candidate_summary(result: MatchResult, subject_ref: str) -> dict[str, Any]:
    other = result.right_ref if result.left_ref == subject_ref else result.left_ref
    return {
        "ref": other,
        "score": result.score,
        "evidence_weight": result.evidence_weight,
        "band": result.band,
        "reason": result.band_reason,
        "agreed_on": [c.label for c in result.agreements],
        "disagreed_on": [c.label for c in result.disagreements],
    }


# ── Evaluation ───────────────────────────────────────────────────────────────


async def run_evaluation(
    *,
    entity_type: str = "Person",
    sample: int = 1500,
    model: MatchModel = DEFAULT_MODEL,
    persist: bool = True,
) -> dict[str, Any]:
    """Measure the matcher against both labelled sets and record the result.

    The two datasets are reported separately and never combined into a single
    headline figure. They answer different questions — one measures the matcher
    against constructed corruptions, the other against decisions people
    actually made — and averaging them would produce a number that describes
    neither.
    """
    from app.resolution import evaluation

    driver = get_driver()
    profiles = await graph_repo.fetch_profiles(driver, entity_type, limit=sample)
    reports: dict[str, Any] = {}

    synthetic_pairs = evaluation.build_synthetic_set(profiles)
    synthetic = evaluation.evaluate(
        synthetic_pairs,
        dataset="synthetic",
        model=model,
        note=(
            f"Constructed from {len(profiles)} live {entity_type} records by applying named "
            "corruptions, so truth is known by construction. Measures the matcher against a "
            "hypothesis about how sources differ, not against ARGUS's own population."
        ),
    )
    reports["synthetic"] = synthetic.as_dict()

    analyst_labels = await repo.labels(origin="analyst")
    # One query per entity type rather than two per label: the same N+1 that
    # made subject resolution slow, in a place that runs over the whole
    # accumulated label set every time a report is published.
    by_type: dict[str, set[str]] = {}
    for label in analyst_labels:
        by_type.setdefault(label["entity_type"], set()).update(
            (label["left_ref"], label["right_ref"])
        )
    labelled_profiles: dict[str, EntityProfile] = {}
    for label_type, refs in by_type.items():
        labelled_profiles |= await graph_repo.fetch_profiles_by_refs(
            driver, label_type, sorted(refs)
        )

    analyst_pairs: list[evaluation.LabelledPair] = []
    skipped = 0
    for label in analyst_labels:
        left = labelled_profiles.get(label["left_ref"])
        right = labelled_profiles.get(label["right_ref"])
        if left is None or right is None or left.entity_type != right.entity_type:
            skipped += 1
            continue
        analyst_pairs.append(
            evaluation.LabelledPair(
                left=left, right=right, is_same=label["is_same"], corruption="analyst"
            )
        )

    analyst = evaluation.evaluate(
        analyst_pairs,
        dataset="analyst",
        model=model,
        note=(
            f"Every decision made in the review queue ({len(analyst_pairs)} pair(s)"
            + (f", {skipped} skipped because a record is no longer in the graph" if skipped else "")
            + "). The only measurement against the population ARGUS actually sees — and "
            "biased towards pairs the matcher already thought were worth raising, so it "
            "measures precision far better than recall."
        ),
    )
    reports["analyst"] = analyst.as_dict()

    if persist:
        for name, report in (("synthetic", synthetic), ("analyst", analyst)):
            if report.overall.pairs == 0:
                continue
            await repo.record_evaluation(
                model_version=report.model_version,
                model_fingerprint=report.model_fingerprint,
                dataset=name,
                metrics=report.as_dict(),
                notes=report.note,
            )

    return reports


# ── Job registration ─────────────────────────────────────────────────────────


@queue.register(MATCH_JOB_KIND)
async def _run_match_job(job: queue.Job) -> None:
    """Durable-queue entry point, so a long sweep survives a restart.

    A sweep over 20,000 records is minutes of work; running it inside the HTTP
    request that asked for it would tie it to the least durable thing in the
    system. The outcome is recorded in `resolution_runs`, which is where the UI
    reads it from — the handler returns nothing because the run's own record is
    the result.
    """
    payload = job.payload or {}
    entity_types = payload.get("entity_types")
    outcome = await run_matcher(
        entity_types if isinstance(entity_types, list) else None,
        triggered_by=str(payload.get("triggered_by", MATCHER_ACTOR)),
        apply_auto=bool(payload.get("apply_auto", True)),
    )
    logger.info("resolution run complete", extra={"outcome": outcome.as_dict()})
