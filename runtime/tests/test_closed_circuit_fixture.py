"""
Canonical closed-circuit fixture.

ONE self-contained demonstration of the first working constitutional runtime
circuit, asserting each stage:

  observation -> event-log -> state projection -> FieldState
              -> gate (REAL kernel) -> receipt -> lineage -> replay

This is the frozen reference: if the circuit ever regresses, this fails. It is
both a test and the documented canonical fixture referenced by
CLOSED_CIRCUIT_REPORT.md. Run directly to see each stage:

    python runtime/tests/test_closed_circuit_fixture.py
"""
import importlib.util
import sys
from pathlib import Path

# Allow running directly (python runtime/tests/test_closed_circuit_fixture.py)
# as well as under pytest, by putting the repo root on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

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

_COORDS = sp_mod.COORDINATES


def run_canonical_circuit():
    """Run the full circuit and return a dict of per-stage artefacts."""
    # STAGE 0: a typed observation (all six coordinates honestly measured).
    values = {"Omega": 0.7, "rho": 0.0, "kappa": 0.0, "tau": 0.3, "Theta": 0.7, "NSV": 0.0}
    observation = {"coordinates": {
        n: {"populated": True, "value": values[n], "confidence": 1.0} for n in _COORDS
    }}

    # The proposal the kernel will judge against the projected state.
    transformation = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})

    # Substrate.
    log = event_log_mod.EventLog()
    lineage_graph = lineage_mod.LineageGraph()
    receipt_log = receipts_mod.ReceiptLog()

    # Run the loop (observation -> ... -> receipt + lineage).
    result = loop_mod.run_loop(
        observation_payload=observation,
        transformation=transformation,
        logical_step=0,
        min_confidence=0.5,
        gate_evaluate=evaluate, gate_input_cls=GateInput,
        field_state_cls=FieldState, thresholds=GateThresholds(),
        event_log=log, state_projection_module=sp_mod,
        receipts_module=receipts_mod, lineage_module=lineage_mod,
        lineage_graph=lineage_graph, receipt_log=receipt_log,
    )

    # REPLAY: reload everything and re-verify end to end.
    reloaded_log = event_log_mod.EventLog.deserialize(log.serialize())
    reloaded_receipts = receipts_mod.ReceiptLog.deserialize(receipt_log.serialize())
    replay_ok = (
        reloaded_log.verify_integrity()
        and all(
            receipts_mod.verify_receipt_against_log(r, reloaded_log)
            and receipts_mod.verify_receipt_lineage(r, lineage_graph)
            for r in reloaded_receipts.receipts()
        )
    )

    return {
        "observation": observation,
        "event_seqs": result.event_seqs,
        "projection_status": result.projection_status,
        "field_state": result.field_state,
        "outcome": result.outcome,
        "reason_codes": result.reason_codes,
        "receipt_id": result.receipt_id,
        "lineage_transformation_id": result.lineage_transformation_id,
        "replay_ok": replay_ok,
        "n_events": len(log),
        "n_receipts": len(receipt_log),
        "n_lineage": len(lineage_graph),
    }


def test_canonical_closed_circuit():
    """The frozen reference: the full circuit runs and replays end to end."""
    c = run_canonical_circuit()
    # observation -> event-log
    assert c["n_events"] == 2                      # observation + gate result
    assert 0 in c["event_seqs"]
    # projection -> FieldState
    assert c["projection_status"] == "READY"
    assert c["field_state"]["Omega"] == 0.7
    assert c["field_state"]["tau"] == 0.3
    # gate (REAL kernel) decides
    assert c["outcome"] == "EXECUTE"
    assert len(c["reason_codes"]) >= 1
    # receipt
    assert c["receipt_id"] is not None
    assert c["n_receipts"] == 1
    # lineage
    assert c["lineage_transformation_id"] is not None
    assert c["n_lineage"] == 1
    # replay reconstructs and verifies the whole circuit
    assert c["replay_ok"] is True


if __name__ == "__main__":
    c = run_canonical_circuit()
    print("=" * 72)
    print("CANONICAL CLOSED CIRCUIT")
    print("=" * 72)
    print(f"  observation        : 6 coordinates, all populated, confidence 1.0")
    print(f"  -> event-log       : {c['n_events']} events recorded (seqs {list(c['event_seqs'])})")
    print(f"  -> projection      : {c['projection_status']}")
    print(f"  -> FieldState      : Omega={c['field_state']['Omega']} tau={c['field_state']['tau']} ...")
    print(f"  -> gate (kernel)   : {c['outcome']}  reasons={list(c['reason_codes'])}")
    print(f"  -> receipt         : {c['receipt_id']}")
    print(f"  -> lineage         : {c['lineage_transformation_id']}")
    print(f"  -> replay          : {'VERIFIED' if c['replay_ok'] else 'FAILED'}")
    print("=" * 72)
    print("kernel decides, substrate remembers.")
