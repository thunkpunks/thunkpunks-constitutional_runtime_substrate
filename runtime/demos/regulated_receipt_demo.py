"""
Regulated Transformation Receipt — demonstration.

FICTIONAL workflow. REAL circuit. GENUINE receipt.

Scenario (clearly fictional, illustrative only):
  A clinical decision-support system proposes a transformation that would cross
  from "decision-support only" into "write-back" (mutating a patient record).
  This is the regulated high-stakes step: the question an auditor asks is not
  "was the model good" but "can the organisation prove what was decided, under
  what constraints, on what evidence, by what authority — and that the record
  was not altered afterward?"

What this demo proves ordinary orchestration stacks cannot natively do:
  - the decision is bound to an APPEND-ONLY, HASH-CHAINED event
  - the outcome is recorded as evidence but PRODUCED only by the kernel
  - the receipt is TAMPER-EVIDENT: altering any link makes verify_* return False
  - the whole thing REPLAYS deterministically
  - the auditor view is READ-ONLY: it cannot change what it inspects

Discipline (per continuation contract):
  - no new authority: the demo only RUNS the existing closed circuit.
  - no synthetic receipt: the receipt is a genuine product of run_loop over the
    real gate. The workflow is fiction; the evidence is real.
  - the auditor view lives in OBSERVABILITY: it reads snapshots, emits
    non-authoritative observations, and structurally cannot influence the outcome.
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from runtime.components.gate import evaluate, GateInput, GateThresholds
from runtime.core.types import FieldState, Transformation

_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"
_OBS_DIR = Path(__file__).resolve().parent.parent / "layers" / "observability-layer" / "observability"


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
obs_mod = _load("observability", _OBS_DIR / "observability.py")

_COORDS = sp_mod.COORDINATES


def run_regulated_workflow():
    """
    Run the fictional clinical write-back proposal through the REAL closed
    circuit. Returns (receipt, event_log, lineage_graph, receipt_log, loop_result).
    """
    # Observed runtime state at the moment of the proposed write-back.
    # Omega = remaining optionality, Theta = renegotiability, tau = commitment
    # depth, NSV = irrecoverable residue. A write-back to a patient record is a
    # high-commitment, low-renegotiability, residue-bearing step.
    observed = {
        "Omega": 0.45, "rho": 0.10, "kappa": 0.05,
        "tau": 0.55, "Theta": 0.40, "NSV": 0.15,
    }
    observation = {"coordinates": {
        n: {"populated": True, "value": observed[n], "confidence": 1.0} for n in _COORDS
    }}

    # The proposed transformation: cross into write-back. Irreversible, commits
    # depth, leaves residue (a written record cannot be un-written, only corrected).
    proposal = Transformation.new(
        typed_effects={"tau": 0.30, "NSV": 0.25, "Theta": -0.20},
        description="clinical decision-support -> write-back to patient record",
    )

    log = event_log_mod.EventLog()
    lineage_graph = lineage_mod.LineageGraph()
    receipt_log = receipts_mod.ReceiptLog()

    result = loop_mod.run_loop(
        observation_payload=observation,
        transformation=proposal,
        logical_step=0,
        min_confidence=0.5,
        gate_evaluate=evaluate, gate_input_cls=GateInput,
        field_state_cls=FieldState, thresholds=GateThresholds(),
        event_log=log, state_projection_module=sp_mod,
        receipts_module=receipts_mod, lineage_module=lineage_mod,
        lineage_graph=lineage_graph, receipt_log=receipt_log,
    )
    receipt = receipt_log.receipts()[0] if len(receipt_log) else None
    return receipt, log, lineage_graph, receipt_log, result


def run_support_only_workflow():
    """
    Paired counterpart to run_regulated_workflow, SAME circuit, SAME auditor view.

    Fictional: the clinical system proposes a READ-ONLY decision-support summary
    (no write-back). Low commitment, reversible, low residue, high remaining
    optionality and renegotiability. The regulated question is identical — prove
    what was decided, on what evidence, unaltered — but the constitutional verdict
    differs because the runtime situation differs. This is the contrast: the
    separation is not a rubber stamp; the same machinery yields EXECUTE here and
    DEFER for the write-back, each provable and each tamper-evident.
    """
    observed = {
        "Omega": 0.85, "rho": 0.00, "kappa": 0.00,
        "tau": 0.15, "Theta": 0.85, "NSV": 0.02,
    }
    observation = {"coordinates": {
        n: {"populated": True, "value": observed[n], "confidence": 1.0} for n in _COORDS
    }}
    proposal = Transformation.new(
        typed_effects={"tau": 0.05, "NSV": 0.01},
        description="decision-support summary (read-only, no write-back)",
    )

    log = event_log_mod.EventLog()
    lineage_graph = lineage_mod.LineageGraph()
    receipt_log = receipts_mod.ReceiptLog()

    result = loop_mod.run_loop(
        observation_payload=observation,
        transformation=proposal,
        logical_step=0,
        min_confidence=0.5,
        gate_evaluate=evaluate, gate_input_cls=GateInput,
        field_state_cls=FieldState, thresholds=GateThresholds(),
        event_log=log, state_projection_module=sp_mod,
        receipts_module=receipts_mod, lineage_module=lineage_mod,
        lineage_graph=lineage_graph, receipt_log=receipt_log,
    )
    receipt = receipt_log.receipts()[0] if len(receipt_log) else None
    return receipt, log, lineage_graph, receipt_log, result


def run_paired_demo() -> dict:
    """
    Run BOTH fictional workflows through the SAME circuit and present the paired
    auditor view. The point: identical machinery, identical evidential guarantees,
    DIFFERENT constitutional verdicts driven by the runtime situation — each one
    provable and tamper-evident.
    """
    wb_receipt, wb_log, wb_lin, _, _ = run_regulated_workflow()
    so_receipt, so_log, so_lin, _, _ = run_support_only_workflow()

    write_back = auditor_view(wb_receipt, wb_log, wb_lin)
    support_only = auditor_view(so_receipt, so_log, so_lin)

    return {
        "write_back": write_back,        # expected DEFER (held for human review)
        "support_only": support_only,    # expected EXECUTE (admissible as proposed)
        "same_circuit": True,
        "contrast": f"{support_only['decision']} vs {write_back['decision']}",
    }


def auditor_view(receipt, event_log, lineage_graph) -> dict:
    """
    The auditor-facing READ-ONLY verification. Lives in observability semantics:
    it reads, verifies, and emits non-authoritative observations. It cannot alter
    the receipt, the log, or the outcome — it only reports whether the evidence
    holds.
    """
    self_ok = receipts_mod.verify_receipt_self(receipt)
    log_ok = receipts_mod.verify_receipt_against_log(receipt, event_log)
    lineage_ok = receipts_mod.verify_receipt_lineage(receipt, lineage_graph)
    verified = self_ok and log_ok and lineage_ok

    trace_obs = obs_mod.summarize_trace(event_log.serialize())

    return {
        "decision": receipt.outcome,                 # the kernel's verdict (recorded)
        "reason_codes": list(receipt.reason_codes),
        "receipt_self_intact": self_ok,
        "bound_event_intact": log_ok,
        "lineage_intact": lineage_ok,
        "verified": verified,
        "trace_observation": trace_obs.to_dict(),    # non-authoritative
    }
