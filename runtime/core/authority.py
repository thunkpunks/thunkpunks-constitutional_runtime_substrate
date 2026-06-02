"""
Read/write authority enforcement.

Constitutional commitment: every component declares its reads and writes.
The MCP router enforces against this map. Any undeclared write is a
constitutional violation, not a warning.

This is the structural enforcement of "no two Skills write the same dimension
in the same step without an explicit merge contract."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .types import PayloadType


@dataclass(frozen=True)
class ComponentAuthority:
    """
    Declared read/write authority for a component.

    `reads` and `writes` are payload types this component may consume or emit.
    `forbidden_writes` is an explicit denial list — useful for components
    that should never touch certain payload types regardless of pipeline order.
    """
    component_id: str
    reads: frozenset[PayloadType]
    writes: frozenset[PayloadType]
    forbidden_writes: frozenset[PayloadType] = frozenset()


# v1 authority map. Translated directly from handoff four's authority requirement,
# expressed in payload types rather than free-form field names.
AUTHORITY_MAP: dict[str, ComponentAuthority] = {
    "scenario_synthesis": ComponentAuthority(
        component_id="scenario_synthesis",
        reads=frozenset(),
        writes=frozenset({PayloadType.SCENARIO}),
    ),
    "scenario_validator": ComponentAuthority(
        component_id="scenario_validator",
        reads=frozenset({PayloadType.SCENARIO}),
        writes=frozenset({PayloadType.SCENARIO_VALIDATION}),
    ),
    "field_projection": ComponentAuthority(
        component_id="field_projection",
        reads=frozenset({PayloadType.SCENARIO, PayloadType.SCENARIO_VALIDATION}),
        writes=frozenset({PayloadType.FIELD_STATE}),
    ),
    "transformation_candidate": ComponentAuthority(
        component_id="transformation_candidate",
        reads=frozenset({PayloadType.SCENARIO, PayloadType.FIELD_STATE}),
        writes=frozenset({PayloadType.TRANSFORMATION}),
    ),
    "algebraic_gate": ComponentAuthority(
        component_id="algebraic_gate",
        reads=frozenset({
            PayloadType.FIELD_STATE,
            PayloadType.TRANSFORMATION,
            PayloadType.SURFACE_ASSIGNMENT,
        }),
        writes=frozenset({PayloadType.GATE_OUTCOME}),
        # The gate is the constitutional authority; it must not emit
        # diagnostics or escalations directly. Those go through other components.
        forbidden_writes=frozenset({
            PayloadType.DIAGNOSTIC,
            PayloadType.ESCALATION,
        }),
    ),
    "reshape_operator": ComponentAuthority(
        component_id="reshape_operator",
        reads=frozenset({
            PayloadType.TRANSFORMATION,
            PayloadType.GATE_OUTCOME,
            PayloadType.FIELD_STATE,
        }),
        writes=frozenset({PayloadType.RESHAPE_ATTEMPT, PayloadType.TRANSFORMATION}),
    ),
    "surface_assignment": ComponentAuthority(
        component_id="surface_assignment",
        reads=frozenset({PayloadType.FIELD_STATE}),
        writes=frozenset({PayloadType.SURFACE_ASSIGNMENT}),
    ),
    "hbtl": ComponentAuthority(
        component_id="hbtl",
        reads=frozenset({
            PayloadType.FIELD_STATE,
            PayloadType.SURFACE_ASSIGNMENT,
            PayloadType.GATE_OUTCOME,
            PayloadType.DIAGNOSTIC,
        }),
        writes=frozenset({PayloadType.ESCALATION}),
    ),
    "diagnostics": ComponentAuthority(
        component_id="diagnostics",
        # Diagnostics has the widest read surface — by design, and a v2 hardening target.
        reads=frozenset(PayloadType),
        writes=frozenset({PayloadType.DIAGNOSTIC}),
        # Critical: diagnostics may not modify state. Report-only invariant.
        forbidden_writes=frozenset({
            PayloadType.FIELD_STATE,
            PayloadType.TRANSFORMATION,
            PayloadType.GATE_OUTCOME,
            PayloadType.SURFACE_ASSIGNMENT,
            PayloadType.BENCH_OBSERVATION,
            PayloadType.SESSION_STATE,
            PayloadType.RUNTIME_ANALYTICS,
        }),
    ),
    # Bench-runtime interface components
    "lambda_0": ComponentAuthority(
        component_id="lambda_0",
        # Lambda_0 reads observation, session, and (optionally) the projected
        # field state to check structural well-formedness. It emits a pre-gate
        # output (SAFE_HOLD) on violation.
        reads=frozenset({
            PayloadType.BENCH_OBSERVATION,
            PayloadType.SESSION_STATE,
            PayloadType.FIELD_STATE,
        }),
        writes=frozenset({PayloadType.PRE_GATE_OUTPUT}),
        # Lambda_0 must never author state or a gate outcome. It is a
        # well-formedness boundary, not a decision-maker.
        forbidden_writes=frozenset({
            PayloadType.FIELD_STATE,
            PayloadType.GATE_OUTCOME,
            PayloadType.SESSION_STATE,
            PayloadType.TRANSFORMATION,
        }),
    ),
    "bench_emitter": ComponentAuthority(
        component_id="bench_emitter",
        # The bench is an external source; it reads nothing from the runtime.
        # It emits observations and reads runtime analytics for display only.
        reads=frozenset(),
        writes=frozenset({PayloadType.BENCH_OBSERVATION}),
        # Critical: the bench must NEVER write tau, Theta, or anything constitutionally
        # owned by the runtime. The bench is observational-only.
        forbidden_writes=frozenset({
            PayloadType.FIELD_STATE,
            PayloadType.TRANSFORMATION,
            PayloadType.GATE_OUTCOME,
            PayloadType.SESSION_STATE,
            PayloadType.SURFACE_ASSIGNMENT,
            PayloadType.DIAGNOSTIC,
            PayloadType.ESCALATION,
        }),
    ),
    "session_state_manager": ComponentAuthority(
        component_id="session_state_manager",
        reads=frozenset({
            PayloadType.BENCH_OBSERVATION,
            PayloadType.GATE_OUTCOME,
            PayloadType.SESSION_STATE,
        }),
        # Owns SessionState advancement. Also produces FieldState (from projection)
        # and RuntimeAnalytics (for downstream display).
        writes=frozenset({
            PayloadType.SESSION_STATE,
            PayloadType.FIELD_STATE,
            PayloadType.RUNTIME_ANALYTICS,
        }),
    ),
    "bench_display": ComponentAuthority(
        component_id="bench_display",
        # The bench display (Field Instrument, Blender Renderer) consumes
        # RuntimeAnalytics and may NOT write anything constitutional back.
        reads=frozenset({PayloadType.RUNTIME_ANALYTICS}),
        writes=frozenset(),  # observational consumer only
        forbidden_writes=frozenset(PayloadType),  # belt and braces
    ),
}


class AuthorityViolation(Exception):
    """Raised when a component attempts a write outside its declared authority."""


def check_write_authority(component_id: str, payload_type: PayloadType) -> None:
    """
    Raise AuthorityViolation if the component is not authorized to write
    this payload type. Called by the router before any write is committed.
    """
    if component_id not in AUTHORITY_MAP:
        raise AuthorityViolation(
            f"Component '{component_id}' has no declared authority. "
            f"Components must be registered in AUTHORITY_MAP before they may write."
        )
    authority = AUTHORITY_MAP[component_id]
    if payload_type in authority.forbidden_writes:
        raise AuthorityViolation(
            f"Component '{component_id}' is explicitly forbidden from writing "
            f"payload_type '{payload_type.value}'."
        )
    if payload_type not in authority.writes:
        raise AuthorityViolation(
            f"Component '{component_id}' is not authorized to write "
            f"payload_type '{payload_type.value}'. "
            f"Declared writes: {sorted(p.value for p in authority.writes)}."
        )


def check_read_authority(component_id: str, payload_type: PayloadType) -> None:
    """
    Raise AuthorityViolation if the component is not authorized to read
    this payload type. Reads are advisory in v1 — they constrain what
    components may consume, not what they may merely observe in logs.
    """
    if component_id not in AUTHORITY_MAP:
        raise AuthorityViolation(
            f"Component '{component_id}' has no declared authority."
        )
    authority = AUTHORITY_MAP[component_id]
    if payload_type not in authority.reads:
        raise AuthorityViolation(
            f"Component '{component_id}' is not authorized to read "
            f"payload_type '{payload_type.value}'. "
            f"Declared reads: {sorted(p.value for p in authority.reads)}."
        )
