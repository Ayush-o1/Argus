"""Per-attribute comparators.

**Every comparator returns `None` when the attribute cannot be compared**, and
that is the single most important design decision in this module.

A missing attribute is not agreement and it is not disagreement — it is the
absence of evidence, and the two are routinely confused. A matcher that scores
a missing date of birth as 0.0 will refuse to merge two records that are
obviously the same person; one that scores it as 1.0 will merge two strangers
who happen to share a common name and a city. Neither system is telling the
truth about what it knows, and both produce confident output while doing it.

So comparators here answer one of two questions and never mix them:

    "how alike are these two values?"   -> a float in [0, 1]
    "I cannot say"                      -> None

`scoring.py` then keeps the two apart, and carries the proportion of evidence
that was actually comparable all the way to the UI.
"""

from __future__ import annotations

from datetime import date

from app.geometry import haversine_km
from app.resolution.normalize import (
    identifier_key,
    name_tokens,
    normalize_text,
    parse_date,
    phone_digits,
)

# Below this many trailing digits, two phone numbers agreeing means very little
# — plenty of unrelated numbers share their last four.
_PHONE_SUFFIX = 8

# Distance at which two coordinates stop being evidence of anything. 50km is
# roughly "same metropolitan area"; beyond it the signal is noise.
_GEO_FLOOR_KM = 50.0
_GEO_CEILING_KM = 2.0

def jaro_winkler(left: str, right: str, *, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity in [0, 1].

    Implemented here rather than pulled from a dependency because a match score
    must be reproducible from this repository alone — a scoring function whose
    behaviour can change under `pip install --upgrade` is not something an
    analyst can be asked to defend a merge with two years later.

    Winkler's prefix bonus is kept: name typos overwhelmingly occur after the
    first few characters, so a shared prefix is genuine evidence.
    """
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    match_window = max(len(left), len(right)) // 2 - 1
    if match_window < 0:
        match_window = 0

    left_matched = [False] * len(left)
    right_matched = [False] * len(right)
    matches = 0

    for i, ch in enumerate(left):
        start = max(0, i - match_window)
        end = min(i + match_window + 1, len(right))
        for j in range(start, end):
            if right_matched[j] or right[j] != ch:
                continue
            left_matched[i] = True
            right_matched[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # Transpositions: matched characters that appear in a different order.
    transpositions = 0
    k = 0
    for i, matched in enumerate(left_matched):
        if not matched:
            continue
        while not right_matched[k]:
            k += 1
        if left[i] != right[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    jaro = (
        matches / len(left) + matches / len(right) + (matches - transpositions) / matches
    ) / 3.0

    prefix = 0
    for a, b in zip(left, right, strict=False):
        if a != b:
            break
        prefix += 1
        if prefix == 4:
            break

    return jaro + prefix * prefix_weight * (1 - jaro)


def name_similarity(left: str | None, right: str | None, *, kind: str = "person") -> float | None:
    """Compare two names, tolerating reordering, missing middle names and typos.

    Three views are taken and the best is used, because the same pair of names
    can be "the same" under any one of them:

      * **token overlap** handles reordering and extra tokens — "Smith, John A"
        against "John Smith".
      * **whole-string Jaro-Winkler** handles typos that token matching misses,
        since a misspelt token overlaps with nothing.
      * **initials plus surname** handles the very common case of a source that
        only ever records "J. Smith".

    Taking the maximum is deliberate and it is not free: it makes this
    comparator optimistic. That is the right bias *here* only because the
    optimism is bounded by everything else — an optimistic name score alone
    cannot reach the auto-merge band (see `scoring.MatchModel`).
    """
    if not left or not right:
        return None

    left_tokens = name_tokens(left, kind=kind)
    right_tokens = name_tokens(right, kind=kind)
    if not left_tokens or not right_tokens:
        return None

    # 1. Token set overlap, allowing fuzzy token equality.
    matched = 0
    remaining = list(right_tokens)
    for token in left_tokens:
        best_index, best_score = -1, 0.0
        for index, candidate in enumerate(remaining):
            score = jaro_winkler(token, candidate)
            if score > best_score:
                best_index, best_score = index, score
        if best_score >= 0.9 and best_index >= 0:
            matched += 1
            remaining.pop(best_index)
    # Divided by the smaller side: a source that records a middle name should
    # not be penalised against one that does not.
    token_score = matched / min(len(left_tokens), len(right_tokens))

    # 2. Whole-string similarity, order-independent.
    whole = jaro_winkler(" ".join(sorted(left_tokens)), " ".join(sorted(right_tokens)))

    # 3. Initial-plus-surname, only when one side is genuinely abbreviated.
    #
    # Restricted to people. "J. Smith" abbreviating "John Smith" is a personal
    # naming convention; organisations do not have initials in that sense, and
    # applying the rule to them made single-letter fragments of a legal form
    # read as matching initials — scoring two unrelated Dutch companies as an
    # agreeing name because both ended in "B.V.".
    abbreviated = 0.0
    if kind == "person":
        short, long = sorted((left_tokens, right_tokens), key=len)
        if len(short) >= 1 and short[-1] == long[-1]:
            leading_short = [t for t in short[:-1] if len(t) == 1]
            if leading_short and len(short) < len(long):
                if all(
                    any(l_token[0] == initial for l_token in long[:-1])
                    for initial in leading_short
                ):
                    abbreviated = 0.88

    return max(token_score, whole, abbreviated)


def exact_similarity(left: str | None, right: str | None) -> float | None:
    """Exact match after normalisation. 1.0 or 0.0, never in between.

    For values where partial similarity has no meaning: a country code that is
    75% similar to another country code is simply a different country.
    """
    if not left or not right:
        return None
    return 1.0 if normalize_text(left) == normalize_text(right) else 0.0


def identifier_similarity(left: str | None, right: str | None) -> float | None:
    """Exact match on a formatting-insensitive identifier key."""
    if not left or not right:
        return None
    left_key, right_key = identifier_key(left), identifier_key(right)
    if not left_key or not right_key:
        return None
    return 1.0 if left_key == right_key else 0.0


def phone_similarity(left: str | None, right: str | None) -> float | None:
    """Compare phone numbers on their significant digits.

    A full-digit match is 1.0. A suffix match is 0.9 rather than 1.0 because
    the disagreement in the prefix might be a country code recorded two ways —
    or might be two genuinely different numbers in different countries. ARGUS
    cannot tell which from the digits alone, so it does not claim to.
    """
    if not left or not right:
        return None
    left_digits, right_digits = phone_digits(left), phone_digits(right)
    if not left_digits or not right_digits:
        return None
    if left_digits == right_digits:
        return 1.0
    if len(left_digits) >= _PHONE_SUFFIX and len(right_digits) >= _PHONE_SUFFIX:
        if left_digits[-_PHONE_SUFFIX:] == right_digits[-_PHONE_SUFFIX:]:
            return 0.9
    return 0.0


def date_similarity(left: str | date | None, right: str | date | None) -> float | None:
    """Compare two dates, with partial credit only for named, specific errors.

    Exact is 1.0. Two cases get partial credit because they are documented data
    entry faults rather than a general notion of "close":

      * **day/month transposition** — the single most common date error in
        systems that cross national conventions.
      * **month precision padded to the first** — a source that records only a
        month and writes the day as 01.

    Everything else is 0.0, including two dates a week apart in the same month.
    "Close in time" is not evidence of being the same birth date, and on a
    disqualifying attribute that distinction decides whether two records are
    treated as two people.

    The month rule used to fire for *any* two days in the same month, which
    turned a real disagreement — the 16th versus the 23rd — into 0.5 and stopped
    it disqualifying. The docstring already claimed the behaviour implemented
    here; the code did something laxer, and a unit test written from the
    docstring is what caught it.
    """
    left_date, right_date = parse_date(left), parse_date(right)
    if left_date is None or right_date is None:
        return None
    if left_date == right_date:
        return 1.0
    if left_date.year == right_date.year:
        if left_date.day == right_date.month and left_date.month == right_date.day:
            return 0.7
        if left_date.month == right_date.month and 1 in (left_date.day, right_date.day):
            return 0.5
    return 0.0


def geo_similarity(
    left: tuple[float, float] | None, right: tuple[float, float] | None
) -> float | None:
    """Proximity as a weak similarity signal, linear between 2km and 50km.

    Weighted low wherever it is used. Two people in the same city is barely
    evidence — a city holds millions — so this exists to break ties between
    otherwise equal candidates, not to carry a merge.
    """
    if left is None or right is None:
        return None
    distance = haversine_km(left[0], left[1], right[0], right[1])
    if distance <= _GEO_CEILING_KM:
        return 1.0
    if distance >= _GEO_FLOOR_KM:
        return 0.0
    return 1.0 - (distance - _GEO_CEILING_KM) / (_GEO_FLOOR_KM - _GEO_CEILING_KM)


def set_similarity(left: list[str] | None, right: list[str] | None) -> float | None:
    """Jaccard-style overlap for multi-valued attributes such as aliases.

    Empty on either side is `None`, not 0.0: an entity with no recorded aliases
    has not been observed to differ from one that has them.
    """
    if not left or not right:
        return None
    left_set = {normalize_text(v) for v in left if v}
    right_set = {normalize_text(v) for v in right if v}
    if not left_set or not right_set:
        return None
    intersection = left_set & right_set
    if not intersection:
        return 0.0
    # Over the smaller set: one source listing more aliases than another is not
    # evidence against a match.
    return len(intersection) / min(len(left_set), len(right_set))
