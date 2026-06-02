"""
Trajectory object.

Constitutional role: makes traversal history a FIRST-CLASS runtime object,
so admissibility can become path-conditioned rather than state-only.

This is a TYPED VIEW over an ordered slice of the trace ledger. It introduces
NO new instrumentation — every quantity it exposes is derived from TraceRecords
that the runtime already writes. There is NO geometry here, no manifold, no
surface. A Trajectory is an ordered, immutable sequence of recorded transitions
plus the cumulative quantities that path-dependent admissibility needs.

What it earns (and only this):
- CLAIM A (path-distinguishability): two states with identical coordinates but
  different histories are DISTINCT, because their lineage hashes differ.
- CLAIM B SUBSTRATE (path-dependent admissibility): cumulative NSV, cumulative
  Omega-erosion, and peak tau are the path-dependent quantities a future
  horizon-aware gate (K3) will read. The Trajectory carries them; it does not
  yet enforce budgets on them (that is K3).

What it does NOT claim:
- No geometry, curvature, surface, sheet, or homotopy (Tier-3 gated).
- No enforcement — the Trajectory is a read model. The gate enforces.

Loop detection (reversible vs irreversible):
- A loop is a return to (approximately) the same field-state coordinates.
- It is REVERSIBLE if cumulative NSV did not rise across the loop.
- It is IRREVERSIBLE if cumulative NSV rose — the system paid irreversible
  residue to traverse the loop, so the apparent return is not a true return.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Any

from ..core.bench_interface import TraceRecord, SessionState
from ..core.types import FieldState


COMPONENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class Checkpoint:
    """A recoverable point in the trajectory: a recorded session state."""
    logical_step: int
    tick_id: str
    tau: float
    Theta: float
    cumulative_NSV: float


@dataclass(frozen=True)
class LoopFinding:
    """A detected return to (approximately) a prior coordinate neighbourhood."""
    from_step: int
    to_step: int
    reversible: bool
    nsv_rise_across_loop: float
    coordinate_distance: float


@dataclass(frozen=True)
class Trajectory:
    """
    An immutable, ordered view over a slice of recorded transitions for one
    session. Carries the path-dependent quantities that distinguish histories
    and that path-conditioned admissibility will read.

    Construct via Trajectory.from_records(...). Do not mutate; a trajectory is
    a snapshot view, and extending it produces a new Trajectory.
    """
    session_id: str
    records: tuple[TraceRecord, ...]

    # Derived cumulative quantities (computed at construction).
    lineage_hash: str
    cumulative_NSV: float
    cumulative_Omega_erosion: float   # sum of positive Omega DROPS along the path
    peak_tau: float
    n_accepted: int                   # count of terminal-accepting (EXECUTE) steps
    n_records: int

    @staticmethod
    def from_records(session_id: str, records: list[TraceRecord]) -> "Trajectory":
        """
        Build a Trajectory from an ordered list of records for one session.

        Records must:
        - all belong to session_id,
        - be in strictly increasing logical_step order.

        Raises ValueError on violation, because a trajectory with reordered or
        cross-session records would misrepresent the path.
        """
        ordered = list(records)
        for r in ordered:
            if r.session_id != session_id:
                raise ValueError(
                    f"record session {r.session_id} != trajectory session {session_id}"
                )
        steps = [r.logical_step for r in ordered]
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError(
                "trajectory records must be in strictly increasing logical_step order"
            )

        # Derive cumulative quantities.
        # CUMULATIVE NSV — modeling note: irreversible residue accrues from
        # COMMITTED transformations, not from raw observations. accepted_delta
        # records the committed delta on EXECUTE (None otherwise). So cumulative
        # NSV is the sum of accepted NSV-deltas along the path. This is more
        # correct than reading observation NSV: a rejected gesture's residue is
        # never paid, because the transformation never committed.
        #
        # (SessionState does not yet carry NSV as a session accumulator alongside
        # tau/Theta. Whether to add it is a K1 consideration — NSV is structurally
        # a monotone session accumulator like tau. For now the Trajectory derives
        # it from accepted_delta, which is the authoritative committed-residue
        # record. Flagged in BUILD_LOG.)
        cumulative_NSV = 0.0
        cumulative_Omega_erosion = 0.0
        peak_tau = 0.0
        n_accepted = 0

        prev_omega: Optional[float] = None
        for r in ordered:
            fs = r.field_state_at_gate
            peak_tau = max(peak_tau, r.next_session_state.tau, fs.tau)
            # Cumulative NSV: sum of committed (accepted) NSV deltas.
            if r.accepted_delta is not None:
                cumulative_NSV += max(0.0, r.accepted_delta.get("NSV", 0.0))
            # Omega erosion: sum positive drops in Omega across consecutive gates.
            if prev_omega is not None and fs.Omega < prev_omega:
                cumulative_Omega_erosion += (prev_omega - fs.Omega)
            prev_omega = fs.Omega
            # Accepted steps (EXECUTE is the only terminal-accepting outcome).
            if r.gate_outcome == "EXECUTE":
                n_accepted += 1

        lineage_hash = Trajectory._compute_lineage_hash(ordered)

        return Trajectory(
            session_id=session_id,
            records=tuple(ordered),
            lineage_hash=lineage_hash,
            cumulative_NSV=cumulative_NSV,
            cumulative_Omega_erosion=cumulative_Omega_erosion,
            peak_tau=peak_tau,
            n_accepted=n_accepted,
            n_records=len(ordered),
        )

    @staticmethod
    def _compute_lineage_hash(records: list[TraceRecord]) -> str:
        """
        Content-addressed hash of the ordered path.

        This is what makes two identical-coordinate states DISTINCT when reached
        by different histories: the hash binds to the full ordered sequence of
        (step, outcome, transformation, field-state) tuples, not just the
        endpoint.
        """
        material = []
        for r in records:
            material.append({
                "step": r.logical_step,
                "outcome": r.gate_outcome or r.pre_gate_outcome,
                "transformation_id": (r.transformation or {}).get("transformation_id"),
                "fs": r.field_state_at_gate.to_dict(),
            })
        canonical = json.dumps(material, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # -- views -------------------------------------------------------------

    @property
    def current_state(self) -> Optional[FieldState]:
        """
        The most recent field state. This is the 'where you are' that a
        state-only gate would see — recoverable from the trajectory, so a
        trajectory-aware gate is a strict superset of a state-only gate.
        """
        if not self.records:
            return None
        return self.records[-1].field_state_at_gate

    @property
    def current_session_state(self) -> Optional[SessionState]:
        if not self.records:
            return None
        return self.records[-1].next_session_state

    def checkpoints(self) -> list[Checkpoint]:
        """
        Recoverable points along the trajectory. Every recorded next-state is a
        candidate checkpoint for recovery. Cumulative NSV at each is tracked so
        recoverability estimation can reason about residue-at-checkpoint.
        """
        out: list[Checkpoint] = []
        running_nsv = 0.0
        for r in self.records:
            if r.accepted_delta is not None:
                running_nsv += max(0.0, r.accepted_delta.get("NSV", 0.0))
            ss = r.next_session_state
            out.append(Checkpoint(
                logical_step=r.logical_step,
                tick_id=r.tick_id,
                tau=ss.tau,
                Theta=ss.Theta,
                cumulative_NSV=running_nsv,
            ))
        return out

    def detect_loops(self, coordinate_epsilon: float = 0.05) -> list[LoopFinding]:
        """
        Detect returns to (approximately) a prior coordinate neighbourhood, and
        classify each as reversible or irreversible.

        Two field states are 'the same neighbourhood' if their Omega, rho,
        kappa are within coordinate_epsilon (we compare the unbounded-but-
        observed coordinates; tau/Theta/NSV are path quantities, not position).

        A loop is REVERSIBLE iff cumulative NSV did not rise across it.
        IRREVERSIBLE iff NSV rose — the apparent return cost irreversible residue,
        so it is not a true return.
        """
        findings: list[LoopFinding] = []
        recs = self.records

        # Precompute cumulative committed residue at each record index.
        cum_nsv_at: list[float] = []
        running = 0.0
        for r in recs:
            if r.accepted_delta is not None:
                running += max(0.0, r.accepted_delta.get("NSV", 0.0))
            cum_nsv_at.append(running)

        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                a = recs[i].field_state_at_gate
                b = recs[j].field_state_at_gate
                dist = max(
                    abs(a.Omega - b.Omega),
                    abs(a.rho - b.rho),
                    abs(a.kappa - b.kappa),
                )
                if dist <= coordinate_epsilon:
                    # Residue rise across the loop = committed residue between
                    # the two visits. A return at higher committed residue is
                    # an irreversible loop: the apparent return cost residue.
                    nsv_rise = cum_nsv_at[j] - cum_nsv_at[i]
                    findings.append(LoopFinding(
                        from_step=recs[i].logical_step,
                        to_step=recs[j].logical_step,
                        reversible=(nsv_rise <= 0.0),
                        nsv_rise_across_loop=nsv_rise,
                        coordinate_distance=dist,
                    ))
        return findings

    def distinguishes_from(self, other: "Trajectory") -> bool:
        """
        True iff these two trajectories are distinct paths, even if they end at
        the same coordinates. This is Claim A operationalized: distinctness is
        decided by lineage hash, not by endpoint.
        """
        return self.lineage_hash != other.lineage_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "lineage_hash": self.lineage_hash,
            "cumulative_NSV": self.cumulative_NSV,
            "cumulative_Omega_erosion": self.cumulative_Omega_erosion,
            "peak_tau": self.peak_tau,
            "n_accepted": self.n_accepted,
            "n_records": self.n_records,
        }
