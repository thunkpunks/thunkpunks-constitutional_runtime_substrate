"""
Replay Integration — event-log + lineage + receipts as one evidential chain.

This is NOT a new substrate. It is INTEGRATION PROOF: it exercises the three
substrate layers (event log, lineage, receipts) together and proves their
separate guarantees compose into one tamper-evident, replayable evidential
chain.

THE DISCIPLINE THAT KEEPS THIS HONEST:
  The integrator REINVENTS NO INTEGRITY MACHINERY. It coordinates the three
  layers' EXISTING verification:
    - event log: EventLog.deserialize re-verifies its hash-chain (fail-closed).
    - lineage:   build_lineage_from_records re-validates structural ancestry.
    - receipts:  ReceiptLog.deserialize re-verifies each receipt self-hash, and
                 verify_receipt_against_log / verify_receipt_lineage cross-check
                 bindings.
  If the integrator added its own hash or its own ordering rule, it would be new
  substrate masquerading as integration. It does not. It calls what exists and
  reports whether the composed chain holds.

  No admissibility decision: the integrator validates EVIDENCE, never produces a
  verdict. It does not import GateOutcome or the gate. An outcome string travels
  through it as opaque evidence (it lives on receipts), never as something the
  integrator evaluates.

WHAT REPLAY PROVES (the integration acceptance set):
  - the event log can be reloaded (chain intact)
  - lineage can be reconstructed from the recorded events
  - receipts can be recovered and validated against log + lineage
  - outcome history remains attributable (each receipt -> its event -> its lineage)
  - tampering ANYWHERE in the chain fails validation
  - replay order is deterministic
  - orphaned lineage or receipts fail
  - deletion/reorder of events breaks replay validity

DISCIPLINE: layer = runtime; status EXPERIMENTALLY_BOUNDED; imports only the
three substrate modules (by their public surfaces) and stdlib. No kernel import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


COMPONENT_VERSION = "0.1.0"


class ReplayIntegrityError(Exception):
    """Raised when the composed evidential chain fails to replay/validate."""


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of a replay integration check."""
    ok: bool
    n_events: int
    n_lineage: int
    n_receipts: int
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "n_events": self.n_events,
            "n_lineage": self.n_lineage,
            "n_receipts": self.n_receipts,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class EvidentialBundle:
    """
    The serialized form of a complete evidential chain: the three substrate logs
    as text. This is what gets persisted and replayed. It is a CONTAINER, not a
    new integrity primitive — each field is the existing layer's own serialization.
    """
    event_log_text: str
    lineage_records: list[dict[str, Any]]   # serialized LineageRecord dicts
    receipt_log_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_log_text": self.event_log_text,
            "lineage_records": self.lineage_records,
            "receipt_log_text": self.receipt_log_text,
        }


def replay_evidential_chain(
    bundle: EvidentialBundle,
    *,
    event_log_module: Any,
    lineage_module: Any,
    receipts_module: Any,
) -> ReplayResult:
    """
    Replay a complete evidential chain and validate it end-to-end.

    The substrate modules are passed in (dependency injection) rather than
    imported, so the integrator couples to their PUBLIC SURFACES, not their
    import paths — and the test harness can supply the dynamically-loaded
    modules (the substrate lives under hyphenated dirs that aren't importable).

    Returns a ReplayResult. ok=True iff every layer reloaded, reconstructed, and
    cross-validated. Any failure is collected with a reason; the function does
    not raise on validation failure (it reports), but DOES surface the substrate
    layers' own fail-closed exceptions as failures.
    """
    failures: list[str] = []

    # 1. Event log reloads with its chain intact (fail-closed on tamper).
    event_log = None
    try:
        event_log = event_log_module.EventLog.deserialize(bundle.event_log_text)
    except Exception as e:
        failures.append(f"event_log_reload_failed: {e}")

    n_events = len(event_log) if event_log is not None else 0

    # 2. Lineage reconstructs from its records (fail-closed on bad ancestry).
    lineage_graph = None
    try:
        records = [
            lineage_module.LineageRecord(
                transformation_id=r["transformation_id"],
                event_seq=r["event_seq"],
                parent_ids=tuple(r["parent_ids"]),
                receipt_content_hash=r.get("receipt_content_hash"),
            )
            for r in bundle.lineage_records
        ]
        lineage_graph = lineage_module.build_lineage_from_records(records)
    except Exception as e:
        failures.append(f"lineage_reconstruct_failed: {e}")

    n_lineage = len(lineage_graph) if lineage_graph is not None else 0

    # 3. Receipts recover with each self-hash intact (fail-closed on tamper).
    receipt_log = None
    try:
        receipt_log = receipts_module.ReceiptLog.deserialize(bundle.receipt_log_text)
    except Exception as e:
        failures.append(f"receipt_reload_failed: {e}")

    n_receipts = len(receipt_log) if receipt_log is not None else 0

    # 4. Cross-validation: every receipt binds to a real event and a real lineage.
    #    (Only attempted if all three layers reloaded — otherwise the failures
    #    above already explain the break.)
    if event_log is not None and lineage_graph is not None and receipt_log is not None:
        for receipt in receipt_log.receipts():
            if not receipts_module.verify_receipt_against_log(receipt, event_log):
                failures.append(
                    f"orphan_or_tampered_event_binding: receipt {receipt.receipt_id} "
                    f"does not bind to event seq {receipt.event_seq}"
                )
            if not receipts_module.verify_receipt_lineage(receipt, lineage_graph):
                failures.append(
                    f"orphan_lineage_binding: receipt {receipt.receipt_id} refers to "
                    f"lineage id {receipt.lineage_transformation_id} with no record"
                )

        # 5. Lineage event_seq references must point at real events (attribution).
        for tid in lineage_graph.replay_order():
            rec = lineage_graph.record(tid)
            if rec.event_seq < 0 or rec.event_seq >= n_events:
                failures.append(
                    f"orphan_lineage_event: transformation {tid} references event "
                    f"seq {rec.event_seq} which does not exist"
                )

    return ReplayResult(
        ok=(len(failures) == 0),
        n_events=n_events,
        n_lineage=n_lineage,
        n_receipts=n_receipts,
        failures=tuple(failures),
    )


def assert_replayable(
    bundle: EvidentialBundle,
    *,
    event_log_module: Any,
    lineage_module: Any,
    receipts_module: Any,
) -> ReplayResult:
    """
    Like replay_evidential_chain but raises ReplayIntegrityError on any failure.
    For callers that want fail-closed replay rather than a report.
    """
    result = replay_evidential_chain(
        bundle,
        event_log_module=event_log_module,
        lineage_module=lineage_module,
        receipts_module=receipts_module,
    )
    if not result.ok:
        raise ReplayIntegrityError("; ".join(result.failures))
    return result
