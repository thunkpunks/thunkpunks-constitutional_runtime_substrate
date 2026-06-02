"""
State Projection — mapping recorded observations into FieldState through the
evidence substrate.

This is the FIRST capability step after evidential hardening, so it is
deliberately narrow. It maps a typed observation (recorded as an event) into the
kernel's FieldState, binds the projection to the source event, and emits
projection evidence that is itself replay-reconstructable and tamper-evident.

THE DISCIPLINE LINE:
  Projection produces a FieldState AND the evidence that it did so. It must NOT
  decide anything about that FieldState. It does not evaluate admissibility, does
  not import GateOutcome/gate, does not touch thresholds, does not score. It maps
  observation -> FieldState and records that it happened. The kernel receives the
  FieldState through the declared boundary (a ProjectionRecord the caller hands
  to the gate / assembler); projection never calls the gate.

  Honesty preserved (from the CanonicalObservation work): an unpopulated or
  low-confidence coordinate does NOT become a fabricated zero. Projection
  produces either a complete FieldState (status READY) or a HOLD with the
  coordinates that were not trustworthy — the same measured-zero != unmodelled-
  blank discipline, now in the Python substrate, bound to the event log.

WHAT IT READS / EMITS:
  - reads: an observation EVENT from the event log (by seq), whose payload holds
    the typed per-coordinate observation.
  - emits: a ProjectionRecord binding (source_event_seq, source_content_hash,
    resulting FieldState OR hold reasons, projection_hash). Replay-reconstructable
    and tamper-evident: a tampered source event breaks the binding; a tampered
    projection record fails its self-hash.

DISCIPLINE: layer = runtime; status EXPERIMENTALLY_BOUNDED; stdlib-only; imports
no kernel module; couples to the event log by duck type (modules injected).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"

# The six FieldState coordinates projection targets. logical_step is positional
# metadata, supplied separately, not a projected observation coordinate.
COORDINATES = ("Omega", "rho", "kappa", "tau", "Theta", "NSV")


class ProjectionViolation(Exception):
    """Raised when a projection is structurally invalid or inconsistent."""


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class CoordinateReading:
    """
    A single coordinate's observation, with honesty markers.

    populated=False means the coordinate was NOT measured: value must be None and
    confidence must be 0. A measured zero (populated=True, value=0.0) is distinct
    from an unmodelled blank — the distinction projection must preserve.
    """
    populated: bool
    value: Optional[float]
    confidence: float

    def __post_init__(self) -> None:
        if not self.populated:
            if self.value is not None:
                raise ProjectionViolation("unpopulated coordinate must not carry a value")
            if self.confidence != 0:
                raise ProjectionViolation("unpopulated coordinate must have confidence 0")
        else:
            if self.value is None:
                raise ProjectionViolation("populated coordinate must carry a value")
            if self.confidence <= 0:
                raise ProjectionViolation("populated coordinate must have confidence > 0")

    def to_dict(self) -> dict[str, Any]:
        return {"populated": self.populated, "value": self.value, "confidence": self.confidence}


@dataclass(frozen=True)
class ProjectionRecord:
    """
    The evidence that an observation was projected into a FieldState.

    Either status READY with a complete field_state, or status MEASUREMENT_HOLD
    with the reason codes (unpopulated / low-confidence coordinates). Bound to the
    source event by (source_event_seq, source_content_hash). Self-hashed.
    """
    projection_id: str
    source_event_seq: int
    source_content_hash: str
    status: str                       # "READY" | "MEASUREMENT_HOLD"
    field_state: Optional[dict[str, float]]   # present iff READY (6 coords + logical_step)
    reason_codes: tuple[str, ...]
    projection_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_id": self.projection_id,
            "source_event_seq": self.source_event_seq,
            "source_content_hash": self.source_content_hash,
            "status": self.status,
            "field_state": self.field_state,
            "reason_codes": list(self.reason_codes),
            "projection_hash": self.projection_hash,
        }

    @staticmethod
    def compute_hash(
        projection_id: str, source_event_seq: int, source_content_hash: str,
        status: str, field_state: Optional[dict[str, float]],
        reason_codes: tuple[str, ...],
    ) -> str:
        return _hash(_canonical({
            "projection_id": projection_id,
            "source_event_seq": source_event_seq,
            "source_content_hash": source_content_hash,
            "status": status,
            "field_state": field_state,
            "reason_codes": list(reason_codes),
        }))


def _readings_from_payload(payload: dict[str, Any]) -> dict[str, CoordinateReading]:
    """
    Extract per-coordinate readings from an observation event's payload.

    Expected payload shape: payload["coordinates"][coord] = {populated, value, confidence}.
    A coordinate absent from the payload is treated as UNPOPULATED (honest blank),
    not as zero.
    """
    coords_in = payload.get("coordinates", {})
    readings: dict[str, CoordinateReading] = {}
    for name in COORDINATES:
        c = coords_in.get(name)
        if c is None:
            readings[name] = CoordinateReading(populated=False, value=None, confidence=0.0)
        else:
            readings[name] = CoordinateReading(
                populated=c.get("populated", False),
                value=c.get("value"),
                confidence=c.get("confidence", 0.0),
            )
    return readings


def project_event(
    projection_id: str,
    event_seq: int,
    event_content_hash: str,
    payload: dict[str, Any],
    logical_step: int,
    min_confidence: float,
) -> ProjectionRecord:
    """
    Project one observation event into a FieldState (or a hold).

    DETERMINISTIC: the same (payload, logical_step, min_confidence) always yields
    the same record (same field_state or same reason codes, same hash).

    HONEST: an unpopulated coordinate, or a populated coordinate below
    min_confidence, produces a MEASUREMENT_HOLD naming that coordinate — never a
    fabricated zero. Only when all six coordinates are populated and trusted does
    it produce a READY FieldState.

    This function does NOT decide admissibility. It maps and records. The
    resulting FieldState is handed to the kernel through the declared boundary by
    the caller; projection never evaluates it.
    """
    readings = _readings_from_payload(payload)
    reason_codes: list[str] = []
    field_state: dict[str, float] = {}

    for name in COORDINATES:
        r = readings[name]
        if not r.populated:
            reason_codes.append(f"UNPOPULATED_COORDINATE:{name}")
            continue
        if r.confidence < min_confidence:
            reason_codes.append(f"LOW_CONFIDENCE_COORDINATE:{name}")
            continue
        field_state[name] = float(r.value)  # type: ignore[arg-type]

    if reason_codes:
        status = "MEASUREMENT_HOLD"
        fs: Optional[dict[str, float]] = None
    else:
        status = "READY"
        field_state["logical_step"] = logical_step
        fs = field_state

    projection_hash = ProjectionRecord.compute_hash(
        projection_id, event_seq, event_content_hash, status, fs, tuple(reason_codes)
    )
    return ProjectionRecord(
        projection_id=projection_id,
        source_event_seq=event_seq,
        source_content_hash=event_content_hash,
        status=status,
        field_state=fs,
        reason_codes=tuple(reason_codes),
        projection_hash=projection_hash,
    )


def verify_projection_self(record: ProjectionRecord) -> bool:
    """Verify a projection record's own content hashes to projection_hash."""
    expected = ProjectionRecord.compute_hash(
        record.projection_id, record.source_event_seq, record.source_content_hash,
        record.status, record.field_state, record.reason_codes,
    )
    return expected == record.projection_hash


def verify_projection_against_log(record: ProjectionRecord, event_log: Any) -> bool:
    """
    Verify a projection against an event log:
      1. the record's own content is intact (self-hash), AND
      2. the source event exists at source_event_seq with the same content_hash.

    A tampered source event breaks (2); an orphan projection (no such event)
    fails. `event_log` is accepted by duck type (.entries() with .seq, .content_hash).
    """
    if not verify_projection_self(record):
        return False
    entries = event_log.entries()
    if record.source_event_seq < 0 or record.source_event_seq >= len(entries):
        return False  # orphan
    entry = entries[record.source_event_seq]
    return (
        entry.seq == record.source_event_seq
        and entry.content_hash == record.source_content_hash
    )


def project_from_log(
    event_log: Any,
    event_seq: int,
    logical_step: int,
    min_confidence: float,
    projection_id: Optional[str] = None,
) -> ProjectionRecord:
    """
    Read an observation event from the log by seq and project it. Binds the
    projection to that event's content hash, so the result is replay-bound to the
    source. Raises if the event seq does not exist (orphan source).
    """
    entries = event_log.entries()
    if event_seq < 0 or event_seq >= len(entries):
        raise ProjectionViolation(f"no event at seq {event_seq} to project")
    entry = entries[event_seq]
    pid = projection_id or f"proj-{event_seq}"
    return project_event(
        projection_id=pid,
        event_seq=entry.seq,
        event_content_hash=entry.content_hash,
        payload=entry.payload,
        logical_step=logical_step,
        min_confidence=min_confidence,
    )
