"""Normalisation primitives for entity matching.

Everything here is deterministic, dependency-free and pure. That is a
requirement rather than a preference: a match score has to be reproducible
months later when someone asks why two records were merged, and a score that
depends on a library version, a locale, or a remote service cannot be
re-derived from the record alone.

The functions are deliberately conservative. Normalisation destroys
information, and information destroyed here shows up downstream as a false
match that a human then has to un-do. Where a transformation would be
aggressive — stripping a whole token, collapsing two different scripts — it is
either not done or done only for a named, enumerated set.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

# Honorifics and generational suffixes carry no identifying information and
# appear inconsistently across sources: "Dr. Sarah Ellis" and "Sarah Ellis" are
# the same person under every reading. Enumerated rather than pattern-matched
# so an unexpected token is kept rather than silently discarded.
#
# Single letters are never listed: `V` is far more often a middle initial than
# a generational suffix, and dropping an initial loses real signal.
_PERSON_NOISE_TOKENS = frozenset(
    {
        "mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir", "dame", "lord", "lady",
        "rev", "capt", "col", "gen", "sgt", "hon",
        "jr", "sr", "ii", "iii", "iv",
    }
)

# Legal forms differ between a company's registered name and how a source
# writes it ("Bayan Cargo Movers Co Ltd" vs "Bayan Cargo Movers"). Dropping
# them for comparison is right; dropping them from storage would not be, which
# is why this only ever applies to a comparison key.
_ORG_NOISE_TOKENS = frozenset(
    {
        "ltd", "limited", "llc", "llp", "lp", "inc", "incorporated", "co", "corp",
        "corporation", "company", "gmbh", "ag", "sa", "sas", "srl", "spa", "bv",
        "nv", "plc", "pvt", "private", "pte", "pty", "oy", "ab", "as", "kk",
        "holdings", "holding", "group", "international", "intl", "the", "and",
    }
)

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
# Dotted acronyms: `B.V.`, `U.S.A.`, `S.p.A.`. Without this, stripping
# punctuation turns "B.V." into the two tokens "b" and "v", which then look
# exactly like personal initials — and did, until an organisation match scored
# "Alpine Exports B.V." against "Zenith Medical Systems B.V." as an agreeing
# name. Requires two or more letter-dot groups so a genuine personal initial
# ("J. Smith") is left alone.
_DOTTED_ACRONYM = re.compile(r"\b(?:[^\W\d_]\.){2,}", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")
_NON_DIGIT = re.compile(r"\D")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y")


def strip_accents(value: str) -> str:
    """Fold accented characters onto their base letters.

    `José` and `Jose` are routinely the same person recorded by two systems
    with different encoding histories. Non-Latin scripts are left alone: NFKD
    decomposition does not transliterate them, and pretending it does would
    silently mangle names this codebase has no business rewriting.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_text(value: str) -> str:
    """Casefold, de-accent, join dotted acronyms, drop punctuation, collapse space."""
    folded = strip_accents(value).casefold()
    joined = _DOTTED_ACRONYM.sub(lambda m: m.group(0).replace(".", ""), folded)
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", joined)).strip()


def name_tokens(value: str, *, kind: str = "person") -> list[str]:
    """Comparison tokens for a name, with noise tokens removed.

    Returns tokens in source order. Order is preserved rather than sorted
    because some comparators care about it (initials, first-token weighting)
    and any that do not can sort for themselves.

    If removing noise would leave nothing — an organisation literally named
    "The Group" — the un-filtered tokens are returned instead. An empty
    comparison key silently matches everything, which is the worst possible
    failure for this function.
    """
    noise = _ORG_NOISE_TOKENS if kind == "organization" else _PERSON_NOISE_TOKENS
    tokens = [t for t in normalize_text(value).split() if t]
    kept = [t for t in tokens if t not in noise]
    return kept or tokens


def initials(tokens: list[str]) -> str:
    return "".join(t[0] for t in tokens if t)


def soundex(token: str) -> str:
    """Classic Soundex — a 4-character phonetic code.

    Used for *blocking* (deciding which pairs are worth scoring at all), never
    for scoring. That distinction matters: Soundex is crude enough that
    treating a code match as evidence of identity would produce confident
    nonsense, but crude-and-fast is exactly right for narrowing 20,000 records
    to a few dozen worth comparing properly.
    """
    cleaned = _NON_ALNUM.sub("", strip_accents(token)).upper()
    letters = "".join(ch for ch in cleaned if ch.isalpha())
    if not letters:
        return ""

    codes = {
        **dict.fromkeys("BFPV", "1"),
        **dict.fromkeys("CGJKQSXZ", "2"),
        **dict.fromkeys("DT", "3"),
        **dict.fromkeys("L", "4"),
        **dict.fromkeys("MN", "5"),
        **dict.fromkeys("R", "6"),
    }

    first = letters[0]
    result = [first]
    previous = codes.get(first, "")

    for ch in letters[1:]:
        code = codes.get(ch, "")
        if code and code != previous:
            result.append(code)
            if len(result) == 4:
                break
        # H and W are transparent: they do not separate two consonants that
        # would otherwise collapse. Vowels do separate them.
        if ch not in "HW":
            previous = code

    return "".join(result).ljust(4, "0")


def phonetic_token(token: str) -> str:
    """A blocking code for one name token, in any script.

    Soundex only speaks Latin: it keeps `[A-Z]` and discards everything else,
    so `김동현`, `الأستاذة` and `Χατζαντώνης` all reduce to the empty string. A
    blocking key built from those is empty, the record joins no block, and it
    is never compared with anything.

    That is not a rounding error in recall — it is a whole class of people
    ARGUS cannot deduplicate, and it fails silently and unevenly: records with
    Western names get matched, records without them do not. It was found by
    the evaluation harness reporting `blocking_recall` below 1.0 for people
    whose only other key was a phone number.

    So a token that produces no Soundex code falls back to a prefix of its
    normalised form. That is a weaker key — a typo in the first character
    costs the block — but a weaker key is a different thing entirely from no
    key, and the cost is measured per corruption rather than assumed.
    """
    code = soundex(token)
    if code:
        return code
    folded = normalize_text(token)
    # Marked `U:` so the two kinds of key can never collide, and so a report
    # showing them makes it obvious which path a record took.
    return f"U:{folded[:4]}" if folded else ""


def phone_digits(value: str) -> str:
    """Digits only. Leading international prefixes are left in place.

    Comparison happens on a suffix (see `similarity.phone_similarity`) rather
    than by guessing a country code here: "+1 645221119" and "645221119" are
    plausibly the same line, but rewriting one into the other requires knowing
    a country ARGUS has not been told.
    """
    digits = _NON_DIGIT.sub("", value)
    return digits.lstrip("0")


def identifier_key(value: str) -> str:
    """Uppercase alphanumerics only — for plates, IMEIs, registration numbers.

    `GJ-10-BB-9031`, `gj10bb9031` and `GJ 10 BB 9031` are one plate written
    three ways by three systems.
    """
    return _NON_ALNUM.sub("", value).upper()


def parse_date(value: str | date | None) -> date | None:
    """Best-effort date parse. Returns None rather than guessing.

    Ambiguous numeric dates are the classic trap: `03/04/1990` is two different
    days depending on the writer's country. The formats are tried in a fixed
    order and the first that parses wins, so the behaviour is at least
    predictable — but a mis-read date can only ever *lower* a match score here,
    because date disagreement is a disqualifier rather than a tiebreaker.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    # Trim a time component if one came along.
    text = text.split("T")[0].split(" ")[0] if "T" in text else text

    from datetime import datetime

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
