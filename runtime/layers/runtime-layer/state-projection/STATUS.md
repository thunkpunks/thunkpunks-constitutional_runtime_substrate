# State Projection — Status

## Status: IMPLEMENTED

State projection is built, classified as a runtime-layer module, and all
acceptance tests pass (18/18). Marked EXPERIMENTALLY_BOUNDED per instruction,
until deterministic projection, replay reconstruction, tamper detection, and
boundary tests have been exercised by a real end-to-end pipeline feeding the
kernel (not only by its own fixtures). Promotion path recorded below.

## Acceptance criteria — all met

| Criterion | Mechanism | Verified by |
|-----------|-----------|-------------|
| Projection schema exists | `ProjectionRecord` (source binding + status + field_state/reasons + hash) | TestSchemaExists |
| Typed observations project deterministically | `project_event`; same input -> same record | TestDeterministicProjection |
| Projection links back to event-log entry | source_event_seq + source_content_hash; verify_against_log | TestLinksToEventLog |
| Projection is replay-reconstructable | reproject same event after reload -> identical record | TestReplayReconstruction |
| Tampered source event invalidates projection | content-hash mismatch detected | TestTamperDetection |
| Orphan projection fails validation | bad source_event_seq fails; project_from missing seq raises | TestOrphanFails |
| Kernel receives FieldState only through declared boundary | projection emits a record; never calls the gate | TestBoundaryAndNoDecision |
| Kernel does not import projection layer | stdlib-only leaf | test_projection_imports_only_stdlib |
| Projection does not decide admissibility | no GateOutcome/gate/evaluate; status is not a verdict | test_projection_does_not_decide_admissibility |

Test count: 18/18 passing.

## Honesty preserved (measured-zero != unmodelled-blank)

Projection carries the CanonicalObservation honesty discipline into the Python
substrate: an unpopulated coordinate, a coordinate absent from the payload, or a
populated coordinate below min_confidence produces a MEASUREMENT_HOLD naming that
coordinate — never a fabricated zero. Only when all six coordinates are populated
and trusted does projection produce a READY FieldState. A coordinate honestly
measured as 0.0 projects to 0.0 (READY), distinct from a blank (HOLD). Tested
both ways.

## The discipline line

Projection produces a FieldState AND the evidence that it did so, but decides
nothing about that FieldState:
- `status` is a PROJECTION status (READY | MEASUREMENT_HOLD), explicitly NOT a
  gate outcome (tested: status is never EXECUTE/TRANSFORM/DEFER/REJECT).
- No GateOutcome import, no gate/constitution/coherence/horizon, no evaluate.
- The resulting FieldState reaches the kernel only when the CALLER hands the
  ProjectionRecord across the declared boundary (to the assembler / gate).
  Projection never calls the gate.

## Integrity model

Reuses the event log; invents no new crypto. A projection binds to its source
event by (source_event_seq, source_content_hash) and self-hashes its content.
Verification checks both: the record's own content is intact, and the source
event still exists with the same content hash (tamper / orphan detection).

## Recorded explicitly

- **State projection is a runtime mapping** from recorded observations into
  FieldState, bound to the source event and emitting projection evidence.
- **It does not decide admissibility.** No gate, no evaluation, no verdict; its
  READY/HOLD status is a projection status, not an outcome.
- **It does not widen kernel authority, alter invariants, or mutate thresholds.**
  min_confidence is a projection input supplied by the caller, not a kernel
  threshold it reaches into; it produces a FieldState the kernel may later judge.

## Scope discipline

This step added no observability scoring, domain semantics, Wolfram witness,
Runtime University, agents, or orchestration. It builds only on the event-log
substrate and the established honesty discipline.

## Promotion criterion

Promote EXPERIMENTALLY_BOUNDED -> IMPLEMENTED when projection is exercised
end-to-end: a recorded observation projected into a FieldState that is then
handed across the declared boundary and evaluated by the gate, with the
projection evidence linked to the resulting receipt. That closes the loop
(observation -> projection -> gate -> receipt -> lineage) and proves the
integration surface, not just projection's unit behaviour.

## Build order position

  event log -> lineage -> receipts -> replay strengthening -> **state
  projection** -> observability later.

We are here. The evidence substrate is complete and the first capability step
(projection) is built and bounded. State projection is the bridge from the
evidence chain to the kernel's input boundary; the end-to-end loop is its
promotion path.

## Promotion record

Promoted EXPERIMENTALLY_BOUNDED -> IMPLEMENTED by the end-to-end evidential
kernel loop. The loop (test_evidential_loop, 15/15) ran a recorded observation
through projection into a FieldState, across the declared boundary to the REAL
gate, and back into a receipt and lineage — deterministically, with the gate
genuinely deciding (EXECUTE for a clean commit, REJECT for a catastrophic step),
the honest hold path skipping the gate when projection is incomplete, and
tampering at any layer breaking replay. Projection's integration surface is now
proven end-to-end, not just its unit behaviour. IMPLEMENTED.
