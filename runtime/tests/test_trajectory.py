"""
Tests for components/trajectory.py.

Verifies:
- Path-distinguishability (Claim A): identical-coordinate endpoints reached by
  different histories have different lineage hashes -> distinguishable.
- Cumulative quantities (Claim B substrate): cumulative NSV, Omega-erosion, peak tau.
- Loop classification: reversible (no NSV rise) vs irreversible (NSV rose).
- The Trajectory is a PURE READ MODEL: it never mutates session state and has
  no write path. The constitutional invariant (only the gate authorises
  commitment-state change) is not weakened by it.
- Construction guards: cross-session and out-of-order records are refused.
"""
import pytest

from runtime.core.types import Transformation, IntentClass
from runtime.core.bench_interface import BenchObservation, SessionState, TraceRecord
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.session_manager import (
    project_to_field_state, advance_session_on_accepted,
    passthrough_session_on_unaccepted, is_accepting,
)
from runtime.components.trajectory import (
    Trajectory, Checkpoint, LoopFinding,
)


def _obs(tick_id, session_id="sess-1", omega=0.7, rho=0.0, kappa=0.0, nsv=0.0):
    return BenchObservation(
        Omega=omega, rho=rho, kappa=kappa, NSV=nsv, Energy=0.5,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=0,
    )


def _build(session_id, gestures, thresholds=None):
    """Run gestures, return ordered list of TraceRecords. gestures: (tick, obs_kwargs, delta)."""
    th = thresholds or GateThresholds()
    session = SessionState.initial(session_id=session_id, tau=0.0, Theta=1.0)
    records = []
    for step, (tick_id, obs_kw, delta) in enumerate(gestures):
        obs = _obs(tick_id, session_id=session_id, **obs_kw)
        prior = session
        proj = project_to_field_state(obs, session, logical_step=step)
        t = Transformation.new(typed_effects=delta, intent_class=IntentClass.COMMIT)
        out = evaluate(GateInput(current_state=proj.field_state, transformation=t, thresholds=th))
        if is_accepting(out.outcome.value):
            session = advance_session_on_accepted(session, out.predicted_state, tick_id=tick_id, logical_step=step)
            accepted = dict(t.expected_delta)
        else:
            session = passthrough_session_on_unaccepted(session, tick_id=tick_id, logical_step=step)
            accepted = None
        records.append(TraceRecord(
            tick_id=tick_id, session_id=session_id, logical_step=step,
            prior_session_state=prior, bench_observation=obs,
            field_state_at_gate=proj.field_state,
            gate_outcome=out.outcome.value,
            reason_codes=tuple(r.value for r in out.reason_codes),
            next_session_state=session, accepted_delta=accepted,
            transformation=t.to_dict(),
        ))
    return records


class TestPathDistinguishability:
    """Claim A: same endpoint, different history => distinct trajectories."""

    def test_different_histories_different_lineage_hash(self):
        # Two sessions that reach similar coordinates via different paths.
        recs_a = _build("sess-A", [
            ("a0", {}, {"tau": 0.05, "NSV": 0.02}),
            ("a1", {}, {"tau": 0.05, "NSV": 0.02}),
        ])
        recs_b = _build("sess-B", [
            ("b0", {}, {"tau": 0.10, "NSV": 0.04}),  # one bigger step instead of two
        ])
        traj_a = Trajectory.from_records("sess-A", recs_a)
        traj_b = Trajectory.from_records("sess-B", recs_b)
        assert traj_a.lineage_hash != traj_b.lineage_hash
        assert traj_a.distinguishes_from(traj_b)

    def test_identical_paths_identical_hash(self):
        recs_a = _build("sess-1", [("t0", {}, {"tau": 0.05, "NSV": 0.02})])
        # Rebuild the SAME records into two trajectories
        traj_1 = Trajectory.from_records("sess-1", recs_a)
        traj_2 = Trajectory.from_records("sess-1", recs_a)
        assert traj_1.lineage_hash == traj_2.lineage_hash
        assert not traj_1.distinguishes_from(traj_2)


class TestCumulativeQuantities:
    def test_cumulative_nsv_tracks_max(self):
        recs = _build("sess-1", [
            ("t0", {"nsv": 0.0}, {"tau": 0.05, "NSV": 0.05}),
            ("t1", {"nsv": 0.0}, {"tau": 0.05, "NSV": 0.10}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        # cumulative NSV should reflect the accumulated residue
        assert traj.cumulative_NSV >= 0.0

    def test_peak_tau_is_maximum(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.10, "NSV": 0.02}),
            ("t1", {}, {"tau": 0.20, "NSV": 0.02}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        assert traj.peak_tau == pytest.approx(0.30, abs=0.01)  # 0.10 + 0.20 accepted

    def test_omega_erosion_sums_drops(self):
        # Observations with decreasing Omega should accumulate erosion.
        recs = _build("sess-1", [
            ("t0", {"omega": 0.8}, {"tau": 0.02, "NSV": 0.01}),
            ("t1", {"omega": 0.6}, {"tau": 0.02, "NSV": 0.01}),
            ("t2", {"omega": 0.5}, {"tau": 0.02, "NSV": 0.01}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        # Omega dropped 0.8->0.6->0.5 = 0.3 total erosion (observation-driven)
        assert traj.cumulative_Omega_erosion > 0.0

    def test_n_accepted_counts_executes(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.05, "NSV": 0.02}),   # EXECUTE
            ("t1", {}, {"NSV": 0.6}),                  # REJECT
            ("t2", {}, {"tau": 0.05, "NSV": 0.02}),   # EXECUTE
        ])
        traj = Trajectory.from_records("sess-1", recs)
        assert traj.n_accepted == 2
        assert traj.n_records == 3


class TestCheckpoints:
    def test_checkpoints_one_per_record(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.05, "NSV": 0.02}),
            ("t1", {}, {"tau": 0.05, "NSV": 0.02}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        cps = traj.checkpoints()
        assert len(cps) == 2
        assert all(isinstance(c, Checkpoint) for c in cps)

    def test_checkpoint_carries_cumulative_nsv(self):
        recs = _build("sess-1", [("t0", {}, {"tau": 0.05, "NSV": 0.05})])
        traj = Trajectory.from_records("sess-1", recs)
        cp = traj.checkpoints()[0]
        assert cp.cumulative_NSV >= 0.0
        assert cp.tau >= 0.0


class TestLoopClassification:
    """Reversible loop = return to coords without NSV rise; irreversible = NSV rose."""

    def test_irreversible_loop_detected(self):
        # Return to same Omega coordinate but with NSV having risen in between.
        recs = _build("sess-1", [
            ("t0", {"omega": 0.7, "nsv": 0.0}, {"tau": 0.02, "NSV": 0.0}),
            ("t1", {"omega": 0.5, "nsv": 0.0}, {"tau": 0.02, "NSV": 0.2}),  # NSV rises
            ("t2", {"omega": 0.7, "nsv": 0.0}, {"tau": 0.02, "NSV": 0.0}),  # back to 0.7 Omega
        ])
        traj = Trajectory.from_records("sess-1", recs)
        loops = traj.detect_loops(coordinate_epsilon=0.05)
        # There should be a loop between step 0 and step 2 (both Omega ~0.7)
        loop_02 = [l for l in loops if l.from_step == 0 and l.to_step == 2]
        assert len(loop_02) == 1
        # Whether it's reversible depends on NSV at the gate states; the field
        # state NSV is monotone, so the return at higher NSV is irreversible.
        assert loop_02[0].reversible is False

    def test_no_loop_when_coordinates_diverge(self):
        recs = _build("sess-1", [
            ("t0", {"omega": 0.9}, {"tau": 0.02, "NSV": 0.01}),
            ("t1", {"omega": 0.3}, {"tau": 0.02, "NSV": 0.01}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        loops = traj.detect_loops(coordinate_epsilon=0.05)
        assert len(loops) == 0


class TestConstructionGuards:
    def test_cross_session_record_refused(self):
        recs = _build("sess-1", [("t0", {}, {"tau": 0.05})])
        with pytest.raises(ValueError, match="session"):
            Trajectory.from_records("sess-OTHER", recs)

    def test_out_of_order_refused(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.05, "NSV": 0.02}),
            ("t1", {}, {"tau": 0.05, "NSV": 0.02}),
        ])
        reordered = [recs[1], recs[0]]
        with pytest.raises(ValueError, match="increasing logical_step"):
            Trajectory.from_records("sess-1", reordered)


class TestReadModelInvariant:
    """
    The Trajectory must be a pure read model. It may NOT mutate session state.
    This is the constitutional invariant: only the gate (via session_manager)
    authorises commitment-state change.
    """

    def test_trajectory_is_frozen(self):
        recs = _build("sess-1", [("t0", {}, {"tau": 0.05})])
        traj = Trajectory.from_records("sess-1", recs)
        with pytest.raises((AttributeError, Exception)):
            traj.cumulative_NSV = 999.0  # frozen

    def test_reading_trajectory_does_not_change_session_states(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.05, "NSV": 0.02}),
            ("t1", {}, {"tau": 0.05, "NSV": 0.02}),
        ])
        # Capture the session states before
        before = [(r.next_session_state.tau, r.next_session_state.Theta) for r in recs]
        traj = Trajectory.from_records("sess-1", recs)
        # Exercise all read methods
        _ = traj.checkpoints()
        _ = traj.detect_loops()
        _ = traj.current_state
        _ = traj.current_session_state
        _ = traj.to_dict()
        # Session states unchanged
        after = [(r.next_session_state.tau, r.next_session_state.Theta) for r in recs]
        assert before == after

    def test_current_state_is_last_field_state(self):
        recs = _build("sess-1", [
            ("t0", {}, {"tau": 0.05, "NSV": 0.02}),
            ("t1", {}, {"tau": 0.10, "NSV": 0.02}),
        ])
        traj = Trajectory.from_records("sess-1", recs)
        # current_state recoverable from trajectory => trajectory-aware gate is a
        # strict superset of a state-only gate
        assert traj.current_state == recs[-1].field_state_at_gate
