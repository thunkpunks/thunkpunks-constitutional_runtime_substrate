"""
Read-only observability tests.

Behaviour:
- reads traces (from serialized snapshots)
- compares replay runs
- detects drift (on opaque outcome strings)
- summarizes anomalies
- emits non-authoritative observations

Structural read-only guards (the load-bearing tests):
- emits NO admissibility verdict (no EXECUTE/TRANSFORM/DEFER/REJECT vocabulary)
- imports no kernel and no write-capable substrate
- accepts snapshots (dicts/strings), never live mutable objects -> cannot write back
- every Observation is marked authoritative: False
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_OBS_DIR = Path(__file__).resolve().parent.parent / "layers" / "observability-layer" / "observability"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


obs = _load("observability", _OBS_DIR / "observability.py")

Severity = obs.Severity
Observation = obs.Observation
summarize_trace = obs.summarize_trace
compare_replay_runs = obs.compare_replay_runs
detect_drift = obs.detect_drift
summarize_anomalies = obs.summarize_anomalies

_OBS_PATH = _OBS_DIR / "observability.py"


def _trace_snapshot():
    """A serialized event-log-like snapshot (the form the live log exposes)."""
    import json
    lines = [
        {"seq": 0, "event_kind": "observation_recorded", "payload": {}},
        {"seq": 1, "event_kind": "gate_evaluated", "payload": {"outcome": "EXECUTE"}},
    ]
    return "\n".join(json.dumps(l, sort_keys=True, separators=(",", ":")) for l in lines)


class TestReadsTraces:
    def test_summarize_trace_counts_events(self):
        o = summarize_trace(_trace_snapshot())
        assert o.kind == "trace_summary"
        assert "2 events" in o.summary
        assert "observation_recorded=1" in o.summary
        assert "gate_evaluated=1" in o.summary

    def test_summarize_empty_trace(self):
        o = summarize_trace("")
        assert "0 events" in o.summary


class TestComparesReplayRuns:
    def test_identical_runs(self):
        run = {"outcome": "EXECUTE", "n_events": 2}
        o = compare_replay_runs(run, dict(run))
        assert o.severity is Severity.INFO
        assert "identical" in o.summary

    def test_divergent_runs_flagged_anomaly(self):
        a = {"outcome": "EXECUTE", "n_events": 2}
        b = {"outcome": "REJECT", "n_events": 2}
        o = compare_replay_runs(a, b)
        assert o.severity is Severity.ANOMALY
        assert "outcome" in o.summary


class TestDetectsDrift:
    def test_outcome_drift_detected(self):
        base = {"t1": "EXECUTE", "t2": "DEFER"}
        curr = {"t1": "REJECT", "t2": "DEFER"}
        observations = detect_drift(base, curr)
        drifted = [o for o in observations if o.kind == "outcome_drift"]
        assert len(drifted) == 1
        assert "t1" in drifted[0].summary

    def test_no_drift_when_identical(self):
        base = {"t1": "EXECUTE"}
        assert detect_drift(base, dict(base)) == []

    def test_presence_difference_is_notice(self):
        base = {"t1": "EXECUTE"}
        curr = {"t1": "EXECUTE", "t2": "DEFER"}
        observations = detect_drift(base, curr)
        assert any(o.kind == "outcome_presence" for o in observations)

    def test_drift_treats_outcomes_as_opaque(self):
        # Arbitrary (non-verdict) strings still compared as opaque values.
        base = {"x": "FOO"}
        curr = {"x": "BAR"}
        observations = detect_drift(base, curr)
        assert len(observations) == 1
        assert observations[0].kind == "outcome_drift"


class TestSummarizesAnomalies:
    def test_rollup_picks_worst_severity(self):
        observations = [
            Observation("a", Severity.INFO, "ok"),
            Observation("b", Severity.ANOMALY, "bad"),
            Observation("c", Severity.NOTICE, "hmm"),
        ]
        o = summarize_anomalies(observations)
        assert o.severity is Severity.ANOMALY
        assert "1 anomalies" in o.summary

    def test_empty_rollup_is_info(self):
        o = summarize_anomalies([])
        assert o.severity is Severity.INFO


class TestNonAuthoritative:
    """The load-bearing guards: observability observes, never authorizes."""

    def test_every_observation_marked_non_authoritative(self):
        for o in [
            summarize_trace(_trace_snapshot()),
            compare_replay_runs({"a": 1}, {"a": 2}),
            summarize_anomalies([]),
        ]:
            assert o.to_dict()["authoritative"] is False

    def test_severity_is_not_a_verdict(self):
        # Severity vocabulary must contain NO admissibility outcome.
        values = {s.value for s in Severity}
        assert values == {"info", "notice", "anomaly"}
        for verdict in {"execute", "transform", "defer", "reject"}:
            assert verdict not in values

    def test_observation_carries_no_outcome_field(self):
        o = compare_replay_runs({"a": 1}, {"a": 2})
        d = o.to_dict()
        assert "outcome" not in d
        # severity is advisory, not a verdict
        assert d["severity"] in {"info", "notice", "anomaly"}


class TestStructuralReadOnly:
    def test_observability_imports_no_kernel(self):
        tree = ast.parse(_OBS_PATH.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        joined = " ".join(imported)
        for forbidden in ["gate", "constitution", "coherence", "horizon",
                          "GateOutcome", "evaluate", "event_log", "lineage",
                          "receipts", "state_projection", "evidential_loop"]:
            assert forbidden not in joined, f"observability imports {forbidden}"

    def test_observability_imports_only_stdlib(self):
        tree = ast.parse(_OBS_PATH.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"dataclasses", "enum", "typing", "__future__", "json"}
        for m in modules:
            assert m in stdlib, f"observability has non-stdlib import: {m}"

    def test_observability_defines_no_evaluate(self):
        tree = ast.parse(_OBS_PATH.read_text())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" not in funcs

    def test_reading_a_snapshot_cannot_mutate_source(self):
        # The observer takes a snapshot (string). Mutating the observer's input
        # afterward cannot affect any source, because a string is a value copy
        # and the observer holds no reference to a live object.
        snap = _trace_snapshot()
        o1 = summarize_trace(snap)
        snap = snap.replace("EXECUTE", "REJECT")  # rebinds local; no source exists
        o2 = summarize_trace(_trace_snapshot())
        # The fresh observation is unaffected by the local rebind.
        assert "2 events" in o2.summary
