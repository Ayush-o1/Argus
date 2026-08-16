"""Entity resolution: deciding when two records denote the same real thing.

The package is deliberately layered so that the part which *decides* is pure
and the part which *persists* is thin:

    normalize.py   text, phone, date and identifier normalisation
    similarity.py  per-attribute comparators; None means "cannot compare"
    profile.py     the narrow, allowlisted view of an entity the matcher sees
    blocking.py    which pairs are worth scoring at all
    scoring.py     weights, thresholds, bands, and the reason for each
    clustering.py  pairwise decisions -> clusters, contradictions left standing
    evaluation.py  precision and recall against a labelled set

Nothing in here performs I/O. `services/resolution.py` holds every database
call, which is what lets the whole decision path be tested — and re-derived
years later — without a running stack.
"""
