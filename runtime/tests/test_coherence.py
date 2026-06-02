"""
Tests for components/coherence.py and its wiring into the gate (K2).

The defining property to prove: the coherence relation is IRREDUCIBLE to
per-dimension bounds — it flags a joint combination where each coordinate is
individually in-bounds. If it were reducible, it would be just another threshold.

Verifies:
- A jointly-incoherent state (high tau + high Theta) is flagged, though each
  coordinate is individually valid.
- A coherent state is not flagged.
- The relation routes to TRANSFORM (reshapeable severity) in the gate.
- coherence_relation_count() == 1 here (one STATIC relation); constitution
  reports 2 total couplings (this + the dynamic theta_tau coupling).
- The region is no longer a box (the mechanical manifold test).
"""
import pytest

from runtime.core.types import FieldState, Transformation, GateOutcome, GateReasonCode
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.coherence import (
    check_coherence, coherence_relation_count, CoherenceSeverity,
    COMMITMENT_RENEGOTIABILITY_BOUND, COMMITMENT_RENEGOTIABILITY_RELATION,
)
from runtime.components.constitution import constitution


def _state(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0):
    return FieldState(Omega=Omega, rho=rho, kappa=kappa, tau=tau, Theta=Theta, NSV=NSV, logical_step=0)


class TestIrreducibility:
    """The relation flags a joint combination where each coordinate is in-bounds."""

    def test_high_tau_high_theta_is_incoherent(self):
        # tau=0.8 (in [0,1]), Theta=0.8 (in [0,1]) — each individually valid —
        # but sum 1.6 > bound 1.4 -> incoherent.
        s = _state(tau=0.8, Theta=0.8)
        violations = check_coherence(s)
        assert len(violations) == 1
        assert violations[0].relation_name == "commitment_renegotiability_coherence"

    def test_each_coordinate_individually_inbounds(self):
        # Confirm the point of irreducibility: neither coordinate alone violates
        # any per-dimension bound; only their COMBINATION does.
        s = _state(tau=0.8, Theta=0.8)
        assert 0.0 <= s.tau <= 1.0   # individually fine
        assert 0.0 <= s.Theta <= 1.0  # individually fine
        assert check_coherence(s)     # but jointly incoherent

    def test_high_tau_low_theta_is_coherent(self):
        # Deep commitment with LOW renegotiability is coherent (that is what
        # commitment IS). tau=0.8, Theta=0.2, sum 1.0 <= 1.4.
        s = _state(tau=0.8, Theta=0.2)
        assert check_coherence(s) == []

    def test_low_tau_high_theta_is_coherent(self):
        # Shallow commitment with high renegotiability is coherent.
        s = _state(tau=0.2, Theta=0.8)
        assert check_coherence(s) == []


class TestBoundExactness:
    def test_at_bound_is_coherent(self):
        # tau + Theta == bound exactly -> coherent (<=).
        s = _state(tau=0.7, Theta=0.7)  # sum 1.4 == bound
        assert check_coherence(s) == []

    def test_just_over_bound_is_incoherent(self):
        s = _state(tau=0.71, Theta=0.7)  # sum 1.41 > bound
        assert len(check_coherence(s)) == 1


class TestGateRouting:
    """A coherence violation routes to TRANSFORM (reshapeable) in the gate."""

    def test_gate_routes_incoherent_to_transform(self):
        # Start coherent, transform INTO an incoherent joint state.
        # Start tau=0.6, Theta=0.85 (sum 1.45 > 1.4) is already incoherent, so
        # build a transformation that lands there from a coherent start.
        # Use a renegotiation event so Theta does not cool, producing high+high.
        s = _state(tau=0.6, Theta=0.85)  # predicted will inherit; pick delta small
        t = Transformation.new(typed_effects={"tau": 0.05})
        out = evaluate(GateInput(current_state=s, transformation=t,
                                 thresholds=GateThresholds(), renegotiation_event=True))
        # predicted tau ~0.65, Theta ~0.85 (no cooling due to renegotiation) -> sum 1.5
        assert GateReasonCode.COHERENCE_VIOLATION in out.reason_codes
        assert out.outcome == GateOutcome.TRANSFORM

    def test_coherent_transform_not_flagged(self):
        s = _state(tau=0.3, Theta=0.7)
        t = Transformation.new(typed_effects={"tau": 0.05, "NSV": 0.02})
        out = evaluate(GateInput(current_state=s, transformation=t, thresholds=GateThresholds()))
        assert GateReasonCode.COHERENCE_VIOLATION not in out.reason_codes


class TestRegionIsNoLongerABox:
    """The mechanical manifold test."""

    def test_static_coherence_relation_present(self):
        assert coherence_relation_count() == 1  # one STATIC joint relation

    def test_constitution_reports_two_couplings(self):
        # The static relation + the dynamic theta_tau coupling = 2 total.
        assert constitution().coherence_relation_count() == 2

    def test_region_no_longer_box(self):
        # count > 1 is the mechanical test: the admissible region is defined by
        # relations AMONG coordinates, not independent per-dimension bounds.
        assert constitution().coherence_relation_count() > 1

    def test_relation_severity_is_reshapeable(self):
        assert COMMITMENT_RENEGOTIABILITY_RELATION.severity == CoherenceSeverity.RESHAPEABLE
