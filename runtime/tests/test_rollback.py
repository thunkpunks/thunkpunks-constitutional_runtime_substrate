"""
Tests for components/rollback.py.

Verifies the recovery invariants:
- Recovery restores tau and Theta from a recorded checkpoint.
- Recovery is BOUNDED: distance beyond max is refused.
- Recovery is NSV-HONEST: it does NOT erase irreversible residue.
- Recovery is provenance-preserving: a RecoveryRecord captures from/to/retained.
- Ordinary advance() monotonicity is UNTOUCHED: tau still cannot decrease
  through the normal path; only recovery may decrease it.
- Cross-session recovery is refused.
"""
import pytest

from runtime.core.bench_interface import SessionState
from runtime.components.rollback import (
    recover_to_checkpoint,
    rollback_distance_between,
    RecoveryRefused,
    RecoveryResult,
    RecoveryRecord,
)


def _checkpoint(session_id="sess-1", tau=0.2, Theta=0.8, step=2):
    s = SessionState.initial(session_id=session_id, tau=tau, Theta=Theta)
    # set last_logical_step via a passthrough to simulate a recorded checkpoint
    return SessionState(
        session_id=session_id, tau=tau, Theta=Theta,
        last_tick_id=f"t{step}", last_logical_step=step, renegotiation_count=0,
    )


def _current(session_id="sess-1", tau=0.6, Theta=0.4, step=8):
    return SessionState(
        session_id=session_id, tau=tau, Theta=Theta,
        last_tick_id=f"t{step}", last_logical_step=step, renegotiation_count=1,
    )


class TestRecoveryRestoresCheckpoint:
    def test_recovered_tau_matches_checkpoint(self):
        cur = _current(tau=0.6)
        ckpt = _checkpoint(tau=0.2)
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.3, reason="test",
            max_rollback_distance=0.5,
            recovery_tick_id="recov", recovery_logical_step=9,
        )
        assert result.recovered_session.tau == 0.2
        assert result.recovered_session.Theta == 0.8

    def test_recovered_state_advances_logical_step(self):
        cur = _current(step=8)
        ckpt = _checkpoint(step=2)
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.3, reason="test",
            max_rollback_distance=0.5,
            recovery_tick_id="recov", recovery_logical_step=9,
        )
        # The recovery is itself an event at step 9
        assert result.recovered_session.last_logical_step == 9
        assert result.recovered_session.last_tick_id == "recov"


class TestNSVHonesty:
    """The constitutional crux: recovery does NOT erase irreversible residue."""

    def test_recovered_state_retains_current_nsv(self):
        cur = _current(tau=0.6)
        ckpt = _checkpoint(tau=0.2)
        # The checkpoint was at a time of lower NSV, but recovery must retain
        # the CURRENT (higher) NSV. We pass current_NSV explicitly.
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.45, reason="test",
            max_rollback_distance=0.5,
            recovery_tick_id="recov", recovery_logical_step=9,
        )
        assert result.record.resulting_NSV == 0.45
        assert result.record.irreversible_residue_retained == 0.45

    def test_recovery_record_documents_retained_residue(self):
        cur = _current()
        ckpt = _checkpoint()
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.5, reason="audit",
            max_rollback_distance=0.5,
            recovery_tick_id="r", recovery_logical_step=9,
        )
        # The record makes explicit that NSV was retained, not reset
        assert result.record.from_NSV == 0.5
        assert result.record.resulting_NSV == 0.5
        assert result.record.irreversible_residue_retained == 0.5


class TestBounding:
    def test_within_bound_succeeds(self):
        cur = _current(tau=0.6)
        ckpt = _checkpoint(tau=0.2)  # distance 0.4
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.1, reason="test",
            max_rollback_distance=0.5,
            recovery_tick_id="r", recovery_logical_step=9,
        )
        assert result.record.rollback_distance == pytest.approx(0.4)

    def test_beyond_bound_refused(self):
        cur = _current(tau=0.9)
        ckpt = _checkpoint(tau=0.2)  # distance 0.7 > bound 0.5
        with pytest.raises(RecoveryRefused, match="exceeds sanctioned bound"):
            recover_to_checkpoint(
                cur, ckpt, current_NSV=0.1, reason="test",
                max_rollback_distance=0.5,
                recovery_tick_id="r", recovery_logical_step=9,
            )

    def test_zero_distance_refused(self):
        cur = _current(tau=0.4)
        ckpt = _checkpoint(tau=0.4)  # nothing to recover
        with pytest.raises(RecoveryRefused, match="nothing to recover"):
            recover_to_checkpoint(
                cur, ckpt, current_NSV=0.1, reason="test",
                max_rollback_distance=0.5,
                recovery_tick_id="r", recovery_logical_step=9,
            )

    def test_checkpoint_ahead_refused(self):
        cur = _current(tau=0.3)
        ckpt = _checkpoint(tau=0.5)  # checkpoint is ahead of current
        with pytest.raises(RecoveryRefused, match="ABOVE current"):
            recover_to_checkpoint(
                cur, ckpt, current_NSV=0.1, reason="test",
                max_rollback_distance=0.5,
                recovery_tick_id="r", recovery_logical_step=9,
            )


class TestCrossSessionRefused:
    def test_different_session_refused(self):
        cur = _current(session_id="sess-A")
        ckpt = _checkpoint(session_id="sess-B")
        with pytest.raises(RecoveryRefused, match="cannot recover across sessions"):
            recover_to_checkpoint(
                cur, ckpt, current_NSV=0.1, reason="test",
                max_rollback_distance=0.9,
                recovery_tick_id="r", recovery_logical_step=9,
            )


class TestOrdinaryMonotonicityUntouched:
    """
    Recovery is the ONLY sanctioned tau decrease. Ordinary advance() still
    forbids decrease — the protected physics is intact.
    """

    def test_advance_still_forbids_tau_decrease(self):
        s = SessionState.initial(session_id="sess-1", tau=0.5, Theta=0.5)
        with pytest.raises(ValueError, match="monotonicity"):
            s.advance(new_tau=0.3, new_Theta=0.5, tick_id="t", logical_step=1)

    def test_recovery_does_not_use_advance(self):
        # Recovery produces a lower-tau state without raising — proving it
        # does NOT route through advance()'s monotonicity guard.
        cur = _current(tau=0.6)
        ckpt = _checkpoint(tau=0.2)
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.1, reason="test",
            max_rollback_distance=0.5,
            recovery_tick_id="r", recovery_logical_step=9,
        )
        assert result.recovered_session.tau < cur.tau  # decreased, no raise


class TestRollbackDistanceEstimation:
    def test_distance_computed_without_performing(self):
        cur = _current(tau=0.6)
        ckpt = _checkpoint(tau=0.2)
        d = rollback_distance_between(cur, ckpt)
        assert d == pytest.approx(0.4)


class TestRecoveryRecordSerialization:
    def test_record_serializes(self):
        import json
        cur = _current()
        ckpt = _checkpoint()
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.2, reason="test",
            max_rollback_distance=0.9,
            recovery_tick_id="r", recovery_logical_step=9,
        )
        json.dumps(result.record.to_dict())  # raises if not serializable
