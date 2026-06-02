"""
Standard calibration fixture suite.

These are the curated cases whose ABSENCE the audit flagged. They are DATA, not
code: each case names a scenario, an expected outcome, and a justification for
why that outcome is correct given the gate's semantics.

Expected outcomes are derived from the gate's ACTUAL thresholds (defaults):
  nsv_step >= 0.5 (catastrophic)        -> REJECT
  0.2 < nsv_step < 0.5                   -> TRANSFORM
  predicted Omega <= 0.05 (half-floor)   -> REJECT
  0.05 < predicted Omega <= 0.1 (floor)  -> TRANSFORM
  predicted tau >= 0.85 without HBTL     -> DEFER
  predicted Theta < 0.15                 -> DEFER
  none of the above                      -> EXECUTE

Adversarial cases straddle these boundaries (just within / just beyond), because
those are the cases most likely to catch verdict drift when K2 (a coherence
relation) changes the admissible region.
"""
from __future__ import annotations

from ..core.types import FieldState, Transformation, GateOutcome
from .gate import GateThresholds
from .calibration import CalibrationCase, boundary_pair


def _state(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0):
    return FieldState(Omega=Omega, rho=rho, kappa=kappa, tau=tau, Theta=Theta, NSV=NSV, logical_step=0)


def standard_suite() -> list[CalibrationCase]:
    """The standard calibration fixture suite."""
    th = GateThresholds()  # defaults
    cases: list[CalibrationCase] = []

    # --- Nominal cases, one per outcome ----------------------------------

    cases.append(CalibrationCase(
        name="nominal_execute",
        field_state=_state(Omega=0.7, tau=0.3, Theta=0.7, NSV=0.0),
        transformation=Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02}),
        thresholds=th,
        expected_outcome=GateOutcome.EXECUTE,
        justification="Small commitment, modest residue, no floor/ceiling crossed.",
    ))

    cases.append(CalibrationCase(
        name="nominal_reject_catastrophic_nsv",
        field_state=_state(NSV=0.0),
        transformation=Transformation.new(typed_effects={"NSV": 0.6}),
        thresholds=th,
        expected_outcome=GateOutcome.REJECT,
        justification="NSV step 0.6 >= catastrophic 0.5; categorical reject.",
    ))

    cases.append(CalibrationCase(
        name="nominal_transform_nsv_step",
        field_state=_state(NSV=0.0),
        transformation=Transformation.new(typed_effects={"NSV": 0.3}),
        thresholds=th,
        expected_outcome=GateOutcome.TRANSFORM,
        justification="NSV step 0.3 in (0.2, 0.5): over max, below catastrophic; reshape-eligible.",
    ))

    cases.append(CalibrationCase(
        name="nominal_defer_theta_floor",
        field_state=_state(Omega=0.7, tau=0.3, Theta=0.20, NSV=0.0),
        transformation=Transformation.new(typed_effects={"tau": 0.30, "NSV": 0.0}),
        thresholds=th,
        expected_outcome=GateOutcome.DEFER,
        justification="tau rise cools Theta below floor 0.15; renegotiability lost -> defer.",
    ))

    # --- Adversarial boundary pairs --------------------------------------

    # NSV catastrophic boundary: just below 0.5 (TRANSFORM) vs just at/above (REJECT)
    cases.extend(boundary_pair(
        name_prefix="adv_nsv_catastrophic",
        base_state=_state(NSV=0.0),
        threshold_field="nsv_step_catastrophic",
        thresholds=th,
        delta_below={"NSV": 0.49},   # just below catastrophic -> TRANSFORM
        delta_above={"NSV": 0.50},   # at catastrophic -> REJECT
        expected_below=GateOutcome.TRANSFORM,
        expected_above=GateOutcome.REJECT,
        justification="NSV catastrophic boundary at 0.5",
    ))

    # NSV step-max boundary: just below 0.2 (EXECUTE) vs just above (TRANSFORM)
    cases.extend(boundary_pair(
        name_prefix="adv_nsv_step_max",
        base_state=_state(NSV=0.0),
        threshold_field="nsv_step_max",
        thresholds=th,
        delta_below={"NSV": 0.19},   # below max -> EXECUTE
        delta_above={"NSV": 0.21},   # above max, below catastrophic -> TRANSFORM
        expected_below=GateOutcome.EXECUTE,
        expected_above=GateOutcome.TRANSFORM,
        justification="NSV per-step max boundary at 0.2",
    ))

    # K2 coherence boundary: a JOINT-coordinate adversarial pair. Each coordinate
    # is individually in-bounds; only the combination crosses the coherence bound.
    # Within: tau=0.6 + Theta=0.7 = 1.3 <= 1.4 -> coherent -> EXECUTE.
    # Beyond: tau=0.6 + Theta=0.85 = 1.45 > 1.4 -> incoherent -> TRANSFORM.
    # renegotiation_event would be needed to hold Theta high; here we start at the
    # target Theta and apply a tiny tau nudge so the predicted state is the probe.
    cases.append(CalibrationCase(
        name="adv_coherence_within",
        field_state=_state(tau=0.55, Theta=0.70),
        transformation=Transformation.new(typed_effects={"tau": 0.05}),
        thresholds=th,
        expected_outcome=GateOutcome.EXECUTE,
        justification="Joint: predicted tau~0.6 + Theta~0.7 = ~1.3 <= 1.4 coherence bound; "
                      "each coordinate in-bounds and the combination is coherent.",
        is_adversarial=True,
    ))

    return cases
