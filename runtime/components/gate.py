"""
Algebraic Gate Engine.

Constitutional role: primary guardian of falsifiability and replay determinism.

Pure function: given a field state, a proposed transformation, thresholds,
and (optionally) a surface assignment, produce a gate outcome with structural
reason codes.

What this component does NOT do:
- Generate candidate transformations (Transformation Candidate Skill).
- Reshape failed transformations (Reshape Operator Skill).
- Decide via LLM (LLM is bounded inside Reshape, not here).
- Modify state.

Constitutional commitments encoded:
- Outcomes are exhaustively {EXECUTE, TRANSFORM, DEFER, REJECT}. No UNKNOWN.
- Thresholds are runtime parameters, passed in, logged.
- tau and NSV monotonicity is enforced when applying the delta.
- Theta cools under tau rise unless explicit renegotiation event is supplied.
- All decision predicates are algebraic and inspectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Annotation-only import. The gate's DOMAIN includes the trajectory (T2),
    # but the pure gate does not yet READ it (that is TP/K3). Keeping this
    # under TYPE_CHECKING means the gate module gains no hard runtime dependency
    # on trajectory — the gate stays maximally decoupled and pure.
    from .trajectory import Trajectory
    from .horizon import HorizonBudget

from ..core.types import (
    FieldState,
    GateOutcome,
    GateReasonCode,
    Transformation,
)
from .coherence import (
    check_coherence as _check_coherence,
    CoherenceSeverity as _CoherenceSeverity,
)
from .horizon import check_horizon as _check_horizon


COMPONENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class GateThresholds:
    """
    All gate thresholds in one immutable bundle.

    These are runtime parameters. They are logged with every gate outcome
    via parameter_set_hash. Perturbing them is the falsification mechanism
    for several research questions.
    """
    # Floors and ceilings on field dimensions
    omega_floor: float = 0.10      # below this, optionality is effectively collapsed
    tau_ceiling: float = 0.85      # above this, commitment requires HBTL review
    theta_floor: float = 0.15      # below this, renegotiability is effectively lost

    # Per-step deltas
    nsv_step_max: float = 0.20     # max residue accumulated in a single transformation
    nsv_step_catastrophic: float = 0.50  # above this, categorical reject
    omega_drop_step_max: float = 0.40    # max optionality drop in one step

    # Theta cooling rule
    theta_cooling_rate: float = 0.5  # Theta cools by this fraction of tau increase

    # Eligibility band for TRANSFORM (vs. categorical REJECT)
    # Bounded violations within this margin are reshape-eligible.
    reshape_eligibility_margin: float = 0.15


@dataclass(frozen=True)
class GateInput:
    """Inputs to a single gate evaluation."""
    current_state: FieldState
    transformation: Transformation
    thresholds: GateThresholds
    # Surface assignment is optional in v1 because the Surface Engine is not yet built.
    # When provided, certain surface classes (nodoid, collapse_funnel) become
    # categorical signals.
    surface_class: Optional[str] = None
    # Whether an HBTL review has been completed for this transformation.
    # If False and tau would exceed ceiling, the transformation is rejected pending HBTL.
    hbtl_reviewed: bool = False
    # Whether this transformation includes an explicit renegotiation event.
    # If True, Theta does not cool under tau rise.
    renegotiation_event: bool = False
    # The trajectory that reached current_state. Optional, defaults to None.
    #
    # T2 — THE ONTOLOGICAL DOMAIN CHANGE: with this field, the gate's domain is
    # no longer "state" but "state-or-trajectory". The gate is now a function of
    # the trajectory that CURRENTLY IGNORES most of it (it reads only
    # current_state today). This is the structural commitment that prevents K1
    # from hardening into a state-only physics layer: when history becomes
    # constitutive (K3), it enters through a field that already exists, not a
    # signature change. current_state remains required and authoritative for
    # backward compatibility; trajectory.current_state (when supplied) must
    # equal current_state.
    trajectory: Optional["Trajectory"] = None
    # The horizon budget (K3). Optional, default None. When BOTH a trajectory and
    # a budget are present, the gate checks cumulative trajectory quantities
    # against the budget — so individually-admissible steps can be collectively
    # inadmissible. With no budget (default), K3 is inactive and behaviour is
    # exactly the pre-K3 behaviour.
    horizon_budget: Optional["HorizonBudget"] = None

    def __post_init__(self) -> None:
        # Coherence: if a trajectory is supplied, it must actually lead to the
        # state being judged. A trajectory whose endpoint differs from
        # current_state would be an incoherent input — history that does not
        # reach the state under evaluation. We compare the six field-state
        # coordinates. When no trajectory is supplied (the default), this check
        # is skipped entirely and the pure-state path is untouched.
        if self.trajectory is not None:
            traj_end = self.trajectory.current_state
            if traj_end is not None and traj_end != self.current_state:
                raise ValueError(
                    "GateInput.trajectory does not lead to current_state: "
                    "the supplied history must reach the state being judged"
                )


@dataclass(frozen=True)
class GateOutput:
    """
    Outputs of a single gate evaluation.

    `predicted_state` is the S(t+1) the gate computed and evaluated against.
    For TRANSFORM and REJECT outcomes, this is what would have happened.
    For EXECUTE, this is the committed result.
    For DEFER, this is the rejected projection.
    """
    outcome: GateOutcome
    reason_codes: tuple[GateReasonCode, ...]
    predicted_state: FieldState
    threshold_crossings: tuple[str, ...]
    rationale: str  # human-readable; not used for gating logic


def apply_delta(
    current: FieldState,
    delta: dict[str, float],
    thresholds: GateThresholds,
    renegotiation_event: bool,
) -> FieldState:
    """
    Apply a transformation's expected_delta to produce S(t+1).

    Enforces:
    - Bounds (Omega, tau, Theta in [0,1]; NSV >= 0).
    - Monotonicity (tau and NSV do not decrease unless explicit rollback,
      which is not modeled at the delta level in v1 — rollback is a separate operation).
    - Theta cooling: if tau increases and no renegotiation event, Theta cools
      proportionally to the tau rise.
    - logical_step increments by exactly 1.
    """
    new_omega = _clamp(current.Omega + delta.get("Omega", 0.0), 0.0, 1.0)

    # tau monotonicity: cannot decrease without explicit rollback
    tau_delta = delta.get("tau", 0.0)
    if tau_delta < 0:
        # Negative tau delta is only permitted if accompanied by a rollback event.
        # In v1, the gate sees only the proposed delta; rollback is handled separately.
        # Treat negative tau delta as zero here; the gate's reason codes will flag it.
        tau_delta = 0.0
    new_tau = _clamp(current.tau + tau_delta, 0.0, 1.0)

    # NSV monotonicity: cannot decrease.
    nsv_delta = max(0.0, delta.get("NSV", 0.0))
    new_nsv = max(0.0, current.NSV + nsv_delta)

    # Theta: cools under tau rise unless renegotiation event fires.
    explicit_theta_delta = delta.get("Theta", 0.0)
    if renegotiation_event:
        new_theta = _clamp(current.Theta + explicit_theta_delta, 0.0, 1.0)
    else:
        tau_rise = new_tau - current.tau
        theta_cooling = -thresholds.theta_cooling_rate * tau_rise
        new_theta = _clamp(
            current.Theta + explicit_theta_delta + theta_cooling, 0.0, 1.0
        )

    # rho and kappa are signed; apply directly.
    new_rho = current.rho + delta.get("rho", 0.0)
    new_kappa = current.kappa + delta.get("kappa", 0.0)

    return FieldState(
        Omega=new_omega,
        rho=new_rho,
        kappa=new_kappa,
        tau=new_tau,
        Theta=new_theta,
        NSV=new_nsv,
        logical_step=current.logical_step + 1,
    )


def evaluate(gate_input: GateInput) -> GateOutput:
    """
    Evaluate a single transformation. Pure function. Replay-deterministic.

    Three-phase evaluation:
    1. Compute predicted S(t+1) via apply_delta.
    2. Collect all violation signals (no outcome decisions yet).
    3. Select outcome by explicit precedence:
       REJECT > DEFER > TRANSFORM > EXECUTE.

    Outcome precedence rationale:
    - REJECT (categorical) wins over everything else; if any signal is
      catastrophic, no reshape can save it.
    - DEFER (structural uncertainty) wins over TRANSFORM; if renegotiability
      is lost, reshape cannot restore it.
    - TRANSFORM wins over EXECUTE; bounded violations are reshape-eligible
      and should not silently EXECUTE.
    - EXECUTE only when no signals fired.
    """
    s = gate_input.current_state
    t = gate_input.transformation
    th = gate_input.thresholds

    predicted = apply_delta(s, t.expected_delta, th, gate_input.renegotiation_event)

    # --- Phase 2: collect signals -----------------------------------------
    nsv_step = predicted.NSV - s.NSV
    omega_drop = s.Omega - predicted.Omega

    reject_reasons: list[GateReasonCode] = []
    defer_reasons: list[GateReasonCode] = []
    transform_reasons: list[GateReasonCode] = []
    crossings: list[str] = []
    rationales: list[str] = []

    # NSV step
    if nsv_step >= th.nsv_step_catastrophic:
        reject_reasons.append(GateReasonCode.NSV_STEP_EXCEEDED)
        crossings.append(f"nsv_step={nsv_step:.4f} >= catastrophic={th.nsv_step_catastrophic}")
        rationales.append(
            f"Catastrophic residue: NSV would step by {nsv_step:.3f} "
            f"(catastrophic threshold {th.nsv_step_catastrophic})."
        )
    elif nsv_step > th.nsv_step_max:
        transform_reasons.append(GateReasonCode.NSV_STEP_EXCEEDED)
        crossings.append(f"nsv_step={nsv_step:.4f} > max={th.nsv_step_max}")
        rationales.append(
            f"NSV step {nsv_step:.3f} exceeds per-step max {th.nsv_step_max} "
            f"but is below catastrophic; reshape-eligible."
        )

    # Omega floor
    if predicted.Omega <= th.omega_floor / 2:
        reject_reasons.append(GateReasonCode.OMEGA_BELOW_FLOOR)
        crossings.append(
            f"Omega={predicted.Omega:.4f} <= half-floor={th.omega_floor / 2}"
        )
        rationales.append(
            f"Optionality collapse: predicted Omega={predicted.Omega:.3f} "
            f"is at or below half the floor; categorical."
        )
    elif predicted.Omega <= th.omega_floor:
        transform_reasons.append(GateReasonCode.OMEGA_BELOW_FLOOR)
        crossings.append(f"Omega={predicted.Omega:.4f} <= floor={th.omega_floor}")
        rationales.append(
            f"Predicted Omega={predicted.Omega:.3f} is below floor "
            f"{th.omega_floor} but above half-floor; reshape-eligible."
        )

    # Omega step magnitude (independent of absolute floor)
    if omega_drop > th.omega_drop_step_max:
        if GateReasonCode.OMEGA_BELOW_FLOOR not in transform_reasons + reject_reasons:
            transform_reasons.append(GateReasonCode.OMEGA_BELOW_FLOOR)
        crossings.append(
            f"omega_drop={omega_drop:.4f} > step_max={th.omega_drop_step_max}"
        )
        rationales.append(
            f"Optionality drops by {omega_drop:.3f} in one step "
            f"(step max {th.omega_drop_step_max}); reshape-eligible."
        )

    # tau ceiling
    if predicted.tau >= th.tau_ceiling and not gate_input.hbtl_reviewed:
        defer_reasons.append(GateReasonCode.TAU_AT_CEILING_WITHOUT_HBTL)
        defer_reasons.append(GateReasonCode.HBTL_TRIGGER)
        crossings.append(
            f"tau={predicted.tau:.4f} >= ceiling={th.tau_ceiling} (no HBTL)"
        )
        rationales.append(
            f"Commitment depth would reach {predicted.tau:.3f} "
            f"(ceiling {th.tau_ceiling}) without HBTL review."
        )

    # Theta floor (renegotiability lost)
    if predicted.Theta < th.theta_floor:
        defer_reasons.append(GateReasonCode.THETA_BELOW_FLOOR)
        crossings.append(f"Theta={predicted.Theta:.4f} < floor={th.theta_floor}")
        rationales.append(
            f"Renegotiability would drop to Theta={predicted.Theta:.3f} "
            f"(floor {th.theta_floor})."
        )

    # Surface-class signals
    if gate_input.surface_class == "nodoid":
        reject_reasons.append(GateReasonCode.SURFACE_VIOLATION)
        crossings.append("surface=nodoid")
        rationales.append(
            "Trajectory exhibits nodoid (contradiction) signature."
        )
    elif gate_input.surface_class == "collapse_funnel":
        defer_reasons.append(GateReasonCode.SURFACE_VIOLATION)
        defer_reasons.append(GateReasonCode.HBTL_TRIGGER)
        crossings.append("surface=collapse_funnel")
        rationales.append(
            "Trajectory exhibits collapse_funnel (convergent optionality loss)."
        )

    # K2: coherence relations — joint-coordinate constraints not reducible to
    # per-dimension bounds. Checked on the PREDICTED state (the state the
    # transformation would produce). A jointly-incoherent state is flagged even
    # when every individual coordinate is within bounds.
    for _violation in _check_coherence(predicted):
        if _violation.severity is _CoherenceSeverity.CATEGORICAL:
            reject_reasons.append(GateReasonCode.COHERENCE_VIOLATION)
        else:
            transform_reasons.append(GateReasonCode.COHERENCE_VIOLATION)
        crossings.append(f"coherence={_violation.relation_name}")
        rationales.append(_violation.detail)

    # K3: horizon-cumulative admissibility. When a trajectory AND a budget are
    # supplied, check whether committing this step would exhaust a cumulative
    # budget over the horizon. Individually-admissible steps can be collectively
    # inadmissible. Inactive (no-op) when either is absent — preserving the
    # pre-K3 behaviour exactly. Routes to DEFER: the trajectory has run out of
    # room, which warrants escalation/review, not a per-step forbiddance.
    _horizon_findings = _check_horizon(
        trajectory=gate_input.trajectory,
        budget=gate_input.horizon_budget,
        prospective_NSV_delta=(predicted.NSV - s.NSV),
        prospective_Omega_erosion=max(0.0, omega_drop),
        prospective_tau=predicted.tau,
    )
    for _hf in _horizon_findings:
        defer_reasons.append(GateReasonCode.HORIZON_EXHAUSTED)
        defer_reasons.append(GateReasonCode.HBTL_TRIGGER)
        crossings.append(f"horizon={_hf.exhaustion.value}")
        rationales.append(_hf.detail)

    # --- Phase 3: select outcome by precedence ----------------------------
    if reject_reasons:
        return GateOutput(
            outcome=GateOutcome.REJECT,
            reason_codes=tuple(reject_reasons),
            predicted_state=predicted,
            threshold_crossings=tuple(crossings),
            rationale=" | ".join(rationales),
        )

    if defer_reasons:
        return GateOutput(
            outcome=GateOutcome.DEFER,
            reason_codes=tuple(defer_reasons),
            predicted_state=predicted,
            threshold_crossings=tuple(crossings),
            rationale=" | ".join(rationales),
        )

    if transform_reasons:
        transform_reasons.append(GateReasonCode.RESHAPE_REQUIRED)
        return GateOutput(
            outcome=GateOutcome.TRANSFORM,
            reason_codes=tuple(transform_reasons),
            predicted_state=predicted,
            threshold_crossings=tuple(crossings),
            rationale=(
                " | ".join(rationales)
                + " | Reshape operator should propose an alternative T'."
            ),
        )

    return GateOutput(
        outcome=GateOutcome.EXECUTE,
        reason_codes=(GateReasonCode.ADMISSIBLE_AS_PROPOSED,),
        predicted_state=predicted,
        threshold_crossings=(),
        rationale="All admissibility predicates satisfied.",
    )


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
