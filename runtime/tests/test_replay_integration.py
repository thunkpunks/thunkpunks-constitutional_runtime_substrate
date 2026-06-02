"""
Replay integration tests — the integration acceptance set.

Exercises event-log + lineage + receipts together as one evidential chain and
proves tampering anywhere fails. If this passes, the three substrate layers are
promotable from EXPERIMENTALLY_BOUNDED to IMPLEMENTED.

- replay integration fixture exists
- event-log + lineage + receipts replay together
- replay reconstructs full evidential chain
- replay detects tampered event payload
- replay detects tampered lineage ancestry
- replay detects tampered receipt outcome/reason codes
- replay detects deleted/reordered entries
- replay rejects orphan receipts
- replay rejects orphan lineage
- kernel imports no substrate layer
- substrates do not decide admissibility
- full regression passes
"""
import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _LAYERS / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


event_log = _load("event_log", "event-log/event_log.py")
lineage = _load("lineage", "lineage/lineage.py")
receipts = _load("receipts", "receipts/receipts.py")
replay_integration = _load("replay_integration", "replay-integration/replay_integration.py")

EventLog = event_log.EventLog
LineageRecord = lineage.LineageRecord
build_lineage_from_records = lineage.build_lineage_from_records
issue_receipt = receipts.issue_receipt
EvidenceRef = receipts.EvidenceRef
ReceiptLog = receipts.ReceiptLog
EvidentialBundle = replay_integration.EvidentialBundle
replay_evidential_chain = replay_integration.replay_evidential_chain
assert_replayable = replay_integration.assert_replayable
ReplayIntegrityError = replay_integration.ReplayIntegrityError

_REPLAY_PATH = _LAYERS / "replay-integration" / "replay_integration.py"

_MODULES = dict(
    event_log_module=event_log,
    lineage_module=lineage,
    receipts_module=receipts,
)


def _build_chain():
    """
    A complete evidential chain: two primitives (a, b), a composite (c derived
    from a, b), each recorded as an event, with lineage and a receipt for c.
    Returns an EvidentialBundle.
    """
    log = EventLog()
    ea = log.append("s", 0, "transformation_proposed", {"id": "a"})
    eb = log.append("s", 1, "transformation_proposed", {"id": "b"})
    ec = log.append("s", 2, "gate_evaluated", {"id": "c", "outcome": "EXECUTE"})

    lin_records = [
        LineageRecord("a", 0, (), receipt_content_hash=ea.content_hash),
        LineageRecord("b", 1, (), receipt_content_hash=eb.content_hash),
        LineageRecord("c", 2, ("a", "b"), receipt_content_hash=ec.content_hash),
    ]
    # Validate the lineage builds (sanity), then serialize records.
    build_lineage_from_records(lin_records)

    rl = ReceiptLog()
    rl.add(issue_receipt(
        receipt_id="r-c", transformation_id="c", lineage_transformation_id="c",
        event_seq=ec.seq, event_content_hash=ec.content_hash,
        outcome="EXECUTE", reason_codes=("clean_small_commit",),
        evidence_refs=(EvidenceRef("event", str(ec.seq)),),
    ))

    return EvidentialBundle(
        event_log_text=log.serialize(),
        lineage_records=[r.to_dict() for r in lin_records],
        receipt_log_text=rl.serialize(),
    )


class TestFixtureAndHappyPath:
    def test_fixture_builds(self):
        bundle = _build_chain()
        assert bundle.event_log_text
        assert len(bundle.lineage_records) == 3
        assert bundle.receipt_log_text

    def test_full_chain_replays(self):
        result = replay_evidential_chain(_build_chain(), **_MODULES)
        assert result.ok, result.failures
        assert result.n_events == 3
        assert result.n_lineage == 3
        assert result.n_receipts == 1

    def test_assert_replayable_passes_on_clean_chain(self):
        # Does not raise.
        assert_replayable(_build_chain(), **_MODULES)

    def test_replay_is_deterministic(self):
        b = _build_chain()
        r1 = replay_evidential_chain(b, **_MODULES)
        r2 = replay_evidential_chain(b, **_MODULES)
        assert r1.to_dict() == r2.to_dict()


class TestTamperedEventPayload:
    def test_tampered_event_payload_fails(self):
        bundle = _build_chain()
        lines = bundle.event_log_text.splitlines()
        d = json.loads(lines[2]); d["payload"] = {"id": "c", "outcome": "REJECT"}
        lines[2] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        tampered = EvidentialBundle(
            event_log_text="\n".join(lines),
            lineage_records=bundle.lineage_records,
            receipt_log_text=bundle.receipt_log_text,
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("event_log_reload_failed" in f for f in result.failures)


class TestTamperedLineageAncestry:
    def test_tampered_ancestry_fails(self):
        bundle = _build_chain()
        # Corrupt c's ancestry to claim an unknown parent.
        recs = [dict(r) for r in bundle.lineage_records]
        for r in recs:
            if r["transformation_id"] == "c":
                r["parent_ids"] = ["ghost"]
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=recs,
            receipt_log_text=bundle.receipt_log_text,
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("lineage_reconstruct_failed" in f for f in result.failures)


class TestTamperedReceipt:
    def test_tampered_receipt_outcome_fails(self):
        bundle = _build_chain()
        line = json.loads(bundle.receipt_log_text)
        line["outcome"] = "REJECT"  # tamper, leave stale receipt_hash
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=bundle.lineage_records,
            receipt_log_text=json.dumps(line),
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("receipt_reload_failed" in f for f in result.failures)

    def test_tampered_receipt_reason_codes_fail(self):
        bundle = _build_chain()
        line = json.loads(bundle.receipt_log_text)
        line["reason_codes"] = ["fabricated_reason"]
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=bundle.lineage_records,
            receipt_log_text=json.dumps(line),
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok


class TestDeletedReordered:
    def test_deleted_event_breaks_replay(self):
        bundle = _build_chain()
        lines = bundle.event_log_text.splitlines()
        del lines[1]  # remove event b
        tampered = EvidentialBundle(
            event_log_text="\n".join(lines),
            lineage_records=bundle.lineage_records,
            receipt_log_text=bundle.receipt_log_text,
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("event_log_reload_failed" in f for f in result.failures)

    def test_reordered_events_break_replay(self):
        bundle = _build_chain()
        lines = bundle.event_log_text.splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        tampered = EvidentialBundle(
            event_log_text="\n".join(lines),
            lineage_records=bundle.lineage_records,
            receipt_log_text=bundle.receipt_log_text,
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok


class TestOrphans:
    def test_orphan_receipt_event_binding_fails(self):
        bundle = _build_chain()
        # Receipt bound to a non-existent event seq.
        rl = ReceiptLog()
        rl.add(issue_receipt("r-x", "c", "c", event_seq=99,
                             event_content_hash="deadbeef", outcome="EXECUTE"))
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=bundle.lineage_records,
            receipt_log_text=rl.serialize(),
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("orphan_or_tampered_event_binding" in f for f in result.failures)

    def test_orphan_receipt_lineage_binding_fails(self):
        bundle = _build_chain()
        log = EventLog.deserialize(bundle.event_log_text)
        e = log.entries()[2]
        rl = ReceiptLog()
        # Receipt binds to a real event but a lineage id with no record.
        rl.add(issue_receipt("r-x", "ghost", "ghost", e.seq, e.content_hash, outcome="EXECUTE"))
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=bundle.lineage_records,
            receipt_log_text=rl.serialize(),
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("orphan_lineage_binding" in f for f in result.failures)

    def test_orphan_lineage_event_reference_fails(self):
        bundle = _build_chain()
        # Lineage record referencing an event seq beyond the log.
        recs = [dict(r) for r in bundle.lineage_records]
        recs.append({"transformation_id": "d", "event_seq": 99,
                     "parent_ids": [], "receipt_content_hash": None})
        tampered = EvidentialBundle(
            event_log_text=bundle.event_log_text,
            lineage_records=recs,
            receipt_log_text=bundle.receipt_log_text,
        )
        result = replay_evidential_chain(tampered, **_MODULES)
        assert not result.ok
        assert any("orphan_lineage_event" in f for f in result.failures)


class TestNoKernelCoupling:
    def test_replay_integration_imports_only_stdlib(self):
        tree = ast.parse(_REPLAY_PATH.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"dataclasses", "typing", "__future__"}
        for m in modules:
            assert m in stdlib, f"replay integration has non-stdlib import: {m}"

    def test_replay_does_not_decide_admissibility(self):
        tree = ast.parse(_REPLAY_PATH.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        joined = " ".join(imported)
        for forbidden in ["GateOutcome", "gate", "constitution", "coherence", "horizon", "evaluate"]:
            assert forbidden not in joined
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" not in func_names
