"""
Measurement provenance.

Constitutional role: distinguish "we do not trust this measurement" from
"this move is inadmissible." Bad signal must NOT become false rejection
(REJECT) nor false confidence (EXECUTE). It becomes a distinct third thing:
MEASUREMENT_HOLD — the runtime declines to judge an untrusted measurement.

WHY THIS MUST EXIST BEFORE HISTORY BECOMES CONSTITUTIVE:
Once trajectory history conditions the verdict (K3), a measurement error does
not just affect one tick — it propagates into the cumulative quantities that
condition all future verdicts. An untrusted measurement that is silently
treated as trusted would amplify into false geometry. So measurement provenance
must be constitutive ALONGSIDE history: the runtime must know which parts of the
trajectory rest on trusted signal before it lets the trajectory shape admissibility.

DESIGN:
- MeasurementProvenance is a companion to BenchObservation, carrying signal
  quality. It is SEPARATE from the observed values so it cannot be confused with
  admissibility data.
- Absent provenance is treated as UNKNOWN trust — an honest distinct state, NOT
  silently "trusted." Backward compatible: existing observations have no
  provenance and are flagged unknown, not waved through.
- The pre-gate check emits MEASUREMENT_HOLD when confidence is below threshold.
  Sequencing: Lambda_0 (well-formedness) -> measurement provenance (trust) ->
  gate (admissibility). Malformed = SAFE_HOLD; well-formed-but-untrusted =
  MEASUREMENT_HOLD; well-formed-and-trusted = reaches the gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from ..core.bench_interface import (
    BenchObservation,
    PreGateOutcome,
    PreGateOutput,
)


COMPONENT_VERSION = "0.1.0"
LAYER_NAME = "measurement_provenance"


class CalibrationStatus(str, Enum):
    """Calibration state of the measurement source."""
    CALIBRATED = "calibrated"
    UNCALIBRATED = "uncalibrated"
    STALE = "stale"            # calibration expired
    UNKNOWN = "unknown"        # no calibration info supplied — honest default


@dataclass(frozen=True)
class MeasurementProvenance:
    """
    Signal-quality metadata accompanying a BenchObservation.

    SEPARATE from the observed values: this describes how much to TRUST the
    measurement, never what the measurement admits.

    confidence: scalar in [0, 1]. 1 = fully trusted, 0 = no trust.
    source: identifier of the measuring instrument / channel.
    calibration: calibration status of the source.
    staleness_ms: age of the measurement in ms (0 = fresh). Stale signal may be
        present but untrustworthy.
    notes: free-form provenance notes (audit only).
    """
    confidence: float
    source: str
    calibration: CalibrationStatus = CalibrationStatus.UNKNOWN
    staleness_ms: int = 0
    notes: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence out of [0,1]: {self.confidence}")
        if self.staleness_ms < 0:
            raise ValueError(f"staleness_ms negative: {self.staleness_ms}")
        if not self.source:
            raise ValueError("source is required")

    @staticmethod
    def unknown() -> "MeasurementProvenance":
        """
        The honest default for an observation with no supplied provenance.
        confidence 0.0 + UNKNOWN calibration: NOT trusted, NOT rejected — the
        runtime knows it does not know. A measurement-quality threshold of 0.0
        would let these through; any positive threshold holds them.
        """
        return MeasurementProvenance(
            confidence=0.0, source="unknown", calibration=CalibrationStatus.UNKNOWN,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "source": self.source,
            "calibration": self.calibration.value,
            "staleness_ms": self.staleness_ms,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class MeasurementPolicy:
    """
    Thresholds governing whether a measurement is trustworthy enough to evaluate.

    These are NOT admissibility thresholds. They govern TRUST, not ADMISSIBILITY.
    A measurement can be fully trusted and still describe an inadmissible move;
    a measurement can be untrusted and describe a perfectly fine move. The two
    axes are orthogonal — that orthogonality is the whole point.
    """
    min_confidence: float = 0.5
    max_staleness_ms: int = 1000
    require_calibration: bool = False  # if True, UNCALIBRATED/UNKNOWN -> hold

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError(f"min_confidence out of [0,1]: {self.min_confidence}")


@dataclass(frozen=True)
class MeasurementResult:
    """
    Result of the measurement-provenance check.

    trustworthy True  -> proceed to the gate.
    trustworthy False -> MEASUREMENT_HOLD; the gate does not run for this tick.
    """
    trustworthy: bool
    reasons: tuple[str, ...]
    provenance: MeasurementProvenance

    def to_pre_gate_output(self) -> Optional[PreGateOutput]:
        """None if trustworthy (proceed); a MEASUREMENT_HOLD PreGateOutput otherwise."""
        if self.trustworthy:
            return None
        return PreGateOutput(
            outcome=PreGateOutcome.MEASUREMENT_HOLD,
            layer=LAYER_NAME,
            reason="; ".join(self.reasons) if self.reasons else "measurement not trustworthy",
            triggered_thresholds=self.reasons,
        )


def evaluate_measurement(
    obs: BenchObservation,
    provenance: Optional[MeasurementProvenance] = None,
    policy: Optional[MeasurementPolicy] = None,
) -> MeasurementResult:
    """
    Check whether a measurement is trustworthy enough to evaluate.

    Args:
        obs: the bench observation (its values are NOT inspected here — this
            check is about TRUST, not admissibility).
        provenance: signal-quality metadata. If None, treated as UNKNOWN trust
            (confidence 0.0) — an honest "we don't know," not silent trust.
        policy: trust thresholds; defaults applied if None.

    Returns:
        MeasurementResult. trustworthy True -> proceed to gate.
        trustworthy False -> MEASUREMENT_HOLD.
    """
    prov = provenance or MeasurementProvenance.unknown()
    pol = policy or MeasurementPolicy()
    reasons: list[str] = []

    if prov.confidence < pol.min_confidence:
        reasons.append(
            f"confidence {prov.confidence:.2f} < min {pol.min_confidence:.2f}"
        )
    if prov.staleness_ms > pol.max_staleness_ms:
        reasons.append(
            f"staleness {prov.staleness_ms}ms > max {pol.max_staleness_ms}ms"
        )
    if pol.require_calibration and prov.calibration in (
        CalibrationStatus.UNCALIBRATED,
        CalibrationStatus.UNKNOWN,
        CalibrationStatus.STALE,
    ):
        reasons.append(f"calibration {prov.calibration.value} but calibration required")

    return MeasurementResult(
        trustworthy=(len(reasons) == 0),
        reasons=tuple(reasons),
        provenance=prov,
    )
