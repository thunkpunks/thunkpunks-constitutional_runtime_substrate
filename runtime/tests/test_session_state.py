"""
Stress tests for the bench-runtime interface.

The five tests the pronouncement requires, plus three new ones that emerged
from the consolidation:

- T6: TRANSFORM is non-terminal — gate-outcome TRANSFORM does NOT advance
       the session (this was the bug consolidated out).
- T7: FAST_PRUNED is structurally distinct from gate REJECT (pre-gate
       outcomes never appear in GateOutcome and vice versa).
- T8: TraceRecord captures both prior and next session state for replay.

If any of these fail, the integration is unsafe.
"""
import pytest

from runtime.core.types import (
    FieldState,
    Transformation,
    GateOutcome,
    PayloadType,
)
from runtime.core.bench_interface import (
    BenchObservation,
    SessionState,
    PreGateOutcome,
    PreGateOutput,
    Lambda0Status,
    TraceRecord,
)
from runtime.core.authority import AuthorityViolation, check_write_authority
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.session_manager import (
    project_to_field_state,
    advance_session_on_accepted,
    passthrough_session_on_unaccepted,
    build_analytics,
    is_accepting,
    ACCEPTING_OUTCOMES,
)


def _obs(
    Omega=0.5, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5,
    session_id="sess-1", tick_id="tick-1", timestamp_ms=0,
) -> BenchObservation:
    return BenchObservation(
        Omega=Omega, rho=rho, kappa=kappa, NSV=NSV, Energy=Energy,
        omega_raw=tuple([0.5] * 9),
        session_id=session_id, tick_id=tick_id, timestamp_ms=timestamp_ms,
    )


# ============================================================================
# T1: Rejected gesture does not increase tau
# ============================================================================

class TestRejectedGestureDoesNotIncreaseTau:
    def test_rejected_gesture_passes_through_unchanged(self):
        session = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="tick-bad")
        proj = project_to_field_state(obs, session, logical_step=0)

        bad_t = Transformation.new(expected_delta={"NSV": 0.6})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=bad_t,
            thresholds=GateThresholds(),
        ))
        assert out.outcome == GateOutcome.REJECT
        assert not is_accepting(out.outcome.value)

        session_after = passthrough_session_on_unaccepted(
            session, tick_id="tick-bad", logical_step=0,
        )
        assert session_after.tau == session.tau
        assert session_after.Theta == session.Theta
        assert session_after.renegotiation_count == session.renegotiation_count

    def test_deferred_gesture_does_not_advance(self):
        session = SessionState.initial(session_id="sess-1", tau=0.5, Theta=0.5)
        t = Transformation.new(expected_delta={"tau": 0.4})
        out = evaluate(GateInput(
            current_state=FieldState(
                Omega=0.7, rho=0, kappa=0, tau=session.tau, Theta=session.Theta,
                NSV=0.0, logical_step=0,
            ),
            transformation=t,
            thresholds=GateThresholds(tau_ceiling=0.85),
            hbtl_reviewed=False,
        ))
        assert out.outcome == GateOutcome.DEFER
        assert not is_accepting(out.outcome.value)


# ============================================================================
# T2: Accepted (EXECUTE) gesture advances tau
# ============================================================================

class TestExecutedGestureAdvancesTau:
    def test_executed_transformation_advances_tau(self):
        session = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="tick-good")
        proj = project_to_field_state(obs, session, logical_step=0)

        good_t = Transformation.new(expected_delta={"tau": 0.05, "NSV": 0.02})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=good_t,
            thresholds=GateThresholds(),
        ))
        assert out.outcome == GateOutcome.EXECUTE
        assert is_accepting(out.outcome.value)

        session_after = advance_session_on_accepted(
            session, out.predicted_state, tick_id="tick-good", logical_step=0,
        )
        assert session_after.tau > session.tau
        assert session_after.tau == out.predicted_state.tau

    def test_tau_monotonicity_violation_raises(self):
        session = SessionState.initial(session_id="sess-1", tau=0.5, Theta=0.5)
        with pytest.raises(ValueError, match="monotonicity"):
            session.advance(
                new_tau=0.3, new_Theta=0.5,
                tick_id="tick-bad", logical_step=0,
            )


# ============================================================================
# T3: Energy does not alter FieldState equality
# ============================================================================

class TestEnergyDoesNotAlterFieldState:
    def test_field_state_independent_of_energy(self):
        session = SessionState.initial(session_id="sess-1", tau=0.2, Theta=0.7)
        obs_low = _obs(Energy=0.1, session_id="sess-1", tick_id="tick-a")
        obs_high = _obs(Energy=0.9, session_id="sess-1", tick_id="tick-b")
        proj_a = project_to_field_state(obs_low, session, logical_step=0)
        proj_b = project_to_field_state(obs_high, session, logical_step=0)
        assert proj_a.field_state == proj_b.field_state
        assert proj_a.energy != proj_b.energy
        assert proj_a.energy == 0.1
        assert proj_b.energy == 0.9

    def test_field_state_has_no_energy_field(self):
        """FieldState's dataclass has no Energy field. Hard structural test."""
        from dataclasses import fields
        field_names = {f.name for f in fields(FieldState)}
        assert "Energy" not in field_names
        assert "energy" not in field_names
        assert field_names == {"Omega", "rho", "kappa", "tau", "Theta", "NSV", "logical_step"}


# ============================================================================
# T4: RuntimeAnalytics is read-only for bench display
# ============================================================================

class TestRuntimeAnalyticsIsReadOnlyForBenchDisplay:
    def test_bench_display_cannot_write_runtime_analytics(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_display", PayloadType.RUNTIME_ANALYTICS)

    def test_bench_display_cannot_write_session_state(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_display", PayloadType.SESSION_STATE)

    def test_bench_display_cannot_write_field_state(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_display", PayloadType.FIELD_STATE)

    def test_bench_display_cannot_write_gate_outcome(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_display", PayloadType.GATE_OUTCOME)

    def test_bench_emitter_cannot_write_session_state(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_emitter", PayloadType.SESSION_STATE)

    def test_bench_emitter_cannot_write_field_state(self):
        with pytest.raises(AuthorityViolation):
            check_write_authority("bench_emitter", PayloadType.FIELD_STATE)


# ============================================================================
# T5: Replay reconstructs accumulator state
# ============================================================================

class TestReplayReconstructsAccumulatorState:
    def test_replay_matches_live(self):
        sequence = [
            (_obs(tick_id="t1"), Transformation.new({"tau": 0.05, "NSV": 0.02}), GateOutcome.EXECUTE),
            (_obs(tick_id="t2"), Transformation.new({"NSV": 0.6}), GateOutcome.REJECT),
            (_obs(tick_id="t3"), Transformation.new({"tau": 0.03, "NSV": 0.01}), GateOutcome.EXECUTE),
            # DEFER: delta of 0.7 pushes tau past ceiling without HBTL
            (_obs(tick_id="t4"), Transformation.new({"tau": 0.7}), GateOutcome.DEFER),
        ]

        def run(initial_session):
            history = [initial_session]
            session = initial_session
            for i, (obs, t, expected) in enumerate(sequence):
                proj = project_to_field_state(obs, session, logical_step=i)
                out = evaluate(GateInput(
                    current_state=proj.field_state,
                    transformation=t,
                    thresholds=GateThresholds(tau_ceiling=0.85),
                ))
                assert out.outcome == expected, (
                    f"step {i}: expected {expected}, got {out.outcome}"
                )
                if is_accepting(out.outcome.value):
                    session = advance_session_on_accepted(
                        session, out.predicted_state,
                        tick_id=obs.tick_id, logical_step=i,
                    )
                else:
                    session = passthrough_session_on_unaccepted(
                        session, tick_id=obs.tick_id, logical_step=i,
                    )
                history.append(session)
            return history

        initial = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        live = run(initial)
        replay = run(initial)

        assert len(live) == len(replay)
        for a, b in zip(live, replay):
            assert a.tau == b.tau
            assert a.Theta == b.Theta
            assert a.last_tick_id == b.last_tick_id
            assert a.last_logical_step == b.last_logical_step


# ============================================================================
# T6: TRANSFORM is non-terminal — does NOT advance session
# ============================================================================

class TestTransformIsNonTerminal:
    """
    TRANSFORM is the entry point to the reshape loop. The gate has flagged
    a bounded violation as reshape-eligible but has NOT approved any state.
    Advancing the session on TRANSFORM would commit to a flagged state.
    """

    def test_transform_not_in_accepting_outcomes(self):
        assert GateOutcome.TRANSFORM.value not in ACCEPTING_OUTCOMES
        assert not is_accepting(GateOutcome.TRANSFORM.value)

    def test_only_execute_accepts(self):
        """Exactly EXECUTE is accepting; all others are not."""
        assert ACCEPTING_OUTCOMES == frozenset({GateOutcome.EXECUTE.value})
        assert is_accepting(GateOutcome.EXECUTE.value)
        assert not is_accepting(GateOutcome.TRANSFORM.value)
        assert not is_accepting(GateOutcome.DEFER.value)
        assert not is_accepting(GateOutcome.REJECT.value)

    def test_transform_outcome_does_not_advance_tau(self):
        """End-to-end: a TRANSFORM outcome flows through passthrough, not advance."""
        session = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="tick-transform")
        proj = project_to_field_state(obs, session, logical_step=0)

        # NSV step of 0.3 is above nsv_step_max (0.2) but below catastrophic (0.5):
        # reshape-eligible bounded violation -> TRANSFORM.
        t = Transformation.new(expected_delta={"NSV": 0.3})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=t,
            thresholds=GateThresholds(),
        ))
        assert out.outcome == GateOutcome.TRANSFORM
        assert not is_accepting(out.outcome.value)

        session_after = passthrough_session_on_unaccepted(
            session, tick_id="tick-transform", logical_step=0,
        )
        assert session_after.tau == session.tau
        assert session_after.Theta == session.Theta


# ============================================================================
# T7: FAST_PRUNED is structurally distinct from gate REJECT
# ============================================================================

class TestPreGateOutcomesAreDistinctFromGateOutcomes:
    """
    SAFE_HOLD and FAST_PRUNED are pre-gate outcomes; they never appear in
    GateOutcome. EXECUTE/TRANSFORM/DEFER/REJECT are gate outcomes; they
    never appear in PreGateOutcome.
    """

    def test_pre_gate_outcomes_are_safe_hold_and_fast_pruned(self):
        assert set(PreGateOutcome) == {
            PreGateOutcome.SAFE_HOLD,
            PreGateOutcome.FAST_PRUNED,
            PreGateOutcome.MEASUREMENT_HOLD,
        }

    def test_gate_outcomes_have_no_pre_gate_values(self):
        gate_values = {o.value for o in GateOutcome}
        pre_gate_values = {p.value for p in PreGateOutcome}
        assert gate_values.isdisjoint(pre_gate_values)

    def test_fast_pruned_and_rejected_are_different_values(self):
        assert PreGateOutcome.FAST_PRUNED.value != GateOutcome.REJECT.value

    def test_neither_pre_gate_outcome_is_accepting(self):
        assert not is_accepting(PreGateOutcome.SAFE_HOLD.value)
        assert not is_accepting(PreGateOutcome.FAST_PRUNED.value)

    def test_pre_gate_output_carries_its_layer_identity(self):
        """PreGateOutput records which layer emitted it."""
        out = PreGateOutput(
            outcome=PreGateOutcome.SAFE_HOLD,
            layer="lambda_0",
            reason="placeholder Lambda_0 violation",
            triggered_thresholds=("L1_sampling",),
        )
        assert out.outcome == PreGateOutcome.SAFE_HOLD
        assert out.layer == "lambda_0"


# ============================================================================
# T8: TraceRecord captures prior and next session state
# ============================================================================

class TestTraceRecordCausalLink:
    """
    Every session state update must be causally linked to a logged gate
    outcome. TraceRecord is the carrier of that link.
    """

    def test_trace_record_requires_exactly_one_outcome(self):
        """Cannot have both gate_outcome and pre_gate_outcome, nor neither."""
        session = SessionState.initial(session_id="sess-1")
        obs = _obs()
        fs = FieldState(
            Omega=0.5, rho=0, kappa=0, tau=0, Theta=1, NSV=0, logical_step=0,
        )
        # Both set: error
        with pytest.raises(ValueError, match="exactly one"):
            TraceRecord(
                tick_id="t1", session_id="sess-1", logical_step=0,
                prior_session_state=session,
                bench_observation=obs,
                field_state_at_gate=fs,
                gate_outcome="EXECUTE",
                pre_gate_outcome="SAFE_HOLD",
                next_session_state=session,
            )
        # Neither set: error
        with pytest.raises(ValueError, match="exactly one"):
            TraceRecord(
                tick_id="t1", session_id="sess-1", logical_step=0,
                prior_session_state=session,
                bench_observation=obs,
                field_state_at_gate=fs,
                next_session_state=session,
            )

    def test_trace_record_carries_prior_and_next_session_state(self):
        session_prior = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="t1")
        proj = project_to_field_state(obs, session_prior, logical_step=0)
        t = Transformation.new({"tau": 0.05, "NSV": 0.02})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=t,
            thresholds=GateThresholds(),
        ))
        session_next = advance_session_on_accepted(
            session_prior, out.predicted_state, tick_id="t1", logical_step=0,
        )
        record = TraceRecord(
            tick_id="t1", session_id="sess-1", logical_step=0,
            prior_session_state=session_prior,
            bench_observation=obs,
            field_state_at_gate=proj.field_state,
            gate_outcome=out.outcome.value,
            reason_codes=tuple(r.value for r in out.reason_codes),
            next_session_state=session_next,
            accepted_delta=dict(t.expected_delta),
            transformation=t.to_dict(),
        )
        # The trace makes the prior -> next transition fully inspectable
        assert record.prior_session_state.tau == 0.1
        assert record.next_session_state.tau > record.prior_session_state.tau
        assert record.next_session_state.tau == out.predicted_state.tau


# ============================================================================
# Supplementary: Session continuity contract
# ============================================================================

class TestSessionContinuityContract:
    def test_session_id_mismatch_raises(self):
        session = SessionState.initial(session_id="sess-A")
        obs = _obs(session_id="sess-B")
        with pytest.raises(ValueError, match="Session mismatch"):
            project_to_field_state(obs, session, logical_step=0)


# ============================================================================
# Supplementary: RuntimeAnalytics correctly reflects post-tick state
# ============================================================================

class TestRuntimeAnalyticsReflectPostTickState:
    def test_analytics_after_accepted_tick_shows_advanced_tau(self):
        session = SessionState.initial(session_id="sess-1", tau=0.1, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="t1")
        proj = project_to_field_state(obs, session, logical_step=0)
        t = Transformation.new({"tau": 0.05, "NSV": 0.02})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=t,
            thresholds=GateThresholds(),
        ))
        assert out.outcome == GateOutcome.EXECUTE
        session_after = advance_session_on_accepted(
            session, out.predicted_state, tick_id="t1", logical_step=0,
        )
        analytics = build_analytics(
            obs, session_after,
            outcome_str=out.outcome.value,
            is_pre_gate=False,
            reason_codes=tuple(r.value for r in out.reason_codes),
            logical_step=0,
        )
        assert analytics.tau == session_after.tau
        assert analytics.tau > session.tau
        assert analytics.Energy == obs.Energy
        assert analytics.is_pre_gate is False

    def test_analytics_after_rejected_tick_shows_unchanged_tau(self):
        session = SessionState.initial(session_id="sess-1", tau=0.3, Theta=0.7)
        obs = _obs(session_id="sess-1", tick_id="t2")
        proj = project_to_field_state(obs, session, logical_step=0)
        t = Transformation.new({"NSV": 0.6})
        out = evaluate(GateInput(
            current_state=proj.field_state,
            transformation=t,
            thresholds=GateThresholds(),
        ))
        assert out.outcome == GateOutcome.REJECT
        session_after = passthrough_session_on_unaccepted(
            session, tick_id="t2", logical_step=0,
        )
        analytics = build_analytics(
            obs, session_after,
            outcome_str=out.outcome.value,
            is_pre_gate=False,
            reason_codes=tuple(r.value for r in out.reason_codes),
            logical_step=0,
        )
        assert analytics.tau == session.tau

    def test_analytics_after_pre_gate_outcome_marked(self):
        """When a PreGate layer short-circuits, is_pre_gate is True."""
        session = SessionState.initial(session_id="sess-1", tau=0.2, Theta=0.8)
        obs = _obs(session_id="sess-1", tick_id="t3")
        session_after = passthrough_session_on_unaccepted(
            session, tick_id="t3", logical_step=0,
        )
        analytics = build_analytics(
            obs, session_after,
            outcome_str=PreGateOutcome.FAST_PRUNED.value,
            is_pre_gate=True,
            reason_codes=("pi_fast_rho_exceeded",),
            logical_step=0,
        )
        assert analytics.is_pre_gate is True
        assert analytics.gate_outcome_str == "FAST_PRUNED"
        assert analytics.tau == session.tau  # not advanced
