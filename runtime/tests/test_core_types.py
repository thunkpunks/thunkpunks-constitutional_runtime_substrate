"""
Tests for core/types.py.

Each test verifies one constitutional invariant. Test names describe the
invariant, not the implementation detail.
"""
import json
import pytest

from runtime.core.types import (
    FieldState,
    GateOutcome,
    GateReasonCode,
    Transformation,
    Provenance,
    parameter_set_hash,
    PayloadType,
    Envelope,
)


# -- FieldState bounds --------------------------------------------------------

class TestFieldStateBounds:
    """FieldState enforces bounds at construction; out-of-bounds is a violation."""

    def test_valid_state_constructs(self):
        s = FieldState(Omega=0.5, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.1, logical_step=0)
        assert s.Omega == 0.5

    def test_omega_above_one_rejected(self):
        with pytest.raises(ValueError, match="Omega"):
            FieldState(Omega=1.5, rho=0, kappa=0, tau=0.3, Theta=0.7, NSV=0, logical_step=0)

    def test_omega_below_zero_rejected(self):
        with pytest.raises(ValueError, match="Omega"):
            FieldState(Omega=-0.1, rho=0, kappa=0, tau=0.3, Theta=0.7, NSV=0, logical_step=0)

    def test_tau_above_one_rejected(self):
        with pytest.raises(ValueError, match="tau"):
            FieldState(Omega=0.5, rho=0, kappa=0, tau=1.1, Theta=0.7, NSV=0, logical_step=0)

    def test_theta_below_zero_rejected(self):
        with pytest.raises(ValueError, match="Theta"):
            FieldState(Omega=0.5, rho=0, kappa=0, tau=0.3, Theta=-0.01, NSV=0, logical_step=0)

    def test_nsv_negative_rejected(self):
        with pytest.raises(ValueError, match="NSV"):
            FieldState(Omega=0.5, rho=0, kappa=0, tau=0.3, Theta=0.7, NSV=-1.0, logical_step=0)

    def test_logical_step_negative_rejected(self):
        with pytest.raises(ValueError, match="logical_step"):
            FieldState(Omega=0.5, rho=0, kappa=0, tau=0.3, Theta=0.7, NSV=0, logical_step=-1)

    def test_state_is_frozen(self):
        """FieldState is immutable. Transitions produce new instances."""
        s = FieldState(Omega=0.5, rho=0, kappa=0, tau=0.3, Theta=0.7, NSV=0, logical_step=0)
        with pytest.raises((AttributeError, Exception)):
            s.Omega = 0.6  # frozen dataclass


# -- GateOutcome closure ------------------------------------------------------

class TestGateOutcomeClosure:
    """The outcome space is exactly four. No fifth UNKNOWN."""

    def test_outcomes_are_exactly_four(self):
        outcomes = set(GateOutcome)
        assert outcomes == {
            GateOutcome.EXECUTE,
            GateOutcome.TRANSFORM,
            GateOutcome.DEFER,
            GateOutcome.REJECT,
        }
        assert len(outcomes) == 4

    def test_no_unknown_outcome(self):
        with pytest.raises((AttributeError, ValueError)):
            GateOutcome.UNKNOWN  # constitutional refusal


# -- Provenance hashing -------------------------------------------------------

class TestParameterSetHash:
    """parameter_set_hash is stable and order-independent."""

    def test_same_params_same_hash(self):
        a = parameter_set_hash({"omega_floor": 0.1, "tau_ceiling": 0.85})
        b = parameter_set_hash({"omega_floor": 0.1, "tau_ceiling": 0.85})
        assert a == b

    def test_order_independent(self):
        a = parameter_set_hash({"omega_floor": 0.1, "tau_ceiling": 0.85})
        b = parameter_set_hash({"tau_ceiling": 0.85, "omega_floor": 0.1})
        assert a == b

    def test_different_params_different_hash(self):
        a = parameter_set_hash({"omega_floor": 0.1, "tau_ceiling": 0.85})
        b = parameter_set_hash({"omega_floor": 0.2, "tau_ceiling": 0.85})
        assert a != b


# -- Envelope construction ----------------------------------------------------

class TestEnvelopeConstruction:
    """Envelopes are addressable and carry provenance."""

    def test_new_envelope_has_unique_id(self):
        e1 = Envelope.new(
            logical_step=0,
            component_id="test",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={"Omega": 0.5},
            provenance_ref="prov-1",
        )
        e2 = Envelope.new(
            logical_step=0,
            component_id="test",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={"Omega": 0.5},
            provenance_ref="prov-1",
        )
        assert e1.envelope_id != e2.envelope_id

    def test_envelope_carries_provenance_ref(self):
        e = Envelope.new(
            logical_step=0,
            component_id="test",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={},
            provenance_ref="prov-1",
        )
        assert e.provenance_ref == "prov-1"

    def test_envelope_serializes_to_json(self):
        """Envelopes must be JSON-serializable for replay persistence."""
        e = Envelope.new(
            logical_step=0,
            component_id="test",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={"Omega": 0.5},
            provenance_ref="prov-1",
        )
        d = e.to_dict()
        json.dumps(d)  # raises if not serializable
        assert d["payload_type"] == "field_state"
