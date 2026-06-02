"""
Bench-runtime interface types.

Implements Spec Addendum 001 (Position A): the bench is observational only,
tau and Theta are runtime-owned session accumulators, FieldState stays 6D,
Energy is recorded but not constitutionalized.

Outcome typology:
    Pre-gate outcomes (short-circuit): SAFE_HOLD, FAST_PRUNED
    Gate outcomes (algebraic, closed at four): EXECUTE, TRANSFORM, DEFER, REJECT

The two layers are constitutionally distinct. SAFE_HOLD and FAST_PRUNED never
appear in a GateOutput. EXECUTE/TRANSFORM/DEFER/REJECT never appear in a
PreGateOutput.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional

from .types import FieldState


# --------------------------------------------------------------------------
# Bench → Runtime: BenchObservation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BenchObservation:
    """
    A single bench tick observation.

    Five derived admissibility quantities (Omega, rho, kappa, NSV, Energy)
    plus the 9D raw omega vector preserved for provenance, plus tick metadata.

    The bench computes these. It does NOT compute tau, Theta, acceptance,
    commitment, or renegotiability.
    """
    Omega: float           # optionality in [0, 1]
    rho: float             # collapse rate (signed)
    kappa: float           # curvature (signed)
    NSV: float             # irrecoverable residue (>= 0)
    Energy: float          # activation level (>= 0); NOT an admissibility dimension
    omega_raw: tuple[float, ...]  # 9D raw omega vector for provenance
    tick_id: str
    timestamp_ms: int
    session_id: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.Omega <= 1.0:
            raise ValueError(f"BenchObservation.Omega out of bounds: {self.Omega}")
        if self.NSV < 0.0:
            raise ValueError(f"BenchObservation.NSV negative: {self.NSV}")
        if self.Energy < 0.0:
            raise ValueError(f"BenchObservation.Energy negative: {self.Energy}")
        if len(self.omega_raw) != 9:
            raise ValueError(
                f"BenchObservation.omega_raw must have 9 components; got {len(self.omega_raw)}"
            )
        if not self.tick_id:
            raise ValueError("BenchObservation.tick_id is required")
        if not self.session_id:
            raise ValueError("BenchObservation.session_id is required")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["omega_raw"] = list(self.omega_raw)
        return d


# --------------------------------------------------------------------------
# Runtime internal: SessionState
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionState:
    """
    Runtime-owned session accumulator for tau (commitment depth) and
    Theta (topology temperature).

    tau is monotone non-decreasing under acceptance.
    Theta cools under tau rise unless explicit renegotiation events fire.

    Updated ONLY after a gate decision is known, and ONLY on terminal
    accepting outcomes. The only terminal accepting outcome is EXECUTE.

    TRANSFORM is non-terminal: the gate has flagged a bounded violation as
    reshape-eligible but has NOT approved any state. TRANSFORM routes to
    the reshape operator; the session advances only when reshape produces
    a reshaped T' that then EXECUTEs. If reshape exhausts, the final
    outcome is DEFER and the session does not advance.

    DEFER and REJECT do not advance the session.
    """
    session_id: str
    tau: float
    Theta: float
    last_tick_id: Optional[str] = None
    last_logical_step: int = -1  # -1 means no ticks observed yet
    renegotiation_count: int = 0

    def __post_init__(self) -> None:
        if not self.session_id:
            raise ValueError("SessionState.session_id is required")
        if not 0.0 <= self.tau <= 1.0:
            raise ValueError(f"SessionState.tau out of bounds: {self.tau}")
        if not 0.0 <= self.Theta <= 1.0:
            raise ValueError(f"SessionState.Theta out of bounds: {self.Theta}")

    @staticmethod
    def initial(
        session_id: str,
        tau_0: float = 0.0,
        Theta_0: float = 1.0,
        *,
        tau: Optional[float] = None,
        Theta: Optional[float] = None,
    ) -> SessionState:
        """
        Create an initial session state. Default: tau=0 (no commitment yet),
        Theta=1 (maximum renegotiability).

        Both `tau_0`/`Theta_0` and `tau`/`Theta` keywords accepted; the
        keyword forms take precedence if both are supplied. The double
        naming is a compatibility convenience and may be tightened later.
        """
        actual_tau = tau if tau is not None else tau_0
        actual_Theta = Theta if Theta is not None else Theta_0
        return SessionState(
            session_id=session_id,
            tau=actual_tau,
            Theta=actual_Theta,
            last_tick_id=None,
            last_logical_step=-1,
            renegotiation_count=0,
        )

    def advance(
        self,
        new_tau: float,
        new_Theta: float,
        tick_id: str,
        logical_step: int,
        is_renegotiation: bool = False,
    ) -> SessionState:
        """
        Advance the session accumulator after a terminal accepting outcome.

        Enforces tau monotonicity within the session: rollback must be an
        explicit operation, not a silent decrement.

        Called only by session_manager.advance_session_on_accepted, which
        is itself called only when is_accepting(outcome) is True.
        """
        if new_tau < self.tau:
            raise ValueError(
                f"tau monotonicity violation in session {self.session_id}: "
                f"{self.tau} -> {new_tau}. Rollback must be an explicit "
                f"operation, not a silent decrement."
            )
        return SessionState(
            session_id=self.session_id,
            tau=new_tau,
            Theta=new_Theta,
            last_tick_id=tick_id,
            last_logical_step=logical_step,
            renegotiation_count=(
                self.renegotiation_count + (1 if is_renegotiation else 0)
            ),
        )

    def passthrough(self, tick_id: str, logical_step: int) -> SessionState:
        """
        Pass session state through unchanged after a non-accepting outcome.

        tau, Theta, and renegotiation_count are preserved. last_tick_id and
        last_logical_step update so the trace records that this tick occurred.
        """
        return SessionState(
            session_id=self.session_id,
            tau=self.tau,
            Theta=self.Theta,
            last_tick_id=tick_id,
            last_logical_step=logical_step,
            renegotiation_count=self.renegotiation_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Pre-gate outcomes (short-circuit outcomes from layers before the gate)
# --------------------------------------------------------------------------

class PreGateOutcome(str, Enum):
    """
    Outcomes from layers that run BEFORE the algebraic gate.

    These are NOT gate outcomes. They short-circuit the gate.
    The algebraic gate's outcome space (EXECUTE/TRANSFORM/DEFER/REJECT)
    remains closed at four.
    """
    SAFE_HOLD = "SAFE_HOLD"       # Lambda_0 violation; well-formedness failure
    FAST_PRUNED = "FAST_PRUNED"   # Pi_fast proxy filter rejected early
    MEASUREMENT_HOLD = "MEASUREMENT_HOLD"  # measurement not trustworthy enough to evaluate;
    #                                        NOT a rejection (the move may be fine) and NOT
    #                                        confidence (we did not trust the signal). The gate
    #                                        declined to judge an untrusted measurement.


@dataclass(frozen=True)
class PreGateOutput:
    """
    Output of a pre-gate layer.

    If outcome is SAFE_HOLD or FAST_PRUNED, the algebraic gate is NOT run
    for this tick. The session state is NOT advanced.
    """
    outcome: PreGateOutcome
    layer: str                      # which layer emitted this (e.g., "lambda_0", "pi_fast")
    reason: str
    triggered_thresholds: tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Runtime → Bench: RuntimeAnalytics
# --------------------------------------------------------------------------

class Lambda0Status(str, Enum):
    """Lambda_0 (foundational well-formedness) status."""
    VALID = "valid"
    VIOLATED = "violated"
    UNCHECKED = "unchecked"   # Lambda_0 layer not yet enabled in v1


@dataclass(frozen=True)
class RuntimeAnalytics:
    """
    Runtime analytical output for Bench display, Blender rendering, and trace.

    Seven dimensions (six FieldState dimensions plus Energy) plus diagnostics.
    Read-only to consumers. The bench may display these but may not write them.

    `gate_outcome_str` is a string rather than a GateOutcome enum because it
    may be either a GateOutcome value or a PreGateOutcome value.
    """
    Omega: float
    rho: float
    kappa: float
    tau: float
    Theta: float
    NSV: float
    Energy: float

    gate_outcome_str: str            # GateOutcome OR PreGateOutcome string value
    is_pre_gate: bool                # True if outcome came from pre-gate layer
    reason_codes: tuple[str, ...]

    lambda0_status: Lambda0Status
    epistemic_risk: float            # [0, 1]; higher = more uncertain

    tick_id: str
    session_id: str
    logical_step: int

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lambda0_status"] = self.lambda0_status.value
        return d


# --------------------------------------------------------------------------
# Trace record
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TraceRecord:
    """
    Immutable per-tick trace record.

    Captures everything needed to replay the tick deterministically:
    prior session state, the observation, the gate input, the outcome,
    and the next session state.

    Invariant I8: every session state update is caused by a logged gate
    outcome. The trace record is the carrier of that causal link.
    """
    tick_id: str
    session_id: str
    logical_step: int

    prior_session_state: SessionState
    bench_observation: BenchObservation
    field_state_at_gate: FieldState

    # Either a gate outcome or a pre-gate outcome, but not both.
    gate_outcome: Optional[str] = None         # GateOutcome.value if gate ran
    pre_gate_outcome: Optional[str] = None     # PreGateOutcome.value if short-circuited

    reason_codes: tuple[str, ...] = ()
    next_session_state: SessionState = None  # type: ignore
    accepted_delta: Optional[dict[str, float]] = None  # populated only on EXECUTE (terminal acceptance)

    # The transformation evaluated at this tick, serialized.
    # None when the tick short-circuited at a pre-gate layer (e.g. Lambda_0
    # SAFE_HOLD), because no transformation reached the gate. Required for
    # replay to re-run the gate: without it, replay can verify state sequences
    # but cannot re-evaluate the decision.
    transformation: Optional[dict] = None  # Transformation.to_dict() or None

    def __post_init__(self) -> None:
        if (self.gate_outcome is None) == (self.pre_gate_outcome is None):
            raise ValueError(
                "TraceRecord must have exactly one of gate_outcome or pre_gate_outcome"
            )
        if self.next_session_state is None:
            raise ValueError("TraceRecord.next_session_state is required")
        # If the gate ran (gate_outcome set), a transformation must be present
        # to support replay. If a pre-gate layer short-circuited, transformation
        # may be None (nothing reached the gate).
        if self.gate_outcome is not None and self.transformation is None:
            raise ValueError(
                "TraceRecord with a gate_outcome must carry the transformation "
                "that was evaluated (required for replay)"
            )

    def to_dict(self) -> dict:
        """Serialize for the append-only ledger. JSON-compatible."""
        return {
            "tick_id": self.tick_id,
            "session_id": self.session_id,
            "logical_step": self.logical_step,
            "prior_session_state": self.prior_session_state.to_dict(),
            "bench_observation": self.bench_observation.to_dict(),
            "field_state_at_gate": self.field_state_at_gate.to_dict(),
            "gate_outcome": self.gate_outcome,
            "pre_gate_outcome": self.pre_gate_outcome,
            "reason_codes": list(self.reason_codes),
            "next_session_state": self.next_session_state.to_dict(),
            "accepted_delta": self.accepted_delta,
            "transformation": self.transformation,
        }
