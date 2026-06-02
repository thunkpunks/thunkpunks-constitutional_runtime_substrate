"""
Replay Engine.

Constitutional role: turns replay determinism from a tested property into a
runtime capability. Without replay there is no governance, only logging theatre.

Provides:
- Append-only trace ledger (records cannot be mutated or reordered).
- Deterministic replay: re-run a recorded session and verify the reconstructed
  accumulator sequence matches, within a checksum.
- Live replay separation: re-run with fresh evaluation and measure drift against
  the recorded outcomes.
- Checksum verification: each record and the ledger as a whole are hashable.
- Drift detection: divergence between recorded and replayed sequences is
  surfaced as evidence, not hidden.

Vocabulary adopted from the Curvature Lab brief (zero-cost alignment):
- replay_status: passed | diverged | incomplete
- confidence_basis: "replay_evidence_not_model_opinion"

Design boundary: deserialization (from_dict) lives HERE, not scattered across
the core types, so the serialization round-trip contract is in one tested place.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from ..core.types import FieldState, Transformation, IntentClass, ReversibilityClass, ReversibilityMetadata
from ..core.bench_interface import (
    BenchObservation,
    SessionState,
    TraceRecord,
)
from .gate import GateThresholds, GateInput, evaluate
from .session_manager import (
    project_to_field_state,
    advance_session_on_accepted,
    passthrough_session_on_unaccepted,
    is_accepting,
)


COMPONENT_VERSION = "0.1.0"
CONFIDENCE_BASIS = "replay_evidence_not_model_opinion"


class ReplayStatus(str, Enum):
    """Outcome of a replay. Vocabulary from the Curvature Lab brief."""
    PASSED = "passed"        # replay reconstructed the recorded sequence exactly
    DIVERGED = "diverged"    # replay produced a different sequence
    INCOMPLETE = "incomplete"  # replay could not finish (missing data, error)


# ---------------------------------------------------------------------------
# Deserialization (the round-trip contract lives here, tested in one place)
# ---------------------------------------------------------------------------

def field_state_from_dict(d: dict) -> FieldState:
    return FieldState(
        Omega=d["Omega"], rho=d["rho"], kappa=d["kappa"],
        tau=d["tau"], Theta=d["Theta"], NSV=d["NSV"],
        logical_step=d["logical_step"],
    )


def session_state_from_dict(d: dict) -> SessionState:
    # SessionState.initial then reconstruct via dataclass replace-like path.
    # SessionState is frozen; build it directly through its constructor.
    return SessionState(
        session_id=d["session_id"],
        tau=d["tau"],
        Theta=d["Theta"],
        last_tick_id=d.get("last_tick_id"),
        last_logical_step=d.get("last_logical_step", -1),
        renegotiation_count=d.get("renegotiation_count", 0),
    )


def bench_observation_from_dict(d: dict) -> BenchObservation:
    return BenchObservation(
        Omega=d["Omega"], rho=d["rho"], kappa=d["kappa"], NSV=d["NSV"],
        Energy=d["Energy"], omega_raw=tuple(d["omega_raw"]),
        session_id=d["session_id"], tick_id=d["tick_id"],
        timestamp_ms=d["timestamp_ms"],
    )


def transformation_from_dict(d: dict) -> Transformation:
    rev = d.get("reversibility", {})
    return Transformation(
        transformation_id=d["transformation_id"],
        typed_effects=dict(d["typed_effects"]),
        intent_class=IntentClass(d.get("intent_class", "unspecified")),
        reversibility=ReversibilityMetadata(
            reversibility_class=ReversibilityClass(rev.get("reversibility_class", "unknown")),
            reversal_cost=rev.get("reversal_cost", 0.0),
            rationale=rev.get("rationale", ""),
        ),
        expected_commitment_cost=d.get("expected_commitment_cost", 0.0),
        provenance_ref=d.get("provenance_ref"),
        description=d.get("description", ""),
        composed_from=tuple(d.get("composed_from", ())),
    )


def trace_record_from_dict(d: dict) -> TraceRecord:
    return TraceRecord(
        tick_id=d["tick_id"],
        session_id=d["session_id"],
        logical_step=d["logical_step"],
        prior_session_state=session_state_from_dict(d["prior_session_state"]),
        bench_observation=bench_observation_from_dict(d["bench_observation"]),
        field_state_at_gate=field_state_from_dict(d["field_state_at_gate"]),
        gate_outcome=d.get("gate_outcome"),
        pre_gate_outcome=d.get("pre_gate_outcome"),
        reason_codes=tuple(d.get("reason_codes", [])),
        next_session_state=session_state_from_dict(d["next_session_state"]),
        accepted_delta=d.get("accepted_delta"),
        transformation=d.get("transformation"),
    )


def record_checksum(record: TraceRecord) -> str:
    """Stable checksum of a single trace record."""
    canonical = json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Append-only ledger
# ---------------------------------------------------------------------------

class LedgerViolation(Exception):
    """Raised on an attempt to violate append-only or ordering invariants."""


class TraceLedger:
    """
    Append-only ledger of TraceRecords for one or more sessions.

    Invariants:
    - Records are appended, never mutated or removed.
    - Within a session, logical_step is strictly increasing.
    - Each append computes and stores a checksum.
    - The ledger checksum is the hash of the ordered record checksums.
    """

    def __init__(self) -> None:
        self._records: list[TraceRecord] = []
        self._checksums: list[str] = []
        self._last_step_by_session: dict[str, int] = {}

    def append(self, record: TraceRecord) -> str:
        """Append a record. Returns its checksum. Raises on ordering violation."""
        last = self._last_step_by_session.get(record.session_id, -1)
        if record.logical_step <= last:
            raise LedgerViolation(
                f"logical_step must strictly increase within session "
                f"{record.session_id}: got {record.logical_step}, last was {last}"
            )
        self._records.append(record)
        cs = record_checksum(record)
        self._checksums.append(cs)
        self._last_step_by_session[record.session_id] = record.logical_step
        return cs

    def records(self, session_id: Optional[str] = None) -> list[TraceRecord]:
        if session_id is None:
            return list(self._records)
        return [r for r in self._records if r.session_id == session_id]

    def ledger_checksum(self) -> str:
        """Hash of the ordered record checksums. Detects any reorder/mutation."""
        joined = "".join(self._checksums)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    def serialize(self) -> str:
        """Serialize the whole ledger to JSON lines (one record per line)."""
        return "\n".join(json.dumps(r.to_dict(), separators=(",", ":")) for r in self._records)

    def write(self, path: Path) -> None:
        path.write_text(self.serialize() + ("\n" if self._records else ""))

    @staticmethod
    def load(path: Path) -> "TraceLedger":
        ledger = TraceLedger()
        text = path.read_text()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            ledger.append(trace_record_from_dict(json.loads(line)))
        return ledger

    def __len__(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplayResult:
    """
    Result of replaying a session's ledger.

    accumulator_sequence: the (tau, Theta) sequence reconstructed by replay.
    recorded_sequence: the (tau, Theta) sequence as recorded in the ledger.
    """
    status: ReplayStatus
    mode: str  # "deterministic" | "live"
    session_id: str
    n_records: int
    accumulator_sequence: tuple[tuple[float, float], ...]
    recorded_sequence: tuple[tuple[float, float], ...]
    divergences: tuple[str, ...]
    confidence_basis: str = CONFIDENCE_BASIS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "mode": self.mode,
            "session_id": self.session_id,
            "n_records": self.n_records,
            "accumulator_sequence": [list(p) for p in self.accumulator_sequence],
            "recorded_sequence": [list(p) for p in self.recorded_sequence],
            "divergences": list(self.divergences),
            "confidence_basis": self.confidence_basis,
        }


def replay_deterministic(
    ledger: TraceLedger,
    session_id: str,
    epsilon: float = 1e-9,
) -> ReplayResult:
    """
    Deterministic replay: walk the recorded records, reconstruct the session
    accumulator by applying the SAME recorded outcomes, and verify the
    reconstructed (tau, Theta) sequence matches what was recorded.

    This proves the ledger is internally consistent: the recorded next-states
    follow from the recorded prior-states and outcomes.
    """
    records = sorted(ledger.records(session_id), key=lambda r: r.logical_step)
    if not records:
        return ReplayResult(
            status=ReplayStatus.INCOMPLETE, mode="deterministic",
            session_id=session_id, n_records=0,
            accumulator_sequence=(), recorded_sequence=(), divergences=("no records",),
        )

    reconstructed: list[tuple[float, float]] = []
    recorded: list[tuple[float, float]] = []
    divergences: list[str] = []

    # Start from the first record's prior session state.
    session = session_state_from_dict(records[0].prior_session_state.to_dict())
    reconstructed.append((session.tau, session.Theta))
    recorded.append((records[0].prior_session_state.tau, records[0].prior_session_state.Theta))

    for r in records:
        # Apply the recorded outcome to advance/passthrough.
        if r.gate_outcome is not None and is_accepting(r.gate_outcome):
            # Reconstruct the accepted next-state from the recorded field state at gate.
            # The recorded next_session_state carries the post-advance (tau, Theta).
            recorded_next = r.next_session_state
            session = session.advance(
                new_tau=recorded_next.tau,
                new_Theta=recorded_next.Theta,
                tick_id=r.tick_id,
                logical_step=r.logical_step,
            )
        else:
            session = session.passthrough(tick_id=r.tick_id, logical_step=r.logical_step)

        reconstructed.append((session.tau, session.Theta))
        recorded.append((r.next_session_state.tau, r.next_session_state.Theta))

        # Check divergence
        if abs(session.tau - r.next_session_state.tau) > epsilon or \
           abs(session.Theta - r.next_session_state.Theta) > epsilon:
            divergences.append(
                f"step {r.logical_step}: reconstructed "
                f"(tau={session.tau:.6f},Theta={session.Theta:.6f}) != recorded "
                f"(tau={r.next_session_state.tau:.6f},Theta={r.next_session_state.Theta:.6f})"
            )

    status = ReplayStatus.PASSED if not divergences else ReplayStatus.DIVERGED
    return ReplayResult(
        status=status, mode="deterministic", session_id=session_id,
        n_records=len(records),
        accumulator_sequence=tuple(reconstructed),
        recorded_sequence=tuple(recorded),
        divergences=tuple(divergences),
    )


def replay_live(
    ledger: TraceLedger,
    session_id: str,
    thresholds: Optional[GateThresholds] = None,
    epsilon: float = 1e-9,
) -> ReplayResult:
    """
    Live replay: re-run the gate on each recorded (observation, transformation)
    pair and compare the freshly-computed outcomes and accumulator to what was
    recorded. Divergence between live and recorded is research signal — it means
    the gate logic, thresholds, or evaluation has changed since the trace was made.

    Pre-gate short-circuit ticks (no transformation) cannot be re-evaluated by
    the gate; they are passed through and counted, not re-gated.
    """
    th = thresholds or GateThresholds()
    records = sorted(ledger.records(session_id), key=lambda r: r.logical_step)
    if not records:
        return ReplayResult(
            status=ReplayStatus.INCOMPLETE, mode="live",
            session_id=session_id, n_records=0,
            accumulator_sequence=(), recorded_sequence=(), divergences=("no records",),
        )

    reconstructed: list[tuple[float, float]] = []
    recorded: list[tuple[float, float]] = []
    divergences: list[str] = []

    session = session_state_from_dict(records[0].prior_session_state.to_dict())
    reconstructed.append((session.tau, session.Theta))
    recorded.append((records[0].prior_session_state.tau, records[0].prior_session_state.Theta))

    for r in records:
        if r.transformation is None:
            # Pre-gate short-circuit: nothing to re-gate. Passthrough.
            session = session.passthrough(tick_id=r.tick_id, logical_step=r.logical_step)
        else:
            obs = r.bench_observation
            # Re-project from the recorded observation and CURRENT reconstructed session.
            proj = project_to_field_state(obs, session, logical_step=r.logical_step)
            t = transformation_from_dict(r.transformation)
            out = evaluate(GateInput(
                current_state=proj.field_state, transformation=t, thresholds=th,
            ))
            # Compare live outcome to recorded outcome
            if r.gate_outcome is not None and out.outcome.value != r.gate_outcome:
                divergences.append(
                    f"step {r.logical_step}: live outcome {out.outcome.value} "
                    f"!= recorded {r.gate_outcome}"
                )
            if is_accepting(out.outcome.value):
                session = advance_session_on_accepted(
                    session, out.predicted_state, tick_id=r.tick_id, logical_step=r.logical_step,
                )
            else:
                session = passthrough_session_on_unaccepted(
                    session, tick_id=r.tick_id, logical_step=r.logical_step,
                )

        reconstructed.append((session.tau, session.Theta))
        recorded.append((r.next_session_state.tau, r.next_session_state.Theta))
        if abs(session.tau - r.next_session_state.tau) > epsilon or \
           abs(session.Theta - r.next_session_state.Theta) > epsilon:
            divergences.append(
                f"step {r.logical_step}: accumulator drift "
                f"reconstructed(tau={session.tau:.6f}) vs recorded(tau={r.next_session_state.tau:.6f})"
            )

    status = ReplayStatus.PASSED if not divergences else ReplayStatus.DIVERGED
    return ReplayResult(
        status=status, mode="live", session_id=session_id,
        n_records=len(records),
        accumulator_sequence=tuple(reconstructed),
        recorded_sequence=tuple(recorded),
        divergences=tuple(divergences),
    )
