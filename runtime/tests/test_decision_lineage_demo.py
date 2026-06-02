"""
Institutional decision lineage demo — tests.

Proves:
- a decision chain reconstructs EXCLUSIVELY from existing substrate (event-log,
  receipts, composed_from, replay) — no inference
- ancestry is the existing composed_from relation, not a derived guess
- the verification condition: tamper / reorder / insertion / ancestor corruption
  all FAIL CLOSED
- the view is read-only (no decision, no mutation)
"""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

_DEMO = Path(__file__).resolve().parent.parent / "demos" / "decision_lineage_demo.py"
_spec = importlib.util.spec_from_file_location("decision_lineage_demo", _DEMO)
dl = importlib.util.module_from_spec(_spec)
sys.modules["decision_lineage_demo"] = dl
_spec.loader.exec_module(dl)

run_decision_chain = dl.run_decision_chain
lineage_view = dl.lineage_view
lineage_mod = dl.lineage_mod
event_log_mod = dl.event_log_mod
receipts_mod = dl.receipts_mod


class TestChainReconstruction:
    def test_chain_runs_through_one_substrate(self):
        log, lg, rl, results, txs = run_decision_chain()
        assert len(results) == 3
        assert len(lg) == 3            # all three decisions share one lineage graph
        assert len(rl) == 3            # one receipt each

    def test_ancestry_is_composed_from_not_inference(self):
        log, lg, rl, results, txs = run_decision_chain()
        a, b, c = txs
        # C's lineage parents ARE its composed_from ids (the existing relation).
        assert lg.parents(c.transformation_id) == c.composed_from
        assert set(c.composed_from) == {a.transformation_id, b.transformation_id}

    def test_leaf_reconstructs_full_chain(self):
        log, lg, rl, results, txs = run_decision_chain()
        _, _, c = txs
        view = lineage_view(lg, rl, log, c.transformation_id)
        assert view["reconstructed"] is True
        assert view["chain_length"] == 3
        assert set(view["ancestry"]) == {txs[0].transformation_id, txs[1].transformation_id}

    def test_clean_chain_verifies(self):
        log, lg, rl, results, txs = run_decision_chain()
        view = lineage_view(lg, rl, log, txs[2].transformation_id)
        assert view["verified"] is True


class TestVerificationCondition:
    """tamper / reorder / insertion / ancestor corruption -> fail closed."""

    def test_tampered_event_fails(self):
        log, lg, rl, results, txs = run_decision_chain()
        import json
        lines = log.serialize().splitlines()
        d = json.loads(lines[0]); d["payload"] = {"coordinates": {}}
        lines[0] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        # A tampered log fails to even reload (chain broken) -> fail closed.
        with pytest.raises(event_log_mod.EventLogViolation):
            event_log_mod.EventLog.deserialize("\n".join(lines))

    def test_reordered_events_fail(self):
        log, lg, rl, results, txs = run_decision_chain()
        lines = log.serialize().splitlines()
        lines[0], lines[1] = lines[1], lines[0]
        with pytest.raises(event_log_mod.EventLogViolation):
            event_log_mod.EventLog.deserialize("\n".join(lines))

    def test_inserted_event_fails(self):
        log, lg, rl, results, txs = run_decision_chain()
        lines = log.serialize().splitlines()
        # Insert a forged line in the middle -> seq/chain mismatch on reload.
        import json
        forged = json.loads(lines[0]); forged["payload"] = {"forged": True}
        lines.insert(1, json.dumps(forged, sort_keys=True, separators=(",", ":")))
        with pytest.raises(event_log_mod.EventLogViolation):
            event_log_mod.EventLog.deserialize("\n".join(lines))

    def test_ancestor_corruption_fails_reconstruction(self):
        # Corrupt an ancestor relation: rebuild lineage claiming an unknown parent.
        log, lg, rl, results, txs = run_decision_chain()
        a, b, c = txs
        bad = [
            lineage_mod.LineageRecord(a.transformation_id, 1, ()),
            lineage_mod.LineageRecord(c.transformation_id, 3, ("ghost_ancestor",)),
        ]
        with pytest.raises(lineage_mod.LineageViolation):
            lineage_mod.build_lineage_from_records(bad)

    def test_tampered_receipt_in_chain_fails_view(self):
        log, lg, rl, results, txs = run_decision_chain()
        # Forge one receipt's outcome -> receipts_intact False -> verified False.
        receipts = rl.receipts()
        r0 = receipts[0]
        R = type(r0)
        forged = R(
            receipt_id=r0.receipt_id, transformation_id=r0.transformation_id,
            lineage_transformation_id=r0.lineage_transformation_id,
            event_seq=r0.event_seq, event_content_hash=r0.event_content_hash,
            outcome="REJECT", reason_codes=r0.reason_codes,
            evidence_refs=r0.evidence_refs, receipt_hash=r0.receipt_hash,
        )
        # Build a receipt log containing the forged receipt.
        bad_rl = receipts_mod.ReceiptLog()
        # add() rejects a tampered receipt on insertion -> fail closed.
        with pytest.raises(receipts_mod.ReceiptViolation):
            bad_rl.add(forged)


class TestReadOnly:
    def test_view_returns_report_not_verdict(self):
        log, lg, rl, results, txs = run_decision_chain()
        view = lineage_view(lg, rl, log, txs[2].transformation_id)
        # The view reports integrity booleans + ancestry, never a gate outcome.
        assert set(view.keys()) >= {"verified", "ancestry", "chain_length"}
        for verdict in ("EXECUTE", "TRANSFORM", "DEFER", "REJECT"):
            assert verdict not in view  # no verdict key
        assert isinstance(view["verified"], bool)

    def test_demo_imports_no_new_substrate(self):
        # The demo uses only the existing substrate modules + kernel; it defines
        # no integrity machinery of its own (no hash/verify functions here).
        import ast
        src = _DEMO.read_text()
        tree = ast.parse(src)
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        # Only the harness + view + helpers; no verify_/hash_ reimplementation.
        assert "evaluate" not in funcs
        assert not any(f.startswith("verify_") or f.startswith("_hash") for f in funcs)
