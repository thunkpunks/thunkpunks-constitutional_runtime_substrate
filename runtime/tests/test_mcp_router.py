"""
Tests for components/mcp_router.py.

The router holds these invariants:
- Every envelope is addressable by envelope_id.
- Out-of-order arrival doesn't change logical order.
- Authority violations are rejected.
- Schema violations are rejected.
- Provenance gaps are rejected.
- Logical step conflicts are rejected.
"""
import pytest

from runtime.core.types import Envelope, PayloadType, Provenance
from runtime.core.authority import AuthorityViolation
from runtime.components.mcp_router import (
    MCPRouter,
    SchemaViolation,
    ProvenanceGap,
    LogicalStepConflict,
)


def _envelope(
    router: MCPRouter,
    component_id: str,
    payload_type: PayloadType,
    logical_step: int,
    provenance_ref: str = "prov-1",
    register_prov: bool = True,
) -> Envelope:
    if register_prov:
        router.register_provenance(provenance_ref)
    return Envelope.new(
        logical_step=logical_step,
        component_id=component_id,
        component_version="0.1.0",
        payload_type=payload_type,
        payload={},
        provenance_ref=provenance_ref,
    )


class TestAddressability:
    def test_envelope_retrievable_by_id(self):
        r = MCPRouter()
        e = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        r.emit(e)
        retrieved = r.get(e.envelope_id)
        assert retrieved is e

    def test_missing_envelope_returns_none(self):
        r = MCPRouter()
        assert r.get("nonexistent") is None


class TestOrdering:
    def test_in_order_arrival_preserved(self):
        r = MCPRouter()
        e0 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        r.emit(e0)
        e1 = _envelope(r, "field_projection", PayloadType.FIELD_STATE, 1, register_prov=False)
        r.emit(e1)
        e2 = _envelope(r, "algebraic_gate", PayloadType.GATE_OUTCOME, 2, register_prov=False)
        r.emit(e2)

        ordered = r.all_envelopes_ordered()
        assert [e.logical_step for e in ordered] == [0, 1, 2]

    def test_out_of_order_arrival_reordered(self):
        """Out-of-order arrival is reordered to logical-step order."""
        r = MCPRouter()
        e2 = _envelope(r, "algebraic_gate", PayloadType.GATE_OUTCOME, 2)
        e0 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0, register_prov=False)
        e1 = _envelope(r, "field_projection", PayloadType.FIELD_STATE, 1, register_prov=False)
        # Emit out of order.
        r.emit(e2)
        r.emit(e0)
        r.emit(e1)

        ordered = r.all_envelopes_ordered()
        assert [e.logical_step for e in ordered] == [0, 1, 2]
        assert r.stats.reordered_messages >= 1

    def test_envelopes_at_step(self):
        r = MCPRouter()
        e0 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        e1 = _envelope(r, "field_projection", PayloadType.FIELD_STATE, 0, register_prov=False)
        r.emit(e0)
        r.emit(e1)
        at_step_0 = r.envelopes_at_step(0)
        assert len(at_step_0) == 2

    def test_channel_log(self):
        r = MCPRouter()
        for step in [0, 2, 1]:
            e = _envelope(
                r, "scenario_synthesis", PayloadType.SCENARIO, step,
                register_prov=(step == 0),
            )
            r.emit(e)
        log = r.channel_log("scenario_synthesis", PayloadType.SCENARIO)
        assert [e.logical_step for e in log] == [0, 1, 2]


class TestAuthorityEnforcement:
    def test_authority_violation_propagates(self):
        r = MCPRouter()
        r.register_provenance("prov-1")
        # algebraic_gate cannot write FIELD_STATE
        bad = Envelope.new(
            logical_step=0,
            component_id="algebraic_gate",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={},
            provenance_ref="prov-1",
        )
        with pytest.raises(AuthorityViolation):
            r.emit(bad)
        assert r.stats.rejected_authority == 1

    def test_diagnostics_cannot_emit_state(self):
        r = MCPRouter()
        r.register_provenance("prov-1")
        bad = Envelope.new(
            logical_step=0,
            component_id="diagnostics",
            component_version="0.1.0",
            payload_type=PayloadType.FIELD_STATE,
            payload={},
            provenance_ref="prov-1",
        )
        with pytest.raises(AuthorityViolation, match="forbidden"):
            r.emit(bad)


class TestSchemaValidation:
    def test_negative_logical_step_rejected_at_construct_or_emit(self):
        r = MCPRouter()
        r.register_provenance("prov-1")
        # We construct via dataclass directly to bypass Envelope.new, since
        # logical_step is also validated in the router.
        from dataclasses import replace
        good = Envelope.new(
            logical_step=0,
            component_id="scenario_synthesis",
            component_version="0.1.0",
            payload_type=PayloadType.SCENARIO,
            payload={},
            provenance_ref="prov-1",
        )
        bad = replace(good, logical_step=-1)
        with pytest.raises(SchemaViolation, match="logical_step"):
            r.emit(bad)

    def test_duplicate_envelope_id_rejected(self):
        r = MCPRouter()
        r.register_provenance("prov-1")
        e = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0, register_prov=False)
        r.emit(e)
        with pytest.raises(SchemaViolation, match="Duplicate"):
            r.emit(e)


class TestProvenanceGap:
    def test_unregistered_provenance_rejected(self):
        r = MCPRouter()
        # Do not register provenance.
        e = Envelope.new(
            logical_step=0,
            component_id="scenario_synthesis",
            component_version="0.1.0",
            payload_type=PayloadType.SCENARIO,
            payload={},
            provenance_ref="prov-dangling",
        )
        with pytest.raises(ProvenanceGap):
            r.emit(e)


class TestLogicalStepConflict:
    def test_same_channel_same_step_rejected(self):
        r = MCPRouter()
        r.register_provenance("prov-1")
        e1 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 5, register_prov=False)
        r.emit(e1)
        e2 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 5, register_prov=False)
        with pytest.raises(LogicalStepConflict):
            r.emit(e2)

    def test_different_components_same_step_allowed(self):
        """Different components may emit at the same logical step."""
        r = MCPRouter()
        r.register_provenance("prov-1")
        e1 = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0, register_prov=False)
        r.emit(e1)
        e2 = _envelope(r, "field_projection", PayloadType.FIELD_STATE, 0, register_prov=False)
        r.emit(e2)  # no raise


class TestSubscription:
    def test_subscriber_receives_envelope(self):
        r = MCPRouter()
        received = []
        r.subscribe(PayloadType.SCENARIO, received.append)
        e = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        r.emit(e)
        assert received == [e]

    def test_subscriber_filtered_by_payload_type(self):
        r = MCPRouter()
        scenarios = []
        r.subscribe(PayloadType.SCENARIO, scenarios.append)
        e_sc = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        e_fs = _envelope(r, "field_projection", PayloadType.FIELD_STATE, 1, register_prov=False)
        r.emit(e_sc)
        r.emit(e_fs)
        assert scenarios == [e_sc]


class TestStatsAreDiagnosticOnly:
    """The router emits stats but does not act on them. Diagnostic honesty."""

    def test_stats_increment_on_emit(self):
        r = MCPRouter()
        e = _envelope(r, "scenario_synthesis", PayloadType.SCENARIO, 0)
        r.emit(e)
        assert r.stats.total_messages == 1
        assert r.stats.by_component["scenario_synthesis"] == 1
        assert r.stats.by_payload_type["scenario"] == 1
