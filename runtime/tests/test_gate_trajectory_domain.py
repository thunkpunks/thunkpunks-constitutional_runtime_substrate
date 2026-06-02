"""
Tests for T2: widening the gate's domain to admit the trajectory.

T2 is an ONTOLOGICAL change, not a behavioural one. It must hold:
- The gate's verdict is IDENTICAL whether or not a trajectory is supplied
  (the gate's domain now includes history, but the gate still ignores it).
- A supplied trajectory that does NOT lead to current_state is rejected as
  incoherent.
- The no-trajectory path (the default) is completely untouched.

This proves the domain was widened without changing behaviour — the structural
commitment that lets history become constitutive later (K3) through a field
that already exists, rather than a signature change.
"""
import pytest

from runtime.core.types import Transformation, IntentClass, FieldState
from runtime.core.bench_interface import BenchObservation, SessionState, TraceRecord
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.session_manager import (
    project_to_field_state, advance_session_on_accepted,
    passthrough_session_on_unaccepted, is_accepting,
)
from runtime.components.trajectory import Trajectory


def _obs(tick_id, session_id="sess-1", omega=0.7, nsv=0.0):
    return BenchObservation(
        Omega=omega, rho=0.0, kappa=0.0, NSV=nsv, Energy=0.5,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=0,
    )


def _build_trajectory(session_id, gestures):
    """Run gestures, return (Trajectory, final_field_state, final_session)."""
    th = GateThresholds()
    session = SessionState.initial(session_id=session_id, tau=0.0, Theta=1.0)
    records = []
    last_proj = None
    for step, delta in enumerate(gestures):
        obs = _obs(f"t{step}", session_id=session_id, nsv=delta.get("NSV", 0.0))
        prior = session
        proj = project_to_field_state(obs, session, logical_step=step)
        last_proj = proj
        t = Transformation.new(typed_effects=delta, intent_class=IntentClass.COMMIT)
        out = evaluate(GateInput(current_state=proj.field_state, transformation=t, thresholds=th))
        if is_accepting(out.outcome.value):
            session = advance_session_on_accepted(session, out.predicted_state, tick_id=f"t{step}", logical_step=step)
            accepted = dict(t.expected_delta)
        else:
            session = passthrough_session_on_unaccepted(session, tick_id=f"t{step}", logical_step=step)
            accepted = None
        records.append(TraceRecord(
            tick_id=f"t{step}", session_id=session_id, logical_step=step,
            prior_session_state=prior, bench_observation=obs,
            field_state_at_gate=proj.field_state,
            gate_outcome=out.outcome.value,
            reason_codes=tuple(r.value for r in out.reason_codes),
            next_session_state=session, accepted_delta=accepted,
            transformation=t.to_dict(),
        ))
    traj = Trajectory.from_records(session_id, records)
    return traj, records[-1].field_state_at_gate


class TestVerdictUnchangedByTrajectory:
    """The gate's verdict must not depend on whether a trajectory is supplied."""

    def test_same_verdict_with_and_without_trajectory(self):
        traj, end_state = _build_trajectory("sess-1", [
            {"tau": 0.05, "NSV": 0.02},
            {"tau": 0.05, "NSV": 0.02},
        ])
        t = Transformation.new(typed_effects={"tau": 0.03, "NSV": 0.01})
        th = GateThresholds()

        without = evaluate(GateInput(current_state=end_state, transformation=t, thresholds=th))
        with_traj = evaluate(GateInput(current_state=end_state, transformation=t, thresholds=th, trajectory=traj))

        assert without.outcome == with_traj.outcome
        assert without.predicted_state == with_traj.predicted_state
        assert without.reason_codes == with_traj.reason_codes

    def test_reject_verdict_unchanged_by_trajectory(self):
        traj, end_state = _build_trajectory("sess-1", [{"tau": 0.05, "NSV": 0.02}])
        t = Transformation.new(typed_effects={"NSV": 0.6})  # catastrophic
        th = GateThresholds()
        without = evaluate(GateInput(current_state=end_state, transformation=t, thresholds=th))
        with_traj = evaluate(GateInput(current_state=end_state, transformation=t, thresholds=th, trajectory=traj))
        assert without.outcome == with_traj.outcome


class TestCoherenceCheck:
    """A supplied trajectory must lead to current_state."""

    def test_incoherent_trajectory_rejected(self):
        traj, end_state = _build_trajectory("sess-1", [{"tau": 0.05, "NSV": 0.02}])
        # Use a DIFFERENT current_state than the trajectory's endpoint
        wrong_state = FieldState(Omega=0.1, rho=5.0, kappa=5.0, tau=0.9, Theta=0.1, NSV=0.5, logical_step=99)
        t = Transformation.new(typed_effects={"tau": 0.01})
        with pytest.raises(ValueError, match="does not lead to current_state"):
            GateInput(current_state=wrong_state, transformation=t, thresholds=GateThresholds(), trajectory=traj)

    def test_coherent_trajectory_accepted(self):
        traj, end_state = _build_trajectory("sess-1", [{"tau": 0.05, "NSV": 0.02}])
        t = Transformation.new(typed_effects={"tau": 0.01})
        # end_state IS the trajectory endpoint -> coherent -> no raise
        gi = GateInput(current_state=end_state, transformation=t, thresholds=GateThresholds(), trajectory=traj)
        assert gi.trajectory is traj


class TestNoTrajectoryPathUntouched:
    def test_default_is_none(self):
        t = Transformation.new(typed_effects={"tau": 0.01})
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        gi = GateInput(current_state=s, transformation=t, thresholds=GateThresholds())
        assert gi.trajectory is None

    def test_no_trajectory_evaluates_normally(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome is not None
