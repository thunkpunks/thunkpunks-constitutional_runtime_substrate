"""
Lineage hardening tests — the acceptance criteria.

- lineage schema exists
- lineage entries link to event-log entries (via event_seq + receipt hash)
- parent/child transformation ancestry is preserved
- tampering with ancestry fails validation
- replay can reconstruct lineage order
- kernel imports nothing from lineage  (structural: lineage is a leaf)
- lineage does not decide admissibility (no gate/evaluate/outcome)
- full regression passes
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

# Load the event-log and lineage modules from their hyphenated-dir locations.
_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"

def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _LAYERS / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

event_log = _load("event_log", "event-log/event_log.py")
lineage = _load("lineage", "lineage/lineage.py")

EventLog = event_log.EventLog
LineageRecord = lineage.LineageRecord
LineageGraph = lineage.LineageGraph
LineageViolation = lineage.LineageViolation
lineage_record_from_transformation = lineage.lineage_record_from_transformation
build_lineage_from_records = lineage.build_lineage_from_records

_LINEAGE_PATH = _LAYERS / "lineage" / "lineage.py"


def _scenario():
    """
    A small lawful ancestry: two primitives a, b recorded, then composite c
    derived from (a, b). Returns (event_log, [records]) with event seqs assigned
    in recording order.
    """
    log = EventLog()
    ra = log.append("s", 0, "transformation_proposed", {"id": "a"})
    rb = log.append("s", 1, "transformation_proposed", {"id": "b"})
    rc = log.append("s", 2, "transformation_proposed", {"id": "c", "composed_from": ["a", "b"]})

    records = [
        lineage_record_from_transformation("a", (), event_seq=ra.seq, receipt_content_hash=ra.content_hash),
        lineage_record_from_transformation("b", (), event_seq=rb.seq, receipt_content_hash=rb.content_hash),
        lineage_record_from_transformation("c", ("a", "b"), event_seq=rc.seq, receipt_content_hash=rc.content_hash),
    ]
    return log, records


class TestSchemaExists:
    def test_lineage_record_fields(self):
        r = LineageRecord(transformation_id="t", event_seq=0, parent_ids=())
        for fld in ("transformation_id", "event_seq", "parent_ids", "receipt_content_hash"):
            assert hasattr(r, fld)

    def test_primitive_vs_derived(self):
        prim = LineageRecord("a", 0, ())
        derived = LineageRecord("c", 2, ("a", "b"))
        assert prim.is_primitive
        assert not derived.is_primitive

    def test_record_serialises(self):
        r = LineageRecord("c", 2, ("a", "b"), receipt_content_hash="abc")
        d = r.to_dict()
        assert d["parent_ids"] == ["a", "b"]
        assert d["event_seq"] == 2


class TestLinksToEventLog:
    def test_lineage_event_seq_matches_log(self):
        log, records = _scenario()
        graph = build_lineage_from_records(records)
        # Each lineage record's event_seq must point at a real log entry.
        for tid in graph.replay_order():
            rec = graph.record(tid)
            assert rec.event_seq < len(log)
            assert log.entries()[rec.event_seq].seq == rec.event_seq

    def test_receipt_hash_links_to_recording_event(self):
        log, records = _scenario()
        graph = build_lineage_from_records(records)
        # The receipt_content_hash on a lineage record must match the content
        # hash of the event at its event_seq.
        for tid in graph.replay_order():
            rec = graph.record(tid)
            assert rec.receipt_content_hash == log.entries()[rec.event_seq].content_hash


class TestAncestryPreserved:
    def test_parents_and_children(self):
        _, records = _scenario()
        g = build_lineage_from_records(records)
        assert g.parents("c") == ("a", "b")
        assert "c" in g.children("a")
        assert "c" in g.children("b")
        assert g.children("c") == ()  # nothing derives from c yet

    def test_full_ancestry_chain(self):
        # a -> c -> d : ancestry of d is [c, a]
        log = EventLog()
        records = [
            LineageRecord("a", 0, ()),
            LineageRecord("c", 1, ("a",)),
            LineageRecord("d", 2, ("c",)),
        ]
        g = build_lineage_from_records(records)
        anc = g.ancestry("d")
        assert "c" in anc and "a" in anc
        assert anc.index("c") < anc.index("a")  # nearest first

    def test_primitive_has_no_ancestry(self):
        g = build_lineage_from_records([LineageRecord("a", 0, ())])
        assert g.ancestry("a") == []


class TestTamperingFailsValidation:
    def test_lawful_forward_ancestry_accepted(self):
        # Sanity: a parent that precedes its child IS accepted (the lawful case).
        g = LineageGraph()
        g.add(LineageRecord("c", 0, ()))
        g.add(LineageRecord("d", 1, ("c",)))  # c(0) precedes d(1): lawful
        assert g.parents("d") == ("c",)

    def test_unknown_parent_rejected(self):
        g = LineageGraph()
        with pytest.raises(LineageViolation, match="no prior lineage record"):
            g.add(LineageRecord("c", 0, ("ghost",)))

    def test_self_parent_rejected(self):
        g = LineageGraph()
        with pytest.raises(LineageViolation):
            g.add(LineageRecord("c", 0, ("c",)))

    def test_duplicate_record_rejected(self):
        g = LineageGraph()
        g.add(LineageRecord("a", 0, ()))
        with pytest.raises(LineageViolation, match="already has a lineage"):
            g.add(LineageRecord("a", 1, ()))

    def test_future_parent_rejected(self):
        # Parent exists but has a LATER seq than the child — forward-flow violation.
        g = LineageGraph()
        g.add(LineageRecord("a", 5, ()))
        with pytest.raises(LineageViolation, match="precede"):
            g.add(LineageRecord("c", 3, ("a",)))  # c(3) derives from a(5): unlawful

    def test_tampered_event_log_fails_first(self):
        # If the underlying event log is tampered, it fails integrity before
        # lineage is even built — lineage inherits the log's tamper-evidence.
        log, _ = _scenario()
        import json
        lines = log.serialize().splitlines()
        d = json.loads(lines[1]); d["payload"] = {"id": "TAMPERED"}
        lines[1] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        with pytest.raises(event_log.EventLogViolation):
            EventLog.deserialize("\n".join(lines))


class TestReplayReconstruction:
    def test_replay_order_is_seq_order(self):
        _, records = _scenario()
        g = build_lineage_from_records(records)
        assert g.replay_order() == ["a", "b", "c"]

    def test_graph_is_replayable(self):
        _, records = _scenario()
        g = build_lineage_from_records(records)
        assert g.validate_replayable()

    def test_reconstruction_reproduces_graph(self):
        _, records = _scenario()
        g1 = build_lineage_from_records(records)
        # Rebuild from the same records in seq order -> identical structure.
        g2 = build_lineage_from_records(records)
        assert g1.to_dict() == g2.to_dict()

    def test_out_of_order_records_are_sorted_then_validated(self):
        # build_lineage_from_records sorts by event_seq, so supplying records
        # out of order still reconstructs lawfully.
        recs = [LineageRecord("c", 2, ("a", "b")), LineageRecord("a", 0, ()), LineageRecord("b", 1, ())]
        g = build_lineage_from_records(recs)
        assert g.replay_order() == ["a", "b", "c"]


class TestNoKernelCoupling:
    def test_lineage_imports_only_stdlib(self):
        src = _LINEAGE_PATH.read_text()
        tree = ast.parse(src)
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"dataclasses", "typing", "__future__"}
        for m in modules:
            assert m in stdlib, f"lineage has non-stdlib import: {m}"

    def test_lineage_does_not_decide_admissibility(self):
        src = _LINEAGE_PATH.read_text()
        assert "GateOutcome" not in src
        assert "def evaluate" not in src
        assert "EXECUTE" not in src and "REJECT" not in src
        # No gate/constitution/coherence/horizon imports.
        for forbidden in ["from .gate", "import gate", "constitution", "coherence", "horizon"]:
            assert forbidden not in src, f"lineage references {forbidden}"
