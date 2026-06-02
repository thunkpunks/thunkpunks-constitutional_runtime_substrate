# State Projection — Observations into FieldState through the Evidence Substrate

**Status: EXPERIMENTALLY_BOUNDED** (built, 18/18 tests pass; promotion path in STATUS.md).

The first capability step after evidential hardening, and deliberately narrow.
It maps a typed observation (recorded as an event) into the kernel's FieldState,
binds the projection to the source event, and emits projection evidence that is
replay-reconstructable and tamper-evident.

## What it does

- Reads an observation event from the event log (by seq).
- Maps its per-coordinate readings into a FieldState — honestly.
- Emits a `ProjectionRecord` binding (source_event_seq, source_content_hash,
  resulting FieldState OR hold reasons, self-hash).

## Honesty: measured-zero != unmodelled-blank

An unpopulated coordinate, an absent coordinate, or a populated coordinate below
`min_confidence` produces a **MEASUREMENT_HOLD** naming that coordinate — never a
fabricated zero. Only when all six coordinates are populated and trusted does
projection produce a **READY** FieldState. A coordinate measured as 0.0 projects
to 0.0 (READY); a blank holds. The CanonicalObservation discipline, now in the
Python substrate and bound to the event log.

## The discipline line: maps, does not decide

Projection produces a FieldState and the evidence that it did so — and decides
nothing about it:
- `status` is READY | MEASUREMENT_HOLD, **not** a gate outcome.
- No `GateOutcome` import, no gate/constitution/coherence/horizon, no evaluate.
- The FieldState reaches the kernel only when the caller hands the
  ProjectionRecord across the declared boundary. Projection never calls the gate.

## Integrity (reuses the event log)

A projection binds to its source event by `(source_event_seq,
source_content_hash)` and self-hashes. Verification checks both: the record is
intact and the source event still exists with the same content hash. A tampered
source event or an orphan projection (no such event) fails. No parallel chain.

## What it is NOT (discipline)

- **No admissibility decision** — maps and records; produces no verdict.
- **No kernel widening / invariant change / threshold mutation** — `min_confidence`
  is a caller-supplied projection input, not a kernel threshold reached into.
- **No observability scoring, domain semantics, or orchestration.**
- **No duplicate projection path** — it is the substrate-bound, evidence-emitting
  projection; the kernel's own `session_manager.project_to_field_state` remains
  the in-kernel path. This layer adds the event-bound, replayable form.

## Build order position

  event log -> lineage -> receipts -> replay strengthening -> **state
  projection** -> observability later.

We are here. Next is the end-to-end loop (observation -> projection -> gate ->
receipt -> lineage), which is also projection's promotion path. Observability
comes after.
