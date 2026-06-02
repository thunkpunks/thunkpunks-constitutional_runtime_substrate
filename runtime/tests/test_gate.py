"""
Tests for components/gate.py.

The gate is the constitutional authority. Its tests verify:
- All four outcomes are reachable under appropriate inputs.
- The gate is pure (same input -> same output).
- Monotonicity of tau and NSV is enforced by apply_delta.
- Theta cools under tau rise unless renegotiation event fires.
- Predicate logic matches the spec.
"""
import pytest

from runtime.core.types import FieldState, Transformation, GateOutcome, GateReasonCode
from runtime.components.gate import (
    GateThresholds,
    GateInput,
    GateOutput,
    apply_delta,
    evaluate,
)


# -- helpers -----------------------------------------------------------------

def _state(**kwargs) -> FieldState:
    defaults = dict(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
    defaults.update(kwargs)
    return FieldState(**defaults)


def _t(delta: dict, desc: str = "test") -> Transformation:
    return Transformation.new(expected_delta=delta, description=desc)


# -- apply_delta -------------------------------------------------------------

class TestApplyDelta:
    """apply_delta enforces bounds, monotonicity, theta cooling."""

    def test_logical_step_increments_by_one(self):
        s = _state(logical_step=5)
        s2 = apply_delta(s, {"Omega": -0.1}, GateThresholds(), renegotiation_event=False)
        assert s2.logical_step == 6

    def test_omega_clamped_to_unit_interval(self):
        s = _state(Omega=0.9)
        s2 = apply_delta(s, {"Omega": 0.5}, GateThresholds(), renegotiation_event=False)
        assert s2.Omega == 1.0

    def test_tau_monotone_under_apply(self):
        """tau cannot decrease via delta. Negative tau deltas are zeroed."""
        s = _state(tau=0.5)
        s2 = apply_delta(s, {"tau": -0.2}, GateThresholds(), renegotiation_event=False)
        assert s2.tau == 0.5  # decrease blocked

    def test_nsv_monotone_under_apply(self):
        s = _state(NSV=0.3)
        s2 = apply_delta(s, {"NSV": -0.1}, GateThresholds(), renegotiation_event=False)
        assert s2.NSV == 0.3  # decrease blocked

    def test_theta_cools_with_tau_rise(self):
        """Without renegotiation event, Theta cools proportionally to tau rise."""
        s = _state(tau=0.3, Theta=0.7)
        th = GateThresholds(theta_cooling_rate=0.5)
        s2 = apply_delta(s, {"tau": 0.2}, th, renegotiation_event=False)
        # tau rises by 0.2; theta cools by 0.5 * 0.2 = 0.1
        assert s2.Theta == pytest.approx(0.6, abs=1e-9)

    def test_renegotiation_event_prevents_theta_cooling(self):
        s = _state(tau=0.3, Theta=0.7)
        th = GateThresholds(theta_cooling_rate=0.5)
        s2 = apply_delta(s, {"tau": 0.2}, th, renegotiation_event=True)
        assert s2.Theta == 0.7  # no cooling


# -- gate determinism --------------------------------------------------------

class TestGateDeterminism:
    """Pure function: same input, same output."""

    def test_same_input_same_output(self):
        s = _state()
        t = _t({"Omega": -0.1, "tau": 0.1, "NSV": 0.05})
        th = GateThresholds()
        out1 = evaluate(GateInput(current_state=s, transformation=t, thresholds=th))
        out2 = evaluate(GateInput(current_state=s, transformation=t, thresholds=th))
        assert out1.outcome == out2.outcome
        assert out1.reason_codes == out2.reason_codes
        assert out1.predicted_state == out2.predicted_state


# -- all four outcomes reachable ---------------------------------------------

class TestAllFourOutcomes:
    """Every gate outcome must be reachable. If one is unreachable, the spec is dead."""

    def test_execute_for_admissible_transformation(self):
        s = _state(Omega=0.7, tau=0.3, Theta=0.7, NSV=0.0)
        t = _t({"Omega": -0.05, "tau": 0.05, "NSV": 0.02})
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome == GateOutcome.EXECUTE
        assert GateReasonCode.ADMISSIBLE_AS_PROPOSED in out.reason_codes

    def test_reject_for_catastrophic_nsv(self):
        s = _state()
        t = _t({"NSV": 0.6})  # above catastrophic
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome == GateOutcome.REJECT
        assert GateReasonCode.NSV_STEP_EXCEEDED in out.reason_codes

    def test_reject_for_catastrophic_omega_collapse(self):
        s = _state(Omega=0.2)
        t = _t({"Omega": -0.18})  # would drop Omega to 0.02, below half-floor
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome == GateOutcome.REJECT
        assert GateReasonCode.OMEGA_BELOW_FLOOR in out.reason_codes

    def test_defer_for_theta_below_floor(self):
        """Renegotiability loss routes to DEFER, not REJECT."""
        s = _state(tau=0.3, Theta=0.3)
        # Large tau rise -> theta cools below floor
        t = _t({"tau": 0.5})
        th = GateThresholds(theta_floor=0.2, theta_cooling_rate=0.5)
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=th))
        # Theta would be: 0.3 - 0.5 * 0.5 = 0.05, below floor 0.2
        assert out.outcome == GateOutcome.DEFER
        assert GateReasonCode.THETA_BELOW_FLOOR in out.reason_codes

    def test_defer_for_tau_ceiling_without_hbtl(self):
        s = _state(tau=0.7)
        t = _t({"tau": 0.2})  # would reach 0.9, above ceiling
        out = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(tau_ceiling=0.85),
            hbtl_reviewed=False,
        ))
        assert out.outcome == GateOutcome.DEFER
        assert GateReasonCode.TAU_AT_CEILING_WITHOUT_HBTL in out.reason_codes
        assert GateReasonCode.HBTL_TRIGGER in out.reason_codes

    def test_transform_for_bounded_nsv_violation(self):
        """NSV step above max but below catastrophic -> TRANSFORM (reshape-eligible)."""
        s = _state()
        # nsv_step_max default is 0.2, catastrophic is 0.5
        t = _t({"NSV": 0.3})
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome == GateOutcome.TRANSFORM
        assert GateReasonCode.NSV_STEP_EXCEEDED in out.reason_codes
        assert GateReasonCode.RESHAPE_REQUIRED in out.reason_codes

    def test_transform_for_bounded_omega_drop(self):
        s = _state(Omega=0.8)
        # omega_drop_step_max default 0.4; drop by 0.5
        t = _t({"Omega": -0.5})
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.outcome == GateOutcome.TRANSFORM


# -- surface-class signals ---------------------------------------------------

class TestSurfaceSignals:
    def test_nodoid_categorical_reject(self):
        s = _state()
        t = _t({"Omega": -0.01})
        out = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(),
            surface_class="nodoid",
        ))
        assert out.outcome == GateOutcome.REJECT

    def test_collapse_funnel_defers(self):
        s = _state()
        t = _t({"Omega": -0.01})
        out = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(),
            surface_class="collapse_funnel",
        ))
        assert out.outcome == GateOutcome.DEFER


# -- hbtl_reviewed allows tau ceiling ----------------------------------------

class TestHBTLReview:
    def test_hbtl_reviewed_allows_tau_at_ceiling(self):
        s = _state(tau=0.7, NSV=0.0)
        t = _t({"tau": 0.2, "NSV": 0.05})  # would hit tau_ceiling
        out = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(tau_ceiling=0.85),
            hbtl_reviewed=True,
        ))
        # Should not DEFER on tau ceiling reason — HBTL has been done.
        assert GateReasonCode.TAU_AT_CEILING_WITHOUT_HBTL not in out.reason_codes


# -- threshold perturbability ------------------------------------------------

class TestThresholdPerturbation:
    """
    Q9: thresholds are perturbable. Same transformation, different thresholds,
    different outcomes — and the differences must be lawful.
    """

    def test_tighter_omega_floor_changes_outcome(self):
        s = _state(Omega=0.25)
        t = _t({"Omega": -0.1})  # would drop to 0.15

        # Loose floor (0.1): EXECUTE
        out_loose = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(omega_floor=0.1),
        ))
        # Tight floor (0.2): DEFER or REJECT
        out_tight = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(omega_floor=0.2),
        ))
        assert out_loose.outcome == GateOutcome.EXECUTE
        assert out_tight.outcome in {GateOutcome.REJECT, GateOutcome.DEFER, GateOutcome.TRANSFORM}

    def test_lawful_nsv_threshold_perturbation(self):
        """Increasing NSV step max should make a previously-TRANSFORM transformation EXECUTE."""
        s = _state()
        t = _t({"NSV": 0.25})

        out_strict = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(nsv_step_max=0.20),
        ))
        out_lax = evaluate(GateInput(
            current_state=s, transformation=t,
            thresholds=GateThresholds(nsv_step_max=0.30),
        ))
        assert out_strict.outcome == GateOutcome.TRANSFORM
        assert out_lax.outcome == GateOutcome.EXECUTE


# -- predicted_state always present ------------------------------------------

class TestPredictedStateAlwaysPresent:
    """Every gate output carries the predicted S(t+1), even on REJECT/DEFER."""

    @pytest.mark.parametrize("delta,expected_outcome_in", [
        ({"Omega": -0.01, "NSV": 0.01}, {GateOutcome.EXECUTE}),
        ({"NSV": 0.6}, {GateOutcome.REJECT}),
        ({"NSV": 0.3}, {GateOutcome.TRANSFORM}),
    ])
    def test_predicted_state_present(self, delta, expected_outcome_in):
        s = _state()
        t = _t(delta)
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert out.predicted_state is not None
        assert out.predicted_state.logical_step == s.logical_step + 1
        assert out.outcome in expected_outcome_in
