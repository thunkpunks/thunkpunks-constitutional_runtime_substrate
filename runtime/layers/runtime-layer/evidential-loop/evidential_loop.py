"""
End-to-End Evidential Kernel Loop — closing the circuit.

Proves the substrate can carry a typed observation all the way through the
kernel and back into evidence, with NO authority leakage:

  observation -> event-log -> state projection -> FieldState
              -> gate evaluation (the REAL kernel) -> receipt -> lineage -> replay

THE STRUCTURAL PROOF OF NON-LEAKAGE:
  This loop is a COORDINATOR that sits OUTSIDE both the kernel and the substrate.
  - The substrate layers (event-log, projection, receipts, lineage, replay) do
    not import the kernel.
  - The kernel (gate, constitution, ...) does not import the substrate.
  - The loop imports both and wires them together by passing values across the
    declared boundary (a projected FieldState handed to gate.evaluate; the
    verdict recorded as an opaque outcome string on a receipt).
  If the loop can connect them without either importing the other, the
  separation is real — proven by construction, not asserted.

  The kernel decides admissibility (it is the only thing that calls evaluate and
  produces a GateOutcome). Every substrate layer only RECORDS what happened. The
  outcome crosses back into the substrate as an OPAQUE STRING on a receipt; no
  substrate layer evaluates, re-derives, or polices it.

DISCIPLINE: layer = runtime-integration; status EXPERIMENTALLY_BOUNDED. The
substrate modules are injected (they live under hyphenated dirs); the kernel is
imported normally. Adds no new substrate and no new capability — it orchestrates
existing pieces and proves the circuit holds.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"


class LoopIntegrityError(Exception):
    """Raised when the end-to-end loop fails to run or replay consistently."""


@dataclass(frozen=True)
class LoopResult:
    """The artefacts produced by one pass through the loop."""
    event_seqs: tuple[int, ...]        # the events recorded (observation, gate result)
    projection_status: str             # READY | MEASUREMENT_HOLD
    field_state: Optional[dict]        # the projected FieldState (None if held)
    outcome: Optional[str]             # the gate verdict (None if held before gate)
    reason_codes: tuple[str, ...]
    receipt_id: Optional[str]
    lineage_transformation_id: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_seqs": list(self.event_seqs),
            "projection_status": self.projection_status,
            "field_state": self.field_state,
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "receipt_id": self.receipt_id,
            "lineage_transformation_id": self.lineage_transformation_id,
        }


def run_loop(
    *,
    observation_payload: dict[str, Any],
    transformation,                 # a kernel Transformation (the proposal)
    logical_step: int,
    min_confidence: float,
    # kernel (imported normally by the caller and passed in, to keep this module
    # importable without the kernel on the path; the caller supplies the real one)
    gate_evaluate,                  # gate.evaluate
    gate_input_cls,                 # gate.GateInput
    field_state_cls,                # core.types.FieldState
    thresholds,                     # gate.GateThresholds
    # substrate modules (injected; live under hyphenated dirs)
    event_log,                      # an EventLog instance
    state_projection_module,
    receipts_module,
    lineage_module,
    lineage_graph,                  # a LineageGraph being built across the loop
    receipt_log,                    # a ReceiptLog the loop appends issued receipts to
) -> LoopResult:
    """
    Run one observation through the full evidential kernel loop.

    Steps:
      1. Record the observation as an event (event-log).
      2. Project that event into a FieldState (state-projection), bound to it.
      3. If projection HOLDS, stop here (honest: no FieldState to evaluate).
      4. Otherwise build the FieldState and hand it across the declared boundary
         to the REAL gate (kernel decides).
      5. Record the gate result as an event; issue a receipt binding the outcome
         (opaque) to that event and the transformation's lineage.
      6. Link lineage: the transformation and its event.

    Returns a LoopResult capturing every artefact, so replay can reconstruct it.
    """
    event_seqs: list[int] = []

    # 1. Record observation.
    obs_event = event_log.append(
        "loop", logical_step, "observation_recorded", observation_payload
    )
    event_seqs.append(obs_event.seq)

    # 2. Project (bound to the observation event).
    projection = state_projection_module.project_from_log(
        event_log, obs_event.seq, logical_step=logical_step, min_confidence=min_confidence
    )

    # 3. Honest hold: if projection did not yield a complete FieldState, stop.
    if projection.status != "READY":
        return LoopResult(
            event_seqs=tuple(event_seqs),
            projection_status=projection.status,
            field_state=None, outcome=None,
            reason_codes=projection.reason_codes,
            receipt_id=None, lineage_transformation_id=None,
        )

    # 4. Build FieldState and cross the declared boundary into the REAL kernel.
    fs = projection.field_state
    field_state = field_state_cls(
        Omega=fs["Omega"], rho=fs["rho"], kappa=fs["kappa"],
        tau=fs["tau"], Theta=fs["Theta"], NSV=fs["NSV"],
        logical_step=fs["logical_step"],
    )
    gate_out = gate_evaluate(gate_input_cls(
        current_state=field_state, transformation=transformation, thresholds=thresholds,
    ))
    outcome_str = gate_out.outcome.value                 # recorded as OPAQUE evidence
    reason_strs = tuple(r.value for r in gate_out.reason_codes)

    # 5. Record the gate result as an event; issue a receipt.
    result_event = event_log.append(
        "loop", logical_step + 1, "gate_evaluated",
        {"transformation_id": transformation.transformation_id, "outcome": outcome_str},
    )
    event_seqs.append(result_event.seq)

    # 6. Lineage: link the transformation (and its composed_from ancestry) to the
    #    event that recorded it.
    lineage_record = lineage_module.lineage_record_from_transformation(
        transformation_id=transformation.transformation_id,
        composed_from=transformation.composed_from,
        event_seq=result_event.seq,
        receipt_content_hash=result_event.content_hash,
    )
    lineage_graph.add(lineage_record)

    receipt = receipts_module.issue_receipt(
        receipt_id=f"r-{transformation.transformation_id[:8]}",
        transformation_id=transformation.transformation_id,
        lineage_transformation_id=transformation.transformation_id,
        event_seq=result_event.seq,
        event_content_hash=result_event.content_hash,
        outcome=outcome_str,                              # opaque: the gate's verdict
        reason_codes=reason_strs,
        evidence_refs=(
            receipts_module.EvidenceRef("observation_event", str(obs_event.seq)),
            receipts_module.EvidenceRef("projection", projection.projection_id),
        ),
    )
    receipt_log.add(receipt)

    return LoopResult(
        event_seqs=tuple(event_seqs),
        projection_status="READY",
        field_state=fs,
        outcome=outcome_str,
        reason_codes=reason_strs,
        receipt_id=receipt.receipt_id,
        lineage_transformation_id=transformation.transformation_id,
    )
