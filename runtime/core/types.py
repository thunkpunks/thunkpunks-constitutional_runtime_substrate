"""
Core runtime types.

Constitutional commitments encoded here:
- FieldState uses bounded scalars (no vectors, distributions, embeddings).
- tau and NSV are monotone non-decreasing (enforced at update boundary, not by type).
- Theta cools with tau rise unless renegotiation events fire (enforced by update rule).
- GateOutcome is a closed four-valued enumeration; no fifth UNKNOWN.
- Every Envelope carries logical_step (canonical clock) and provenance_ref.
- Every Envelope is addressable by envelope_id.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional
import uuid
import hashlib
import json


# --------------------------------------------------------------------------
# Field algebra
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldState:
    """
    S(t) = {Omega, rho, kappa, tau, Theta, NSV}

    Bounded scalar field. Frozen because field states are immutable snapshots;
    transitions produce new FieldState instances, never mutations.
    """
    Omega: float       # optionality, [0, 1]
    rho: float         # collapse rate, signed
    kappa: float       # curvature, signed
    tau: float         # commitment depth, [0, 1], monotone non-decreasing under accumulation
    Theta: float       # topology temperature, [0, 1]
    NSV: float         # irrecoverable residue, [0, inf), monotone non-decreasing
    logical_step: int  # canonical clock

    def __post_init__(self) -> None:
        # Bounds enforcement at construction time.
        # Out-of-bounds field state is a constitutional violation, not a soft warning.
        if not 0.0 <= self.Omega <= 1.0:
            raise ValueError(f"Omega out of bounds [0,1]: {self.Omega}")
        if not 0.0 <= self.tau <= 1.0:
            raise ValueError(f"tau out of bounds [0,1]: {self.tau}")
        if not 0.0 <= self.Theta <= 1.0:
            raise ValueError(f"Theta out of bounds [0,1]: {self.Theta}")
        if self.NSV < 0.0:
            raise ValueError(f"NSV negative: {self.NSV}")
        if self.logical_step < 0:
            raise ValueError(f"logical_step negative: {self.logical_step}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Gate outcomes
# --------------------------------------------------------------------------

class GateOutcome(str, Enum):
    """
    Closed four-valued enumeration. No UNKNOWN.
    DEFER subsumes: cannot-decide, HBTL-required, reshape-exhausted, renegotiability-lost.
    The reason is logged in provenance; the outcome stays four-valued.
    """
    EXECUTE = "EXECUTE"
    TRANSFORM = "TRANSFORM"
    DEFER = "DEFER"
    REJECT = "REJECT"


class GateReasonCode(str, Enum):
    """
    Structural reasons logged alongside gate outcomes.
    These are not the outcome; they explain why the outcome was chosen.
    """
    # REJECT reasons
    OMEGA_BELOW_FLOOR = "omega_below_floor"
    NSV_STEP_EXCEEDED = "nsv_step_exceeded"
    TAU_AT_CEILING_WITHOUT_HBTL = "tau_at_ceiling_without_hbtl"

    # DEFER reasons
    THETA_BELOW_FLOOR = "theta_below_floor"
    HBTL_TRIGGER = "hbtl_trigger"
    RESHAPE_EXHAUSTED = "reshape_exhausted"
    CANNOT_DECIDE = "cannot_decide"

    # TRANSFORM reasons
    RESHAPE_REQUIRED = "reshape_required"

    # Coherence relation (K2): a joint-coordinate constraint not reducible to
    # per-dimension bounds. Each coordinate may be individually in-bounds while
    # the COMBINATION is incoherent.
    COHERENCE_VIOLATION = "coherence_violation"

    # Horizon-cumulative (K3): a cumulative budget over the trajectory is
    # exhausted. Individually-admissible steps are collectively inadmissible.
    HORIZON_EXHAUSTED = "horizon_exhausted"

    # Surface-based signals (can route to REJECT or DEFER depending on surface class)
    SURFACE_VIOLATION = "surface_violation"

    # EXECUTE reasons
    ADMISSIBLE_AS_PROPOSED = "admissible_as_proposed"


# --------------------------------------------------------------------------
# Transformation
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Transformation
# --------------------------------------------------------------------------

class IntentClass(str, Enum):
    """
    Minimal classification of what KIND of move a transformation is.

    This is deliberately small. It is not a domain taxonomy and not a DSL.
    It exists so the gate, the trace, and later the reshape operator can
    reason about transformation type without parsing the effect dict.

    Deferred: domain-specific intent vocabularies, hierarchical intents,
    learned intent classification. Those are expansion, not foundation.
    """
    COMMIT = "commit"            # a move that increases commitment depth (raises tau)
    EXPLORE = "explore"          # a move that opens optionality (raises Omega)
    STABILIZE = "stabilize"      # a move that reduces collapse rate / curvature
    RENEGOTIATE = "renegotiate"  # a move that restores renegotiability (raises Theta)
    RECOVER = "recover"          # a recovery move (handled by the rollback path)
    UNSPECIFIED = "unspecified"  # intent not declared; the honest default


class ReversibilityClass(str, Enum):
    """
    Coarse reversibility classification for a transformation.

    Reversibility is a property the runtime needs in order to reason about
    recoverability. This is the minimal honest set; finer gradations
    (cost curves, partial reversibility) are deferred.
    """
    REVERSIBLE = "reversible"            # can be undone at low cost
    COSTLY_REVERSIBLE = "costly"         # can be undone but at material cost
    IRREVERSIBLE = "irreversible"        # cannot be undone (contributes to NSV)
    UNKNOWN = "unknown"                  # reversibility not assessed; honest default


@dataclass(frozen=True)
class ReversibilityMetadata:
    """
    Structured reversibility information for a transformation.

    `reversal_cost` is an estimate of the NSV/commitment cost of undoing this
    move, only meaningful when reversibility_class is REVERSIBLE or COSTLY.
    """
    reversibility_class: ReversibilityClass = ReversibilityClass.UNKNOWN
    reversal_cost: float = 0.0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reversibility_class": self.reversibility_class.value,
            "reversal_cost": self.reversal_cost,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class Transformation:
    """
    A first-class proposed move from S(t) to S(t+1).

    The transformation is now a structurally-real object, not an anonymous
    delta dict. It carries:
      - typed_effects (the field-dimension deltas; the gate reads these)
      - intent_class (what kind of move this is)
      - reversibility (recoverability metadata)
      - expected_commitment_cost (estimated tau contribution)
      - provenance_ref (link to a Provenance record)
      - description (human-readable rationale)

    SCOPE NOTE: this is the MINIMAL first-class object — enough to stabilize
    the serialization shape so the replay ledger is born against the correct
    boundary. Deferred (do not add yet): composition semantics (T1 ∘ T2),
    inverse mapping, a transformation algebra, domain grammars, surface
    signatures, trajectory classification.

    Backward compatibility: `expected_delta` is retained as an alias-accessor
    for `typed_effects` so existing gate code and call sites keep working.
    """
    transformation_id: str
    typed_effects: dict[str, float]              # field-state deltas
    intent_class: IntentClass = IntentClass.UNSPECIFIED
    reversibility: ReversibilityMetadata = field(default_factory=ReversibilityMetadata)
    expected_commitment_cost: float = 0.0
    provenance_ref: Optional[str] = None
    description: str = ""
    # Lineage for composed transformations. Empty for hand-authored ones; for a
    # composite A∘B it holds (A.id, B.id). This is the one schema change for
    # composition — additive and backward compatible (defaults to empty).
    composed_from: tuple[str, ...] = ()

    @property
    def expected_delta(self) -> dict[str, float]:
        """
        Backward-compatible accessor. The gate and existing call sites read
        `.expected_delta`; it now maps to `typed_effects`. This keeps the
        first-class upgrade non-breaking.
        """
        return self.typed_effects

    @staticmethod
    def new(
        expected_delta: dict[str, float] | None = None,
        description: str = "",
        *,
        typed_effects: dict[str, float] | None = None,
        intent_class: IntentClass = IntentClass.UNSPECIFIED,
        reversibility: Optional[ReversibilityMetadata] = None,
        expected_commitment_cost: float | None = None,
        provenance_ref: Optional[str] = None,
    ) -> Transformation:
        """
        Construct a transformation.

        Backward-compatible: `Transformation.new(expected_delta={...})` still
        works exactly as before. The typed path uses the keyword arguments.

        `expected_delta` and `typed_effects` are synonyms; exactly one should
        be supplied. If both are given, they must be equal.
        """
        if typed_effects is None and expected_delta is None:
            raise ValueError("must supply typed_effects (or expected_delta)")
        if typed_effects is not None and expected_delta is not None:
            if typed_effects != expected_delta:
                raise ValueError(
                    "typed_effects and expected_delta both supplied and differ"
                )
        effects = typed_effects if typed_effects is not None else expected_delta
        assert effects is not None  # for type-checkers

        # If commitment cost not given, default to the tau effect if present.
        if expected_commitment_cost is None:
            expected_commitment_cost = max(0.0, effects.get("tau", 0.0))

        return Transformation(
            transformation_id=str(uuid.uuid4()),
            typed_effects=effects,
            intent_class=intent_class,
            reversibility=reversibility or ReversibilityMetadata(),
            expected_commitment_cost=expected_commitment_cost,
            provenance_ref=provenance_ref,
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformation_id": self.transformation_id,
            "typed_effects": self.typed_effects,
            "intent_class": self.intent_class.value,
            "reversibility": self.reversibility.to_dict(),
            "expected_commitment_cost": self.expected_commitment_cost,
            "provenance_ref": self.provenance_ref,
            "description": self.description,
            "composed_from": list(self.composed_from),
        }

    @classmethod
    def compose(cls, a: "Transformation", b: "Transformation") -> "Transformation":
        """
        Compose two transformations into one: A then B, as a single candidate.

        BOUNDED PRIMITIVE — the safety contract:
          - Pure: takes two given transformations, returns a Transformation.
            Touches NO state, performs NO search, applies NO delta.
          - Composition success means "lawfully constructed candidate", NOT
            "admissible". The composite is still only an input; the gate remains
            the sole admission authority.
          - Agrees with sequential application: the composite's effects are the
            per-coordinate sum of the components', so applying A∘B equals
            applying A then B (for the linear/monotone coordinates). Compose adds
            EXPRESSIVENESS (you can name the composite) without adding CAPABILITY
            (the kernel could already reach those states stepwise).

        Fails closed (raises CompositionRefusal) on:
          - BOUNDS_EXCEEDED: a bounded coordinate's summed effect cannot apply to
            any valid state (e.g. tau effect summing beyond its [0,1] range).
          - MONOTONICITY_VIOLATION: a net-negative aggregate effect on a monotone
            coordinate (tau, NSV) — only sanctioned recovery decreases these, and
            recovery is not a transformation.

        Compose does NOT check the coherence relation: coherence is a property of
        a predicted STATE, and compose produces no state. The gate checks
        coherence when the composite is evaluated.
        """
        # 1. Additive effect algebra, per coordinate.
        composed_effects: dict[str, float] = dict(a.typed_effects)
        for k, v in b.typed_effects.items():
            composed_effects[k] = composed_effects.get(k, 0.0) + v

        # 2. Fail-closed: bounds. Bounded coordinates live in [0,1]; a summed
        # POSITIVE effect larger than the full range cannot apply to any state.
        BOUNDED = {"Omega", "tau", "Theta"}
        for k in BOUNDED:
            if k in composed_effects and abs(composed_effects[k]) > 1.0:
                raise CompositionRefusal(
                    failure=CompositionFailure.BOUNDS_EXCEEDED,
                    detail=(
                        f"Composed effect on {k} is {composed_effects[k]:.3f}; "
                        f"its magnitude exceeds the representable range (1.0). No "
                        f"valid state could absorb this composite — fail closed."
                    ),
                )

        # 3. Fail-closed: monotonicity. tau and NSV only move up through
        # transformations; a net-negative aggregate is structurally illegal.
        for k in ("tau", "NSV"):
            if composed_effects.get(k, 0.0) < 0.0:
                raise CompositionRefusal(
                    failure=CompositionFailure.MONOTONICITY_VIOLATION,
                    detail=(
                        f"Composed effect on {k} is {composed_effects[k]:.3f} < 0. "
                        f"{k} is monotone non-decreasing through transformations; "
                        f"only sanctioned recovery (not a transformation) decreases "
                        f"it. Fail closed."
                    ),
                )

        # 4. Reversibility degrades to the worse-of-the-two.
        composed_rev = _compose_reversibility(a.reversibility, b.reversibility)

        # 5. Commitment cost sums (conservative — composing costly moves costs
        # more, never less).
        composed_cost = a.expected_commitment_cost + b.expected_commitment_cost

        # 6. Intent: equal-or-unspecified.
        composed_intent = (
            a.intent_class if a.intent_class == b.intent_class
            else IntentClass.UNSPECIFIED
        )

        return cls(
            transformation_id=str(uuid.uuid4()),
            typed_effects=composed_effects,
            intent_class=composed_intent,
            reversibility=composed_rev,
            expected_commitment_cost=composed_cost,
            provenance_ref=None,  # lineage lives in composed_from, not a single ref
            description=f"compose({a.transformation_id[:8]}, {b.transformation_id[:8]})",
            composed_from=(a.transformation_id, b.transformation_id),
        )


# Reversibility severity ordering for composition (worse-of-the-two).
_REVERSIBILITY_SEVERITY = {
    ReversibilityClass.REVERSIBLE: 0,
    ReversibilityClass.COSTLY_REVERSIBLE: 1,
    ReversibilityClass.IRREVERSIBLE: 2,
    ReversibilityClass.UNKNOWN: 3,  # unknown is contagious — the worst severity
}


def _compose_reversibility(
    a: "ReversibilityMetadata", b: "ReversibilityMetadata"
) -> "ReversibilityMetadata":
    """Combine reversibility: worse-of-the-two class, summed reversal cost."""
    worse = max(
        (a.reversibility_class, b.reversibility_class),
        key=lambda c: _REVERSIBILITY_SEVERITY[c],
    )
    return ReversibilityMetadata(
        reversibility_class=worse,
        reversal_cost=a.reversal_cost + b.reversal_cost,
        rationale="composed",
    )


class CompositionFailure(str, Enum):
    """Structural reasons a composition is refused (fail-closed)."""
    BOUNDS_EXCEEDED = "bounds_exceeded"
    MONOTONICITY_VIOLATION = "monotonicity_violation"


class CompositionRefusal(Exception):
    """
    Raised when two transformations cannot be lawfully composed.

    Carries a structural CompositionFailure reason. A refusal is NOT an
    admissibility verdict — it means the composite could not be lawfully
    CONSTRUCTED, distinct from a constructed composite being judged inadmissible
    by the gate.
    """
    def __init__(self, failure: "CompositionFailure", detail: str = "") -> None:
        self.failure = failure
        self.detail = detail
        super().__init__(f"{failure.value}: {detail}")


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """
    Provenance record. Every gate outcome, every component emission, every
    state transition links back to one of these.
    """
    provenance_id: str
    runtime_version: str
    component_versions: dict[str, str]
    seeds: dict[str, int]
    parameter_set_hash: str
    predecessor_provenance: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parameter_set_hash(params: dict[str, Any]) -> str:
    """Stable hash of a parameter set. Used to detect threshold changes across runs."""
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# MCP envelope
# --------------------------------------------------------------------------

class PayloadType(str, Enum):
    """Canonical payload types. Adding a new one is a constitutional act."""
    FIELD_STATE = "field_state"
    TRANSFORMATION = "transformation"
    GATE_OUTCOME = "gate_outcome"
    SURFACE_ASSIGNMENT = "surface_assignment"
    SCENARIO = "scenario"
    SCENARIO_VALIDATION = "scenario_validation"
    DIAGNOSTIC = "diagnostic"
    ESCALATION = "escalation"
    REPLAY_TRACE = "replay_trace"
    RESHAPE_ATTEMPT = "reshape_attempt"
    # Bench-runtime interface
    BENCH_OBSERVATION = "bench_observation"
    SESSION_STATE = "session_state"
    RUNTIME_ANALYTICS = "runtime_analytics"
    # Pre-gate layer outputs (SAFE_HOLD from Lambda_0, FAST_PRUNED from Pi_fast)
    PRE_GATE_OUTPUT = "pre_gate_output"


@dataclass(frozen=True)
class Envelope:
    """
    The canonical MCP message envelope.

    Every component reads and writes through this shape. Addressable by
    envelope_id, totally orderable by logical_step, traceable by provenance_ref.
    """
    envelope_id: str
    logical_step: int
    component_id: str
    component_version: str
    payload_type: PayloadType
    payload: dict[str, Any]
    provenance_ref: str
    predecessor_envelope: Optional[str] = None

    @staticmethod
    def new(
        logical_step: int,
        component_id: str,
        component_version: str,
        payload_type: PayloadType,
        payload: dict[str, Any],
        provenance_ref: str,
        predecessor_envelope: Optional[str] = None,
    ) -> Envelope:
        return Envelope(
            envelope_id=str(uuid.uuid4()),
            logical_step=logical_step,
            component_id=component_id,
            component_version=component_version,
            payload_type=payload_type,
            payload=payload,
            provenance_ref=provenance_ref,
            predecessor_envelope=predecessor_envelope,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["payload_type"] = self.payload_type.value
        return d
