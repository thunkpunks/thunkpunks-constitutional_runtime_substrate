"""
State projection tests — the acceptance criteria.

- projection schema exists
- typed observations project into FieldState deterministically
- projection links back to event-log entry
- projection is replay-reconstructable
- tampered source event invalidates projection
- orphan projection fails validation
- kernel receives FieldState only through declared boundary (projection emits a
  record; it does not call the gate)
- kernel does not import projection layer
- projection does not decide admissibility
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
sp = _load("state_projection", "state-projection/state_projection.py")

EventLog = event_log.EventLog
project_event = sp.project_event
project_from_log = sp.project_from_log
verify_projection_self = sp.verify_projection_self
verify_projection_against_log = sp.verify_projection_against_log
ProjectionRecord = sp.ProjectionRecord
ProjectionViolation = sp.ProjectionViolation
COORDINATES = sp.COORDINATES

_SP_PATH = _LAYERS / "state-projection" / "state_projection.py"


def _full_payload(value=0.5, confidence=1.0):
    """A payload with all six coordinates populated."""
    return {"coordinates": {
        name: {"populated": True, "value": value, "confidence": confidence}
        for name in COORDINATES
    }}


def _log_with_observation(payload):
    log = EventLog()
    e = log.append("s", 0, "observation_recorded", payload)
    return log, e


class TestSchemaExists:
    def test_projection_record_fields(self):
        rec = project_event("p", 0, "h", _full_payload(), logical_step=0, min_confidence=0.5)
        for fld in ("projection_id", "source_event_seq", "source_content_hash",
                    "status", "field_state", "reason_codes", "projection_hash"):
            assert hasattr(rec, fld)


class TestDeterministicProjection:
    def test_full_observation_projects_to_ready_fieldstate(self):
        rec = project_event("p", 0, "h", _full_payload(value=0.3), logical_step=2, min_confidence=0.5)
        assert rec.status == "READY"
        assert rec.field_state["Omega"] == 0.3
        assert rec.field_state["logical_step"] == 2
        assert set(rec.field_state.keys()) == set(COORDINATES) | {"logical_step"}

    def test_projection_is_deterministic(self):
        p = _full_payload(value=0.42)
        r1 = project_event("p", 0, "h", p, logical_step=1, min_confidence=0.5)
        r2 = project_event("p", 0, "h", p, logical_step=1, min_confidence=0.5)
        assert r1.to_dict() == r2.to_dict()

    def test_measured_zero_is_not_a_blank(self):
        # A coordinate honestly measured as 0.0 projects to 0.0 (READY), not a hold.
        p = _full_payload()
        p["coordinates"]["Omega"] = {"populated": True, "value": 0.0, "confidence": 1.0}
        rec = project_event("p", 0, "h", p, logical_step=0, min_confidence=0.5)
        assert rec.status == "READY"
        assert rec.field_state["Omega"] == 0.0

    def test_unpopulated_coordinate_holds_not_zeroes(self):
        p = _full_payload()
        p["coordinates"]["kappa"] = {"populated": False, "value": None, "confidence": 0.0}
        rec = project_event("p", 0, "h", p, logical_step=0, min_confidence=0.5)
        assert rec.status == "MEASUREMENT_HOLD"
        assert "UNPOPULATED_COORDINATE:kappa" in rec.reason_codes
        assert rec.field_state is None

    def test_low_confidence_coordinate_holds(self):
        p = _full_payload()
        p["coordinates"]["tau"] = {"populated": True, "value": 0.4, "confidence": 0.2}
        rec = project_event("p", 0, "h", p, logical_step=0, min_confidence=0.5)
        assert rec.status == "MEASUREMENT_HOLD"
        assert "LOW_CONFIDENCE_COORDINATE:tau" in rec.reason_codes

    def test_missing_coordinate_treated_as_unpopulated(self):
        # A coordinate absent from the payload is an honest blank, not a zero.
        p = {"coordinates": {n: {"populated": True, "value": 0.5, "confidence": 1.0}
                             for n in COORDINATES if n != "NSV"}}
        rec = project_event("p", 0, "h", p, logical_step=0, min_confidence=0.5)
        assert rec.status == "MEASUREMENT_HOLD"
        assert "UNPOPULATED_COORDINATE:NSV" in rec.reason_codes


class TestLinksToEventLog:
    def test_project_from_log_binds_to_event(self):
        log, e = _log_with_observation(_full_payload())
        rec = project_from_log(log, e.seq, logical_step=0, min_confidence=0.5)
        assert rec.source_event_seq == e.seq
        assert rec.source_content_hash == e.content_hash

    def test_projection_verifies_against_log(self):
        log, e = _log_with_observation(_full_payload())
        rec = project_from_log(log, e.seq, logical_step=0, min_confidence=0.5)
        assert verify_projection_against_log(rec, log)


class TestReplayReconstruction:
    def test_projection_reconstructs_from_same_event(self):
        log, e = _log_with_observation(_full_payload(value=0.7))
        r1 = project_from_log(log, e.seq, logical_step=0, min_confidence=0.5)
        # Reload the log, reproject the same event -> identical record.
        reloaded = EventLog.deserialize(log.serialize())
        r2 = project_from_log(reloaded, e.seq, logical_step=0, min_confidence=0.5)
        assert r1.to_dict() == r2.to_dict()

    def test_projection_self_hash_verifies(self):
        rec = project_event("p", 0, "h", _full_payload(), logical_step=0, min_confidence=0.5)
        assert verify_projection_self(rec)


class TestTamperDetection:
    def test_tampered_source_event_invalidates_projection(self):
        log, e = _log_with_observation(_full_payload(value=0.5))
        rec = project_from_log(log, e.seq, logical_step=0, min_confidence=0.5)
        # Build a different log whose event 0 has a different payload -> hash differs.
        other = EventLog()
        other.append("s", 0, "observation_recorded", _full_payload(value=0.9))
        assert not verify_projection_against_log(rec, other)

    def test_tampered_projection_record_fails_self(self):
        rec = project_event("p", 0, "h", _full_payload(value=0.5), logical_step=0, min_confidence=0.5)
        forged = ProjectionRecord(
            projection_id=rec.projection_id, source_event_seq=rec.source_event_seq,
            source_content_hash=rec.source_content_hash, status=rec.status,
            field_state={**rec.field_state, "Omega": 0.99},  # tampered value
            reason_codes=rec.reason_codes, projection_hash=rec.projection_hash,  # stale
        )
        assert not verify_projection_self(forged)


class TestOrphanFails:
    def test_orphan_projection_fails_validation(self):
        log, _ = _log_with_observation(_full_payload())
        orphan = project_event("p", 99, "deadbeef", _full_payload(), logical_step=0, min_confidence=0.5)
        assert not verify_projection_against_log(orphan, log)

    def test_project_from_nonexistent_seq_raises(self):
        log, _ = _log_with_observation(_full_payload())
        with pytest.raises(ProjectionViolation):
            project_from_log(log, 99, logical_step=0, min_confidence=0.5)


class TestBoundaryAndNoDecision:
    def test_projection_emits_record_not_verdict(self):
        # Projection produces a ProjectionRecord. It does not return or contain a
        # gate outcome. The FieldState reaches the kernel only when the caller
        # hands it across the declared boundary.
        rec = project_event("p", 0, "h", _full_payload(), logical_step=0, min_confidence=0.5)
        assert rec.status in {"READY", "MEASUREMENT_HOLD"}
        # status is a projection status, NOT a gate outcome.
        assert rec.status not in {"EXECUTE", "TRANSFORM", "DEFER", "REJECT"}

    def test_projection_imports_only_stdlib(self):
        tree = ast.parse(_SP_PATH.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"hashlib", "json", "dataclasses", "typing", "__future__"}
        for m in modules:
            assert m in stdlib, f"projection has non-stdlib import: {m}"

    def test_projection_does_not_decide_admissibility(self):
        tree = ast.parse(_SP_PATH.read_text())
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
