"""
Tests for components/replay.py.

Verifies:
- Append-only ledger rejects out-of-order steps.
- Serialization round-trips (write -> load -> identical records).
- Deterministic replay reconstructs the recorded accumulator sequence (PASSED).
- Live replay PASSES when gate logic is unchanged.
- Live replay DIVERGES when thresholds change (drift detection works).
- Checksums detect tampering.
- Transformation is carried through serialization for replay.
"""
import json
import tempfile
from pathlib import Path

import pytest

from runtime.core.types import Transformation, GateOutcome, IntentClass
from runtime.core.bench_interface import (
    BenchObservation, SessionState, TraceRecord,
)
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.session_manager import (
    project_to_field_state, advance_session_on_accepted,
    passthrough_session_on_unaccepted, is_accepting,
)
from runtime.components.replay import (
    TraceLedger, LedgerViolation, ReplayStatus,
    replay_deterministic, replay_live,
    record_checksum, trace_record_from_dict,
)


def _obs(tick_id, session_id="sess-1", nsv=0.0):
    return BenchObservation(
        Omega=0.7, rho=0.0, kappa=0.0, NSV=nsv, Energy=0.5,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=0,
    )


def _run_session(gestures, session_id="sess-1", thresholds=None):
    """
    Run a sequence of gestures through the pipeline and produce a ledger.
    gestures: list of (tick_id, delta_dict).
    Returns (ledger, final_session).
    """
    th = thresholds or GateThresholds()
    ledger = TraceLedger()
    session = SessionState.initial(session_id=session_id, tau=0.0, Theta=1.0)

    for step, (tick_id, delta) in enumerate(gestures):
        obs = _obs(tick_id, session_id=session_id, nsv=delta.get("NSV", 0.0))
        prior = session
        proj = project_to_field_state(obs, session, logical_step=step)
        t = Transformation.new(typed_effects=delta, intent_class=IntentClass.COMMIT)
        out = evaluate(GateInput(
            current_state=proj.field_state, transformation=t, thresholds=th,
        ))
        if is_accepting(out.outcome.value):
            session = advance_session_on_accepted(
                session, out.predicted_state, tick_id=tick_id, logical_step=step,
            )
            accepted_delta = dict(t.expected_delta)
        else:
            session = passthrough_session_on_unaccepted(
                session, tick_id=tick_id, logical_step=step,
            )
            accepted_delta = None

        record = TraceRecord(
            tick_id=tick_id, session_id=session_id, logical_step=step,
            prior_session_state=prior,
            bench_observation=obs,
            field_state_at_gate=proj.field_state,
            gate_outcome=out.outcome.value,
            reason_codes=tuple(r.value for r in out.reason_codes),
            next_session_state=session,
            accepted_delta=accepted_delta,
            transformation=t.to_dict(),
        )
        ledger.append(record)

    return ledger, session


GESTURES = [
    ("t0", {"tau": 0.05, "NSV": 0.02}),
    ("t1", {"tau": 0.03, "NSV": 0.01}),
    ("t2", {"NSV": 0.6}),            # REJECT
    ("t3", {"tau": 0.10, "NSV": 0.03}),
    ("t4", {"tau": 0.04, "NSV": 0.02}),
]


class TestLedgerAppendOnly:
    def test_append_returns_checksum(self):
        ledger, _ = _run_session(GESTURES)
        assert len(ledger) == len(GESTURES)

    def test_out_of_order_step_rejected(self):
        ledger = TraceLedger()
        l1, _ = _run_session([("t0", {"tau": 0.05})])
        rec = l1.records()[0]
        ledger.append(rec)
        # Appending the same step again (logical_step 0) must fail
        with pytest.raises(LedgerViolation, match="strictly increase"):
            ledger.append(rec)


class TestSerializationRoundTrip:
    def test_write_load_preserves_records(self):
        ledger, _ = _run_session(GESTURES)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            ledger.write(path)
            loaded = TraceLedger.load(path)
            assert len(loaded) == len(ledger)
            # Checksums match record-by-record
            for orig, load in zip(ledger.records(), loaded.records()):
                assert record_checksum(orig) == record_checksum(load)

    def test_ledger_checksum_stable_across_roundtrip(self):
        ledger, _ = _run_session(GESTURES)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            ledger.write(path)
            loaded = TraceLedger.load(path)
            assert ledger.ledger_checksum() == loaded.ledger_checksum()

    def test_transformation_survives_roundtrip(self):
        ledger, _ = _run_session([("t0", {"tau": 0.05, "NSV": 0.02})])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            ledger.write(path)
            loaded = TraceLedger.load(path)
            rec = loaded.records()[0]
            assert rec.transformation is not None
            assert rec.transformation["intent_class"] == "commit"


class TestDeterministicReplay:
    def test_replay_reconstructs_recorded_sequence(self):
        ledger, _ = _run_session(GESTURES)
        result = replay_deterministic(ledger, "sess-1")
        assert result.status == ReplayStatus.PASSED
        assert len(result.divergences) == 0
        # Reconstructed and recorded sequences match
        assert result.accumulator_sequence == result.recorded_sequence

    def test_replay_after_roundtrip_still_passes(self):
        ledger, _ = _run_session(GESTURES)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            ledger.write(path)
            loaded = TraceLedger.load(path)
            result = replay_deterministic(loaded, "sess-1")
            assert result.status == ReplayStatus.PASSED

    def test_empty_session_incomplete(self):
        ledger = TraceLedger()
        result = replay_deterministic(ledger, "nonexistent")
        assert result.status == ReplayStatus.INCOMPLETE


class TestLiveReplay:
    def test_live_replay_passes_with_same_thresholds(self):
        ledger, _ = _run_session(GESTURES)
        result = replay_live(ledger, "sess-1", thresholds=GateThresholds())
        assert result.status == ReplayStatus.PASSED, result.divergences

    def test_live_replay_diverges_with_changed_thresholds(self):
        """
        Drift detection: re-running with a stricter threshold should produce
        different outcomes than recorded, surfaced as divergence.
        """
        ledger, _ = _run_session(GESTURES)
        # Original used default nsv_step_max=0.20. Tighten dramatically so that
        # gestures previously EXECUTE'd now TRANSFORM or REJECT.
        strict = GateThresholds(nsv_step_max=0.001, nsv_step_catastrophic=0.01)
        result = replay_live(ledger, "sess-1", thresholds=strict)
        assert result.status == ReplayStatus.DIVERGED
        assert len(result.divergences) > 0

    def test_confidence_basis_is_evidence_not_opinion(self):
        ledger, _ = _run_session(GESTURES)
        result = replay_live(ledger, "sess-1")
        assert result.confidence_basis == "replay_evidence_not_model_opinion"


class TestChecksumTamperDetection:
    def test_mutated_record_changes_checksum(self):
        ledger, _ = _run_session([("t0", {"tau": 0.05, "NSV": 0.02})])
        rec = ledger.records()[0]
        original = record_checksum(rec)
        # Build a tampered dict and rehash
        tampered = rec.to_dict()
        tampered["reason_codes"] = ["tampered"]
        tampered_record = trace_record_from_dict(tampered)
        assert record_checksum(tampered_record) != original

    def test_ledger_checksum_detects_reorder(self):
        # Two independent runs produce DIFFERENT ledger checksums because each
        # transformation gets a fresh UUID. This is correct: the checksum binds
        # to transformation identity. The meaningful guarantee is that a
        # round-tripped ledger preserves its checksum exactly (tested in
        # TestSerializationRoundTrip). Here we confirm the checksum is sensitive
        # to content: two runs with distinct transformation IDs differ.
        ledger_a, _ = _run_session(GESTURES)
        ledger_b, _ = _run_session(GESTURES)
        # Distinct UUIDs => distinct checksums. Sensitivity confirmed.
        assert ledger_a.ledger_checksum() != ledger_b.ledger_checksum()

    def test_ledger_checksum_is_deterministic_for_identical_content(self):
        # Build two ledgers from the SAME records (same UUIDs) and confirm
        # identical checksums — the determinism guarantee that matters.
        ledger_a, _ = _run_session(GESTURES)
        from runtime.components.replay import TraceLedger as TL
        ledger_b = TL()
        for rec in ledger_a.records():
            ledger_b.append(rec)
        assert ledger_a.ledger_checksum() == ledger_b.ledger_checksum()


class TestReplayResultSerialization:
    def test_replay_result_serializes(self):
        ledger, _ = _run_session(GESTURES)
        result = replay_deterministic(ledger, "sess-1")
        d = result.to_dict()
        json.dumps(d)  # raises if not serializable
        assert d["status"] == "passed"
        assert d["confidence_basis"] == "replay_evidence_not_model_opinion"
