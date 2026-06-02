# Event Log — Append-Only Evidential Trace

**Status: IMPLEMENTED** (append-only, hash-chained, receipted; 20 tests pass).

The primitive runtime memory substrate. Everything downstream reads from it:
replay, lineage, receipts, state projection, provenance — and later, the
Runtime University, Wolfram witness, and domain overlays.

Built first because it is what the others stand on (per GOVERNING_DISCIPLINE:
evidence substrate before capability).

## What it guarantees

1. **Append-only** — entries are appended, never mutated or removed. Frozen
   entries; ordering (strictly increasing logical_step per session) enforced.
2. **Hash-chained (lineage linkage)** — each entry commits to its predecessor's
   chain hash. Tampering with entry N invalidates every entry after N. This is
   what makes the trace *evidential*: alteration is detectable everywhere
   downstream of the change.
3. **Receipts** — appending returns a verifiable Receipt proving a specific
   event was admitted at a specific position with a specific chain state. A
   receipt can be checked against the log later (verify_receipt).
4. **Tamper-evident** — verify_integrity() recomputes the whole chain; payload
   tampering, reorder, insertion, and deletion are all detected. deserialize()
   re-verifies on load and refuses a broken chain (fail-closed).
5. **Value-isolated** — payloads are deep-copied on append, so a later mutation
   of the caller's dict cannot alter stored history.

## What it is NOT (discipline)

- **No kernel widening** — it stores and verifies events; it does not evaluate
  admissibility, call the gate, or emit EXECUTE/TRANSFORM/DEFER/REJECT. (Tested:
  no gate/outcome imports; no GateOutcome; no evaluate.)
- **No orchestration coupling** — depends only on stdlib (hashlib, json,
  dataclasses, typing). (Tested.)
- **Not a new capability** — it hardens the append-only trace replay already
  relied on, adding the chain + receipts that make it evidence.

## Relationship to the existing TraceLedger

`components/replay.py` has a `TraceLedger` (append-only, per-record + ledger
checksums) that replay uses. This EventLog is the hardened evidential form:
it adds the hash-CHAIN (predecessor linkage, not just per-record checksums),
receipts, value-isolation, and load-time re-verification. A future step may
migrate replay onto this substrate; for now it is the standalone substrate the
next build steps (lineage, receipts, state projection) will use.

## Build order position

  boundary enforcement -> **event log** -> lineage -> receipts -> replay
  strengthening -> state projection -> only then domain / witness / pedagogy.

We are here: the event log is built. Next is lineage (reading the chain as a
derivation graph), then receipts as a first-class linkage across events.
