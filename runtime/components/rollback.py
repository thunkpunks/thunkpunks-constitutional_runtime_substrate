"""
Rollback / Recovery.

Constitutional role: the SINGLE sanctioned operation by which commitment depth
(tau) may decrease. Ordinary SessionState.advance forbids tau decrease — that
monotonicity is protected physics. Recovery is the one explicit, logged,
bounded exception.

This completes recoverability from GUARD (the gate refuses moves that would
lose renegotiability) to MECHANISM (the runtime can sanctionedly restore a
prior committed state).

DESIGN DECISIONS (made explicit):

1. Restore TO a recorded prior state, not BY an arbitrary amount.
   Provenance-clean: you recover to a checkpoint that actually existed in the
   trajectory, identified by its logical_step. You cannot invent a state to
   roll back to.

2. Bounded. The tau decrement may not exceed a sanctioned max_rollback_distance.
   A recovery beyond bound is refused (RecoveryRefused). Unbounded rollback
   would let the system erase arbitrary commitment, defeating the point of
   commitment tracking.

3. Logged. Every recovery produces a RecoveryRecord carrying from-state,
   to-state, reason, bound, and — critically — the irreversible residue that
   recovery does NOT erase.

4. NSV-HONEST. This is the constitutional crux. Recovery restores tau
   (commitment depth) and Theta (renegotiability). It does NOT restore NSV.
   NSV is irrecoverable residue by definition. Rolling back commitment does
   not un-spend what was irreversibly lost. A recovery that reset NSV would be
   lying about the cost already paid. So the recovered state carries the
   CURRENT NSV, never the checkpoint's lower NSV.

   Consequence: you can recover to a prior tau/Theta, but the NSV you accrued
   getting there and back stays on the books. Recovery is not time travel; it
   is a sanctioned, accounted retreat.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..core.bench_interface import SessionState


COMPONENT_VERSION = "0.1.0"


class RecoveryRefused(Exception):
    """Raised when a recovery would exceed its sanctioned bound or is otherwise invalid."""


@dataclass(frozen=True)
class RecoveryRecord:
    """
    Provenance record for a single recovery operation.

    Carries everything needed to audit and replay the recovery:
    - the state we recovered FROM (current, higher tau)
    - the state we recovered TO (a recorded checkpoint, lower tau)
    - the resulting state actually produced (checkpoint tau/Theta, CURRENT NSV)
    - the bound that governed the operation
    - the reason
    - the irreversible residue that recovery did NOT erase
    """
    session_id: str
    reason: str
    from_tau: float
    from_Theta: float
    from_NSV: float
    checkpoint_logical_step: int
    checkpoint_tau: float
    checkpoint_Theta: float
    resulting_tau: float
    resulting_Theta: float
    resulting_NSV: float
    rollback_distance: float          # from_tau - checkpoint_tau
    max_rollback_distance: float
    irreversible_residue_retained: float  # NSV not erased by recovery

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "reason": self.reason,
            "from_tau": self.from_tau,
            "from_Theta": self.from_Theta,
            "from_NSV": self.from_NSV,
            "checkpoint_logical_step": self.checkpoint_logical_step,
            "checkpoint_tau": self.checkpoint_tau,
            "checkpoint_Theta": self.checkpoint_Theta,
            "resulting_tau": self.resulting_tau,
            "resulting_Theta": self.resulting_Theta,
            "resulting_NSV": self.resulting_NSV,
            "rollback_distance": self.rollback_distance,
            "max_rollback_distance": self.max_rollback_distance,
            "irreversible_residue_retained": self.irreversible_residue_retained,
        }


@dataclass(frozen=True)
class RecoveryResult:
    """The new session state after recovery, plus the provenance record."""
    recovered_session: SessionState
    record: RecoveryRecord


def recover_to_checkpoint(
    current: SessionState,
    checkpoint: SessionState,
    current_NSV: float,
    reason: str,
    max_rollback_distance: float,
    recovery_tick_id: str,
    recovery_logical_step: int,
) -> RecoveryResult:
    """
    Recover the session to a recorded checkpoint state.

    Args:
        current: the session state we are recovering FROM (higher tau).
        checkpoint: a recorded prior SessionState to recover TO (lower tau).
        current_NSV: the current irreversible residue. This is RETAINED — the
            recovered state carries this NSV, NOT the checkpoint's. Recovery
            does not un-spend irreversible residue.
        reason: why recovery is being performed (logged).
        max_rollback_distance: the sanctioned bound on tau decrement.
        recovery_tick_id, recovery_logical_step: identify the recovery event
            in the trajectory.

    Returns:
        RecoveryResult with the recovered SessionState and a RecoveryRecord.

    Raises:
        RecoveryRefused if:
        - the checkpoint belongs to a different session,
        - the checkpoint tau is not below current tau (nothing to recover),
        - the rollback distance exceeds max_rollback_distance.
    """
    if checkpoint.session_id != current.session_id:
        raise RecoveryRefused(
            f"checkpoint session {checkpoint.session_id} != current session "
            f"{current.session_id}; cannot recover across sessions"
        )

    rollback_distance = current.tau - checkpoint.tau

    if rollback_distance < 0:
        raise RecoveryRefused(
            f"checkpoint tau {checkpoint.tau} is ABOVE current tau {current.tau}; "
            f"recovery only decreases commitment depth, it does not advance it"
        )
    if rollback_distance == 0:
        raise RecoveryRefused(
            f"checkpoint tau equals current tau ({current.tau}); nothing to recover"
        )
    if rollback_distance > max_rollback_distance:
        raise RecoveryRefused(
            f"rollback distance {rollback_distance:.4f} exceeds sanctioned bound "
            f"{max_rollback_distance:.4f}; recovery refused. A recovery this large "
            f"would erase more commitment than the bound permits."
        )

    # Build the recovered state.
    # tau and Theta come from the checkpoint (recoverable quantities).
    # NSV is the CURRENT NSV (irrecoverable; recovery does not un-spend it).
    #
    # We construct directly rather than via advance() because advance() forbids
    # tau decrease — recovery is the sanctioned exception, and it lives HERE,
    # not by relaxing advance(). The protected monotonicity in advance() stays
    # intact: ordinary advancement can never decrease tau; only this explicit,
    # bounded, logged operation can.
    recovered = SessionState(
        session_id=current.session_id,
        tau=checkpoint.tau,
        Theta=checkpoint.Theta,
        last_tick_id=recovery_tick_id,
        last_logical_step=recovery_logical_step,
        renegotiation_count=current.renegotiation_count,  # recoveries do not reset this
    )

    record = RecoveryRecord(
        session_id=current.session_id,
        reason=reason,
        from_tau=current.tau,
        from_Theta=current.Theta,
        from_NSV=current_NSV,
        checkpoint_logical_step=checkpoint.last_logical_step,
        checkpoint_tau=checkpoint.tau,
        checkpoint_Theta=checkpoint.Theta,
        resulting_tau=recovered.tau,
        resulting_Theta=recovered.Theta,
        resulting_NSV=current_NSV,  # retained, not reset
        rollback_distance=rollback_distance,
        max_rollback_distance=max_rollback_distance,
        irreversible_residue_retained=current_NSV,
    )

    return RecoveryResult(recovered_session=recovered, record=record)


def rollback_distance_between(current: SessionState, checkpoint: SessionState) -> float:
    """
    Compute the rollback distance (tau decrement) to a checkpoint, without
    performing the recovery. Useful for recoverability estimation:
    "how far back is the nearest admissible checkpoint, and is it within bound?"

    Returns the tau decrement (may be negative if checkpoint is ahead).
    """
    return current.tau - checkpoint.tau
