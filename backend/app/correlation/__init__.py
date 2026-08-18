"""Correlation: deciding whether two of ARGUS's own findings belong together.

Phase 5 assesses subjects one at a time. This package asks the next question —
given two subjects ARGUS found something in, is there a reason to believe they
are connected? — and answers it from discovered structure only, never from the
`Incident`, `Case` or `Storyline` records that already state the answer.
"""
