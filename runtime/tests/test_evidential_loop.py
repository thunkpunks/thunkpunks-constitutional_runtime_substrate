"""
End-to-end evidential kernel loop tests.

Closes the circuit with the REAL kernel (gate.evaluate), proving the substrate
carries an observation through projection, kernel evaluation, receipt, lineage,
and replay — with no authority leakage.

- typed observation is recorded as an event
- observation projects deterministically into FieldState
- FieldState passed to kernel only through declared boundary
- kernel evaluates without importing substrate layers (structural)
- receipt records outcome and reason codes
- lineage links observation, projection, transformation, receipt
- replay reconstructs the full loop deterministically
- tampering with event/projection/lineage/receipt invalidates replay
- substrate layers do not decide admissibility (structural)
- full regression passes
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

# Real kernel (importable).
from runtime.components.gate import evaluate, GateInput, GateThresholds
from runtime.core.types import FieldState, Transformation

_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _LAYERS / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


event_log_mod = _load("event_log", "event-log/event_log.py")
lineage_mod = _load("lineage", "lineage/lineage.py")
receipts_mod = _load("receipts", "receipts/receipts.py")
sp_mod = _load("state_projection", "state-projection/state_projection.py")
loop_mod = _load("evidential_loop", "evidential-loop/evidential_loop.py")

run_loop = loop_mod.run_loop
LoopResult = loop_mod.LoopResult

_LOOP_PATH = _LAYERS / "evidential-loop" / "evidential_loop.py"
_COORDS = sp_mod.COORDINATES


def _obs(values=None, confidence=1.0):
    """Build an observation payload with all six coords populated."""
    values = values or {"Omega": 0.7, "rho": 0.0, "kappa": 0.0, "tau": 0.3, "Theta": 0.7, "NSV": 0.0}
    return {"coordinates": {
        n: {"populated": True, "value": values[n], "confidence": confidence}
        for n in _COORDS
    }}


def _fresh_substrate():
    return (
        event_log_mod.EventLog(),
        lineage_mod.LineageGraph(),
        receipts_mod.ReceiptLog(),
    )


def _run(obs_payload, transformation, min_confidence=0.5):
    log, lg, rl = _fresh_substrate()
    result = run_loop(
        observation_payload=obs_payload,
        transformation=transformation,
        logical_step=0,
        min_confidence=min_confidence,
        gate_evaluate=evaluate, gate_input_cls=GateInput,
        field_state_cls=FieldState, thresholds=GateThresholds(),
        event_log=log, state_projection_module=sp_mod,
        receipts_module=receipts_mod, lineage_module=lineage_mod,
        lineage_graph=lg, receipt_log=rl,
    )
    return result, log, lg, rl


class TestFullLoop:
    def test_observation_recorded_as_event(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, _, _ = _run(_obs(), t)
        assert len(log) == 2  # observation + gate result
        assert log.entries()[0].event_kind == "observation_recorded"

    def test_full_loop_produces_outcome_and_receipt(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, lg, rl = _run(_obs(), t)
        assert result.projection_status == "READY"
        assert result.outcome == "EXECUTE"     # the REAL gate's verdict
        assert result.receipt_id is not None
        assert len(rl) == 1

    def test_receipt_records_outcome_and_reasons(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, lg, rl = _run(_obs(), t)
        receipt = rl.receipts()[0]
        assert receipt.outcome == "EXECUTE"
        assert len(receipt.reason_codes) >= 1

    def test_lineage_links_transformation_and_event(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, lg, rl = _run(_obs(), t)
        rec = lg.record(t.transformation_id)
        assert rec is not None
        assert rec.event_seq == result.event_seqs[1]  # the gate_evaluated event

    def test_real_gate_rejects_catastrophic(self):
        # The REAL kernel decides — a catastrophic NSV step is REJECTed.
        t = Transformation.new(typed_effects={"NSV": 0.6})
        result, log, lg, rl = _run(_obs(), t)
        assert result.outcome == "REJECT"
        assert rl.receipts()[0].outcome == "REJECT"


class TestHonestHold:
    def test_incomplete_observation_holds_before_gate(self):
        # An unpopulated coordinate -> projection holds -> gate is never called.
        obs = _obs()
        obs["coordinates"]["kappa"] = {"populated": False, "value": None, "confidence": 0.0}
        t = Transformation.new(typed_effects={"tau": 0.05})
        result, log, lg, rl = _run(obs, t)
        assert result.projection_status == "MEASUREMENT_HOLD"
        assert result.outcome is None        # gate never evaluated
        assert len(rl) == 0                  # no receipt issued
        assert len(log) == 1                 # only the observation event


class TestProjectionDeterminism:
    def test_same_observation_same_fieldstate(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        r1, *_ = _run(_obs(values={"Omega":0.6,"rho":0.1,"kappa":0.0,"tau":0.2,"Theta":0.8,"NSV":0.0}), t)
        r2, *_ = _run(_obs(values={"Omega":0.6,"rho":0.1,"kappa":0.0,"tau":0.2,"Theta":0.8,"NSV":0.0}), t)
        assert r1.field_state == r2.field_state


class TestReplayReconstruction:
    def test_full_loop_replays_deterministically(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, lg, rl = _run(_obs(), t)
        # Replay the event log + receipts; confirm they reconstruct and verify.
        reloaded_log = event_log_mod.EventLog.deserialize(log.serialize())
        assert reloaded_log.verify_integrity()
        reloaded_receipts = receipts_mod.ReceiptLog.deserialize(rl.serialize())
        # Every receipt still binds to its event and lineage after reload.
        for receipt in reloaded_receipts.receipts():
            assert receipts_mod.verify_receipt_against_log(receipt, reloaded_log)
            assert receipts_mod.verify_receipt_lineage(receipt, lg)


class TestTamperingInvalidatesReplay:
    def _scenario(self):
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        return _run(_obs(), t)

    def test_tampered_event_breaks_replay(self):
        _, log, _, _ = self._scenario()
        import json
        lines = log.serialize().splitlines()
        d = json.loads(lines[0]); d["payload"] = {"coordinates": {}}
        lines[0] = json.dumps(d, sort_keys=True, separators=(",", ":"))
        with pytest.raises(event_log_mod.EventLogViolation):
            event_log_mod.EventLog.deserialize("\n".join(lines))

    def test_tampered_receipt_breaks_replay(self):
        _, _, _, rl = self._scenario()
        import json
        line = json.loads(rl.serialize())
        line["outcome"] = "EXECUTE" if line["outcome"] != "EXECUTE" else "REJECT"
        with pytest.raises(receipts_mod.ReceiptViolation):
            receipts_mod.ReceiptLog.deserialize(json.dumps(line))

    def test_tampered_lineage_breaks_reconstruction(self):
        result, log, lg, rl = self._scenario()
        # Rebuild lineage with a corrupted ancestry -> fails.
        tid = result.lineage_transformation_id
        bad = [lineage_mod.LineageRecord(tid, lg.record(tid).event_seq, ("ghost",))]
        with pytest.raises(lineage_mod.LineageViolation):
            lineage_mod.build_lineage_from_records(bad)

    def test_tampered_projection_fails_against_log(self):
        result, log, lg, rl = self._scenario()
        # A projection bound to a mismatched content hash fails verification.
        proj = sp_mod.project_event("p", 0, "wronghash", _obs(), logical_step=0, min_confidence=0.5)
        assert not sp_mod.verify_projection_against_log(proj, log)


class TestNoAuthorityLeakage:
    """Structural: the loop wires kernel+substrate without either importing the other."""

    def test_loop_imports_no_kernel_in_substrate_modules(self):
        # Each substrate module must not import the kernel.
        for rel in ["event-log/event_log.py", "lineage/lineage.py",
                    "receipts/receipts.py", "state-projection/state_projection.py"]:
            src = (_LAYERS / rel).read_text()
            tree = ast.parse(src)
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
                elif isinstance(node, ast.Import):
                    imported.extend(a.name for a in node.names)
            joined = " ".join(imported)
            for forbidden in ["gate", "constitution", "coherence", "horizon", "GateOutcome"]:
                assert forbidden not in joined, f"{rel} imports kernel: {forbidden}"

    def test_kernel_does_not_import_substrate(self):
        # The kernel components must not import any substrate layer.
        for comp in ["gate.py", "constitution.py", "coherence.py", "horizon.py"]:
            src = (Path(__file__).resolve().parent.parent / "components" / comp).read_text()
            for forbidden in ["event_log", "lineage", "receipts", "state_projection",
                              "evidential_loop", "replay_integration"]:
                assert forbidden not in src, f"{comp} imports substrate: {forbidden}"

    def test_outcome_crosses_back_as_opaque_string(self):
        # The loop records the gate outcome as a string on the receipt; the
        # substrate never sees a GateOutcome object.
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        result, log, lg, rl = _run(_obs(), t)
        receipt = rl.receipts()[0]
        assert isinstance(receipt.outcome, str)  # opaque, not a GateOutcome enum
