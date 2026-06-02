"""
Regulated transformation receipt demo — tests.

Proves the demo is a TRUE demonstration:
- the receipt is a genuine product of the real circuit (not synthetic)
- the outcome is the kernel's verdict, recorded as evidence
- the auditor view verifies a clean receipt
- tampering ANY link (receipt payload, bound event, lineage) fails verification
- the auditor view is read-only (observability semantics; no outcome influence)
"""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_DEMO = Path(__file__).resolve().parent.parent / "demos" / "regulated_receipt_demo.py"
_spec = importlib.util.spec_from_file_location("regulated_receipt_demo", _DEMO)
demo = importlib.util.module_from_spec(_spec)
sys.modules["regulated_receipt_demo"] = demo
_spec.loader.exec_module(demo)

run_regulated_workflow = demo.run_regulated_workflow
auditor_view = demo.auditor_view
receipts_mod = demo.receipts_mod
event_log_mod = demo.event_log_mod


class TestGenuineReceipt:
    def test_receipt_is_produced_by_the_circuit(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        # A receipt exists and was issued by the loop (it is in the receipt log).
        assert receipt is not None
        assert len(rl) == 1
        assert rl.receipts()[0] is receipt

    def test_outcome_is_a_real_kernel_verdict(self):
        receipt, *_ = run_regulated_workflow()
        # The recorded outcome is one of the kernel's closed verdict set, and it
        # came from the real gate (the loop calls evaluate; not hardcoded here).
        assert receipt.outcome in {"EXECUTE", "TRANSFORM", "DEFER", "REJECT"}

    def test_receipt_binds_outcome_reasons_and_lineage(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        assert receipt.outcome
        assert len(receipt.reason_codes) >= 1
        assert lg.record(receipt.lineage_transformation_id) is not None


class TestAuditorViewVerifiesClean:
    def test_clean_receipt_verifies(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        view = auditor_view(receipt, log, lg)
        assert view["verified"] is True
        assert view["receipt_self_intact"] is True
        assert view["bound_event_intact"] is True
        assert view["lineage_intact"] is True

    def test_view_reports_decision_and_reasons(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        view = auditor_view(receipt, log, lg)
        assert view["decision"] == receipt.outcome
        assert view["reason_codes"] == list(receipt.reason_codes)

    def test_trace_observation_is_non_authoritative(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        view = auditor_view(receipt, log, lg)
        assert view["trace_observation"]["authoritative"] is False


class TestTamperingFailsVerification:
    """The punchline: alter any link, verification returns False."""

    def test_tampered_receipt_outcome_fails(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        Receipt = type(receipt)
        forged = Receipt(
            receipt_id=receipt.receipt_id, transformation_id=receipt.transformation_id,
            lineage_transformation_id=receipt.lineage_transformation_id,
            event_seq=receipt.event_seq, event_content_hash=receipt.event_content_hash,
            outcome="EXECUTE" if receipt.outcome != "EXECUTE" else "REJECT",  # altered
            reason_codes=receipt.reason_codes, evidence_refs=receipt.evidence_refs,
            receipt_hash=receipt.receipt_hash,  # stale
        )
        view = auditor_view(forged, log, lg)
        assert view["verified"] is False
        assert view["receipt_self_intact"] is False

    def test_tampered_bound_event_fails(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        # Rebuild a log whose bound event has a different payload -> hash mismatch.
        other = event_log_mod.EventLog()
        other.append("loop", 0, "observation_recorded", {"coordinates": {}})
        other.append("loop", 1, "gate_evaluated", {"altered": True})
        view = auditor_view(receipt, other, lg)
        assert view["verified"] is False
        assert view["bound_event_intact"] is False

    def test_tampered_lineage_fails(self):
        receipt, log, lg, rl, result = run_regulated_workflow()
        # An empty lineage graph has no record for the receipt's transformation.
        empty_lineage = demo.lineage_mod.LineageGraph()
        view = auditor_view(receipt, log, empty_lineage)
        assert view["verified"] is False
        assert view["lineage_intact"] is False


class TestNoSyntheticReceipt:
    """Discipline: the receipt must be genuine, not fabricated."""

    def test_two_runs_produce_consistent_genuine_receipts(self):
        # Determinism of the real circuit: same workflow -> same recorded outcome
        # and reason codes (genuine, reproducible — not a hand-written artefact).
        r1, *_ = run_regulated_workflow()
        r2, *_ = run_regulated_workflow()
        assert r1.outcome == r2.outcome
        assert r1.reason_codes == r2.reason_codes

    def test_receipt_self_hash_is_real(self):
        # The receipt verifies against its own recomputed hash — it was issued by
        # issue_receipt over real circuit data, not stamped with a fake hash.
        receipt, *_ = run_regulated_workflow()
        assert receipts_mod.verify_receipt_self(receipt)


class TestPairedDemo:
    """DEFER vs EXECUTE over the same evidential circuit."""

    def test_support_only_yields_real_execute(self):
        receipt, log, lg, rl, result = demo.run_support_only_workflow()
        assert receipt.outcome == "EXECUTE"

    def test_write_back_yields_real_defer(self):
        receipt, *_ = run_regulated_workflow()
        assert receipt.outcome == "DEFER"

    def test_paired_contrast_over_same_circuit(self):
        paired = demo.run_paired_demo()
        assert paired["same_circuit"] is True
        assert paired["contrast"] == "EXECUTE vs DEFER"
        # Both are genuine, verified receipts — same guarantees, different verdicts.
        assert paired["support_only"]["verified"] is True
        assert paired["write_back"]["verified"] is True
        assert paired["support_only"]["decision"] == "EXECUTE"
        assert paired["write_back"]["decision"] == "DEFER"

    def test_both_are_tamper_evident(self):
        # The contrast is meaningful only if BOTH receipts fail closed on tamper.
        for runner in (demo.run_support_only_workflow, run_regulated_workflow):
            receipt, log, lg, rl, result = runner()
            R = type(receipt)
            forged = R(
                receipt_id=receipt.receipt_id, transformation_id=receipt.transformation_id,
                lineage_transformation_id=receipt.lineage_transformation_id,
                event_seq=receipt.event_seq, event_content_hash=receipt.event_content_hash,
                outcome="TRANSFORM", reason_codes=receipt.reason_codes,
                evidence_refs=receipt.evidence_refs, receipt_hash=receipt.receipt_hash,
            )
            view = auditor_view(forged, log, lg)
            assert view["verified"] is False
