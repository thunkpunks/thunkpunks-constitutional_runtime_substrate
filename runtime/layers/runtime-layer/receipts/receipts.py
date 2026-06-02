"""
Receipts — the evidence object binding an admissibility outcome to the
event-log and lineage substrate.

The event log proved entries are immutable. Lineage proved transformations have
traceable ancestry. A receipt proves the third thing: that a specific
admissibility OUTCOME was produced for a specific transformation, recorded by a
specific event, supported by specific evidence — and that this binding is
tamper-evident and replay-valid.

THE SHARPEST DISCIPLINE LINE IN THE REPO SO FAR:
  A receipt is the first substrate object that HOLDS an outcome (EXECUTE /
  TRANSFORM / DEFER / REJECT). It must RECORD a verdict the gate produced
  WITHOUT ever PRODUCING one. Therefore:
    - The receipt module does NOT import GateOutcome and does NOT know the closed
      set of legal outcomes. It stores the outcome as an opaque string the caller
      supplies. Validating "is this a legal verdict" would be a step toward
      deciding it — that is the gate's authority, not the receipt's.
    - The receipt does NOT evaluate, re-derive, or second-guess the outcome. It
      records "the gate said X" as evidence. Whether X was correct is not the
      receipt's question.

WHAT A RECEIPT BINDS (the seven the instruction names):
  - what was evaluated          -> transformation_id
  - which lineage it belongs to -> lineage_transformation_id (+ ancestry via the
                                   lineage graph, not duplicated here)
  - which event recorded it      -> event_seq + event_content_hash
  - what outcome was produced    -> outcome (opaque string, gate-supplied)
  - which reason codes emitted   -> reason_codes (opaque strings)
  - what evidence supports it    -> evidence_refs (content hashes / event seqs)
  - whether it remains replay-valid -> verify() against the event log

INTEGRITY MODEL (reuses the event log; invents no new crypto):
  A receipt is bound to an event by (event_seq, event_content_hash). Its own
  content is hashed (receipt_hash). Verification checks that the bound event
  still exists with the same content_hash (so a tampered log breaks the binding)
  and that the receipt's own content still hashes to receipt_hash (so a tampered
  receipt is detected). No parallel chain — derives from the event log's chain.

DISCIPLINE:
  - No kernel widening: records outcomes, does not produce them.
  - No GateOutcome import, no evaluate, no gate/constitution/coherence/horizon.
  - Layer: runtime. Status: EXPERIMENTALLY_BOUNDED.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"


class ReceiptViolation(Exception):
    """Raised when a receipt is structurally invalid or inconsistent with the log."""


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EvidenceRef:
    """
    A reference to a piece of evidence supporting the decision.

    kind is an opaque label (e.g. 'event', 'measurement', 'trajectory'); ref is
    the thing referred to (an event seq as string, a content hash, etc.). The
    receipt layer does not interpret evidence — it records the references so the
    decision can be audited against the substrate.
    """
    kind: str
    ref: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref}


@dataclass(frozen=True)
class Receipt:
    """
    An evidence object binding an admissibility outcome to the substrate.

    `outcome` and `reason_codes` are OPAQUE strings supplied by the caller (the
    gate's verdict, recorded as evidence). The receipt does not validate them
    against any closed set — it does not know or police the outcome vocabulary,
    because knowing it would be a step toward deciding it.
    """
    receipt_id: str
    transformation_id: str            # what was evaluated
    lineage_transformation_id: str    # which lineage it belongs to
    event_seq: int                    # which event recorded it
    event_content_hash: str           # binds to that event's content
    outcome: str                      # what outcome was produced (opaque)
    reason_codes: tuple[str, ...]     # which reason codes were emitted (opaque)
    evidence_refs: tuple[EvidenceRef, ...]  # what evidence supports the decision
    receipt_hash: str                 # hash of this receipt's own content

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "transformation_id": self.transformation_id,
            "lineage_transformation_id": self.lineage_transformation_id,
            "event_seq": self.event_seq,
            "event_content_hash": self.event_content_hash,
            "outcome": self.outcome,
            "reason_codes": list(self.reason_codes),
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "receipt_hash": self.receipt_hash,
        }

    @staticmethod
    def compute_hash(
        receipt_id: str, transformation_id: str, lineage_transformation_id: str,
        event_seq: int, event_content_hash: str, outcome: str,
        reason_codes: tuple[str, ...], evidence_refs: tuple[EvidenceRef, ...],
    ) -> str:
        return _hash(_canonical({
            "receipt_id": receipt_id,
            "transformation_id": transformation_id,
            "lineage_transformation_id": lineage_transformation_id,
            "event_seq": event_seq,
            "event_content_hash": event_content_hash,
            "outcome": outcome,
            "reason_codes": list(reason_codes),
            "evidence_refs": [e.to_dict() for e in evidence_refs],
        }))


def issue_receipt(
    receipt_id: str,
    transformation_id: str,
    lineage_transformation_id: str,
    event_seq: int,
    event_content_hash: str,
    outcome: str,
    reason_codes: tuple[str, ...] = (),
    evidence_refs: tuple[EvidenceRef, ...] = (),
) -> Receipt:
    """
    Construct a receipt with a computed integrity hash.

    NOTE: `outcome` is recorded verbatim. This function does not check that
    `outcome` is a legal gate verdict — that would be policing the gate's
    vocabulary, which is the gate's authority, not the receipt's. The receipt
    records what it was told the outcome was, as evidence.
    """
    receipt_hash = Receipt.compute_hash(
        receipt_id, transformation_id, lineage_transformation_id,
        event_seq, event_content_hash, outcome, reason_codes, evidence_refs,
    )
    return Receipt(
        receipt_id=receipt_id,
        transformation_id=transformation_id,
        lineage_transformation_id=lineage_transformation_id,
        event_seq=event_seq,
        event_content_hash=event_content_hash,
        outcome=outcome,
        reason_codes=reason_codes,
        evidence_refs=evidence_refs,
        receipt_hash=receipt_hash,
    )


def verify_receipt_self(receipt: Receipt) -> bool:
    """
    Verify a receipt's own content hashes to its stored receipt_hash.
    Detects tampering with the receipt payload (outcome, reason codes, etc.).
    """
    expected = Receipt.compute_hash(
        receipt.receipt_id, receipt.transformation_id,
        receipt.lineage_transformation_id, receipt.event_seq,
        receipt.event_content_hash, receipt.outcome,
        receipt.reason_codes, receipt.evidence_refs,
    )
    return expected == receipt.receipt_hash


def verify_receipt_against_log(receipt: Receipt, event_log: Any) -> bool:
    """
    Verify a receipt against an event log:
      1. the receipt's own content is intact (self-hash), AND
      2. the bound event exists at event_seq with the same content_hash.

    `event_log` is any object exposing `.entries()` returning items with
    `.seq` and `.content_hash` (the EventLog substrate). We accept it by duck
    type rather than importing it, to avoid coupling. An orphan receipt (bound
    to a non-existent or mismatched event) fails.
    """
    if not verify_receipt_self(receipt):
        return False
    entries = event_log.entries()
    if receipt.event_seq < 0 or receipt.event_seq >= len(entries):
        return False  # orphan: no such event
    entry = entries[receipt.event_seq]
    if entry.seq != receipt.event_seq:
        return False
    if entry.content_hash != receipt.event_content_hash:
        return False  # the bound event was altered, or receipt points elsewhere
    return True


def verify_receipt_lineage(receipt: Receipt, lineage_graph: Any) -> bool:
    """
    Verify the receipt's lineage binding: the lineage_transformation_id must be a
    known transformation in the lineage graph. `lineage_graph` is accepted by
    duck type (exposing `.record(id)`), to avoid importing the lineage module.

    An orphan receipt (referring to a transformation with no lineage record)
    fails — a receipt must belong to a traceable lineage.
    """
    return lineage_graph.record(receipt.lineage_transformation_id) is not None


class ReceiptLog:
    """
    An append-only collection of receipts, replay-recoverable.

    Like the event log and lineage, receipts are recorded in order and the log
    can be serialized and reconstructed. Reconstruction re-verifies each
    receipt's self-hash (fail-closed on a tampered receipt).
    """

    def __init__(self) -> None:
        self._receipts: list[Receipt] = []

    def add(self, receipt: Receipt) -> None:
        if not verify_receipt_self(receipt):
            raise ReceiptViolation(
                f"receipt {receipt.receipt_id} failed self-hash verification "
                f"(payload tampered before insertion)"
            )
        self._receipts.append(receipt)

    def receipts(self) -> list[Receipt]:
        return list(self._receipts)

    def by_transformation(self, transformation_id: str) -> list[Receipt]:
        return [r for r in self._receipts if r.transformation_id == transformation_id]

    def replay_order(self) -> list[str]:
        """Receipt ids in recorded order — the replay chain."""
        return [r.receipt_id for r in self._receipts]

    def serialize(self) -> str:
        return "\n".join(_canonical(r.to_dict()) for r in self._receipts)

    @staticmethod
    def deserialize(text: str) -> "ReceiptLog":
        """Reconstruct, re-verifying each receipt's self-hash. Fail-closed."""
        log = ReceiptLog()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            receipt = Receipt(
                receipt_id=d["receipt_id"],
                transformation_id=d["transformation_id"],
                lineage_transformation_id=d["lineage_transformation_id"],
                event_seq=d["event_seq"],
                event_content_hash=d["event_content_hash"],
                outcome=d["outcome"],
                reason_codes=tuple(d["reason_codes"]),
                evidence_refs=tuple(
                    EvidenceRef(kind=e["kind"], ref=e["ref"]) for e in d["evidence_refs"]
                ),
                receipt_hash=d["receipt_hash"],
            )
            if not verify_receipt_self(receipt):
                raise ReceiptViolation(
                    f"receipt {receipt.receipt_id} failed verification on load "
                    f"(tampering detected)"
                )
            log._receipts.append(receipt)
        return log

    def __len__(self) -> int:
        return len(self._receipts)
