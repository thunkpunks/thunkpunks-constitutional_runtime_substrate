"""
K2 — Coherence Relations. The keystone that turns the admissible region from a
BOX (independent per-dimension bounds) into a MANIFOLD (a region defined by
relations AMONG coordinates).

WHAT MAKES A RELATION A COHERENCE RELATION (not just another threshold):
  A per-dimension threshold says "Omega alone must be >= floor."
  A coherence relation says "this COMBINATION of coordinates is inadmissible
  EVEN THOUGH each coordinate is individually within bounds."
  The defining property: it cannot be reduced to independent per-dimension
  checks. It is a constraint on the JOINT state.

WHY THIS IS PHYSICS, NOT POLICY:
  The relation below follows from what the coordinates MEAN, not from a tuning
  preference. tau is commitment depth; Theta is renegotiability. You cannot be
  simultaneously deeply committed AND fully renegotiable — commitment that is
  freely renegotiable is not commitment. So a high-tau / high-Theta state is
  INCOHERENT: not merely undesirable, but a contradiction in terms. That is a
  coherence law of the state space, which is why it lives in the protected
  Constitution, not in configurable Policy.

WHAT K2 IS AND IS NOT:
  - It IS: at least one joint constraint, making coherence_relation_count() > 1,
    which mechanically earns "the region is no longer a box."
  - It is NOT: a geometry library, curvature, surfaces, or topology. K2 is the
    MINIMAL honest step — one real coherence relation. "manifold" is earned by
    count > 1; richer geometry (Tier-3 vocabulary) remains gated.

The existing theta_tau_coupling enforces the relation DYNAMICALLY (Theta cools
as tau rises). K2 adds the STATIC coherence check: a given (tau, Theta) pair is
itself flagged if the combination is incoherent, independent of how it was
reached. Dynamics + static coherence together define the region's shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Any

from ..core.types import FieldState, GateOutcome, GateReasonCode


COMPONENT_VERSION = "0.1.0"


class CoherenceSeverity(str, Enum):
    """How a coherence violation routes."""
    CATEGORICAL = "categorical"   # routes to REJECT (the combination cannot stand)
    RESHAPEABLE = "reshapeable"   # routes to TRANSFORM (the combination is reshape-eligible)


@dataclass(frozen=True)
class CoherenceViolation:
    """A detected joint-coordinate incoherence."""
    relation_name: str
    severity: CoherenceSeverity
    detail: str


@dataclass(frozen=True)
class CoherenceRelation:
    """
    A joint-coordinate admissibility constraint.

    `predicate` returns True iff the state is COHERENT under this relation
    (i.e. NO violation). `check` wraps it to return a CoherenceViolation or None.

    The predicate must be a genuine joint constraint — it must read more than one
    coordinate, and it must not be reducible to independent per-dimension bounds.
    """
    name: str
    statement: str
    severity: CoherenceSeverity
    predicate: Callable[[FieldState], bool]

    def check(self, state: FieldState) -> "CoherenceViolation | None":
        if self.predicate(state):
            return None  # coherent
        return CoherenceViolation(
            relation_name=self.name,
            severity=self.severity,
            detail=self.statement,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "statement": self.statement,
            "severity": self.severity.value,
        }


# ---------------------------------------------------------------------------
# The commitment-renegotiability coherence relation (the first true K2 relation)
# ---------------------------------------------------------------------------

# Coherence bound: tau + Theta must not exceed this. Note this is a JOINT bound:
# tau alone may be high (deep commitment is fine if renegotiability is low) and
# Theta alone may be high (full renegotiability is fine if commitment is low),
# but BOTH high simultaneously is incoherent — deep commitment that remains
# fully renegotiable is a contradiction.
#
# This bound is PHYSICS (it expresses the meaning-level incompatibility), set
# conservatively so that ordinary states (where Theta has cooled under tau, per
# the dynamic coupling) never trip it — only states where the joint combination
# is genuinely contradictory.
COMMITMENT_RENEGOTIABILITY_BOUND = 1.4


def _commitment_renegotiability_coherent(state: FieldState) -> bool:
    """
    Coherent iff tau + Theta <= bound.

    This is irreducible to per-dimension bounds: tau in [0,1] and Theta in [0,1]
    are each individually satisfiable at values whose SUM violates the relation
    (e.g. tau=0.8, Theta=0.8: each in-bounds, sum 1.6 > 1.4 incoherent).
    """
    return (state.tau + state.Theta) <= COMMITMENT_RENEGOTIABILITY_BOUND


COMMITMENT_RENEGOTIABILITY_RELATION = CoherenceRelation(
    name="commitment_renegotiability_coherence",
    statement=(
        "Commitment depth (tau) and renegotiability (Theta) cannot both be high: "
        f"tau + Theta must not exceed {COMMITMENT_RENEGOTIABILITY_BOUND}. Deep "
        "commitment that remains fully renegotiable is a contradiction in terms."
    ),
    severity=CoherenceSeverity.RESHAPEABLE,
    predicate=_commitment_renegotiability_coherent,
)


# The active set of coherence relations. K2 adds the first true joint relation
# here. (theta_tau_coupling is a DYNAMIC coupling enforced in apply_delta; the
# relations here are STATIC joint checks on a given state.) Growing this tuple is
# how the region acquires more shape; each addition is a deliberate physics claim.
COHERENCE_RELATIONS: tuple[CoherenceRelation, ...] = (
    COMMITMENT_RENEGOTIABILITY_RELATION,
)


def check_coherence(state: FieldState) -> list[CoherenceViolation]:
    """
    Check a state against all active coherence relations.

    Returns the list of violations (empty = jointly coherent). The gate consults
    this; the relations themselves are defined here (physics), not in the gate.
    """
    violations: list[CoherenceViolation] = []
    for relation in COHERENCE_RELATIONS:
        v = relation.check(state)
        if v is not None:
            violations.append(v)
    return violations


def coherence_relation_count() -> int:
    """
    How many STATIC joint coherence relations are active.

    Together with the one DYNAMIC coupling (theta_tau_coupling), the total
    cross-coordinate relation count exceeds 1 once K2 lands — which is the
    mechanical test for "the region is no longer a box."
    """
    return len(COHERENCE_RELATIONS)
