"""
Synthetic Ingress Wiring — membrane to circuit.

Threads a synthetic canonical observation through:
  synthetic obs -> membrane (admit/refuse) -> event-log -> projection
               -> existing circuit -> replay verification

Discipline: membrane records, circuit decides. Existing substrate only; no new
authority; no kernel change. A REFUSED observation never reaches the substrate
(the wiring stops at the membrane). Coordinator sits outside kernel and membrane;
modules injected. Status EXPERIMENTALLY_BOUNDED.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class IngressResult:
    admitted: bool
    refusal_reason: Optional[str]
    reached_substrate: bool
    projection_status: Optional[str]
    replay_ok: Optional[bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "refusal_reason": self.refusal_reason,
            "reached_substrate": self.reached_substrate,
            "projection_status": self.projection_status,
            "replay_ok": self.replay_ok,
        }


def wire_observation(
    raw_observation: dict[str, Any],
    *,
    logical_step: int,
    min_confidence: float,
    membrane_module: Any,
    event_log: Any,
    state_projection_module: Any,
) -> IngressResult:
    """
    Membrane-first. If refused, return immediately — substrate untouched.
    If admitted, record to event-log, project, and replay-verify.

    Note: this wiring goes obs -> membrane -> event-log -> projection -> replay.
    It does NOT call the gate here; the circuit's gate step is exercised by the
    existing evidential-loop. The membrane records; the circuit decides. This
    proves admitted state reaches a replay-valid projection without the membrane
    touching gate/receipts/lineage.
    """
    # MEMBRANE: admit or refuse. Refusal stops here — substrate untouched.
    admitted, reason = membrane_module.try_admit(raw_observation)
    if admitted is None:
        return IngressResult(
            admitted=False, refusal_reason=reason,
            reached_substrate=False, projection_status=None, replay_ok=None,
        )

    # EVENT-LOG: record the admitted observation as an event (substrate entry).
    event = event_log.append(
        "ingress", logical_step, "observation_recorded",
        admitted.to_event_payload(),
    )

    # PROJECTION: project the recorded event into a FieldState (or HOLD).
    projection = state_projection_module.project_from_log(
        event_log, event.seq, logical_step=logical_step, min_confidence=min_confidence
    )

    # REPLAY: reload the log and re-project the same event -> identical record.
    reloaded = type(event_log).deserialize(event_log.serialize())
    reproj = state_projection_module.project_from_log(
        reloaded, event.seq, logical_step=logical_step, min_confidence=min_confidence
    )
    replay_ok = (
        reloaded.verify_integrity()
        and projection.to_dict() == reproj.to_dict()
    )

    return IngressResult(
        admitted=True, refusal_reason=None,
        reached_substrate=True,
        projection_status=projection.status,
        replay_ok=replay_ok,
    )
