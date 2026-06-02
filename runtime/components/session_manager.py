"""
SessionStateManager.

Constitutional role: bridges stateless bench observation and stateless gate
predicate evaluation by maintaining (tau, Theta) across evaluations.

What this module does:
- Projects BenchObservation + SessionState into a FieldState (plus Energy
  returned separately).
- Advances SessionState only on terminal accepting outcomes (EXECUTE).
- Passes SessionState through unchanged on non-accepting outcomes
  (TRANSFORM, DEFER, REJECT, SAFE_HOLD, FAST_PRUNED).
- Builds RuntimeAnalytics for downstream display.

What this module does NOT do:
- Evaluate admissibility (that is the gate's job).
- Run Lambda_0 checks (separate component, future).
- Run Pi_fast (separate component, future).
- Decide acceptance based on outcome strings directly (the acceptance
  predicate is centralized at the call site via is_accepting()).

Constitutional invariants:
- Energy is NEVER added to FieldState (kept separate, returned alongside).
- TRANSFORM is non-terminal: only EXECUTE advances the session accumulator.
- Every accumulator update is causally linked to a logged gate outcome
  via TraceRecord (built by the caller).
- The module is function-based; no class-heavy orchestrator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.types import FieldState, GateOutcome
from ..core.bench_interface import (
    BenchObservation,
    SessionState,
    RuntimeAnalytics,
    Lambda0Status,
    PreGateOutcome,
    PreGateOutput,
)


COMPONENT_VERSION = "0.2.0"


# --------------------------------------------------------------------------
# Acceptance predicate
# --------------------------------------------------------------------------

# CONSTITUTIONAL: only EXECUTE is terminal-accepting.
#
# TRANSFORM is non-terminal — it indicates the original transformation
# violated thresholds in a reshape-eligible way. The reshape operator
# proposes a T', which is re-evaluated. The session advances when (and
# only when) the reshape loop produces a terminal EXECUTE on a reshaped
# T'. If reshape exhausts, the final outcome becomes DEFER and the
# session does not advance for that tick.
#
# Including TRANSFORM here would commit the session to a state the gate
# flagged as violating thresholds. That is the bug consolidated out.
ACCEPTING_OUTCOMES: frozenset[str] = frozenset({
    GateOutcome.EXECUTE.value,
})


def is_accepting(outcome: str) -> bool:
    """True iff this outcome should advance the session accumulator.

    Only EXECUTE qualifies. TRANSFORM, DEFER, REJECT, SAFE_HOLD, and
    FAST_PRUNED do not advance the session.
    """
    return outcome in ACCEPTING_OUTCOMES


# --------------------------------------------------------------------------
# Projection: BenchObservation + SessionState -> (FieldState, Energy)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Projection:
    """
    The projection result.

    field_state is the 6D FieldState used by the gate. tau and Theta come
    from SessionState, NOT from the observation. The other four come from
    the observation.

    energy is returned separately. It is NOT a FieldState dimension.
    It feeds Pi_fast (when that layer is built) and is recorded in
    RuntimeAnalytics and TraceRecord.
    """
    field_state: FieldState
    energy: float


def project_to_field_state(
    obs: BenchObservation,
    session: SessionState,
    logical_step: int,
) -> Projection:
    """
    Project a BenchObservation + SessionState into runtime inputs.

    Pure function. Two observations differing only by Energy produce
    identical FieldStates. (Stress test T1 from the pronouncement.)

    Raises ValueError if obs and session disagree on session_id.
    """
    if obs.session_id != session.session_id:
        raise ValueError(
            f"Session mismatch: observation says '{obs.session_id}', "
            f"session state says '{session.session_id}'. The session "
            f"continuity contract is violated."
        )

    field_state = FieldState(
        Omega=obs.Omega,
        rho=obs.rho,
        kappa=obs.kappa,
        tau=session.tau,
        Theta=session.Theta,
        NSV=obs.NSV,
        logical_step=logical_step,
    )
    return Projection(field_state=field_state, energy=obs.Energy)


# --------------------------------------------------------------------------
# Session advancement
# --------------------------------------------------------------------------

def advance_session_on_accepted(
    session: SessionState,
    accepted_state: FieldState,
    tick_id: str,
    logical_step: int,
    is_renegotiation: bool = False,
) -> SessionState:
    """
    Advance the session accumulator after a terminal accepting outcome.

    The accepted_state is the FieldState the gate approved (the predicted
    S(t+1) that resulted in EXECUTE). Its tau and Theta become the new
    session accumulator values.

    This function does NOT check the outcome internally. The caller is
    responsible for invoking this only when is_accepting(outcome) is True.
    The acceptance predicate is centralized at ACCEPTING_OUTCOMES.

    Enforces tau monotonicity (via SessionState.advance).
    """
    return session.advance(
        new_tau=accepted_state.tau,
        new_Theta=accepted_state.Theta,
        tick_id=tick_id,
        logical_step=logical_step,
        is_renegotiation=is_renegotiation,
    )


def passthrough_session_on_unaccepted(
    session: SessionState,
    tick_id: str,
    logical_step: int,
) -> SessionState:
    """
    Pass session state through unchanged after a non-accepting outcome.

    Called when the outcome is TRANSFORM, DEFER, REJECT, SAFE_HOLD, or
    FAST_PRUNED. tau, Theta, and renegotiation_count do not advance.
    last_tick_id and last_logical_step update so the trace records that
    this tick occurred.
    """
    return session.passthrough(tick_id=tick_id, logical_step=logical_step)


# --------------------------------------------------------------------------
# Runtime analytics construction
# --------------------------------------------------------------------------

def build_analytics(
    obs: BenchObservation,
    session_after: SessionState,
    outcome_str: str,
    *,
    is_pre_gate: bool,
    reason_codes: tuple[str, ...],
    logical_step: int,
    lambda0_status: Lambda0Status = Lambda0Status.UNCHECKED,
    epistemic_risk: float = 0.5,
) -> RuntimeAnalytics:
    """
    Construct the RuntimeAnalytics output for this tick.

    The analytics reflect session state AFTER the gate decision and
    accumulator update (or passthrough). That is, what the system looks
    like having just processed this tick.

    `outcome_str` may be a GateOutcome value or a PreGateOutcome value.
    `is_pre_gate` distinguishes them so downstream consumers can apply
    the correct semantics (e.g., FAST_PRUNED is not GATE_REJECTED).
    """
    return RuntimeAnalytics(
        Omega=obs.Omega,
        rho=obs.rho,
        kappa=obs.kappa,
        tau=session_after.tau,
        Theta=session_after.Theta,
        NSV=obs.NSV,
        Energy=obs.Energy,
        gate_outcome_str=outcome_str,
        is_pre_gate=is_pre_gate,
        reason_codes=reason_codes,
        lambda0_status=lambda0_status,
        epistemic_risk=epistemic_risk,
        tick_id=obs.tick_id,
        session_id=obs.session_id,
        logical_step=logical_step,
    )
