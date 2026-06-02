"""
Integration test: gate + router composition.

This is the first test that proves two components compose under the
constitutional contracts, not just that each works alone.

The scenario:
1. A scenario synthesis component emits a SCENARIO envelope (placeholder).
2. A field projection component emits a FIELD_STATE envelope.
3. A transformation candidate component emits a TRANSFORMATION envelope.
4. The algebraic gate consumes state + transformation, evaluates, emits GATE_OUTCOME.

Every emission is provenance-checked. Every authority is enforced.
Every envelope is logical-step ordered.
"""
import pytest

from runtime.core.types import (
    FieldState,
    Transformation,
    Envelope,
    PayloadType,
    Provenance,
    GateOutcome,
    parameter_set_hash,
)
from runtime.components.mcp_router import MCPRouter
from runtime.components.gate import (
    GateThresholds,
    GateInput,
    evaluate,
)


def _make_provenance(router: MCPRouter, prov_id: str, params: dict) -> Provenance:
    """Create a provenance record and register it with the router."""
    p = Provenance(
        provenance_id=prov_id,
        runtime_version="0.1.0",
        component_versions={
            "scenario_synthesis": "0.1.0",
            "field_projection": "0.1.0",
            "transformation_candidate": "0.1.0",
            "algebraic_gate": "0.1.0",
        },
        seeds={"experiment": 42},
        parameter_set_hash=parameter_set_hash(params),
    )
    router.register_provenance(prov_id)
    return p


class TestGateRouterComposition:
    """The gate and router compose under constitutional contracts."""

    def test_full_pipeline_execute_outcome(self):
        """Admissible transformation flows end to end and emits EXECUTE."""
        router = MCPRouter()
        thresholds = GateThresholds()
        params = {
            "omega_floor": thresholds.omega_floor,
            "tau_ceiling": thresholds.tau_ceiling,
            "theta_floor": thresholds.theta_floor,
            "nsv_step_max": thresholds.nsv_step_max,
        }
        prov = _make_provenance(router, "prov-experiment-1", params)

        # Step 0: scenario emission
        scenario_env = Envelope.new(
            logical_step=0,
            component_id="scenario_synthesis",
            component_version="0.1.0",
            payload_type=PayloadType.SCENARIO,
            payload={"description": "synthetic test scenario", "domain": "test"},
            provenance_ref=prov.provenance_id,
        )
        router.emit(scenario_env)

        # Step 1: field projection
        initial_state = FieldState(
            Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=1
        )
        field_env = Envelope.new(
            logical_step=1,
            component_id="field_projection",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload=initial_state.to_dict(),
            provenance_ref=prov.provenance_id,
            predecessor_envelope=scenario_env.envelope_id,
        )
        router.emit(field_env)

        # Step 2: transformation candidate
        transformation = Transformation.new(
            expected_delta={"Omega": -0.05, "tau": 0.05, "NSV": 0.02},
            description="modest commitment",
        )
        trans_env = Envelope.new(
            logical_step=2,
            component_id="transformation_candidate",
            component_version="0.1.0",
            payload_type=PayloadType.TRANSFORMATION,
            payload={
                "transformation_id": transformation.transformation_id,
                "expected_delta": transformation.expected_delta,
                "description": transformation.description,
            },
            provenance_ref=prov.provenance_id,
            predecessor_envelope=field_env.envelope_id,
        )
        router.emit(trans_env)

        # Step 3: gate evaluation
        gate_out = evaluate(GateInput(
            current_state=initial_state,
            transformation=transformation,
            thresholds=thresholds,
        ))
        gate_env = Envelope.new(
            logical_step=3,
            component_id="algebraic_gate",
            component_version="0.1.0",
            payload_type=PayloadType.GATE_OUTCOME,
            payload={
                "outcome": gate_out.outcome.value,
                "reason_codes": [r.value for r in gate_out.reason_codes],
                "predicted_state": gate_out.predicted_state.to_dict(),
                "threshold_crossings": list(gate_out.threshold_crossings),
                "rationale": gate_out.rationale,
            },
            provenance_ref=prov.provenance_id,
            predecessor_envelope=trans_env.envelope_id,
        )
        router.emit(gate_env)

        # Assertions on the assembled trace
        assert gate_out.outcome == GateOutcome.EXECUTE

        ordered = router.all_envelopes_ordered()
        assert len(ordered) == 4
        assert [e.logical_step for e in ordered] == [0, 1, 2, 3]
        assert [e.payload_type.value for e in ordered] == [
            "scenario",
            "field_state",
            "transformation",
            "gate_outcome",
        ]

        # The predecessor chain is intact
        assert ordered[1].predecessor_envelope == ordered[0].envelope_id
        assert ordered[2].predecessor_envelope == ordered[1].envelope_id
        assert ordered[3].predecessor_envelope == ordered[2].envelope_id

        # All envelopes link to the same provenance
        assert all(e.provenance_ref == prov.provenance_id for e in ordered)

    def test_full_pipeline_reject_outcome(self):
        """A catastrophic transformation flows through and emits REJECT."""
        router = MCPRouter()
        thresholds = GateThresholds()
        params = {"omega_floor": thresholds.omega_floor}
        prov = _make_provenance(router, "prov-experiment-2", params)

        initial_state = FieldState(
            Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0
        )
        router.emit(Envelope.new(
            logical_step=0,
            component_id="field_projection",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload=initial_state.to_dict(),
            provenance_ref=prov.provenance_id,
        ))

        # Catastrophic NSV step
        transformation = Transformation.new(
            expected_delta={"NSV": 0.6},
            description="catastrophic residue",
        )
        router.emit(Envelope.new(
            logical_step=1,
            component_id="transformation_candidate",
            component_version="0.1.0",
            payload_type=PayloadType.TRANSFORMATION,
            payload={
                "transformation_id": transformation.transformation_id,
                "expected_delta": transformation.expected_delta,
            },
            provenance_ref=prov.provenance_id,
        ))

        gate_out = evaluate(GateInput(
            current_state=initial_state,
            transformation=transformation,
            thresholds=thresholds,
        ))
        assert gate_out.outcome == GateOutcome.REJECT

        router.emit(Envelope.new(
            logical_step=2,
            component_id="algebraic_gate",
            component_version="0.1.0",
            payload_type=PayloadType.GATE_OUTCOME,
            payload={
                "outcome": gate_out.outcome.value,
                "reason_codes": [r.value for r in gate_out.reason_codes],
                "rationale": gate_out.rationale,
            },
            provenance_ref=prov.provenance_id,
        ))

        # Trace is replayable
        gate_envs = router.channel_log("algebraic_gate", PayloadType.GATE_OUTCOME)
        assert len(gate_envs) == 1
        assert gate_envs[0].payload["outcome"] == "REJECT"


class TestReplayability:
    """A trace produced by the gate is deterministically replayable."""

    def test_same_inputs_produce_identical_traces(self):
        """Two runs with the same inputs produce structurally identical traces."""
        thresholds = GateThresholds()
        initial = FieldState(
            Omega=0.6, rho=0.0, kappa=0.0, tau=0.4, Theta=0.6, NSV=0.05, logical_step=0
        )
        t = Transformation(
            transformation_id="fixed-id-for-determinism",
            typed_effects={"Omega": -0.1, "tau": 0.1, "NSV": 0.1},
            description="deterministic test",
        )

        out_a = evaluate(GateInput(current_state=initial, transformation=t, thresholds=thresholds))
        out_b = evaluate(GateInput(current_state=initial, transformation=t, thresholds=thresholds))

        assert out_a.outcome == out_b.outcome
        assert out_a.reason_codes == out_b.reason_codes
        assert out_a.predicted_state == out_b.predicted_state
        assert out_a.threshold_crossings == out_b.threshold_crossings
        assert out_a.rationale == out_b.rationale
