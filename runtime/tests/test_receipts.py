"""
Receipts tests — the acceptance criteria.

- receipt schema exists
- receipt links to event-log entry
- receipt links to lineage entry
- receipt records outcome and reason codes
- tampering with receipt payload fails validation
- orphan receipt fails validation
- replay can recover receipt chain
- kernel does not import receipt layer (structural: receipts is a leaf)
- receipt does not decide admissibility (no GateOutcome / evaluate / gate)
- full regression passes
"""
import ast
import importlib.util
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

EventLog = event_log.EventLog
LineageRecord = lineage.LineageRecord
build_lineage_from_records = lineage.build_lineage_from_records
Receipt = receipts.Receipt
EvidenceRef = receipts.EvidenceRef
ReceiptLog = receipts.ReceiptLog
ReceiptViolation = receipts.ReceiptViolation
issue_receipt = receipts.issue_receipt
verify_receipt_self = receipts.verify_receipt_self
verify_receipt_against_log = receipts.verify_receipt_against_log
verify_receipt_lineage = receipts.verify_receipt_lineage

_RECEIPTS_PATH = _LAYERS / "receipts" / "receipts.py"


def _scenario():
    """Event log + lineage + a receipt for transformation 'c'."""
    log = EventLog()
    log.append("s", 0, "transformation_proposed", {"id": "a"})
    log.append("s", 1, "transformation_proposed", {"id": "b"})
    rc = log.append("s", 2, "gate_evaluated", {"id": "c", "outcome": "EXECUTE"})

    lg = build_lineage_from_records([
        LineageRecord("a", 0, ()),
        LineageRecord("b", 1, ()),
        LineageRecord("c", 2, ("a", "b")),
    ])

    receipt = issue_receipt(
        receipt_id="r-c",
        transformation_id="c",
        lineage_transformation_id="c",
        event_seq=rc.seq,
        event_content_hash=rc.content_hash,
        outcome="EXECUTE",
        reason_codes=("clean_small_commit",),
        evidence_refs=(EvidenceRef("event", str(rc.seq)),),
    )
    return log, lg, receipt


class TestSchemaExists:
    def test_receipt_fields(self):
        _, _, r = _scenario()
        for fld in ("receipt_id", "transformation_id", "lineage_transformation_id",
                    "event_seq", "event_content_hash", "outcome", "reason_codes",
                    "evidence_refs", "receipt_hash"):
            assert hasattr(r, fld)

    def test_receipt_serialises(self):
        _, _, r = _scenario()
        d = r.to_dict()
        assert d["outcome"] == "EXECUTE"
        assert d["reason_codes"] == ["clean_small_commit"]


class TestLinksToEventLog:
    def test_receipt_verifies_against_log(self):
        log, _, r = _scenario()
        assert verify_receipt_against_log(r, log)

    def test_binding_breaks_if_event_altered(self):
        log, _, r = _scenario()
        # Tamper the bound event in a fresh log: rebuild with a different payload.
        bad = EventLog()
        bad.append("s", 0, "transformation_proposed", {"id": "a"})
        bad.append("s", 1, "transformation_proposed", {"id": "b"})
        bad.append("s", 2, "gate_evaluated", {"id": "c", "outcome": "REJECT"})  # different
        # The receipt's event_content_hash no longer matches the (different) event.
        assert not verify_receipt_against_log(r, bad)


class TestLinksToLineage:
    def test_receipt_verifies_against_lineage(self):
        _, lg, r = _scenario()
        assert verify_receipt_lineage(r, lg)

    def test_receipt_with_unknown_lineage_fails(self):
        _, lg, _ = _scenario()
        orphan = issue_receipt(
            receipt_id="r-ghost", transformation_id="ghost",
            lineage_transformation_id="ghost", event_seq=0,
            event_content_hash="x", outcome="EXECUTE",
        )
        assert not verify_receipt_lineage(orphan, lg)


class TestRecordsOutcomeAndReasons:
    def test_outcome_recorded_verbatim(self):
        _, _, r = _scenario()
        assert r.outcome == "EXECUTE"

    def test_reason_codes_recorded(self):
        log = EventLog()
        e = log.append("s", 0, "gate_evaluated", {})
        r = issue_receipt("r", "t", "t", e.seq, e.content_hash,
                          outcome="DEFER", reason_codes=("theta_below_floor", "hbtl_trigger"))
        assert r.reason_codes == ("theta_below_floor", "hbtl_trigger")

    def test_outcome_is_opaque_not_validated(self):
        # The receipt does NOT police the outcome vocabulary — it records what it
        # is told, as evidence. An arbitrary string is accepted (the receipt is
        # not the gate; validating verdicts would be deciding them).
        log = EventLog()
        e = log.append("s", 0, "k", {})
        r = issue_receipt("r", "t", "t", e.seq, e.content_hash, outcome="ANYTHING_THE_GATE_SAID")
        assert r.outcome == "ANYTHING_THE_GATE_SAID"
        assert verify_receipt_self(r)


class TestPayloadTamperingFails:
    def test_tampered_outcome_fails_self_verify(self):
        _, _, r = _scenario()
        # Forge a receipt with a changed outcome but the original hash.
        forged = Receipt(
            receipt_id=r.receipt_id, transformation_id=r.transformation_id,
            lineage_transformation_id=r.lineage_transformation_id,
            event_seq=r.event_seq, event_content_hash=r.event_content_hash,
            outcome="REJECT",  # changed from EXECUTE
            reason_codes=r.reason_codes, evidence_refs=r.evidence_refs,
            receipt_hash=r.receipt_hash,  # stale
        )
        assert not verify_receipt_self(forged)

    def test_tampered_reason_codes_fail(self):
        _, _, r = _scenario()
        forged = Receipt(
            receipt_id=r.receipt_id, transformation_id=r.transformation_id,
            lineage_transformation_id=r.lineage_transformation_id,
            event_seq=r.event_seq, event_content_hash=r.event_content_hash,
            outcome=r.outcome, reason_codes=("fabricated",),
            evidence_refs=r.evidence_refs, receipt_hash=r.receipt_hash,
        )
        assert not verify_receipt_self(forged)

    def test_receiptlog_rejects_tampered_on_add(self):
        _, _, r = _scenario()
        forged = Receipt(
            receipt_id=r.receipt_id, transformation_id=r.transformation_id,
            lineage_transformation_id=r.lineage_transformation_id,
            event_seq=r.event_seq, event_content_hash=r.event_content_hash,
            outcome="REJECT", reason_codes=r.reason_codes,
            evidence_refs=r.evidence_refs, receipt_hash=r.receipt_hash,
        )
        log = ReceiptLog()
        with pytest.raises(ReceiptViolation):
            log.add(forged)


class TestOrphanReceiptFails:
    def test_orphan_event_binding_fails(self):
        log, _, _ = _scenario()
        orphan = issue_receipt("r", "t", "t", event_seq=99,
                               event_content_hash="x", outcome="EXECUTE")
        assert not verify_receipt_against_log(orphan, log)

    def test_orphan_lineage_fails(self):
        _, lg, _ = _scenario()
        orphan = issue_receipt("r", "ghost", "ghost", 0, "x", outcome="EXECUTE")
        assert not verify_receipt_lineage(orphan, lg)


class TestReplayRecoversChain:
    def test_receipt_log_roundtrip(self):
        log, lg, r = _scenario()
        rl = ReceiptLog()
        rl.add(r)
        restored = ReceiptLog.deserialize(rl.serialize())
        assert restored.replay_order() == rl.replay_order()
        assert restored.receipts()[0].to_dict() == r.to_dict()

    def test_deserialize_rejects_tampered_receipt(self):
        log, lg, r = _scenario()
        rl = ReceiptLog(); rl.add(r)
        import json as _json
        line = _json.loads(rl.serialize())
        line["outcome"] = "REJECT"  # tamper, leave stale hash
        with pytest.raises(ReceiptViolation):
            ReceiptLog.deserialize(_json.dumps(line))

    def test_replay_recovers_multiple_receipts_in_order(self):
        log = EventLog()
        e0 = log.append("s", 0, "k", {})
        e1 = log.append("s", 1, "k", {})
        r0 = issue_receipt("r0", "t0", "t0", e0.seq, e0.content_hash, outcome="EXECUTE")
        r1 = issue_receipt("r1", "t1", "t1", e1.seq, e1.content_hash, outcome="DEFER")
        rl = ReceiptLog(); rl.add(r0); rl.add(r1)
        restored = ReceiptLog.deserialize(rl.serialize())
        assert restored.replay_order() == ["r0", "r1"]


class TestNoKernelCoupling:
    def test_receipts_imports_only_stdlib(self):
        tree = ast.parse(_RECEIPTS_PATH.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"hashlib", "json", "dataclasses", "typing", "__future__"}
        for m in modules:
            assert m in stdlib, f"receipts has non-stdlib import: {m}"

    def test_receipts_does_not_decide_admissibility(self):
        src = _RECEIPTS_PATH.read_text()
        tree = ast.parse(src)
        # Structural check: receipts must not IMPORT the outcome enum or any
        # kernel decision module. (We check imports via AST rather than substring,
        # because the module's docstring legitimately MENTIONS GateOutcome while
        # explaining why it deliberately does not import it.)
        imported_names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.append(node.module)
                imported_names.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported_names.extend(a.name for a in node.names)
        joined = " ".join(imported_names)
        for forbidden in ["GateOutcome", "gate", "constitution", "coherence", "horizon", "evaluate"]:
            assert forbidden not in joined, f"receipts imports {forbidden}"
        # And it defines no evaluate function (records outcomes, never produces).
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" not in func_names
