"""
Lambda_0: structural well-formedness check.

Constitutional role: guards the algebraic gate from being asked
algebraically-meaningless questions. Runs BEFORE the gate.

The distinction Lambda_0 enforces:
  - Gate REJECT  = "the algebra evaluated this move and it is inadmissible"
  - Lambda_0 SAFE_HOLD = "the algebra cannot meaningfully run on this input"

These are different mathematical events. A well-formedness failure is not an
admissibility verdict. Conflating them would corrupt downstream falsifiability:
a SAFE_HOLD logged as REJECT would inflate the apparent inadmissibility rate
with cases that were never actually evaluated.

SCOPE NOTE — what this Lambda_0 is NOT:
  This is a STRUCTURAL well-formedness check. It verifies internal consistency
  of field state, session state, and bench observation — that values are finite,
  within declared domains, and mutually consistent. It does NOT verify physical
  calibration, sampling fidelity, or sensor topology. Those are bench-side
  physics-floor concerns and remain explicitly unverified (the bench spec's
  L2/L4/L5 caveats). This component must not be read as certifying physical
  validity. It certifies only that the runtime's own data structures are
  well-formed enough for the gate to evaluate.

Outcome:
  Lambda_0 emits a PreGateOutput with PreGateOutcome.SAFE_HOLD on violation,
  or None when the input is well-formed (meaning: proceed to the gate).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ..core.types import FieldState
from ..core.bench_interface import (
    BenchObservation,
    SessionState,
    PreGateOutcome,
    PreGateOutput,
)


COMPONENT_VERSION = "0.1.0"
LAYER_NAME = "lambda_0"


@dataclass(frozen=True)
class Lambda0Config:
    """
    Configuration for the structural well-formedness check.

    These are not admissibility thresholds. They are structural sanity bounds —
    the outer envelope within which the runtime's data structures are considered
    well-formed at all. Perturbing them is meaningful only for testing the
    well-formedness boundary itself, not for tuning admissibility.
    """
    # The largest magnitude rho or kappa may take before we consider the field
    # state structurally degenerate (not inadmissible — degenerate, i.e. the
    # signed quantities have blown up beyond any plausible operating range).
    max_signed_magnitude: float = 1000.0
    # Whether to require that bench observation and session agree on session_id.
    require_session_continuity: bool = True


@dataclass(frozen=True)
class Lambda0Result:
    """
    Result of a Lambda_0 check.

    `well_formed` True means: proceed to the gate.
    `well_formed` False means: SAFE_HOLD; the gate must not run for this tick.
    `violations` lists the specific structural failures found.
    """
    well_formed: bool
    violations: tuple[str, ...]

    def to_pre_gate_output(self) -> Optional[PreGateOutput]:
        """
        Convert to a PreGateOutput if not well-formed, else None.

        None signals "proceed to gate." A PreGateOutput with SAFE_HOLD
        signals "short-circuit; do not run the gate."
        """
        if self.well_formed:
            return None
        return PreGateOutput(
            outcome=PreGateOutcome.SAFE_HOLD,
            layer=LAYER_NAME,
            reason="; ".join(self.violations) if self.violations else "structural well-formedness failure",
            triggered_thresholds=self.violations,
        )


def _is_finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


def check_field_state(fs: FieldState, config: Lambda0Config) -> list[str]:
    """
    Structural checks on a FieldState.

    Note: FieldState.__post_init__ already enforces bounds at construction,
    so a constructed FieldState is guaranteed in-bounds. These checks are a
    defense-in-depth layer for field states that may arrive via deserialization
    (where __post_init__ bounds hold but finiteness of signed quantities, which
    are unbounded, is not guaranteed) or future code paths that bypass the
    constructor.
    """
    violations: list[str] = []

    # Finiteness of all six dimensions plus logical_step.
    for name, value in [
        ("Omega", fs.Omega), ("rho", fs.rho), ("kappa", fs.kappa),
        ("tau", fs.tau), ("Theta", fs.Theta), ("NSV", fs.NSV),
    ]:
        if not _is_finite(value):
            violations.append(f"field_state.{name}_not_finite")

    # Signed quantities (rho, kappa) within structural magnitude envelope.
    if _is_finite(fs.rho) and abs(fs.rho) > config.max_signed_magnitude:
        violations.append(
            f"field_state.rho_magnitude_exceeds_envelope({abs(fs.rho):.1f}>{config.max_signed_magnitude})"
        )
    if _is_finite(fs.kappa) and abs(fs.kappa) > config.max_signed_magnitude:
        violations.append(
            f"field_state.kappa_magnitude_exceeds_envelope({abs(fs.kappa):.1f}>{config.max_signed_magnitude})"
        )

    return violations


def check_bench_observation(obs: BenchObservation, config: Lambda0Config) -> list[str]:
    """
    Structural checks on a BenchObservation.

    BenchObservation.__post_init__ enforces bounds at construction. These checks
    cover finiteness of signed quantities and Energy, which are not fully
    bounded by the constructor.
    """
    violations: list[str] = []

    for name, value in [
        ("Omega", obs.Omega), ("rho", obs.rho), ("kappa", obs.kappa),
        ("NSV", obs.NSV), ("Energy", obs.Energy),
    ]:
        if not _is_finite(value):
            violations.append(f"bench_observation.{name}_not_finite")

    for i, v in enumerate(obs.omega_raw):
        if not _is_finite(v):
            violations.append(f"bench_observation.omega_raw[{i}]_not_finite")

    if _is_finite(obs.rho) and abs(obs.rho) > config.max_signed_magnitude:
        violations.append("bench_observation.rho_magnitude_exceeds_envelope")
    if _is_finite(obs.kappa) and abs(obs.kappa) > config.max_signed_magnitude:
        violations.append("bench_observation.kappa_magnitude_exceeds_envelope")

    return violations


def check_session_continuity(
    obs: BenchObservation,
    session: SessionState,
    config: Lambda0Config,
) -> list[str]:
    """
    Check that the observation and session agree on session_id.

    A session-continuity break means the runtime is about to project an
    observation from one session against the accumulator of another. The
    resulting field state would be a category error: tau and Theta from one
    trajectory, Omega/rho/kappa/NSV from a different one. The gate could
    evaluate it and produce a confident verdict about a state that never
    coherently existed. That is exactly the kind of meaningless question
    Lambda_0 must catch.
    """
    violations: list[str] = []
    if config.require_session_continuity and obs.session_id != session.session_id:
        violations.append(
            f"session_continuity_break(obs={obs.session_id},session={session.session_id})"
        )
    return violations


def evaluate_lambda0(
    obs: BenchObservation,
    session: SessionState,
    field_state: Optional[FieldState] = None,
    config: Optional[Lambda0Config] = None,
) -> Lambda0Result:
    """
    Run the full Lambda_0 structural well-formedness check.

    Args:
        obs: the bench observation entering the runtime.
        session: the current session accumulator.
        field_state: optionally, the already-projected field state. If provided,
            it is checked too. If None, only obs and session are checked (the
            field state will be projected after Lambda_0 passes).
        config: structural sanity bounds; defaults applied if None.

    Returns:
        Lambda0Result. well_formed True -> proceed to projection/gate.
        well_formed False -> SAFE_HOLD.
    """
    cfg = config or Lambda0Config()
    violations: list[str] = []

    violations.extend(check_bench_observation(obs, cfg))
    violations.extend(check_session_continuity(obs, session, cfg))
    if field_state is not None:
        violations.extend(check_field_state(field_state, cfg))

    return Lambda0Result(
        well_formed=(len(violations) == 0),
        violations=tuple(violations),
    )
