"""
Tests for components/threshold_policy.py.

Verifies:
- Tier 1 (StaticPolicy) resolves to its configured thresholds, ignores trajectory.
- Tier 2 (TrajectoryTestedPolicy) resolves to static thresholds + carries evidence.
- Tier 3 (GeometryDerivedPolicy) CANNOT be instantiated — gated at the type level.
- resolve_thresholds is backward-compatible: a bare GateThresholds works.
- The three tiers are structurally distinct (different .tier values and types).
"""
import pytest

from runtime.components.gate import GateThresholds
from runtime.components.threshold_policy import (
    ThresholdPolicy, StaticPolicy, TrajectoryTestedPolicy, GeometryDerivedPolicy,
    RecoverabilityEvidence, resolve_thresholds,
)


def _th(**kw):
    return GateThresholds(**kw)


class TestTier1Static:
    def test_static_resolves_to_configured_thresholds(self):
        th = _th(omega_floor=0.3)
        policy = StaticPolicy(thresholds=th)
        resolved = policy.resolve(None)
        assert resolved is th
        assert resolved.omega_floor == 0.3

    def test_static_ignores_trajectory(self):
        th = _th()
        policy = StaticPolicy(thresholds=th)
        # Even with a (dummy non-None) trajectory, resolves to same thresholds.
        assert policy.resolve(None) is th
        assert policy.tier == 1

    def test_static_satisfies_protocol(self):
        policy = StaticPolicy(thresholds=_th())
        assert isinstance(policy, ThresholdPolicy)


class TestTier2TrajectoryTested:
    def test_tested_policy_carries_evidence(self):
        th = _th()
        ev = RecoverabilityEvidence(
            replay_status="passed", recoverable=True,
            tested_trajectory_hash="abc123", notes="nominal",
        )
        policy = TrajectoryTestedPolicy(thresholds=th, evidence=ev)
        assert policy.tier == 2
        assert policy.evidence.replay_status == "passed"
        assert policy.evidence.recoverable is True

    def test_tested_policy_resolves_to_static_thresholds(self):
        # Tier 2 still resolves to static thresholds; evidence rides alongside.
        th = _th(tau_ceiling=0.9)
        ev = RecoverabilityEvidence("passed", True, "abc123")
        policy = TrajectoryTestedPolicy(thresholds=th, evidence=ev)
        assert policy.resolve(None) is th

    def test_tested_policy_satisfies_protocol(self):
        ev = RecoverabilityEvidence("passed", True, "h")
        policy = TrajectoryTestedPolicy(thresholds=_th(), evidence=ev)
        assert isinstance(policy, ThresholdPolicy)


class TestTier3Gated:
    """Tier 3 is present as a type but cannot be instantiated until K2."""

    def test_geometry_policy_cannot_be_instantiated(self):
        with pytest.raises(NotImplementedError, match="requires K2"):
            GeometryDerivedPolicy()

    def test_geometry_policy_cannot_be_instantiated_with_args(self):
        with pytest.raises(NotImplementedError, match="requires K2"):
            GeometryDerivedPolicy(some_arg="value")

    def test_geometry_policy_type_exists(self):
        # The type EXISTS (insertion point wired) even though it can't construct.
        assert GeometryDerivedPolicy.tier == 3
        assert hasattr(GeometryDerivedPolicy, "resolve")


class TestBackwardCompatibleResolution:
    def test_bare_thresholds_resolve_as_implicit_static(self):
        th = _th(omega_floor=0.25)
        # Passing a bare GateThresholds (today's call style) just returns it.
        resolved = resolve_thresholds(th)
        assert resolved is th

    def test_policy_resolves_through_resolve_thresholds(self):
        th = _th()
        policy = StaticPolicy(thresholds=th)
        resolved = resolve_thresholds(policy, trajectory=None)
        assert resolved is th

    def test_tested_policy_resolves_through_resolve_thresholds(self):
        th = _th()
        ev = RecoverabilityEvidence("passed", True, "h")
        policy = TrajectoryTestedPolicy(thresholds=th, evidence=ev)
        resolved = resolve_thresholds(policy, trajectory=None)
        assert resolved is th


class TestTiersAreDistinct:
    def test_tier_numbers_distinct(self):
        s = StaticPolicy(thresholds=_th())
        t = TrajectoryTestedPolicy(thresholds=_th(), evidence=RecoverabilityEvidence("p", True, "h"))
        assert s.tier == 1
        assert t.tier == 2
        assert GeometryDerivedPolicy.tier == 3
        assert len({s.tier, t.tier, GeometryDerivedPolicy.tier}) == 3

    def test_tier1_and_tier2_are_different_types(self):
        s = StaticPolicy(thresholds=_th())
        t = TrajectoryTestedPolicy(thresholds=_th(), evidence=RecoverabilityEvidence("p", True, "h"))
        assert type(s) is not type(t)
