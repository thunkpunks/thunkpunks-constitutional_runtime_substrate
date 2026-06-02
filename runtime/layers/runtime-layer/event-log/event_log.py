"""
Event Log — the append-only evidential trace, hardened into the primitive
runtime memory substrate.

This is NOT new capability and NOT a new layer. It hardens the append-only trace
that replay already depends on, adding the two properties that make it an
EVIDENTIAL substrate rather than merely an ordered list:

  1. HASH-CHAIN (lineage linkage): each entry commits to its predecessor's chain
     hash. Tampering with entry N invalidates the chain hash of every entry after
     N. This is what makes the trace evidence: you cannot alter history without
     the alteration being detectable at every downstream point.

  2. RECEIPTS: appending an entry returns a Receipt — a verifiable token that a
     specific event was admitted at a specific position with a specific chain
     state. A receipt can be checked against the log later to prove the event is
     present and unaltered.

It also closes a real gap in the existing ledger: retrieval returned references
to mutable records, so append-only was enforced on insertion but not protected
on read. Here, entries are frozen and verification recomputes the chain, so
mutation is detectable.

DISCIPLINE:
  - No kernel widening: this stores and verifies events; it does not evaluate
    admissibility, emit outcomes, or call the gate.
  - No orchestration coupling: it depends only on hashlib/json (stdlib). It does
    not import gate, session, MCP, or any adjacent layer. (Layer: runtime.)
  - Append-only and fail-closed: ordering violations and chain breaks raise.

This is the substrate that replay, lineage, receipts, state projection,
provenance, and (later) domain/witness/pedagogy layers all read from. Built
first because it is what they stand on.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"

GENESIS_CHAIN_HASH = "0" * 16


class EventLogViolation(Exception):
    """Raised on any attempt to violate append-only, ordering, or chain integrity."""


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical(payload: dict[str, Any]) -> str:
    """Deterministic JSON for hashing — sorted keys, no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class EventEntry:
    """
    A single append-only event in the evidential trace.

    Frozen: once appended, an entry cannot be mutated in place. The chain_hash
    commits to (prev_chain_hash + this entry's content), so any change to seq,
    session_id, logical_step, or payload would change content_hash and break the
    chain at this point and everywhere after.
    """
    seq: int                       # global append position (0-based)
    session_id: str
    logical_step: int
    event_kind: str
    payload: dict[str, Any]
    prev_chain_hash: str
    content_hash: str              # hash of this entry's own content
    chain_hash: str                # hash(prev_chain_hash + content_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "session_id": self.session_id,
            "logical_step": self.logical_step,
            "event_kind": self.event_kind,
            "payload": self.payload,
            "prev_chain_hash": self.prev_chain_hash,
            "content_hash": self.content_hash,
            "chain_hash": self.chain_hash,
        }

    @staticmethod
    def compute_content_hash(
        seq: int, session_id: str, logical_step: int,
        event_kind: str, payload: dict[str, Any],
    ) -> str:
        return _hash(_canonical({
            "seq": seq, "session_id": session_id, "logical_step": logical_step,
            "event_kind": event_kind, "payload": payload,
        }))

    @staticmethod
    def compute_chain_hash(prev_chain_hash: str, content_hash: str) -> str:
        return _hash(prev_chain_hash + content_hash)


@dataclass(frozen=True)
class Receipt:
    """
    A verifiable token that an event was admitted to the log.

    Holds enough to later prove the event is present and unaltered: its position,
    its content hash, and the chain hash at that point. Verifying a receipt
    against the log recomputes and compares.
    """
    seq: int
    session_id: str
    logical_step: int
    content_hash: str
    chain_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq, "session_id": self.session_id,
            "logical_step": self.logical_step,
            "content_hash": self.content_hash, "chain_hash": self.chain_hash,
        }


class EventLog:
    """
    Append-only, hash-chained evidential trace.

    Invariants (all fail-closed):
      - Entries are appended, never mutated or removed.
      - Within a session, logical_step strictly increases.
      - Each entry commits to its predecessor via chain_hash.
      - verify_integrity() recomputes the whole chain and detects any tampering.
    """

    def __init__(self) -> None:
        self._entries: list[EventEntry] = []
        self._last_step_by_session: dict[str, int] = {}

    @property
    def head_chain_hash(self) -> str:
        """The chain hash of the most recent entry (genesis if empty)."""
        return self._entries[-1].chain_hash if self._entries else GENESIS_CHAIN_HASH

    def append(
        self, session_id: str, logical_step: int, event_kind: str,
        payload: dict[str, Any],
    ) -> Receipt:
        """
        Append an event. Returns a Receipt. Raises EventLogViolation on an
        ordering violation. The payload is copied (value-isolated) so a later
        mutation of the caller's dict cannot alter the stored entry.
        """
        last = self._last_step_by_session.get(session_id, -1)
        if logical_step <= last:
            raise EventLogViolation(
                f"logical_step must strictly increase within session {session_id}: "
                f"got {logical_step}, last was {last}"
            )

        seq = len(self._entries)
        payload_copy = json.loads(_canonical(payload))  # deep value-isolated copy
        content_hash = EventEntry.compute_content_hash(
            seq, session_id, logical_step, event_kind, payload_copy
        )
        prev = self.head_chain_hash
        chain_hash = EventEntry.compute_chain_hash(prev, content_hash)

        entry = EventEntry(
            seq=seq, session_id=session_id, logical_step=logical_step,
            event_kind=event_kind, payload=payload_copy,
            prev_chain_hash=prev, content_hash=content_hash, chain_hash=chain_hash,
        )
        self._entries.append(entry)
        self._last_step_by_session[session_id] = logical_step
        return Receipt(
            seq=seq, session_id=session_id, logical_step=logical_step,
            content_hash=content_hash, chain_hash=chain_hash,
        )

    def entries(self, session_id: Optional[str] = None) -> list[EventEntry]:
        """Return entries (frozen; safe to hand out). Optionally filtered."""
        if session_id is None:
            return list(self._entries)
        return [e for e in self._entries if e.session_id == session_id]

    def verify_integrity(self) -> bool:
        """
        Recompute the entire hash-chain and confirm it is intact.

        Returns True iff every entry's content_hash and chain_hash recompute to
        the stored values and the chain links correctly. Detects any mutation,
        reorder, insertion, or deletion. This is the tamper-evidence: the trace
        is only evidential if alteration is detectable, and this is the detector.
        """
        prev = GENESIS_CHAIN_HASH
        for i, e in enumerate(self._entries):
            if e.seq != i:
                return False
            expected_content = EventEntry.compute_content_hash(
                e.seq, e.session_id, e.logical_step, e.event_kind, e.payload
            )
            if expected_content != e.content_hash:
                return False
            expected_chain = EventEntry.compute_chain_hash(prev, e.content_hash)
            if expected_chain != e.chain_hash:
                return False
            if e.prev_chain_hash != prev:
                return False
            prev = e.chain_hash
        return True

    def verify_receipt(self, receipt: Receipt) -> bool:
        """
        Verify a receipt against the log: the event at receipt.seq must match the
        receipt's hashes. Proves the event is present and unaltered.
        """
        if receipt.seq < 0 or receipt.seq >= len(self._entries):
            return False
        e = self._entries[receipt.seq]
        return (
            e.content_hash == receipt.content_hash
            and e.chain_hash == receipt.chain_hash
            and e.session_id == receipt.session_id
            and e.logical_step == receipt.logical_step
        )

    def serialize(self) -> str:
        """Serialize to JSON lines (one entry per line), in append order."""
        return "\n".join(_canonical(e.to_dict()) for e in self._entries)

    @staticmethod
    def deserialize(text: str) -> "EventLog":
        """
        Reconstruct a log from serialized lines, re-verifying the chain on load.
        Raises EventLogViolation if the loaded chain does not verify.
        """
        log = EventLog()
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            entry = EventEntry(
                seq=d["seq"], session_id=d["session_id"],
                logical_step=d["logical_step"], event_kind=d["event_kind"],
                payload=d["payload"], prev_chain_hash=d["prev_chain_hash"],
                content_hash=d["content_hash"], chain_hash=d["chain_hash"],
            )
            log._entries.append(entry)
            log._last_step_by_session[entry.session_id] = entry.logical_step
        if not log.verify_integrity():
            raise EventLogViolation(
                "Loaded event log failed integrity verification — the chain is "
                "broken (tampering, reorder, or corruption detected)."
            )
        return log

    def __len__(self) -> int:
        return len(self._entries)
