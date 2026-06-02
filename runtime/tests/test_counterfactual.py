"""
Tests for components/counterfactual.py.

Verifies the constitutional invariant: counterfactual evaluations may be
inspected but never committed.

Key properties:
- The verdict is IDENTICAL in both modes (trustworthiness: a hypothetical and
  a real evaluation of the same inputs agree).
- AUTHORITATIVE evaluations yield a CommitToken.
- COUNTERFACTUAL evaluations never yield a CommitToken; commit_token() raises.
- A CommitToken cannot be hand-constructed for a counterfactual evaluation.
- counterfactual_compare evaluates policy variants without any commit path.
"""
import pytest

from runtime.core.types import FieldState, Transformation, GateOutcome
from runtime.components.gate import GateInput, GateThresholds
from runtime.components.counterfactual import (
    EvaluationMode,
    CommitToken,
    EvaluationResult,
    CounterfactualWriteAttempt,
    evaluate_with_mode,
    counterfactual_compare,
)


def _state(**kw):
    d = dict(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
    d.update(kw)
    return FieldState(**d)


def _t(delta):
    return Transformation.new(typed_effects=delta)


def _gi(state=None, delta=None, thresholds=None):
    return GateInput(
        current_state=state or _state(),
        transformation=_t(delta or {"tau": 0.05, "NSV": 0.02}),
        thresholds=thresholds or GateThresholds(),
    )


class TestVerdictIdenticalAcrossModes:
    """The verdict must not depend on mode. This is what makes counterfactual trustworthy."""

    def test_same_inputs_same_verdict_both_modes(self):
        gi = _gi()
        auth = evaluate_with_mode(gi, EvaluationMode.AUTHORITATIVE)
        cf = evaluate_with_mode(gi, EvaluationMode.COUNTERFACTUAL)
        assert auth.outcome == cf.outcome
        assert auth.predicted_state == cf.predicted_state
        assert auth.gate_output.reason_codes == cf.gate_output.reason_codes

    def test_reject_verdict_identical_both_modes(self):
        gi = _gi(delta={"NSV": 0.6})  # catastrophic -> REJECT
        auth = evaluate_with_mode(gi, EvaluationMode.AUTHORITATIVE)
        cf = evaluate_with_mode(gi, EvaluationMode.COUNTERFACTUAL)
        assert auth.outcome == GateOutcome.REJECT
        assert cf.outcome == GateOutcome.REJECT


class TestAuthoritativeYieldsCommitToken:
    def test_authoritative_is_committable(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.AUTHORITATIVE)
        assert res.is_committable is True

    def test_authoritative_commit_token_accessible(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.AUTHORITATIVE)
        token = res.commit_token()
        assert isinstance(token, CommitToken)
        assert token.mode == EvaluationMode.AUTHORITATIVE


class TestCounterfactualNeverCommits:
    """The core constitutional invariant."""

    def test_counterfactual_not_committable(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.COUNTERFACTUAL)
        assert res.is_committable is False

    def test_counterfactual_commit_token_raises(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.COUNTERFACTUAL)
        with pytest.raises(CounterfactualWriteAttempt, match="never committed"):
            res.commit_token()

    def test_counterfactual_verdict_still_inspectable(self):
        """Counterfactual can be SEEN, just not committed."""
        res = evaluate_with_mode(_gi(), EvaluationMode.COUNTERFACTUAL)
        # The verdict and predicted state are accessible
        assert res.outcome in set(GateOutcome)
        assert res.predicted_state is not None


class TestCommitTokenCannotBeForged:
    """A CommitToken cannot be hand-constructed for a counterfactual evaluation."""

    def test_commit_token_rejects_counterfactual_mode(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.COUNTERFACTUAL)
        with pytest.raises(CounterfactualWriteAttempt):
            CommitToken(mode=EvaluationMode.COUNTERFACTUAL, gate_output=res.gate_output)

    def test_commit_token_accepts_authoritative_mode(self):
        res = evaluate_with_mode(_gi(), EvaluationMode.AUTHORITATIVE)
        # Constructing one for authoritative is fine
        token = CommitToken(mode=EvaluationMode.AUTHORITATIVE, gate_output=res.gate_output)
        assert token.mode == EvaluationMode.AUTHORITATIVE


class TestCounterfactualCompare:
    """Policy-variant comparison, all counterfactual by construction."""

    def test_compare_returns_outcome_per_variant(self):
        state = _state(Omega=0.25)
        t = _t({"Omega": -0.1})  # would drop Omega to 0.15
        variants = {
            "loose": GateThresholds(omega_floor=0.05),
            "tight": GateThresholds(omega_floor=0.20),
        }
        results = counterfactual_compare(state, t, variants)
        assert set(results.keys()) == {"loose", "tight"}
        # Under loose floor: EXECUTE. Under tight floor: not EXECUTE.
        assert results["loose"] == GateOutcome.EXECUTE
        assert results["tight"] != GateOutcome.EXECUTE

    def test_compare_outcomes_are_gate_outcomes(self):
        results = counterfactual_compare(
            _state(), _t({"tau": 0.05}),
            {"default": GateThresholds()},
        )
        assert results["default"] in set(GateOutcome)


class TestArchitecturalBoundary:
    """
    Document the architectural decision: the pure gate is untouched. The mode
    lives at the commit boundary. This test confirms the gate's evaluate is
    still callable directly and mode-free.
    """

    def test_pure_gate_still_mode_free(self):
        from runtime.components.gate import evaluate
        out = evaluate(_gi())
        # The pure gate returns a GateOutput with no notion of mode
        assert not hasattr(out, "mode")
        assert out.outcome in set(GateOutcome)
