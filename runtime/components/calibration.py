"""
Calibration harness.

Purpose: turn Layer 5 (calibration) from lab-grade to production-candidate by
making threshold/policy testing a CONCRETE, SERIALISABLE, REGRESSION-CHECKABLE
mechanism — not "we can in principle test thresholds."

This is also the safety net K2 must land into: a coherence relation changes
verdicts, and without a golden-master fixture suite we would change the
admissible region with no way to distinguish intended verdict changes from
unintended drift.

What it provides:
  - CalibrationCase: a named, serialisable fixture — a starting state, a
    transformation, a threshold policy, and an EXPECTED outcome.
  - run_case / run_suite: execute cases against the gate, compare actual vs
    expected, report pass/fail with reasons.
  - A regression mode: capture current outcomes as a baseline, then later detect
    which cases changed (the K2 safety net).
  - Adversarial case builders: boundary probes (just-below / just-above a
    threshold) that catch verdict drift the nominal cases miss.

Design discipline:
  - Cases are DATA (serialisable), so a fixture suite lives as a file, not code.
  - The harness uses the PURE gate; it authorises nothing and writes nothing.
  - "expected" outcomes are recorded with a justification string, so a threshold
    is not just tested but JUSTIFIED (why this case should yield this outcome).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..core.types import FieldState, Transformation, GateOutcome
from .gate import GateThresholds, GateInput, evaluate


COMPONENT_VERSION = "0.1.0"


@dataclass(frozen=True)
class CalibrationCase:
    """
    A single calibration fixture: a scenario with an expected outcome.

    The `justification` is required — a calibration case that cannot say WHY it
    should yield its expected outcome is a test without a hypothesis. This is how
    a threshold becomes JUSTIFIED, not merely exercised.
    """
    name: str
    field_state: FieldState
    transformation: Transformation
    thresholds: GateThresholds
    expected_outcome: GateOutcome
    justification: str
    is_adversarial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "field_state": self.field_state.to_dict(),
            "transformation": self.transformation.to_dict(),
            "thresholds": _thresholds_to_dict(self.thresholds),
            "expected_outcome": self.expected_outcome.value,
            "justification": self.justification,
            "is_adversarial": self.is_adversarial,
        }


def _thresholds_to_dict(th: GateThresholds) -> dict[str, float]:
    from dataclasses import asdict
    return asdict(th)


@dataclass(frozen=True)
class CaseResult:
    """Result of running one calibration case."""
    name: str
    passed: bool
    expected: GateOutcome
    actual: GateOutcome
    is_adversarial: bool
    justification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected.value,
            "actual": self.actual.value,
            "is_adversarial": self.is_adversarial,
            "justification": self.justification,
        }


@dataclass(frozen=True)
class SuiteReport:
    """Aggregate result of running a calibration suite."""
    total: int
    passed: int
    failed: int
    adversarial_total: int
    adversarial_passed: int
    results: tuple[CaseResult, ...]

    @property
    def all_passed(self) -> bool:
        return self.failed == 0

    def failures(self) -> list[CaseResult]:
        return [r for r in self.results if not r.passed]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "adversarial_total": self.adversarial_total,
            "adversarial_passed": self.adversarial_passed,
            "all_passed": self.all_passed,
            "results": [r.to_dict() for r in self.results],
        }


def run_case(case: CalibrationCase) -> CaseResult:
    """Run one calibration case against the pure gate."""
    out = evaluate(GateInput(
        current_state=case.field_state,
        transformation=case.transformation,
        thresholds=case.thresholds,
    ))
    return CaseResult(
        name=case.name,
        passed=(out.outcome == case.expected_outcome),
        expected=case.expected_outcome,
        actual=out.outcome,
        is_adversarial=case.is_adversarial,
        justification=case.justification,
    )


def run_suite(cases: list[CalibrationCase]) -> SuiteReport:
    """Run a suite of calibration cases and aggregate the report."""
    results = [run_case(c) for c in cases]
    adversarial = [r for r in results if r.is_adversarial]
    return SuiteReport(
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        adversarial_total=len(adversarial),
        adversarial_passed=sum(1 for r in adversarial if r.passed),
        results=tuple(results),
    )


# ---------------------------------------------------------------------------
# Regression mode — the K2 safety net.
# ---------------------------------------------------------------------------

def capture_baseline(cases: list[CalibrationCase]) -> dict[str, str]:
    """
    Capture the CURRENT actual outcome for each case as a baseline.

    Run this BEFORE a change (e.g. before K2). The returned mapping
    {case_name: outcome_value} is the golden master.
    """
    baseline: dict[str, str] = {}
    for c in cases:
        out = evaluate(GateInput(
            current_state=c.field_state, transformation=c.transformation,
            thresholds=c.thresholds,
        ))
        baseline[c.name] = out.outcome.value
    return baseline


@dataclass(frozen=True)
class RegressionFinding:
    """A case whose outcome changed between baseline and now."""
    name: str
    baseline_outcome: str
    current_outcome: str


def detect_regressions(
    cases: list[CalibrationCase],
    baseline: dict[str, str],
) -> list[RegressionFinding]:
    """
    Detect which cases changed outcome relative to a baseline.

    Run this AFTER a change (e.g. after K2). Every finding is a verdict that
    changed. The point is not that change is bad — K2 SHOULD change some verdicts
    — but that EVERY change must be ACCOUNTED FOR: intended changes are expected
    and unintended changes are drift. The harness surfaces both; the human (or a
    follow-up assertion) decides which is which.
    """
    findings: list[RegressionFinding] = []
    for c in cases:
        out = evaluate(GateInput(
            current_state=c.field_state, transformation=c.transformation,
            thresholds=c.thresholds,
        ))
        prior = baseline.get(c.name)
        if prior is not None and prior != out.outcome.value:
            findings.append(RegressionFinding(
                name=c.name, baseline_outcome=prior, current_outcome=out.outcome.value,
            ))
    return findings


# ---------------------------------------------------------------------------
# Adversarial case builders — boundary probes.
# ---------------------------------------------------------------------------

def boundary_pair(
    name_prefix: str,
    base_state: FieldState,
    threshold_field: str,
    thresholds: GateThresholds,
    delta_below: dict[str, float],
    delta_above: dict[str, float],
    expected_below: GateOutcome,
    expected_above: GateOutcome,
    justification: str,
) -> list[CalibrationCase]:
    """
    Build a pair of adversarial cases straddling a threshold: one just inside
    (admissible) and one just outside (not). These are the cases most likely to
    catch verdict drift, because they sit exactly where a coherence relation (K2)
    or a threshold change would first bite.
    """
    return [
        CalibrationCase(
            name=f"{name_prefix}_within",
            field_state=base_state,
            transformation=Transformation.new(typed_effects=delta_below),
            thresholds=thresholds,
            expected_outcome=expected_below,
            justification=f"{justification} (within {threshold_field})",
            is_adversarial=True,
        ),
        CalibrationCase(
            name=f"{name_prefix}_beyond",
            field_state=base_state,
            transformation=Transformation.new(typed_effects=delta_above),
            thresholds=thresholds,
            expected_outcome=expected_above,
            justification=f"{justification} (beyond {threshold_field})",
            is_adversarial=True,
        ),
    ]
