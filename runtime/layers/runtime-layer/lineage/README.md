# Lineage — Transformation Ancestry over the Evidential Trace

**Status: EXPERIMENTALLY_BOUNDED** (built, 20/20 tests pass; promotion path in STATUS.md).

The event log proved entries cannot be silently mutated. Lineage proves the next
thing: transformations can be traced through **lawful ancestry** — what was
proposed, what it derived from, what event recorded it, what receipt refers to
it, and whether that ancestry remains replayable.

## What it builds on (attaches to; does not invent)

- `Transformation.composed_from` — parent ids of a composed transformation
  (from the bounded-composition build).
- `EventLog` — append-only, hash-chained entries with `(seq, content_hash)`.
- `Receipt` — verifiable token referring to an event by seq + hashes.

## What it adds

- `LineageRecord` — binds a transformation_id to the event seq that recorded it,
  its parent transformation_ids (ancestry), and an optional receipt link.
- `LineageGraph` — reconstructs ancestry over an event log in replay (seq)
  order, validates structural lawfulness (parents known, parents precede
  children, no cycles, append-only per transformation), and answers
  parents/children/ancestry/replay-order queries.

## Integrity (reuses the event log; invents no new crypto)

Lineage has no hash-chain of its own. It derives from the event log, whose chain
already makes tampering detectable — a graph built from a tampered log fails
because the log fails integrity verification first. Lineage's own checks are
structural ancestry consistency.

## What it is NOT (discipline)

- **No kernel widening** — records and reconstructs ancestry; no gate, no
  evaluation, no outcomes.
- **No orchestration/observability coupling** — depends only on the event-log
  substrate and stdlib.
- **Not a new capability** — it makes the existing `composed_from` ancestry
  traceable and replayable over the evidential trace.

## Build order position

  event log -> **lineage** -> receipts -> replay strengthening -> state
  projection -> observability later.

We are here. Lineage is built and bounded. Next is receipts as first-class
cross-event linkage, then replay strengthening (which is also lineage's
promotion path to IMPLEMENTED).
