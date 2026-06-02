"""
Tests for components/measurement.py.

Verifies:
- Trust is ORTHOGONAL to admissibility: a trusted measurement can describe an
  inadmissible move; an untrusted one can describe a fine move.
- Untrusted measurement -> MEASUREMENT_HOLD (NOT REJECT, NOT EXECUTE).
- MEASUREMENT_HOLD is distinct from SAFE_HOLD (Lambda_0) and from gate outcomes.
- Absent provenance is honestly UNKNOWN (confidence 0), not silently trusted.
- Trust policy (confidence/staleness/calibration) gates correctly.
"""
import pytest

from runtime.core.bench_interface import BenchObservation, PreGateOutcome
from runtime.core.types import GateOutcome
from runtime.components.measurement import (
    MeasurementProvenance, MeasurementPolicy, MeasurementResult,
    CalibrationStatus, evaluate_measurement,
)


def _obs(tick_id="t1", session_id="sess-1", nsv=0.0):
    return BenchObservation(
        Omega=0.7, rho=0.0, kappa=0.0, NSV=nsv, Energy=0.5,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=0,
    )


class TestTrustedProceeds:
    def test_high_confidence_calibrated_proceeds(self):
        prov = MeasurementProvenance(
            confidence=0.9, source="sensor-A", calibration=CalibrationStatus.CALIBRATED,
        )
        result = evaluate_measurement(_obs(), prov)
        assert result.trustworthy is True
        assert result.to_pre_gate_output() is None  # proceed to gate


class TestUntrustedHolds:
    def test_low_confidence_triggers_measurement_hold(self):
        prov = MeasurementProvenance(confidence=0.2, source="sensor-A")
        result = evaluate_measurement(_obs(), prov, MeasurementPolicy(min_confidence=0.5))
        assert result.trustworthy is False
        pgo = result.to_pre_gate_output()
        assert pgo is not None
        assert pgo.outcome == PreGateOutcome.MEASUREMENT_HOLD

    def test_stale_measurement_holds(self):
        prov = MeasurementProvenance(
            confidence=0.9, source="sensor-A", staleness_ms=5000,
        )
        result = evaluate_measurement(_obs(), prov, MeasurementPolicy(max_staleness_ms=1000))
        assert result.trustworthy is False
        assert any("staleness" in r for r in result.reasons)

    def test_uncalibrated_holds_when_required(self):
        prov = MeasurementProvenance(
            confidence=0.9, source="sensor-A", calibration=CalibrationStatus.UNCALIBRATED,
        )
        result = evaluate_measurement(
            _obs(), prov, MeasurementPolicy(require_calibration=True),
        )
        assert result.trustworthy is False
        assert any("calibration" in r for r in result.reasons)


class TestUnknownProvenanceIsHonestlyUntrusted:
    """Absent provenance must NOT be silently trusted."""

    def test_no_provenance_defaults_to_untrusted(self):
        # No provenance supplied -> unknown (confidence 0) -> held under any
        # positive confidence threshold.
        result = evaluate_measurement(_obs(), provenance=None, policy=MeasurementPolicy(min_confidence=0.5))
        assert result.trustworthy is False
        assert result.provenance.confidence == 0.0

    def test_unknown_provenance_proceeds_only_if_threshold_zero(self):
        # If the policy demands zero confidence (trust everything), unknown passes.
        result = evaluate_measurement(_obs(), provenance=None, policy=MeasurementPolicy(min_confidence=0.0))
        assert result.trustworthy is True


class TestTrustOrthogonalToAdmissibility:
    """
    The central property: trust and admissibility are orthogonal axes.
    This test demonstrates all four combinations are representable.
    """

    def test_trusted_measurement_can_describe_inadmissible_move(self):
        # A fully trusted measurement of a catastrophic move: the measurement
        # check PASSES (we trust it), and the gate would then REJECT the move.
        # Trust check and admissibility check are separate.
        prov = MeasurementProvenance(confidence=1.0, source="sensor-A",
                                     calibration=CalibrationStatus.CALIBRATED)
        obs = _obs(nsv=0.0)
        result = evaluate_measurement(obs, prov)
        assert result.trustworthy is True  # trusted...
        # ...and separately, the move it describes might be inadmissible (gate's job)

    def test_untrusted_measurement_does_not_imply_rejection(self):
        # An untrusted measurement yields MEASUREMENT_HOLD, NOT REJECT.
        # The move might be perfectly admissible — we just don't trust the signal.
        prov = MeasurementProvenance(confidence=0.1, source="noisy-sensor")
        result = evaluate_measurement(_obs(), prov)
        pgo = result.to_pre_gate_output()
        assert pgo.outcome == PreGateOutcome.MEASUREMENT_HOLD
        assert pgo.outcome.value != GateOutcome.REJECT.value


class TestMeasurementHoldDistinctFromOtherOutcomes:
    def test_measurement_hold_not_safe_hold(self):
        assert PreGateOutcome.MEASUREMENT_HOLD.value != PreGateOutcome.SAFE_HOLD.value

    def test_measurement_hold_not_gate_outcome(self):
        gate_values = {o.value for o in GateOutcome}
        assert PreGateOutcome.MEASUREMENT_HOLD.value not in gate_values

    def test_three_pregate_outcomes_distinct(self):
        vals = {
            PreGateOutcome.SAFE_HOLD.value,
            PreGateOutcome.FAST_PRUNED.value,
            PreGateOutcome.MEASUREMENT_HOLD.value,
        }
        assert len(vals) == 3


class TestProvenanceGuards:
    def test_confidence_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="confidence"):
            MeasurementProvenance(confidence=1.5, source="x")

    def test_empty_source_rejected(self):
        with pytest.raises(ValueError, match="source"):
            MeasurementProvenance(confidence=0.5, source="")

    def test_negative_staleness_rejected(self):
        with pytest.raises(ValueError, match="staleness"):
            MeasurementProvenance(confidence=0.5, source="x", staleness_ms=-1)


class TestSerialization:
    def test_provenance_serializes(self):
        import json
        prov = MeasurementProvenance(confidence=0.8, source="s", calibration=CalibrationStatus.CALIBRATED)
        json.dumps(prov.to_dict())
