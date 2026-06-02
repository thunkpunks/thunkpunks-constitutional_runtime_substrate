"""
K1 — The Physics/Policy Split. The keystone.

This is the architectural line that turns "configurable policy engine" into the
substrate for a "constitutional runtime." It separates:

  PHYSICS (the Constitution): laws the domain author INHERITS and CANNOT edit.
  POLICY (the Configuration): bounds the domain author CONFIGURES.

THE MECHANICAL TEST (not "important vs unimportant"):
  Can the domain author change this value without making the runtime incoherent?
    - If changing it can produce a self-contradicting state space -> PHYSICS.
        (tau decreasing freely makes commitment meaningless; NSV decreasing makes
         "irreversible residue" a lie; reordering outcome precedence makes the
         gate incoherent.)
    - If changing it merely tunes WHERE the admissible region sits without
      breaking coherence -> POLICY.
        (how low Omega may go; the tau ceiling; step bounds.)

WHY THIS IS THE KEYSTONE FOR "COMPILE-YOUR-OWN":
  A compile-your-own admissibility runtime where the author can edit the physics
  is just a policy engine with extra steps. The author compiles the
  CONFIGURATION; they INHERIT the CONSTITUTION. K1 makes that inheritance
  structural: the Constitution is handed over read-only and is uninstantiable
  with altered laws.

WHAT K1 DOES AND DOES NOT DO:
  - It does NOT move the enforcement code. tau monotonicity still lives in
    SessionState.advance; NSV-honesty in recovery; precedence in the gate. Those
    are tested and correct. K1 NAMES and CONSOLIDATES the physics as a protected
    declarative layer that the gate and tooling consult, and that the domain
    author cannot edit. The protection was previously accidental (a property of
    where code lived); K1 makes it deliberate and singular.
  - It does NOT introduce geometry. No coherence relation beyond the one we have
    (Theta-tau). That is K2. K1 only SEPARATES physics from policy; it does not
    enrich the physics.

NSV PROMOTION (the finding from the Trajectory build, resolved here):
  NSV is structurally a monotone session accumulator exactly like tau. K1 records
  it as a constitutional invariant (NSV monotonicity) alongside tau monotonicity.
  Whether to add it as a literal SessionState field is a separate refactor; the
  LAW is declared here regardless.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .gate import GateThresholds


COMPONENT_VERSION = "0.1.0"


class InvariantClass(str, Enum):
    """The kinds of constitutional law."""
    MONOTONICITY = "monotonicity"        # a quantity may only move one direction
    COUPLING = "coupling"                # one coordinate constrains another
    SANCTIONED_EXCEPTION = "sanctioned_exception"  # the sole exception to a law
    OUTCOME_STRUCTURE = "outcome_structure"        # closed outcome space + ordering
    NON_REPRESENTABLE = "non_representable"        # states that cannot be constructed
    HORIZON_CUMULATIVE = "horizon_cumulative"      # cumulative-over-trajectory law (K3)


@dataclass(frozen=True)
class ConstitutionalInvariant:
    """
    A single law of the runtime physics. Declarative: it NAMES the invariant and
    points to where it is ENFORCED. It does not re-implement enforcement.

    `editable` is always False — that is the point. The field exists to make the
    non-editability explicit and assertable.
    """
    name: str
    invariant_class: InvariantClass
    statement: str
    enforced_in: str          # where the executable enforcement lives
    editable: bool = False    # ALWAYS False for constitutional invariants

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "invariant_class": self.invariant_class.value,
            "statement": self.statement,
            "enforced_in": self.enforced_in,
            "editable": self.editable,
        }


# ---------------------------------------------------------------------------
# THE CONSTITUTION — the protected physics. Frozen, canonical, non-editable.
# ---------------------------------------------------------------------------

_CONSTITUTIONAL_INVARIANTS: tuple[ConstitutionalInvariant, ...] = (
    ConstitutionalInvariant(
        name="tau_monotonicity",
        invariant_class=InvariantClass.MONOTONICITY,
        statement="Commitment depth tau is non-decreasing through ordinary advancement.",
        enforced_in="SessionState.advance (raises on decrease)",
    ),
    ConstitutionalInvariant(
        name="nsv_monotonicity",
        invariant_class=InvariantClass.MONOTONICITY,
        statement="Irreversible residue NSV is non-decreasing; it can never be un-spent.",
        enforced_in="apply_delta (NSV delta clamped non-negative); recovery retains NSV",
    ),
    ConstitutionalInvariant(
        name="theta_tau_coupling",
        invariant_class=InvariantClass.COUPLING,
        statement="Renegotiability Theta cools as commitment depth tau rises "
                  "(absent an explicit renegotiation event).",
        enforced_in="apply_delta (Theta cooling under tau rise)",
    ),
    ConstitutionalInvariant(
        name="commitment_renegotiability_coherence",
        invariant_class=InvariantClass.COUPLING,
        statement="(K2) Commitment depth tau and renegotiability Theta cannot "
                  "both be high: their combination is constrained jointly, not "
                  "per-dimension. Deep commitment that remains fully renegotiable "
                  "is incoherent. This is the first STATIC joint coherence "
                  "relation; with it, the admissible region is no longer a box.",
        enforced_in="coherence.check_coherence (consulted by gate.evaluate)",
    ),
    ConstitutionalInvariant(
        name="sanctioned_recovery",
        invariant_class=InvariantClass.SANCTIONED_EXCEPTION,
        statement="The ONLY way tau may decrease is a bounded, logged, "
                  "provenance-preserving recovery that retains NSV.",
        enforced_in="rollback.recover_to_checkpoint (the sole tau-decrement path)",
    ),
    ConstitutionalInvariant(
        name="closed_outcome_space",
        invariant_class=InvariantClass.OUTCOME_STRUCTURE,
        statement="Gate outcomes are exactly {EXECUTE, TRANSFORM, DEFER, REJECT}, "
                  "selected by precedence REJECT > DEFER > TRANSFORM > EXECUTE.",
        enforced_in="gate.evaluate (closed enum + precedence selection)",
    ),
    ConstitutionalInvariant(
        name="commit_authority",
        invariant_class=InvariantClass.NON_REPRESENTABLE,
        statement="Only the gate authorises commitment-state change; a "
                  "counterfactual evaluation cannot produce a commit capability.",
        enforced_in="authority map + CommitToken (absent for counterfactuals)",
    ),
    ConstitutionalInvariant(
        name="bounded_field_state",
        invariant_class=InvariantClass.NON_REPRESENTABLE,
        statement="Field-state coordinates outside their domains cannot be "
                  "constructed (e.g. Omega outside [0,1], tau outside [0,1]).",
        enforced_in="FieldState.__post_init__ (raises at construction)",
    ),
    ConstitutionalInvariant(
        name="horizon_cumulative_admissibility",
        invariant_class=InvariantClass.HORIZON_CUMULATIVE,
        statement="(K3) Cumulative quantities over a trajectory (irreversible "
                  "residue, optionality erosion, peak commitment) CAN be "
                  "inadmissible even when no single step is — a bounded resource "
                  "spent across a horizon can be exhausted. The PRINCIPLE is "
                  "constitutional; the budget VALUES are configurable policy.",
        enforced_in="horizon.check_horizon (consulted by gate.evaluate when a "
                    "trajectory and budget are supplied)",
    ),
)


class ConstitutionViolation(Exception):
    """Raised on any attempt to edit or weaken the Constitution."""


class Constitution:
    """
    The protected physics layer. Handed to domain authors READ-ONLY.

    There is exactly one canonical Constitution. It cannot be constructed with
    altered laws (the constructor refuses arguments). It cannot be mutated
    (no setters; invariants are a frozen tuple). This is what makes "you inherit
    the physics" a structural fact rather than a request.
    """

    def __init__(self, *args, **kwargs) -> None:
        if args or kwargs:
            raise ConstitutionViolation(
                "The Constitution cannot be constructed with altered laws. "
                "It is canonical and non-editable. Domain authors configure "
                "Policy, not Constitution."
            )

    @property
    def invariants(self) -> tuple[ConstitutionalInvariant, ...]:
        return _CONSTITUTIONAL_INVARIANTS

    def invariant(self, name: str) -> ConstitutionalInvariant:
        for inv in _CONSTITUTIONAL_INVARIANTS:
            if inv.name == name:
                return inv
        raise KeyError(f"no constitutional invariant named {name!r}")

    def names(self) -> tuple[str, ...]:
        return tuple(inv.name for inv in _CONSTITUTIONAL_INVARIANTS)

    def is_editable(self, name: str) -> bool:
        # Always False. Present so callers can assert non-editability.
        return self.invariant(name).editable

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": COMPONENT_VERSION,
            "invariants": [inv.to_dict() for inv in _CONSTITUTIONAL_INVARIANTS],
            "coherence_relations": [r.to_dict() for r in self.coherence_relations()],
        }

    def coherence_relations(self) -> tuple[ConstitutionalInvariant, ...]:
        """
        The cross-coordinate coherence relations currently in the Constitution.

        TODAY this is exactly one: theta_tau_coupling. This method is the
        RESERVED INSERTION POINT for K2: K2 adds cross-coordinate constraints
        here, turning the admissible region from a box (independent bounds) into
        a region defined by relations among coordinates (earns "manifold").

        It is a method, not a hardcoded list inside the gate, precisely so K2
        can extend the set of coherence relations WITHOUT touching the gate's
        decision logic. The insertion point exists now; it currently returns the
        single coupling we have. K2 is the act of adding more.
        """
        return tuple(
            inv for inv in _CONSTITUTIONAL_INVARIANTS
            if inv.invariant_class is InvariantClass.COUPLING
        )

    def coherence_relation_count(self) -> int:
        """
        How many cross-coordinate coherence relations the Constitution holds.

        1 today (theta_tau_coupling). When this exceeds 1, K2 has begun: the
        admissible region is no longer a box. This count is the mechanical test
        for "have we earned the word manifold yet" (answer today: no, count==1).
        """
        return len(self.coherence_relations())


# Singleton accessor — there is one Constitution.
_CONSTITUTION = Constitution()


def constitution() -> Constitution:
    """Return the canonical, read-only Constitution."""
    return _CONSTITUTION


# ---------------------------------------------------------------------------
# POLICY — the configurable layer. This is what a domain author may set.
# ---------------------------------------------------------------------------

# The set of GateThresholds fields that are POLICY (configurable). Every field
# not in this set is, by exclusion, not freely configurable. theta_cooling_rate
# is policy (the RATE), but the EXISTENCE of cooling is physics (theta_tau_coupling).
_POLICY_FIELDS: frozenset[str] = frozenset({
    "omega_floor",
    "tau_ceiling",
    "theta_floor",
    "nsv_step_max",
    "nsv_step_catastrophic",
    "omega_drop_step_max",
    "theta_cooling_rate",
    "reshape_eligibility_margin",
})


@dataclass(frozen=True)
class Configuration:
    """
    The configurable policy layer — what a domain author sets.

    Holds the GateThresholds (where the admissible region sits) and nothing that
    would alter the physics. Validation confirms that configuration only touches
    policy fields; it cannot smuggle in a change to a constitutional law.
    """
    thresholds: GateThresholds
    domain_label: str = "unspecified"

    def configured_fields(self) -> frozenset[str]:
        return _POLICY_FIELDS

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return {
            "domain_label": self.domain_label,
            "thresholds": asdict(self.thresholds),
            "policy_fields": sorted(_POLICY_FIELDS),
        }


def validate_configuration_touches_only_policy(
    proposed_field_names: set[str],
) -> list[str]:
    """
    Confirm a proposed configuration edits ONLY policy fields.

    Returns a list of violations (field names that are not policy / are physics).
    Empty list = the configuration is constitutionally safe.

    This is the guard a builder calls before accepting a user's configuration:
    a user trying to set a non-policy field is trying to edit the physics, which
    is refused.
    """
    violations: list[str] = []
    for name in proposed_field_names:
        if name not in _POLICY_FIELDS:
            violations.append(name)
    return violations


@dataclass(frozen=True)
class GovernedRuntime:
    """
    The pairing of the (inherited) Constitution and the (configured) Policy.

    This is what a domain author actually holds: a runtime whose physics they
    inherit and whose policy they set. The Constitution is always the canonical
    singleton; only the Configuration varies per domain.
    """
    configuration: Configuration

    @property
    def constitution(self) -> Constitution:
        # Always the canonical one. A GovernedRuntime cannot carry a custom one.
        return constitution()

    def thresholds(self) -> GateThresholds:
        return self.configuration.thresholds
