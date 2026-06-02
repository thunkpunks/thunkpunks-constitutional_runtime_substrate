"""
Tests for components/calibration.py and the standard fixture suite.

Verifies:
- The standard suite passes (expected outcomes match the gate's actual behaviour).
- run_case / run_suite report correctly.
- Adversarial boundary pairs straddle thresholds.
- Cases are serialisable (fixtures can live as data).
- The regression mechanism (capture_baseline / detect_regressions) detects when
  a verdict changes — the K2 safety net.
"""
import json
import pytest

from runtime.core.types import FieldState, Transformation, GateOutcome
from runtime.components.gate import GateThresholds
from runtime.components.calibration import (
    CalibrationCase, run_case, run_suite,
    capture_baseline, detect_regressions, RegressionFinding,
    boundary_pair,
)
from runtime.components.calibration_fixtures import standard_suite


def _state(**kw):
    d = dict(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
    d.update(kw)
    return FieldState(**d)


class TestStandardSuitePasses:
    """The curated fixture suite must pass — expectations match gate behaviour."""

    def test_standard_suite_all_pass(self):
        report = run_suite(standard_suite())
        assert report.all_passed, [r.name for r in report.failures()]

    def test_standard_suite_has_adversarial_cases(self):
        report = run_suite(standard_suite())
        assert report.adversarial_total >= 4
        assert report.adversarial_passed == report.adversarial_total

    def test_standard_suite_covers_all_four_outcomes(self):
        results = run_suite(standard_suite()).results
        outcomes = {r.actual for r in results}
        assert GateOutcome.EXECUTE in outcomes
        assert GateOutcome.TRANSFORM in outcomes
        assert GateOutcome.REJECT in outcomes
        assert GateOutcome.DEFER in outcomes


class TestRunCase:
    def test_passing_case(self):
        case = CalibrationCase(
            name="t", field_state=_state(),
            transformation=Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02}),
            thresholds=GateThresholds(), expected_outcome=GateOutcome.EXECUTE,
            justification="clean small commit",
        )
        result = run_case(case)
        assert result.passed
        assert result.actual == GateOutcome.EXECUTE

    def test_failing_case_detected(self):
        # Deliberately wrong expectation -> harness must report a failure.
        case = CalibrationCase(
            name="wrong", field_state=_state(),
            transformation=Transformation.new(typed_effects={"NSV": 0.6}),  # actually REJECT
            thresholds=GateThresholds(), expected_outcome=GateOutcome.EXECUTE,  # wrong
            justification="intentionally wrong",
        )
        result = run_case(case)
        assert result.passed is False
        assert result.actual == GateOutcome.REJECT
        assert result.expected == GateOutcome.EXECUTE


class TestSerialisation:
    def test_case_serialises(self):
        case = standard_suite()[0]
        d = case.to_dict()
        json.dumps(d)  # raises if not serialisable
        assert "expected_outcome" in d
        assert "justification" in d

    def test_report_serialises(self):
        report = run_suite(standard_suite())
        json.dumps(report.to_dict())


class TestAdversarialBoundaries:
    def test_boundary_pair_straddles(self):
        pair = boundary_pair(
            name_prefix="x", base_state=_state(NSV=0.0),
            threshold_field="nsv_step_catastrophic", thresholds=GateThresholds(),
            delta_below={"NSV": 0.49}, delta_above={"NSV": 0.50},
            expected_below=GateOutcome.TRANSFORM, expected_above=GateOutcome.REJECT,
            justification="catastrophic boundary",
        )
        assert len(pair) == 2
        results = [run_case(c) for c in pair]
        assert all(r.passed for r in results)
        assert results[0].actual == GateOutcome.TRANSFORM
        assert results[1].actual == GateOutcome.REJECT


class TestRegressionSafetyNet:
    """capture_baseline + detect_regressions = the K2 safety net."""

    def test_no_regressions_when_unchanged(self):
        cases = standard_suite()
        baseline = capture_baseline(cases)
        # Nothing changed -> no regressions.
        findings = detect_regressions(cases, baseline)
        assert findings == []

    def test_regression_detected_when_threshold_changes(self):
        cases = standard_suite()
        baseline = capture_baseline(cases)
        # Simulate a policy change: rebuild the same scenarios with a TIGHTER
        # catastrophic threshold so a previously-TRANSFORM case becomes REJECT.
        tightened = []
        for c in cases:
            tightened.append(CalibrationCase(
                name=c.name, field_state=c.field_state, transformation=c.transformation,
                thresholds=GateThresholds(nsv_step_catastrophic=0.25, nsv_step_max=0.1),
                expected_outcome=c.expected_outcome, justification=c.justification,
                is_adversarial=c.is_adversarial,
            ))
        findings = detect_regressions(tightened, baseline)
        # At least one case must have changed outcome under the tighter policy.
        assert len(findings) > 0
        assert all(isinstance(f, RegressionFinding) for f in findings)
        # Each finding documents the before/after.
        for f in findings:
            assert f.baseline_outcome != f.current_outcome
