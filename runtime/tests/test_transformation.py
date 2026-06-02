"""
Tests for the first-class Transformation object.

Verifies:
- Backward compatibility: Transformation.new(expected_delta=...) still works.
- The typed path: intent_class, reversibility, commitment cost.
- expected_delta accessor maps to typed_effects.
- Serialization round-trips.
- The gate still reads transformations correctly (via expected_delta accessor).
"""
import pytest

from runtime.core.types import (
    Transformation,
    IntentClass,
    ReversibilityClass,
    ReversibilityMetadata,
    FieldState,
)
from runtime.components.gate import GateThresholds, GateInput, evaluate


class TestBackwardCompatibility:
    """The old construction path must keep working."""

    def test_new_with_expected_delta_still_works(self):
        t = Transformation.new(expected_delta={"tau": 0.05, "NSV": 0.02})
        assert t.typed_effects == {"tau": 0.05, "NSV": 0.02}
        assert t.expected_delta == {"tau": 0.05, "NSV": 0.02}  # accessor

    def test_new_with_description_still_works(self):
        t = Transformation.new(expected_delta={"tau": 0.05}, description="modest")
        assert t.description == "modest"

    def test_expected_delta_accessor_maps_to_typed_effects(self):
        t = Transformation.new(typed_effects={"Omega": -0.1})
        assert t.expected_delta is t.typed_effects


class TestTypedPath:
    """The first-class fields are real and constructable."""

    def test_intent_class_defaults_to_unspecified(self):
        t = Transformation.new(typed_effects={"tau": 0.1})
        assert t.intent_class == IntentClass.UNSPECIFIED

    def test_intent_class_can_be_set(self):
        t = Transformation.new(typed_effects={"tau": 0.1}, intent_class=IntentClass.COMMIT)
        assert t.intent_class == IntentClass.COMMIT

    def test_reversibility_defaults_to_unknown(self):
        t = Transformation.new(typed_effects={"tau": 0.1})
        assert t.reversibility.reversibility_class == ReversibilityClass.UNKNOWN

    def test_reversibility_can_be_set(self):
        rev = ReversibilityMetadata(
            reversibility_class=ReversibilityClass.IRREVERSIBLE,
            reversal_cost=0.0,
            rationale="commits external resource",
        )
        t = Transformation.new(typed_effects={"NSV": 0.3}, reversibility=rev)
        assert t.reversibility.reversibility_class == ReversibilityClass.IRREVERSIBLE
        assert t.reversibility.rationale == "commits external resource"

    def test_commitment_cost_defaults_to_tau_effect(self):
        t = Transformation.new(typed_effects={"tau": 0.15, "NSV": 0.02})
        assert t.expected_commitment_cost == 0.15

    def test_commitment_cost_can_be_overridden(self):
        t = Transformation.new(
            typed_effects={"tau": 0.15}, expected_commitment_cost=0.5
        )
        assert t.expected_commitment_cost == 0.5

    def test_commitment_cost_zero_when_no_tau_effect(self):
        t = Transformation.new(typed_effects={"Omega": -0.1})
        assert t.expected_commitment_cost == 0.0

    def test_provenance_ref_optional(self):
        t = Transformation.new(typed_effects={"tau": 0.1}, provenance_ref="prov-1")
        assert t.provenance_ref == "prov-1"


class TestConstructionGuards:
    """The constructor enforces consistency."""

    def test_neither_effects_nor_delta_raises(self):
        with pytest.raises(ValueError, match="must supply"):
            Transformation.new()

    def test_conflicting_effects_and_delta_raises(self):
        with pytest.raises(ValueError, match="differ"):
            Transformation.new(
                expected_delta={"tau": 0.1},
                typed_effects={"tau": 0.2},
            )

    def test_matching_effects_and_delta_ok(self):
        t = Transformation.new(
            expected_delta={"tau": 0.1},
            typed_effects={"tau": 0.1},
        )
        assert t.typed_effects == {"tau": 0.1}


class TestSerialization:
    """Transformation serializes to a stable dict shape for the replay ledger."""

    def test_to_dict_has_all_first_class_fields(self):
        t = Transformation.new(
            typed_effects={"tau": 0.1, "NSV": 0.02},
            intent_class=IntentClass.COMMIT,
            reversibility=ReversibilityMetadata(
                reversibility_class=ReversibilityClass.COSTLY_REVERSIBLE,
                reversal_cost=0.05,
            ),
            description="test commit",
        )
        d = t.to_dict()
        assert set(d.keys()) == {
            "transformation_id",
            "typed_effects",
            "intent_class",
            "reversibility",
            "expected_commitment_cost",
            "provenance_ref",
            "description",
            "composed_from",
        }
        assert d["intent_class"] == "commit"
        assert d["reversibility"]["reversibility_class"] == "costly"

    def test_to_dict_is_json_serializable(self):
        import json
        t = Transformation.new(typed_effects={"tau": 0.1}, intent_class=IntentClass.EXPLORE)
        json.dumps(t.to_dict())  # raises if not serializable


class TestGateStillReadsTransformations:
    """The gate reads transformations via expected_delta; the upgrade is transparent to it."""

    def test_gate_evaluates_typed_transformation(self):
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        t = Transformation.new(
            typed_effects={"tau": 0.05, "NSV": 0.02},
            intent_class=IntentClass.COMMIT,
        )
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        # The gate produces a verdict regardless of the new typed fields
        assert out.outcome is not None
        assert out.predicted_state.tau == pytest.approx(0.35)
