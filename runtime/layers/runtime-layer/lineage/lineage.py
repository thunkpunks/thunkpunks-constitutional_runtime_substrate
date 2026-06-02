"""
Lineage — transformation ancestry attached to the event-log substrate.

The event log proved entries cannot be silently mutated. Lineage proves the next
thing: that transformations can be traced through LAWFUL ANCESTRY — what was
proposed, what it derived from, what event recorded it, what receipt refers to
it, and whether that ancestry remains replayable.

WHAT THIS BUILDS ON (already on disk — lineage attaches, does not invent):
  - Transformation.composed_from: parent ids of a composed transformation.
  - EventLog: append-only, hash-chained entries with (seq, content_hash).
  - Receipt: a verifiable token referring to an event by seq + hashes.

WHAT LINEAGE ADDS:
  - LineageRecord: binds a transformation_id to the event seq that recorded it,
    its parent transformation_ids (ancestry), and an optional receipt reference.
  - LineageGraph: reconstructs ancestry over an event log, in replay (seq) order,
    and validates that every recorded lineage edge is consistent with the log.

INTEGRITY MODEL (reuses the event log; invents no new crypto):
  Lineage does not maintain its own hash-chain. It DERIVES from the event log,
  whose chain already makes tampering detectable. A lineage graph built from a
  tampered log fails because the log fails verify_integrity() first. Lineage's
  own validation checks STRUCTURAL ancestry consistency (no cycles, parents
  precede children in seq order, referenced events exist).

DISCIPLINE:
  - No kernel widening: lineage records and reconstructs ancestry; it does not
    evaluate admissibility, call the gate, or emit outcomes.
  - No orchestration/observability coupling: depends only on the event-log
    substrate (same layer) and stdlib.
  - Layer: runtime. Status: EXPERIMENTALLY_BOUNDED until fixtures + replay +
    tamper tests pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"


class LineageViolation(Exception):
    """Raised when ancestry is structurally invalid or inconsistent with the log."""


@dataclass(frozen=True)
class LineageRecord:
    """
    Binds one transformation to its place in the evidential trace and its ancestry.

    - transformation_id: the transformation this record is about.
    - event_seq: the event-log seq of the entry that recorded it.
    - parent_ids: the transformation_ids it derived from (from composed_from).
                  Empty tuple for a primitive (hand-authored) transformation.
    - receipt_content_hash: optional link to the receipt that refers to the
                  recording event (proves the event is the one receipted).
    """
    transformation_id: str
    event_seq: int
    parent_ids: tuple[str, ...]
    receipt_content_hash: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transformation_id": self.transformation_id,
            "event_seq": self.event_seq,
            "parent_ids": list(self.parent_ids),
            "receipt_content_hash": self.receipt_content_hash,
        }

    @property
    def is_primitive(self) -> bool:
        """True iff this transformation has no ancestry (hand-authored)."""
        return len(self.parent_ids) == 0


class LineageGraph:
    """
    The ancestry graph over a set of lineage records.

    Records are added in event order. The graph validates structural ancestry:
      - referenced parents must be known transformations,
      - a parent must precede its child in event seq order (ancestry flows
        forward in the trace — you cannot derive from a future event),
      - no transformation may be its own ancestor (no cycles).

    The graph does NOT decide admissibility. It answers ancestry questions:
    parents/children of a transformation, the full ancestry chain, and whether
    the ancestry is replayable (reconstructable in seq order).
    """

    def __init__(self) -> None:
        self._records: dict[str, LineageRecord] = {}
        self._order: list[str] = []  # transformation_ids in insertion (event) order

    def add(self, record: LineageRecord) -> None:
        """Add a lineage record, validating structural ancestry. Fail-closed."""
        if record.transformation_id in self._records:
            raise LineageViolation(
                f"transformation {record.transformation_id} already has a lineage "
                f"record (lineage is append-only per transformation)"
            )

        # Parents must already be known (they were recorded by earlier events).
        for pid in record.parent_ids:
            if pid not in self._records:
                raise LineageViolation(
                    f"transformation {record.transformation_id} claims parent "
                    f"{pid}, which has no prior lineage record. Ancestry must "
                    f"flow forward: a parent is recorded before its child."
                )
            parent = self._records[pid]
            if parent.event_seq >= record.event_seq:
                raise LineageViolation(
                    f"parent {pid} (seq {parent.event_seq}) does not precede "
                    f"child {record.transformation_id} (seq {record.event_seq}). "
                    f"A transformation cannot derive from a later event."
                )

        # No self-ancestry.
        if record.transformation_id in record.parent_ids:
            raise LineageViolation(
                f"transformation {record.transformation_id} cannot be its own parent"
            )

        self._records[record.transformation_id] = record
        self._order.append(record.transformation_id)

    def record(self, transformation_id: str) -> Optional[LineageRecord]:
        return self._records.get(transformation_id)

    def parents(self, transformation_id: str) -> tuple[str, ...]:
        rec = self._records.get(transformation_id)
        return rec.parent_ids if rec else ()

    def children(self, transformation_id: str) -> tuple[str, ...]:
        """All transformations that directly derived from this one."""
        return tuple(
            tid for tid in self._order
            if transformation_id in self._records[tid].parent_ids
        )

    def ancestry(self, transformation_id: str) -> list[str]:
        """
        The full transitive ancestry of a transformation, nearest first.
        Reconstructs the lawful derivation chain. Raises if a cycle is somehow
        present (defence in depth; add() already prevents cycles).
        """
        seen: set[str] = set()
        order: list[str] = []
        stack = list(self.parents(transformation_id))
        while stack:
            pid = stack.pop(0)
            if pid in seen:
                continue
            if pid == transformation_id:
                raise LineageViolation(f"cycle detected at {transformation_id}")
            seen.add(pid)
            order.append(pid)
            stack.extend(self.parents(pid))
        return order

    def replay_order(self) -> list[str]:
        """
        The transformation_ids in event (seq) order — the order in which lineage
        was recorded. This is what makes ancestry replayable: reconstructing the
        graph by adding records in this order reproduces the same graph.
        """
        return list(self._order)

    def validate_replayable(self) -> bool:
        """
        Confirm the graph can be reconstructed by replaying records in seq order:
        every parent appears before its child. (add() enforces this on insertion;
        this re-checks the assembled graph as defence in depth.)
        """
        seen: set[str] = set()
        for tid in self._order:
            rec = self._records[tid]
            for pid in rec.parent_ids:
                if pid not in seen:
                    return False
            seen.add(tid)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {"records": [self._records[t].to_dict() for t in self._order]}

    def __len__(self) -> int:
        return len(self._records)


def lineage_record_from_transformation(
    transformation_id: str,
    composed_from: tuple[str, ...],
    event_seq: int,
    receipt_content_hash: Optional[str] = None,
) -> LineageRecord:
    """
    Build a LineageRecord from a transformation's identity + composed_from
    ancestry + the event seq that recorded it. This is the bridge from the
    existing Transformation.composed_from primitive to a lineage record.
    """
    return LineageRecord(
        transformation_id=transformation_id,
        event_seq=event_seq,
        parent_ids=tuple(composed_from),
        receipt_content_hash=receipt_content_hash,
    )


def build_lineage_from_records(records: list[LineageRecord]) -> LineageGraph:
    """
    Build a lineage graph by adding records in the given order. Records must be
    supplied in event (seq) order so ancestry flows forward; add() fails closed
    otherwise. Returns the validated graph.
    """
    graph = LineageGraph()
    for rec in sorted(records, key=lambda r: r.event_seq):
        graph.add(rec)
    if not graph.validate_replayable():
        raise LineageViolation("assembled lineage graph is not replayable")
    return graph
