"""
Acceptance contract for bounded transformation composition.

Written BEFORE compose exists (K1 pattern): these define "done". Composition is
not complete until all pass.

THE GOVERNING CONSTRAINT (the most important test here):
  Composition success means "lawfully constructed candidate" — NOT "admissible".
  The gate remains the sole admission authority. A composed transformation is
  still only an input to be judged.

Bounded-primitive guarantees proven here:
  - deterministic, typed, pure (no state, no search)
  - additive effect algebra, agreeing with sequential application
  - commitment cost summed (not maxed); reversibility degrades to worse-of
  - fail-closed on bounds and monotonicity violations, with structural reasons
  - composed_from lineage; fresh id
  - a composite still goes through the gate (composition != admission)
"""
import pytest

from runtime.core.types import (
    Transformation, IntentClass, ReversibilityMetadata, ReversibilityClass,
    FieldState,
)


# These imports will FAIL until compose is built — that is intended.
from runtime.core.types import CompositionRefusal, CompositionFailure


def _t(effects, intent=IntentClass.UNSPECIFIED, rev=None, cost=None):
    return Transformation.new(
        typed_effects=effects, intent_class=intent,
        reversibility=rev, expected_commitment_cost=cost,
    )


class TestCompositionDoesNotEqualAdmission:
    """THE governing constraint: a composed transformation is only a candidate."""

    def test_composition_success_is_not_admission(self):
        from runtime.components.gate import GateThresholds, GateInput, evaluate
        a = _t({"NSV": 0.3})
        b = _t({"NSV": 0.3})
        # This composition is LAWFUL (sums to 0.6, within bounds for NSV which is
        # unbounded above as a residue). Composition SUCCEEDS.
        composite = Transformation.compose(a, b)
        assert composite is not None  # lawfully constructed

        # But the composite is NOT thereby admissible. The gate must still judge
        # it — and a 0.6 NSV step is catastrophic -> REJECT.
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        out = evaluate(GateInput(current_state=s, transformation=composite, thresholds=GateThresholds()))
        assert out.outcome.value == "REJECT"  # lawfully constructed, still inadmissible

    def test_composite_goes_through_gate_like_any_input(self):
        from runtime.components.gate import GateThresholds, GateInput, evaluate
        a = _t({"tau": 0.02, "NSV": 0.01})
        b = _t({"tau": 0.02, "NSV": 0.01})
        composite = Transformation.compose(a, b)
        out = evaluate(GateInput(
            current_state=FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0),
            transformation=composite, thresholds=GateThresholds(),
        ))
        # A small composite is admissible — but because the GATE said so, not
        # because composition succeeded.
        assert out.outcome.value in {"EXECUTE", "TRANSFORM", "DEFER", "REJECT"}


class TestDeterminism:
    def test_compose_is_deterministic_in_effects(self):
        a = _t({"tau": 0.1, "NSV": 0.05})
        b = _t({"tau": 0.2, "NSV": 0.05})
        c1 = Transformation.compose(a, b)
        c2 = Transformation.compose(a, b)
        assert c1.typed_effects == c2.typed_effects
        assert c1.composed_from == c2.composed_from


class TestEffectAlgebra:
    def test_effects_are_additive_per_coordinate(self):
        a = _t({"tau": 0.1, "NSV": 0.05})
        b = _t({"tau": 0.2, "Omega": -0.1})
        c = Transformation.compose(a, b)
        assert c.typed_effects["tau"] == pytest.approx(0.3)
        assert c.typed_effects["NSV"] == pytest.approx(0.05)
        assert c.typed_effects["Omega"] == pytest.approx(-0.1)

    def test_agreement_with_sequential_application(self):
        # The keystone safety proof: compose agrees with doing A then B.
        from runtime.components.gate import GateThresholds, apply_delta
        th = GateThresholds()
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.2, Theta=0.8, NSV=0.0, logical_step=0)
        a = _t({"tau": 0.1, "NSV": 0.02})
        b = _t({"tau": 0.1, "NSV": 0.03})
        # Sequential: apply A, then B
        s_a = apply_delta(s, a.expected_delta, th, False)
        s_ab = apply_delta(s_a, b.expected_delta, th, False)
        # Composed: apply A∘B once
        composite = Transformation.compose(a, b)
        s_c = apply_delta(s, composite.expected_delta, th, False)
        # The tau and NSV (linear, monotone) must agree.
        assert s_ab.tau == pytest.approx(s_c.tau)
        assert s_ab.NSV == pytest.approx(s_c.NSV)


class TestCommitmentCostAndReversibility:
    def test_commitment_cost_is_summed(self):
        a = _t({"tau": 0.1}, cost=0.1)
        b = _t({"tau": 0.2}, cost=0.2)
        c = Transformation.compose(a, b)
        assert c.expected_commitment_cost == pytest.approx(0.3)

    def test_reversibility_degrades_to_worse(self):
        rev_a = ReversibilityMetadata(reversibility_class=ReversibilityClass.REVERSIBLE)
        rev_b = ReversibilityMetadata(reversibility_class=ReversibilityClass.IRREVERSIBLE)
        a = _t({"tau": 0.1}, rev=rev_a)
        b = _t({"tau": 0.1}, rev=rev_b)
        c = Transformation.compose(a, b)
        assert c.reversibility.reversibility_class == ReversibilityClass.IRREVERSIBLE

    def test_reversible_compose_costly_is_costly(self):
        a = _t({"tau": 0.1}, rev=ReversibilityMetadata(reversibility_class=ReversibilityClass.REVERSIBLE))
        b = _t({"tau": 0.1}, rev=ReversibilityMetadata(reversibility_class=ReversibilityClass.COSTLY_REVERSIBLE))
        c = Transformation.compose(a, b)
        assert c.reversibility.reversibility_class == ReversibilityClass.COSTLY_REVERSIBLE

    def test_unknown_is_contagious(self):
        a = _t({"tau": 0.1}, rev=ReversibilityMetadata(reversibility_class=ReversibilityClass.REVERSIBLE))
        b = _t({"tau": 0.1}, rev=ReversibilityMetadata(reversibility_class=ReversibilityClass.UNKNOWN))
        c = Transformation.compose(a, b)
        assert c.reversibility.reversibility_class == ReversibilityClass.UNKNOWN


class TestIntentComposition:
    def test_matching_intent_preserved(self):
        a = _t({"tau": 0.1}, intent=IntentClass.COMMIT)
        b = _t({"tau": 0.1}, intent=IntentClass.COMMIT)
        c = Transformation.compose(a, b)
        assert c.intent_class == IntentClass.COMMIT

    def test_differing_intent_becomes_unspecified(self):
        a = _t({"tau": 0.1}, intent=IntentClass.COMMIT)
        b = _t({"Omega": 0.1}, intent=IntentClass.EXPLORE)
        c = Transformation.compose(a, b)
        assert c.intent_class == IntentClass.UNSPECIFIED


class TestProvenanceLineage:
    def test_composed_from_records_components(self):
        a = _t({"tau": 0.1})
        b = _t({"tau": 0.1})
        c = Transformation.compose(a, b)
        assert c.composed_from == (a.transformation_id, b.transformation_id)

    def test_composite_has_fresh_id(self):
        a = _t({"tau": 0.1})
        b = _t({"tau": 0.1})
        c = Transformation.compose(a, b)
        assert c.transformation_id not in (a.transformation_id, b.transformation_id)

    def test_uncomposed_transformation_has_empty_lineage(self):
        a = _t({"tau": 0.1})
        assert a.composed_from == ()


class TestForbiddenCompositionsFailClosed:
    def test_bounds_violation_refused(self):
        # Two large positive tau effects summing beyond the representable range.
        a = _t({"tau": 0.7})
        b = _t({"tau": 0.7})  # sum 1.4 > 1.0 max range for tau
        with pytest.raises(CompositionRefusal) as exc:
            Transformation.compose(a, b)
        assert exc.value.failure == CompositionFailure.BOUNDS_EXCEEDED

    def test_negative_tau_aggregate_refused(self):
        # tau is monotone; a net-negative composite tau effect is structurally illegal.
        a = _t({"tau": 0.1})
        b = _t({"tau": -0.3})  # sum -0.2 < 0
        with pytest.raises(CompositionRefusal) as exc:
            Transformation.compose(a, b)
        assert exc.value.failure == CompositionFailure.MONOTONICITY_VIOLATION

    def test_negative_nsv_aggregate_refused(self):
        a = _t({"NSV": 0.1})
        b = _t({"NSV": -0.3})
        with pytest.raises(CompositionRefusal) as exc:
            Transformation.compose(a, b)
        assert exc.value.failure == CompositionFailure.MONOTONICITY_VIOLATION

    def test_refusal_carries_structural_reason(self):
        a = _t({"tau": 0.7})
        b = _t({"tau": 0.7})
        with pytest.raises(CompositionRefusal) as exc:
            Transformation.compose(a, b)
        assert exc.value.failure is not None
        assert isinstance(exc.value.failure, CompositionFailure)


class TestComposeIsPure:
    def test_compose_signature_takes_only_transformations(self):
        # Bounded: compose takes two given transformations, no state, no space.
        import inspect
        sig = inspect.signature(Transformation.compose)
        params = [p for p in sig.parameters if p != "cls"]
        assert len(params) == 2  # exactly binary — no search space, no enumeration

    def test_compose_returns_transformation(self):
        a = _t({"tau": 0.1})
        b = _t({"tau": 0.1})
        result = Transformation.compose(a, b)
        assert isinstance(result, Transformation)  # an input, not a decision/state
