"""
Ingress Membrane — the constitutional boundary.

Ingress is NOT translation plumbing. It is the membrane where an external
observation either earns the status of admissible substrate state or is REFUSED.
Its defining act is refusal: it can look at a well-formed, faithful observation
and still say "no — this does not cross" because something about it would import
external authority the kernel did not grant.

THE CRITICAL SEPARATION (no shadow kernel):
  - The MEMBRANE decides whether an observation may become STATE.
  - The KERNEL decides whether a transformation may become ACTION.
  These are different admissibility judgments. The membrane refuses malformed or
  authority-bearing INPUTS; it NEVER refuses on the grounds the gate would use
  (commitment depth, coherence, horizon). If it did, it would be a second
  authority. The membrane judges admissibility-AS-STATE, not admissibility-AS-
  ACTION.

WHAT CROSSES / WHAT IS REFUSED:
  Crosses: per-coordinate readings with honest markers, and provenance recorded
           AS A CLAIM (never asserted as true).
  Refused (fail-closed): any verdict vocabulary, any `authority` field (at any
           nesting depth), fabricated confidence, silent (undisclosed)
           compression, dishonest coordinates (unpopulated-with-value, etc.).

MEMORY != TRUTH, enforced at the boundary: provenance enters as "source claimed
X", stripped of any power to compel a kernel outcome. External provenance becomes
internal EVIDENCE; it never becomes internal AUTHORITY.

DISCIPLINE: layer = ingress (own pre-declared boundary). It accepts already-
canonicalized input (TS/vendor translation stays outside). It may record an
admitted observation to the event-log substrate; it may NOT reach the gate,
constitution, receipts, or lineage decisions. stdlib-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"

# Coordinates an observation may carry. Kept local (no kernel import); the
# membrane validates shape, not physics.
COORDINATES = ("Omega", "rho", "kappa", "tau", "Theta", "NSV")

# Vocabulary that must NEVER cross the membrane as data — these are authority,
# not observation. A reading labelled with any of these is authority riding in.
VERDICT_VOCABULARY = {"EXECUTE", "TRANSFORM", "DEFER", "REJECT"}

# Field names that carry authority and are forbidden at any nesting depth.
FORBIDDEN_FIELDS = {"authority", "outcome", "verdict", "decision", "gate_outcome"}


class AdmissionRefusal(Exception):
    """Raised when an observation is refused at the membrane (fail-closed)."""


class RefusalReason(str, Enum):
    AUTHORITY_FIELD = "authority_field_present"
    VERDICT_VALUE = "verdict_vocabulary_present"
    FABRICATED_CONFIDENCE = "fabricated_confidence"
    DISHONEST_COORDINATE = "dishonest_coordinate"
    SILENT_COMPRESSION = "undisclosed_compression"
    MALFORMED = "malformed_observation"


@dataclass(frozen=True)
class Provenance:
    """
    Provenance recorded AS A CLAIM. `source_claimed` is what the adapter asserted;
    the membrane records it, never asserts it true. `asserted_true` is always
    False — memory != truth, made explicit in the type.
    """
    source_claimed: str
    modality_claimed: str
    asserted_true: bool = False  # always False; provenance is claim, not truth

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_claimed": self.source_claimed,
            "modality_claimed": self.modality_claimed,
            "asserted_true": False,
        }


@dataclass(frozen=True)
class AdmittedObservation:
    """
    An observation that passed the membrane: authority-stripped, provenance-as-
    claim, compression disclosed. This is what may become substrate state — and
    nothing else does.
    """
    coordinates: dict[str, dict[str, Any]]   # name -> {populated, value, confidence}
    provenance: Provenance
    compression_disclosed: bool
    compression_note: Optional[str]

    def to_event_payload(self) -> dict[str, Any]:
        """The payload form recorded to the event-log (by the caller, not here)."""
        return {
            "coordinates": self.coordinates,
            "provenance": self.provenance.to_dict(),
            "compression_disclosed": self.compression_disclosed,
            "compression_note": self.compression_note,
        }


def _scan_forbidden_fields(obj: Any, path: str = "") -> Optional[str]:
    """
    Recursively scan for forbidden authority fields at ANY nesting depth.
    Returns the path of the first offending field, or None. This is the
    nested-authority-leak guard: authority cannot hide inside a sub-object.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_FIELDS:
                return f"{path}.{k}" if path else k
            found = _scan_forbidden_fields(v, f"{path}.{k}" if path else k)
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            found = _scan_forbidden_fields(v, f"{path}[{i}]")
            if found:
                return found
    return None


def _scan_verdict_values(obj: Any) -> bool:
    """Recursively detect verdict-vocabulary STRINGS anywhere in the input."""
    if isinstance(obj, str):
        return obj in VERDICT_VOCABULARY
    if isinstance(obj, dict):
        return any(_scan_verdict_values(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_scan_verdict_values(v) for v in obj)
    return False


def admit(raw: dict[str, Any]) -> AdmittedObservation:
    """
    The admission predicate. Refuses (fail-closed, raising AdmissionRefusal)
    unless the observation is admissible AS STATE. On success, returns an
    authority-stripped AdmittedObservation.

    The predicate, in order:
      1. structural shape (coordinates dict, provenance present)
      2. recursive authority-field rejection (no `authority`/`outcome`/... at any depth)
      3. recursive verdict-value rejection (no EXECUTE/.../REJECT strings anywhere)
      4. coordinate honesty (no fabricated confidence, no dishonest markers)
      5. compression disclosure (lossy coordinates must be disclosed, not silent)

    NOTE: the predicate tests admissibility-AS-STATE only. It never evaluates the
    transformation or applies gate logic — no shadow kernel.
    """
    if not isinstance(raw, dict):
        raise AdmissionRefusal(RefusalReason.MALFORMED.value)

    # 2. Recursive authority-field rejection (before anything else trusts shape).
    offending = _scan_forbidden_fields(raw)
    if offending is not None:
        raise AdmissionRefusal(f"{RefusalReason.AUTHORITY_FIELD.value}: {offending}")

    # 3. Recursive verdict-value rejection.
    if _scan_verdict_values(raw):
        raise AdmissionRefusal(RefusalReason.VERDICT_VALUE.value)

    # 1. Structural shape.
    coords_in = raw.get("coordinates")
    prov_in = raw.get("provenance")
    if not isinstance(coords_in, dict) or not isinstance(prov_in, dict):
        raise AdmissionRefusal(RefusalReason.MALFORMED.value)
    if "source" not in prov_in and "source_claimed" not in prov_in:
        raise AdmissionRefusal(RefusalReason.MALFORMED.value)

    # 5. Compression disclosure: if any coordinate is marked compressed, the
    # observation must disclose it. Silent compression is refused.
    disclosed = bool(raw.get("compression_disclosed", False))
    note = raw.get("compression_note")
    any_compressed = any(
        isinstance(c, dict) and c.get("compressed", False) for c in coords_in.values()
    )
    if any_compressed and not disclosed:
        raise AdmissionRefusal(RefusalReason.SILENT_COMPRESSION.value)

    # 4. Coordinate honesty + authority-stripping into the canonical shape.
    clean: dict[str, dict[str, Any]] = {}
    for name in COORDINATES:
        c = coords_in.get(name)
        if c is None:
            # Absent coordinate is an honest blank (unpopulated).
            clean[name] = {"populated": False, "value": None, "confidence": 0.0}
            continue
        if not isinstance(c, dict):
            raise AdmissionRefusal(RefusalReason.MALFORMED.value)
        populated = bool(c.get("populated", False))
        value = c.get("value")
        confidence = c.get("confidence", 0.0)
        # Honesty: unpopulated must not carry value/confidence; populated must.
        if not populated:
            if value is not None or (confidence not in (0, 0.0)):
                raise AdmissionRefusal(
                    f"{RefusalReason.DISHONEST_COORDINATE.value}:{name}"
                )
            clean[name] = {"populated": False, "value": None, "confidence": 0.0}
        else:
            if value is None:
                raise AdmissionRefusal(
                    f"{RefusalReason.DISHONEST_COORDINATE.value}:{name}"
                )
            # Fabricated confidence: outside [0,1] or non-numeric.
            if not isinstance(confidence, (int, float)) or not (0.0 < confidence <= 1.0):
                raise AdmissionRefusal(
                    f"{RefusalReason.FABRICATED_CONFIDENCE.value}:{name}"
                )
            clean[name] = {"populated": True, "value": float(value),
                           "confidence": float(confidence)}

    provenance = Provenance(
        source_claimed=str(prov_in.get("source_claimed", prov_in.get("source"))),
        modality_claimed=str(prov_in.get("modality_claimed", prov_in.get("modality", "unknown"))),
    )

    return AdmittedObservation(
        coordinates=clean,
        provenance=provenance,
        compression_disclosed=disclosed,
        compression_note=str(note) if note is not None else None,
    )


def try_admit(raw: dict[str, Any]) -> tuple[Optional[AdmittedObservation], Optional[str]]:
    """
    Non-raising form: returns (admitted, None) on success or (None, reason) on
    refusal. For callers that want to handle refusal as a value, not an exception.
    The membrane still refuses; this only changes how the refusal is surfaced.
    """
    try:
        return admit(raw), None
    except AdmissionRefusal as e:
        return None, str(e)
