"""
Institutional Decision Lineage — demonstration (third face).

Proves that a SEQUENCE of constitutional decisions forms a provable,
tamper-evident derivation chain — reconstructed exclusively from existing
substrate: event-log, receipts, composed_from relations, and the replay
substrate. No new substrate, no new authority, no kernel change, no inference.

FICTIONAL institutional scenario (illustrative):
  A regulated decision derives from prior decisions. Decision C (e.g. a
  write-back) is proposed as a composition of prior decisions A and B (e.g. an
  intake assessment and a support summary). The institutional question is not
  "was C right" but "show me the lawful chain C rests on, and prove no ancestor
  was altered, reordered, or inserted."

HOW THE CHAIN IS BUILT (existing mechanics only):
  - Each decision is a Transformation judged by the REAL gate via the existing
    run_loop, against ONE shared substrate (event-log + lineage graph + receipts
    are injected and persist across the sequence).
  - Ancestry is established by the EXISTING Transformation.compose mechanic,
    which populates composed_from. A composed decision's lineage parents ARE its
    composed_from ids. Nothing infers ancestry; it is the recorded composition.

HOW THE CHAIN IS VERIFIED (read-only, fail-closed):
  - reconstruct: read the lineage graph's ancestry (already validated on build:
    parents precede children, no cycles, no unknown/duplicate parents).
  - integrity: every receipt still binds to its event and lineage; the event-log
    chain still verifies; reordering/insertion/ancestor-corruption breaks it.

DISCIPLINE: this file is a SEQUENCING HARNESS + READ-ONLY VIEW. It composes
decisions using existing composition, runs them through the existing loop, and
reads the result. It decides nothing; the kernel judges each decision
independently. Classification: observability (read-only).
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.components.gate import evaluate, GateInput, GateThresholds
from runtime.core.types import FieldState, Transformation

_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


event_log_mod = _load("event_log", _LAYERS / "event-log/event_log.py")
lineage_mod = _load("lineage", _LAYERS / "lineage/lineage.py")
receipts_mod = _load("receipts", _LAYERS / "receipts/receipts.py")
sp_mod = _load("state_projection", _LAYERS / "state-projection/state_projection.py")
loop_mod = _load("evidential_loop", _LAYERS / "evidential-loop/evidential_loop.py")

_COORDS = sp_mod.COORDINATES


def _observation(values):
    return {"coordinates": {
        n: {"populated": True, "value": values[n], "confidence": 1.0} for n in _COORDS
    }}


def run_decision_chain():
    """
    Run a 3-decision chain through ONE shared substrate. Each decision is judged
    by the real gate. Ancestry is established via the existing compose mechanic.

    Returns (event_log, lineage_graph, receipt_log, [LoopResults], [transformations]).
    """
    log = event_log_mod.EventLog()
    lineage_graph = lineage_mod.LineageGraph()
    receipt_log = receipts_mod.ReceiptLog()

    # Decision A: an intake assessment (primitive — no ancestry).
    a = Transformation.new(
        typed_effects={"tau": 0.05, "NSV": 0.01},
        description="intake assessment (read-only)",
    )
    # Decision B: a support summary (primitive).
    b = Transformation.new(
        typed_effects={"tau": 0.05, "NSV": 0.01},
        description="decision-support summary (read-only)",
    )
    # Decision C: a write-back, COMPOSED from A and B (existing compose mechanic
    # populates composed_from -> these become C's lineage parents).
    c = Transformation.compose(a, b)

    results = []
    transformations = [a, b, c]
    states = [
        {"Omega": 0.85, "rho": 0.0, "kappa": 0.0, "tau": 0.15, "Theta": 0.85, "NSV": 0.02},
        {"Omega": 0.80, "rho": 0.0, "kappa": 0.0, "tau": 0.20, "Theta": 0.80, "NSV": 0.03},
        {"Omega": 0.45, "rho": 0.10, "kappa": 0.05, "tau": 0.55, "Theta": 0.40, "NSV": 0.15},
    ]

    for i, (t, st) in enumerate(zip(transformations, states)):
        result = loop_mod.run_loop(
            observation_payload=_observation(st),
            transformation=t,
            logical_step=i * 2,            # each loop uses logical_step and +1
            min_confidence=0.5,
            gate_evaluate=evaluate, gate_input_cls=GateInput,
            field_state_cls=FieldState, thresholds=GateThresholds(),
            event_log=log, state_projection_module=sp_mod,
            receipts_module=receipts_mod, lineage_module=lineage_mod,
            lineage_graph=lineage_graph, receipt_log=receipt_log,
        )
        results.append(result)

    return log, lineage_graph, receipt_log, results, transformations


def lineage_view(lineage_graph, receipt_log, event_log, leaf_transformation_id) -> dict:
    """
    Read-only institutional decision lineage view.

    Reconstructs the derivation chain of a leaf decision and verifies integrity
    across the whole chain. Reads only; reports only; decides nothing.
    """
    leaf_record = lineage_graph.record(leaf_transformation_id)
    if leaf_record is None:
        return {"reconstructed": False, "reason": "no lineage record for leaf"}

    # Reconstruct ancestry (already structurally validated on graph build).
    ancestry = lineage_graph.ancestry(leaf_transformation_id)
    chain = [leaf_transformation_id] + ancestry

    # Integrity: event-log chain intact, and every receipt binds to event+lineage.
    log_intact = event_log.verify_integrity()
    receipts_intact = all(
        receipts_mod.verify_receipt_against_log(r, event_log)
        and receipts_mod.verify_receipt_lineage(r, lineage_graph)
        for r in receipt_log.receipts()
    )
    replay_order_intact = lineage_graph.validate_replayable()

    verified = log_intact and receipts_intact and replay_order_intact

    return {
        "reconstructed": True,
        "leaf": leaf_transformation_id,
        "ancestry": ancestry,                 # parents, nearest-first
        "chain_length": len(chain),
        "log_intact": log_intact,
        "receipts_intact": receipts_intact,
        "replay_order_intact": replay_order_intact,
        "verified": verified,
    }
