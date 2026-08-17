"""ARGUS's own risk assessment — computed from evidence, or not computed at all.

Every risk number ARGUS displayed before this phase came from the scenario
generator, which assigned it from storyline membership: the platform was
rendering its own answer key with the authority of an analytic finding. This
package replaces that number with one ARGUS derives itself, and — just as
importantly — with an explicit *refusal* to derive one where the evidence does
not support it.

Three rules hold across this package, and each is enforced by a test rather
than by care:

  1. **Admissibility.** A signal may only read data whose existence and value
     are not produced by the storyline injector. `ADMISSIBLE_INPUTS` in
     `evidence.py` is the whitelist, every signal declares what it reads, and
     the declaration is checked. This is stricter than "don't read
     `risk_score`": `CONTROLS` and `SHARES_DEVICE` edges carry no risk field at
     all, yet exist *only* because a storyline created them, so a detector
     keyed on either would be reading the answer key under another name.

  2. **Evidence coverage is part of the answer.** A score is a ratio over the
     signals that could actually be evaluated for that subject. The share of
     the model that was evaluable travels with the score everywhere, and below
     a floor there is no score at all — the band is `insufficient_evidence`,
     which is a finding, not a gap to be filled with a plausible default.

  3. **Ground truth is for measurement only.** `evaluation.py` reads storylines
     to report precision and recall. Nothing in the scoring path can reach
     them: the evidence projection never selects them, so there is no code path
     from a label to a score.
"""

from app.assessment.model import (
    BAND_ELEVATED,
    BAND_INSUFFICIENT,
    BAND_NOTABLE,
    BAND_ROUTINE,
    RiskModel,
    default_model,
)
from app.assessment.scoring import Assessment, assess_all
from app.assessment.signals import SIGNALS, SignalDefinition, SignalOutcome

__all__ = [
    "BAND_ELEVATED",
    "BAND_INSUFFICIENT",
    "BAND_NOTABLE",
    "BAND_ROUTINE",
    "SIGNALS",
    "Assessment",
    "RiskModel",
    "SignalDefinition",
    "SignalOutcome",
    "assess_all",
    "default_model",
]
