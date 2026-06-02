"""
Tests for components/lambda0.py.

Lambda_0 holds these invariants:
- Well-formed inputs pass (well_formed=True, proceed to gate).
- Non-finite values produce SAFE_HOLD.
- Session-continuity breaks produce SAFE_HOLD.
- SAFE_HOLD is a PreGateOutcome, structurally distinct from GateOutcome.REJECT.
- Lambda_0 never produces a gate outcome; it only short-circuits or passes.
"""
import math
import pytest

from runtime.core.types import FieldState, GateOutcome
from runtime.core.bench_interface import (
    BenchObservation,
    SessionState,
    PreGateOutcome,
)
from runtime.components.lambda0 import (
    Lambda0Config,
    Lambda0Result,
    evaluate_lambda0,
    check_field_state,
    check_bench_observation,
    check_session_continuity,
)


def _obs(Omega=0.5, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5,
         session_id="sess-1", tick_id="t1") -> BenchObservation:
    return BenchObservation(
        Omega=Omega, rho=rho, kappa=kappa, NSV=NSV, Energy=Energy,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=0,
    )


def _session(session_id="sess-1", tau=0.2, Theta=0.8) -> SessionState:
    return SessionState.initial(session_id=session_id, tau_0=tau, Theta_0=Theta)


class TestWellFormedInputsPass:
    """Well-formed observation + session => proceed to gate."""

    def test_clean_observation_is_well_formed(self):
        result = evaluate_lambda0(_obs(), _session())
        assert result.well_formed is True
        assert result.violations == ()

    def test_well_formed_result_yields_no_pregate_output(self):
        result = evaluate_lambda0(_obs(), _session())
        assert result.to_pre_gate_output() is None  # None => proceed

    def test_well_formed_with_field_state(self):
        fs = FieldState(Omega=0.5, rho=-2.0, kappa=3.0, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0)
        result = evaluate_lambda0(_obs(), _session(), field_state=fs)
        assert result.well_formed is True


class TestSessionContinuity:
    """A session-id mismatch is a well-formedness failure."""

    def test_session_mismatch_triggers_safe_hold(self):
        obs = _obs(session_id="sess-A")
        session = _session(session_id="sess-B")
        result = evaluate_lambda0(obs, session)
        assert result.well_formed is False
        assert any("session_continuity_break" in v for v in result.violations)

    def test_session_mismatch_yields_safe_hold_pregate_output(self):
        obs = _obs(session_id="sess-A")
        session = _session(session_id="sess-B")
        pgo = evaluate_lambda0(obs, session).to_pre_gate_output()
        assert pgo is not None
        assert pgo.outcome == PreGateOutcome.SAFE_HOLD
        assert pgo.layer == "lambda_0"

    def test_continuity_check_can_be_disabled(self):
        obs = _obs(session_id="sess-A")
        session = _session(session_id="sess-B")
        cfg = Lambda0Config(require_session_continuity=False)
        result = evaluate_lambda0(obs, session, config=cfg)
        # With continuity off, the only potential violation is gone
        assert result.well_formed is True


class TestNonFiniteValues:
    """Non-finite values in field state produce SAFE_HOLD."""

    def test_field_state_with_inf_rho_flagged(self):
        # FieldState constructor allows rho (signed, unbounded), so inf passes
        # construction. Lambda_0 must catch it.
        fs = FieldState(
            Omega=0.5, rho=math.inf, kappa=0.0, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0
        )
        violations = check_field_state(fs, Lambda0Config())
        assert any("rho_not_finite" in v for v in violations)

    def test_field_state_with_nan_kappa_flagged(self):
        fs = FieldState(
            Omega=0.5, rho=0.0, kappa=math.nan, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0
        )
        violations = check_field_state(fs, Lambda0Config())
        assert any("kappa_not_finite" in v for v in violations)

    def test_field_state_evaluated_through_lambda0(self):
        fs = FieldState(
            Omega=0.5, rho=math.inf, kappa=0.0, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0
        )
        result = evaluate_lambda0(_obs(), _session(), field_state=fs)
        assert result.well_formed is False
        pgo = result.to_pre_gate_output()
        assert pgo.outcome == PreGateOutcome.SAFE_HOLD


class TestMagnitudeEnvelope:
    """Signed quantities beyond the structural envelope are degenerate."""

    def test_rho_beyond_envelope_flagged(self):
        fs = FieldState(
            Omega=0.5, rho=5000.0, kappa=0.0, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0
        )
        violations = check_field_state(fs, Lambda0Config(max_signed_magnitude=1000.0))
        assert any("rho_magnitude_exceeds_envelope" in v for v in violations)

    def test_within_envelope_passes(self):
        fs = FieldState(
            Omega=0.5, rho=999.0, kappa=0.0, tau=0.2, Theta=0.8, NSV=0.1, logical_step=0
        )
        violations = check_field_state(fs, Lambda0Config(max_signed_magnitude=1000.0))
        assert not any("rho_magnitude" in v for v in violations)


class TestSafeHoldDistinctFromReject:
    """The constitutional distinction: SAFE_HOLD is not REJECT."""

    def test_safe_hold_is_pregate_not_gate_outcome(self):
        obs = _obs(session_id="sess-A")
        session = _session(session_id="sess-B")
        pgo = evaluate_lambda0(obs, session).to_pre_gate_output()
        # SAFE_HOLD is a PreGateOutcome
        assert isinstance(pgo.outcome, PreGateOutcome)
        # And its value is not any GateOutcome value
        gate_values = {o.value for o in GateOutcome}
        assert pgo.outcome.value not in gate_values

    def test_safe_hold_and_reject_have_different_values(self):
        assert PreGateOutcome.SAFE_HOLD.value != GateOutcome.REJECT.value
        assert PreGateOutcome.SAFE_HOLD.value == "SAFE_HOLD"
        assert GateOutcome.REJECT.value == "REJECT"


class TestBenchObservationChecks:
    """Bench observation finiteness checks."""

    def test_clean_observation_no_violations(self):
        violations = check_bench_observation(_obs(), Lambda0Config())
        assert violations == []

    def test_omega_raw_with_nan_flagged(self):
        obs = BenchObservation(
            Omega=0.5, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5,
            omega_raw=tuple([0.5] * 8 + [math.nan]),
            session_id="sess-1", tick_id="t1", timestamp_ms=0,
        )
        violations = check_bench_observation(obs, Lambda0Config())
        assert any("omega_raw[8]_not_finite" in v for v in violations)


class TestScopeDiscipline:
    """
    Lambda_0 is a structural check. It must not claim to verify physical
    calibration. This test documents that scope by confirming the check
    passes for a structurally-clean observation regardless of whether the
    underlying signal is physically calibrated (which Lambda_0 cannot know).
    """

    def test_structurally_clean_passes_regardless_of_physical_meaning(self):
        # An observation that is structurally fine but might be physically
        # meaningless (e.g. from an uncalibrated bench) still passes Lambda_0.
        # Lambda_0 does not and cannot check physical calibration.
        obs = _obs(Omega=0.5, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5)
        result = evaluate_lambda0(obs, _session())
        assert result.well_formed is True
