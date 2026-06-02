"""
MCP Envelope Router.

Constitutional role: serves replay determinism and inspectability.

Invariants enforced:
- Every message is addressable by envelope_id.
- Every message is orderable by logical_step.
- Every message links to provenance.
- Every component writes only what its authority declaration permits.
- Out-of-order arrival does not change logical order.

Constitutional commitment: contracts above conventions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
from collections import defaultdict

from ..core.types import Envelope, PayloadType
from ..core.authority import check_write_authority, AuthorityViolation


COMPONENT_VERSION = "0.1.0"


class SchemaViolation(Exception):
    """Raised when an envelope fails schema validation."""


class ProvenanceGap(Exception):
    """Raised when an envelope is missing its provenance_ref."""


class LogicalStepConflict(Exception):
    """Raised when two envelopes claim the same (component_id, logical_step) slot."""


@dataclass
class RouterStats:
    """
    Routing telemetry. The router emits this as part of its diagnostic surface;
    it is read by the Diagnostics Module, not interpreted by the router itself.
    """
    total_messages: int = 0
    by_payload_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_component: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    reordered_messages: int = 0
    rejected_authority: int = 0
    rejected_schema: int = 0
    rejected_provenance: int = 0
    rejected_logical_step_conflict: int = 0


class MCPRouter:
    """
    The MCP Envelope Router.

    Components emit envelopes through `emit`. Subscribers register interest in
    payload types via `subscribe`. The router orders envelopes by logical_step
    within each (component_id, payload_type) channel and enforces authority.

    The router does not interpret payloads. It transports them.
    """

    def __init__(self, runtime_version: str = "0.1.0") -> None:
        self.runtime_version = runtime_version
        self._envelopes: dict[str, Envelope] = {}  # envelope_id -> envelope
        self._by_step: list[Envelope] = []  # logical-step-ordered log
        self._by_channel: dict[tuple[str, PayloadType], dict[int, str]] = defaultdict(dict)
        # channel = (component_id, payload_type); inner dict maps logical_step -> envelope_id
        self._subscribers: dict[PayloadType, list[Callable[[Envelope], None]]] = defaultdict(list)
        self._stats = RouterStats()
        self._known_provenance: set[str] = set()

    # -- provenance registration --------------------------------------------

    def register_provenance(self, provenance_id: str) -> None:
        """
        Provenance must be registered before envelopes can reference it.
        This prevents envelopes carrying dangling provenance_refs.
        """
        self._known_provenance.add(provenance_id)

    # -- emission -----------------------------------------------------------

    def emit(self, envelope: Envelope) -> None:
        """
        Validate and route an envelope.

        Raises AuthorityViolation, SchemaViolation, ProvenanceGap, or
        LogicalStepConflict on failure. Failures are constitutional violations
        and propagate; the router does not swallow them.
        """
        self._validate_envelope(envelope)

        # Authority check: may this component write this payload type?
        try:
            check_write_authority(envelope.component_id, envelope.payload_type)
        except AuthorityViolation:
            self._stats.rejected_authority += 1
            raise

        # Provenance check: does the referenced provenance exist?
        if envelope.provenance_ref not in self._known_provenance:
            self._stats.rejected_provenance += 1
            raise ProvenanceGap(
                f"Envelope {envelope.envelope_id} references unregistered "
                f"provenance {envelope.provenance_ref}. Register provenance "
                f"before emitting envelopes that reference it."
            )

        # Logical step conflict check.
        # Two envelopes from the same component, same payload type, same logical step
        # would be a write race. Forbidden.
        channel = (envelope.component_id, envelope.payload_type)
        if envelope.logical_step in self._by_channel[channel]:
            existing = self._by_channel[channel][envelope.logical_step]
            self._stats.rejected_logical_step_conflict += 1
            raise LogicalStepConflict(
                f"Channel ({envelope.component_id}, {envelope.payload_type.value}) "
                f"already has an envelope at logical_step {envelope.logical_step}: "
                f"{existing}. Cannot accept {envelope.envelope_id}."
            )

        # All checks passed. Commit.
        self._envelopes[envelope.envelope_id] = envelope
        self._by_channel[channel][envelope.logical_step] = envelope.envelope_id

        # Maintain logical-step order on the global log.
        # If the new envelope's step is >= the last step, append.
        # Otherwise, insert in order and count it as reordered.
        if not self._by_step or envelope.logical_step >= self._by_step[-1].logical_step:
            self._by_step.append(envelope)
        else:
            # Out-of-order arrival. Insert at correct position.
            self._stats.reordered_messages += 1
            insert_at = 0
            for i, e in enumerate(self._by_step):
                if e.logical_step > envelope.logical_step:
                    insert_at = i
                    break
                insert_at = i + 1
            self._by_step.insert(insert_at, envelope)

        self._stats.total_messages += 1
        self._stats.by_payload_type[envelope.payload_type.value] += 1
        self._stats.by_component[envelope.component_id] += 1

        # Fan out to subscribers.
        for subscriber in self._subscribers[envelope.payload_type]:
            subscriber(envelope)

    # -- subscription -------------------------------------------------------

    def subscribe(
        self,
        payload_type: PayloadType,
        handler: Callable[[Envelope], None],
    ) -> None:
        """Register a handler for a payload type."""
        self._subscribers[payload_type].append(handler)

    # -- retrieval ----------------------------------------------------------

    def get(self, envelope_id: str) -> Optional[Envelope]:
        """Retrieve an envelope by id."""
        return self._envelopes.get(envelope_id)

    def envelopes_at_step(self, logical_step: int) -> list[Envelope]:
        """All envelopes at a given logical step, in arrival order within the step."""
        return [e for e in self._by_step if e.logical_step == logical_step]

    def envelopes_in_range(self, start: int, end: int) -> list[Envelope]:
        """All envelopes with start <= logical_step <= end."""
        return [e for e in self._by_step if start <= e.logical_step <= end]

    def channel_log(
        self, component_id: str, payload_type: PayloadType
    ) -> list[Envelope]:
        """Ordered log for a specific channel."""
        channel = (component_id, payload_type)
        steps = sorted(self._by_channel[channel].keys())
        return [self._envelopes[self._by_channel[channel][s]] for s in steps]

    def all_envelopes_ordered(self) -> list[Envelope]:
        """The full logical-step-ordered log."""
        return list(self._by_step)

    # -- diagnostics --------------------------------------------------------

    @property
    def stats(self) -> RouterStats:
        return self._stats

    # -- internal -----------------------------------------------------------

    def _validate_envelope(self, envelope: Envelope) -> None:
        """Structural validation. Raises SchemaViolation on failure."""
        if not envelope.envelope_id:
            self._stats.rejected_schema += 1
            raise SchemaViolation("envelope_id is required")
        if envelope.logical_step < 0:
            self._stats.rejected_schema += 1
            raise SchemaViolation(
                f"logical_step must be non-negative; got {envelope.logical_step}"
            )
        if not envelope.component_id:
            self._stats.rejected_schema += 1
            raise SchemaViolation("component_id is required")
        if not envelope.component_version:
            self._stats.rejected_schema += 1
            raise SchemaViolation("component_version is required")
        if envelope.envelope_id in self._envelopes:
            self._stats.rejected_schema += 1
            raise SchemaViolation(
                f"Duplicate envelope_id: {envelope.envelope_id}"
            )
        if not envelope.provenance_ref:
            self._stats.rejected_schema += 1
            raise SchemaViolation("provenance_ref is required")
        if not isinstance(envelope.payload, dict):
            self._stats.rejected_schema += 1
            raise SchemaViolation(
                f"payload must be a dict; got {type(envelope.payload).__name__}"
            )
