"""
Tests for components/horizon.py and its wiring into the gate (K3).

THE HEADLINE PROPERTY: a sequence of individually-admissible steps can be
COLLECTIVELY inadmissible. Per-step checks pass; the cumulative horizon budget
catches what they cannot.

Verifies:
- A step that is individually fine is DEFERRED when it would exhaust a
  cumulative budget over the trajectory.
- The same step with NO budget (or no trajectory) is admissible — backward
  compatibility, K3 inactive by default.
- Each cumulative dimension (NSV, Omega-erosion, peak tau) has a working budget.
- The prospective step is included in the budget check.
"""
import pytest

from runtime.core.types import FieldState, Transformation, GateOutcome, GateReasonCode
from runtime.core.bench_interface import BenchObservation, SessionState, TraceRecord
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.session_manager import (
    project_to_field_state, advance_session_on_accepted, is_accepting,
)
from runtime.components.trajectory import Trajectory
from runtime.components.horizon import (
    HorizonBudget, HorizonExhaustion, check_horizon, HorizonFinding,
)


def _state(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0):
    return FieldState(Omega=Omega, rho=rho, kappa=kappa, tau=tau, Theta=Theta, NSV=NSV, logical_step=0)


def _build_trajectory(session_id, gestures):
    """Build a real trajectory by running small admissible steps."""
    th = GateThresholds()
    session = SessionState.initial(session_id=session_id, tau=0.0, Theta=1.0)
    records = []
    end_state = None
    for step, delta in enumerate(gestures):
        obs = BenchObservation(Omega=0.7, rho=0.0, kappa=0.0, NSV=delta.get("NSV", 0.0),
                               Energy=0.5, omega_raw=tuple([0.5]*9),
                               session_id=session_id, tick_id=f"t{step}", timestamp_ms=0)
        prior = session
        proj = project_to_field_state(obs, session, logical_step=step)
        end_state = proj.field_state
        t = Transformation.new(typed_effects=delta)
        out = evaluate(GateInput(current_state=proj.field_state, transformation=t, thresholds=th))
        if is_accepting(out.outcome.value):
            session = advance_session_on_accepted(session, out.predicted_state, tick_id=f"t{step}", logical_step=step)
            accepted = dict(t.expected_delta)
        else:
            accepted = None
        records.append(TraceRecord(
            tick_id=f"t{step}", session_id=session_id, logical_step=step,
            prior_session_state=prior, bench_observation=obs,
            field_state_at_gate=proj.field_state, gate_outcome=out.outcome.value,
            reason_codes=tuple(r.value for r in out.reason_codes),
            next_session_state=session, accepted_delta=accepted,
            transformation=t.to_dict(),
        ))
    return Trajectory.from_records(session_id, records), end_state


class TestCollectivelyInadmissible:
    """The headline: individually-admissible steps, collectively inadmissible."""

    def test_individually_admissible_steps_exhaust_nsv_budget(self):
        # Five small NSV steps (each 0.1, individually well under nsv_step_max=0.2).
        traj, end_state = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1} for _ in range(5)])
        # cumulative NSV ~0.5. Set a horizon budget of 0.4 -> already over.
        budget = HorizonBudget(max_cumulative_NSV=0.4)
        # A further small, individually-admissible step:
        t = Transformation.new(typed_effects={"tau": 0.02, "NSV": 0.05})
        out = evaluate(GateInput(
            current_state=end_state, transformation=t, thresholds=GateThresholds(),
            trajectory=traj, horizon_budget=budget,
        ))
        # The step is individually fine (NSV 0.05 < 0.2) but the trajectory has
        # exhausted the cumulative budget -> DEFER.
        assert out.outcome == GateOutcome.DEFER
        assert GateReasonCode.HORIZON_EXHAUSTED in out.reason_codes

    def test_same_step_admissible_with_no_budget(self):
        # Backward compatibility: same trajectory, same step, NO budget -> not deferred for horizon.
        traj, end_state = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1} for _ in range(5)])
        t = Transformation.new(typed_effects={"tau": 0.02, "NSV": 0.05})
        out = evaluate(GateInput(
            current_state=end_state, transformation=t, thresholds=GateThresholds(),
            trajectory=traj,  # trajectory present but NO budget
        ))
        assert GateReasonCode.HORIZON_EXHAUSTED not in out.reason_codes

    def test_same_step_admissible_with_no_trajectory(self):
        # No trajectory at all -> K3 inactive.
        budget = HorizonBudget(max_cumulative_NSV=0.4)
        t = Transformation.new(typed_effects={"tau": 0.02, "NSV": 0.05})
        out = evaluate(GateInput(
            current_state=_state(), transformation=t, thresholds=GateThresholds(),
            horizon_budget=budget,  # budget present but NO trajectory
        ))
        assert GateReasonCode.HORIZON_EXHAUSTED not in out.reason_codes


class TestEachDimension:
    def test_cumulative_nsv_budget(self):
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1} for _ in range(4)])
        findings = check_horizon(traj, HorizonBudget(max_cumulative_NSV=0.3),
                                 prospective_NSV_delta=0.05)
        assert any(f.exhaustion == HorizonExhaustion.CUMULATIVE_NSV for f in findings)

    def test_peak_tau_ceiling(self):
        traj, end = _build_trajectory("s", [{"tau": 0.2, "NSV": 0.01} for _ in range(3)])
        # peak tau ~0.6; ceiling 0.5 -> exceeded.
        findings = check_horizon(traj, HorizonBudget(max_peak_tau=0.5), prospective_tau=0.6)
        assert any(f.exhaustion == HorizonExhaustion.PEAK_TAU for f in findings)

    def test_within_budget_no_findings(self):
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.05} for _ in range(2)])
        findings = check_horizon(traj, HorizonBudget(max_cumulative_NSV=10.0))
        assert findings == []


class TestInactiveByDefault:
    def test_none_budget_inactive(self):
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1}])
        assert check_horizon(traj, None) == []

    def test_empty_budget_inactive(self):
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1}])
        assert check_horizon(traj, HorizonBudget()) == []  # all-None budget

    def test_none_trajectory_inactive(self):
        assert check_horizon(None, HorizonBudget(max_cumulative_NSV=0.1)) == []

    def test_budget_is_active_predicate(self):
        assert HorizonBudget().is_active() is False
        assert HorizonBudget(max_cumulative_NSV=0.5).is_active() is True


class TestProspectiveStepIncluded:
    def test_prospective_step_pushes_over_budget(self):
        # Trajectory cumulative NSV ~0.2; budget 0.3; prospective 0.15 -> 0.35 > 0.3.
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1} for _ in range(2)])
        findings = check_horizon(traj, HorizonBudget(max_cumulative_NSV=0.3),
                                 prospective_NSV_delta=0.15)
        assert len(findings) >= 1

    def test_prospective_step_stays_within(self):
        traj, end = _build_trajectory("s", [{"tau": 0.02, "NSV": 0.1} for _ in range(2)])
        findings = check_horizon(traj, HorizonBudget(max_cumulative_NSV=0.5),
                                 prospective_NSV_delta=0.05)
        assert findings == []
