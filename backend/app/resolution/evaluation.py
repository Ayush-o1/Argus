"""Measuring the matcher: precision, recall, and where they were measured.

A matcher with no published error rate is an opinion. This module makes it a
measurement, against two datasets that answer different questions:

  **`synthetic`** — records are copied and then deliberately corrupted in ways
  real sources corrupt them: a dropped middle name, a transposed date, a phone
  written with a country code, an accent lost in transit. Truth is known
  because the pair was *constructed*, so recall can be measured against
  corruption types the live population does not yet contain enough of. It
  measures the matcher against a hypothesis about the world.

  **`analyst`** — every decision made in the review queue. Small at first and
  the only dataset that reflects the population ARGUS actually sees. It
  measures the matcher against the world.

Both are reported, separately and always labelled, because a headline figure
from constructed data would be exactly the kind of borrowed authority this
project exists to refuse.

**The matcher never sees a label.** The perturbation functions live here and
are imported by nothing in `scoring`, `blocking` or `profile`; the labelled
pairs are passed to `compare` only as ordinary profiles. `tests/
test_resolution_isolation.py` asserts the import direction stays one-way.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from app.resolution.blocking import blocking_keys
from app.resolution.profile import EntityProfile
from app.resolution.scoring import BAND_AUTO, BAND_REVIEW, DEFAULT_MODEL, MatchModel, compare


@dataclass
class Metrics:
    """Counts first, rates second — and never a rate without its counts.

    `predicted_positive` is deliberately "auto or review", i.e. every pair
    ARGUS put in front of someone or acted on. Reporting precision only for the
    auto band would flatter the matcher by excluding every case it was unsure
    about.
    """

    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    # Of the true pairs that were caught, how many were caught outright.
    auto_true_positive: int = 0
    auto_false_positive: int = 0
    pairs: int = 0

    # True pairs that share no blocking key. These are the dangerous misses:
    # the scorer would very likely have caught them, but they are never scored,
    # so they appear nowhere — not in the queue, not in a rejection, nowhere.
    # Measuring the scorer alone would report recall the live pipeline does not
    # actually achieve.
    blocking_missed: int = 0
    true_pairs_blocked: int = 0
    # Of the true pairs the scorer got right, how many blocking would never
    # have handed it. The difference between `recall` and `pipeline_recall`.
    blocking_missed_among_true_positive: int = 0

    @property
    def precision(self) -> float | None:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else None

    @property
    def recall(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else None

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)

    @property
    def auto_precision(self) -> float | None:
        denominator = self.auto_true_positive + self.auto_false_positive
        return self.auto_true_positive / denominator if denominator else None

    @property
    def blocking_recall(self) -> float | None:
        """Share of true pairs that blocking even brought together.

        The ceiling on everything downstream: a pair blocking misses cannot be
        recovered by any amount of scoring.
        """
        total = self.true_pairs_blocked + self.blocking_missed
        return self.true_pairs_blocked / total if total else None

    @property
    def pipeline_recall(self) -> float | None:
        """Recall of the whole pipeline — blocking and scoring together.

        This is the number that describes what an analyst actually gets. It is
        reported alongside `recall` (the scorer in isolation) rather than
        instead of it, because the gap between them says whether to spend
        effort on blocking keys or on weights.
        """
        total = self.true_positive + self.false_negative
        if not total:
            return None
        recovered = self.true_positive - self.blocking_missed_among_true_positive
        return max(recovered, 0) / total

    def as_dict(self) -> dict[str, Any]:
        return {
            "pairs": self.pairs,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "auto_true_positive": self.auto_true_positive,
            "auto_false_positive": self.auto_false_positive,
            "auto_precision": self.auto_precision,
            "blocking_recall": self.blocking_recall,
            "blocking_missed": self.blocking_missed,
            "pipeline_recall": self.pipeline_recall,
        }


@dataclass
class LabelledPair:
    left: EntityProfile
    right: EntityProfile
    is_same: bool
    # Which corruption produced this pair, for the per-corruption breakdown
    # that tells you *what kind* of duplicate the matcher misses.
    corruption: str = "none"


@dataclass
class EvaluationReport:
    dataset: str
    model_version: str
    model_fingerprint: str
    overall: Metrics
    by_corruption: dict[str, Metrics] = field(default_factory=dict)
    misses: list[dict[str, Any]] = field(default_factory=list)
    false_alarms: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "overall": self.overall.as_dict(),
            "by_corruption": {k: v.as_dict() for k, v in sorted(self.by_corruption.items())},
            # Bounded samples, not the full lists: the point is to make failure
            # inspectable, not to move the whole evaluation set into a report.
            "misses": self.misses[:25],
            "miss_count": len(self.misses),
            "false_alarms": self.false_alarms[:25],
            "false_alarm_count": len(self.false_alarms),
            "note": self.note,
        }


# ── Corruptions ──────────────────────────────────────────────────────────────
#
# Each models a specific, observed way that two systems record one person
# differently. Named, so the report can say *which* kind of duplicate is being
# missed rather than only how many.


def _drop_middle(name: str) -> str:
    parts = name.split()
    return f"{parts[0]} {parts[-1]}" if len(parts) > 2 else name


def _abbreviate_first(name: str) -> str:
    parts = name.split()
    return f"{parts[0][0]} {' '.join(parts[1:])}" if len(parts) > 1 else name


def _swap_order(name: str) -> str:
    parts = name.split()
    return f"{parts[-1]} {' '.join(parts[:-1])}" if len(parts) > 1 else name


def _typo(name: str, rng: random.Random) -> str:
    if len(name) < 4:
        return name
    index = rng.randrange(1, len(name) - 1)
    if name[index] == " " or name[index + 1] == " ":
        return name
    return name[:index] + name[index + 1] + name[index] + name[index + 2 :]


def _transpose_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) != 3:
        return value
    year, month, day = parts
    return f"{year}-{day}-{month}" if int(day) <= 12 else value


def _country_code_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits[-9:] if len(digits) > 9 else digits


CORRUPTIONS = (
    "name_middle_dropped",
    "name_abbreviated",
    "name_reordered",
    "name_typo",
    "dob_transposed",
    "dob_missing",
    "phone_reformatted",
    "phone_missing",
    "sparse_record",
)


def perturb(
    profile: EntityProfile, corruption: str, rng: random.Random
) -> EntityProfile | None:
    """Produce a differently-recorded version of the same entity.

    Returns None when the corruption cannot apply — a single-token name has no
    middle name to drop — rather than returning the profile unchanged. An
    unchanged "corrupted" pair would score 1.0 and quietly inflate recall,
    which is the exact failure mode a labelled set is supposed to prevent.
    """
    attributes = dict(profile.attributes)
    name = str(attributes.get("name", ""))

    if corruption == "name_middle_dropped":
        if len(name.split()) < 3:
            return None
        attributes["name"] = _drop_middle(name)
    elif corruption == "name_abbreviated":
        if len(name.split()) < 2:
            return None
        attributes["name"] = _abbreviate_first(name)
    elif corruption == "name_reordered":
        if len(name.split()) < 2:
            return None
        attributes["name"] = _swap_order(name)
    elif corruption == "name_typo":
        changed = _typo(name, rng)
        if changed == name:
            return None
        attributes["name"] = changed
    elif corruption == "dob_transposed":
        dob = attributes.get("date_of_birth")
        if not dob:
            return None
        changed = _transpose_date(str(dob))
        if changed == str(dob):
            return None
        attributes["date_of_birth"] = changed
    elif corruption == "dob_missing":
        if "date_of_birth" not in attributes:
            return None
        attributes.pop("date_of_birth")
    elif corruption == "phone_reformatted":
        phone = attributes.get("phone")
        if not phone:
            return None
        changed = _country_code_phone(str(phone))
        if not changed or changed == str(phone):
            return None
        attributes["phone"] = changed
    elif corruption == "phone_missing":
        if "phone" not in attributes:
            return None
        attributes.pop("phone")
    elif corruption == "sparse_record":
        # The hardest realistic case: a source that reports almost nothing.
        # Kept because it is where the evidence-weight floor earns its place —
        # these pairs *should* mostly land in `insufficient`, and the report
        # shows that as a recall cost rather than hiding it.
        keep = {"name", "city"}
        attributes = {k: v for k, v in attributes.items() if k in keep}
        if "name" not in attributes:
            return None
    else:
        raise ValueError(f"unknown corruption {corruption!r}")

    return EntityProfile(
        ref=f"{profile.ref}~{corruption}",
        entity_type=profile.entity_type,
        attributes=attributes,
        coordinates=profile.coordinates if corruption != "sparse_record" else None,
        origin="synthetic-evaluation",
    )


def build_synthetic_set(
    profiles: list[EntityProfile],
    *,
    seed: int = 20260815,
    positives_per_corruption: int = 40,
    negatives: int = 400,
) -> list[LabelledPair]:
    """Construct a labelled set: corrupted copies, plus true non-matches.

    Negatives are drawn from *different* records at random. They are the
    control: without them precision is unmeasurable, and a matcher that merges
    everything would score perfect recall.

    Seeded, so the report is reproducible. An evaluation whose numbers move
    between runs cannot be used to decide whether a weight change helped.
    """
    rng = random.Random(seed)
    pairs: list[LabelledPair] = []
    if len(profiles) < 2:
        return pairs

    for corruption in CORRUPTIONS:
        made = 0
        pool = list(profiles)
        rng.shuffle(pool)
        for profile in pool:
            if made >= positives_per_corruption:
                break
            twin = perturb(profile, corruption, rng)
            if twin is None:
                continue
            pairs.append(LabelledPair(left=profile, right=twin, is_same=True, corruption=corruption))
            made += 1

    seen: set[tuple[str, str]] = set()

    # Hard negatives: different people the *blocker* would actually produce.
    #
    # This distinction is the difference between a real precision figure and a
    # flattering one. Random pairs of people almost never share a name, a
    # phone or a city, so the matcher scores them near zero and precision comes
    # out at 1.00 — a number that measures nothing, because those pairs are not
    # the ones it will ever be asked about. The pairs it is asked about are
    # precisely the ones blocking brings together, so they are the ones it has
    # to be measured on.
    by_key: dict[str, list[EntityProfile]] = {}
    for profile in profiles:
        for key in blocking_keys(profile):
            by_key.setdefault(key, []).append(profile)

    colliding = [members for members in by_key.values() if len(members) > 1]
    rng.shuffle(colliding)
    hard_target = negatives // 2
    for members in colliding:
        if sum(1 for p in pairs if p.corruption == "distinct_blocked") >= hard_target:
            break
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left, right = members[i], members[j]
                pair_key = (min(left.ref, right.ref), max(left.ref, right.ref))
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                pairs.append(
                    LabelledPair(
                        left=left, right=right, is_same=False, corruption="distinct_blocked"
                    )
                )

    # Easy negatives: random pairs. Kept as the control on the control — if
    # these ever start scoring as matches, something is badly wrong in a way
    # the hard set might not reveal.
    attempts = 0
    easy = 0
    while easy < negatives - hard_target and attempts < negatives * 20:
        attempts += 1
        left, right = rng.sample(profiles, 2)
        pair_key = (min(left.ref, right.ref), max(left.ref, right.ref))
        if pair_key in seen:
            continue
        seen.add(pair_key)
        easy += 1
        pairs.append(LabelledPair(left=left, right=right, is_same=False, corruption="distinct"))

    return pairs


def evaluate(
    labelled: list[LabelledPair],
    *,
    dataset: str,
    model: MatchModel = DEFAULT_MODEL,
    note: str = "",
) -> EvaluationReport:
    """Score every labelled pair and count the four outcomes.

    A pair is treated as a predicted match if it lands in `auto` or `review` —
    everything ARGUS either acted on or asked about. `insufficient` and
    `reject` are predicted non-matches, so a true pair the matcher declined to
    raise counts as a miss. That is the honest accounting: from an analyst's
    seat, a duplicate that never reaches the queue and a duplicate the matcher
    rejected are the same outcome.
    """
    overall = Metrics()
    by_corruption: dict[str, Metrics] = {}
    misses: list[dict[str, Any]] = []
    false_alarms: list[dict[str, Any]] = []

    for pair in labelled:
        result = compare(pair.left, pair.right, model=model)
        bucket = by_corruption.setdefault(pair.corruption, Metrics())
        overall.pairs += 1
        bucket.pairs += 1

        predicted = result.band in (BAND_AUTO, BAND_REVIEW)

        # Would the live pipeline ever have compared these two at all? Scoring
        # a pair the blocker would never produce measures a matcher ARGUS does
        # not run.
        shared_blocks = blocking_keys(pair.left) & blocking_keys(pair.right)
        if pair.is_same:
            if shared_blocks:
                overall.true_pairs_blocked += 1
                bucket.true_pairs_blocked += 1
            else:
                overall.blocking_missed += 1
                bucket.blocking_missed += 1

        if pair.is_same and predicted:
            overall.true_positive += 1
            bucket.true_positive += 1
            if result.band == BAND_AUTO:
                overall.auto_true_positive += 1
                bucket.auto_true_positive += 1
            if not shared_blocks:
                overall.blocking_missed_among_true_positive += 1
                bucket.blocking_missed_among_true_positive += 1
                misses.append(
                    {
                        "left": pair.left.ref,
                        "right": pair.right.ref,
                        "corruption": pair.corruption,
                        "score": result.score,
                        "evidence_weight": result.evidence_weight,
                        "band": result.band,
                        "reason": (
                            "Scored as a match, but no blocking key brings these two "
                            "together, so the live pipeline would never compare them."
                        ),
                    }
                )
        elif pair.is_same and not predicted:
            overall.false_negative += 1
            bucket.false_negative += 1
            misses.append(
                {
                    "left": pair.left.ref,
                    "right": pair.right.ref,
                    "corruption": pair.corruption,
                    "score": result.score,
                    "evidence_weight": result.evidence_weight,
                    "band": result.band,
                    "reason": result.band_reason,
                }
            )
        elif not pair.is_same and predicted:
            overall.false_positive += 1
            bucket.false_positive += 1
            if result.band == BAND_AUTO:
                overall.auto_false_positive += 1
                bucket.auto_false_positive += 1
            false_alarms.append(
                {
                    "left": pair.left.ref,
                    "right": pair.right.ref,
                    "score": result.score,
                    "evidence_weight": result.evidence_weight,
                    "band": result.band,
                    "reason": result.band_reason,
                }
            )
        else:
            overall.true_negative += 1
            bucket.true_negative += 1

    return EvaluationReport(
        dataset=dataset,
        model_version=model.version,
        model_fingerprint=model.fingerprint(),
        overall=overall,
        by_corruption=by_corruption,
        misses=misses,
        false_alarms=false_alarms,
        note=note,
    )
