"""
Event log hardening tests — the seven acceptance criteria.

1. append-only event schema      (EventEntry shape, serialisable)
2. event ledger fixture          (a known sequence round-trips)
3. replay compatibility test     (serialize -> deserialize -> identical, chain intact)
4. illegal mutation test         (tampering is detected)
5. receipt linkage               (receipts verify; forged receipts fail)
6. no kernel widening            (event log does not import gate/evaluate/outcomes)
7. no orchestration coupling     (event log imports only stdlib)
"""
import ast
import json
from pathlib import Path

import pytest

import importlib.util
import sys

_EVENT_LOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "layers" / "runtime-layer" / "event-log" / "event_log.py"
)
_spec = importlib.util.spec_from_file_location("event_log", _EVENT_LOG_PATH)
event_log = importlib.util.module_from_spec(_spec)
sys.modules["event_log"] = event_log  # register so @dataclass can resolve module
_spec.loader.exec_module(event_log)

EventLog = event_log.EventLog
EventEntry = event_log.EventEntry
Receipt = event_log.Receipt
EventLogViolation = event_log.EventLogViolation
GENESIS_CHAIN_HASH = event_log.GENESIS_CHAIN_HASH


def _fixture_log() -> EventLog:
    log = EventLog()
    log.append("s1", 0, "state_projection", {"omega": 0.7})
    log.append("s1", 1, "transformation_proposed", {"tau": 0.05})
    log.append("s1", 2, "gate_evaluated", {"outcome": "EXECUTE"})
    return log


class Test1_AppendOnlySchema:
    def test_entry_has_evidential_fields(self):
        log = EventLog()
        log.append("s", 0, "k", {"a": 1})
        e = log.entries()[0]
        for fld in ("seq", "session_id", "logical_step", "event_kind",
                    "payload", "prev_chain_hash", "content_hash", "chain_hash"):
            assert hasattr(e, fld)

    def test_first_entry_links_to_genesis(self):
        log = EventLog()
        log.append("s", 0, "k", {})
        assert log.entries()[0].prev_chain_hash == GENESIS_CHAIN_HASH

    def test_entries_are_frozen(self):
        log = EventLog()
        log.append("s", 0, "k", {})
        with pytest.raises(Exception):
            log.entries()[0].seq = 99  # frozen dataclass


class Test2_LedgerFixture:
    def test_known_sequence(self):
        log = _fixture_log()
        assert len(log) == 3
        assert [e.event_kind for e in log.entries()] == [
            "state_projection", "transformation_proposed", "gate_evaluated"
        ]

    def test_ordering_enforced_within_session(self):
        log = EventLog()
        log.append("s", 5, "k", {})
        with pytest.raises(EventLogViolation):
            log.append("s", 5, "k", {})  # not strictly increasing
        with pytest.raises(EventLogViolation):
            log.append("s", 3, "k", {})  # decreasing


class Test3_ReplayCompatibility:
    def test_serialize_deserialize_roundtrip(self):
        log = _fixture_log()
        restored = EventLog.deserialize(log.serialize())
        assert len(restored) == len(log)
        assert restored.head_chain_hash == log.head_chain_hash

    def test_roundtrip_preserves_every_entry(self):
        log = _fixture_log()
        restored = EventLog.deserialize(log.serialize())
        for a, b in zip(log.entries(), restored.entries()):
            assert a.to_dict() == b.to_dict()

    def test_deserialize_verifies_chain(self):
        log = _fixture_log()
        assert EventLog.deserialize(log.serialize()).verify_integrity()


class Test4_IllegalMutation:
    def test_payload_tampering_detected(self):
        log = _fixture_log()
        # Tamper with a serialized entry's payload but keep its hashes.
        lines = log.serialize().splitlines()
        d = json.loads(lines[1])
        d["payload"] = {"tau": 0.99}  # changed; content_hash now stale
        lines[1] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        with pytest.raises(EventLogViolation):
            EventLog.deserialize("\n".join(lines))

    def test_reorder_detected(self):
        log = _fixture_log()
        lines = log.serialize().splitlines()
        lines[1], lines[2] = lines[2], lines[1]  # swap order
        with pytest.raises(EventLogViolation):
            EventLog.deserialize("\n".join(lines))

    def test_deletion_detected(self):
        log = _fixture_log()
        lines = log.serialize().splitlines()
        del lines[1]  # remove middle entry
        with pytest.raises(EventLogViolation):
            EventLog.deserialize("\n".join(lines))

    def test_value_isolation_on_append(self):
        # Mutating the caller's payload after append must not change the entry.
        log = EventLog()
        p = {"omega": 0.5}
        log.append("s", 0, "k", p)
        p["omega"] = -9.0
        assert log.entries()[0].payload["omega"] == 0.5

    def test_intact_log_verifies(self):
        assert _fixture_log().verify_integrity()


class Test5_ReceiptLinkage:
    def test_receipt_verifies_against_log(self):
        log = EventLog()
        r = log.append("s", 0, "k", {"x": 1})
        assert log.verify_receipt(r)

    def test_forged_receipt_fails(self):
        log = EventLog()
        r = log.append("s", 0, "k", {"x": 1})
        forged = Receipt(seq=r.seq, session_id=r.session_id,
                         logical_step=r.logical_step,
                         content_hash="deadbeefdeadbeef", chain_hash=r.chain_hash)
        assert not log.verify_receipt(forged)

    def test_receipt_for_nonexistent_seq_fails(self):
        log = EventLog()
        log.append("s", 0, "k", {})
        phantom = Receipt(seq=99, session_id="s", logical_step=0,
                          content_hash="x", chain_hash="y")
        assert not log.verify_receipt(phantom)

    def test_receipt_survives_roundtrip(self):
        log = _fixture_log()
        r = log.entries()[1]
        receipt = Receipt(seq=r.seq, session_id=r.session_id,
                          logical_step=r.logical_step,
                          content_hash=r.content_hash, chain_hash=r.chain_hash)
        restored = EventLog.deserialize(log.serialize())
        assert restored.verify_receipt(receipt)


class Test6_NoKernelWidening:
    """The event log must not evaluate admissibility or emit outcomes."""

    def test_event_log_does_not_import_gate_or_outcomes(self):
        src = _EVENT_LOG_PATH.read_text()
        tree = ast.parse(src)
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        forbidden = ["gate", "evaluate", "session_manager", "mcp_router",
                     "coherence", "horizon", "constitution"]
        for f in forbidden:
            assert not any(f in m for m in imported), f"event log imports {f}"

    def test_event_log_emits_no_gate_outcome(self):
        src = _EVENT_LOG_PATH.read_text()
        # The log stores events; it must not produce EXECUTE/TRANSFORM/etc itself.
        # (Outcomes may appear as payload DATA, but not as produced verdicts —
        # there is no GateOutcome import and no evaluate call.)
        assert "import" in src  # sanity
        assert "GateOutcome" not in src
        assert "def evaluate" not in src


class Test7_NoOrchestrationCoupling:
    """The event log depends only on stdlib."""

    def test_only_stdlib_imports(self):
        src = _EVENT_LOG_PATH.read_text()
        tree = ast.parse(src)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"hashlib", "json", "dataclasses", "typing", "__future__"}
        for m in modules:
            assert m in stdlib, f"non-stdlib import: {m}"
