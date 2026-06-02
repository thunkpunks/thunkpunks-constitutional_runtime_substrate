# Receipts — Evidence Binding an Outcome to the Substrate

**Status: EXPERIMENTALLY_BOUNDED** (built, 19/19 tests pass; promotion path in STATUS.md).

The event log proved entries are immutable. Lineage proved transformations have
traceable ancestry. A receipt proves the third thing: that a specific
admissibility **outcome** was produced for a specific transformation, recorded
by a specific event, supported by specific evidence — tamper-evident and
replay-valid.

## What a receipt binds (the seven)

| Question | Field |
|----------|-------|
| what was evaluated | `transformation_id` |
| which lineage it belongs to | `lineage_transformation_id` |
| which event recorded it | `event_seq` + `event_content_hash` |
| what outcome was produced | `outcome` (opaque string) |
| which reason codes were emitted | `reason_codes` (opaque strings) |
| what evidence supports it | `evidence_refs` |
| whether it remains replay-valid | `verify_*` against log + lineage |

## The sharp line: records, never produces

A receipt is the first substrate object that HOLDS an outcome. It must record a
verdict the gate produced **without ever producing one**. So the module does not
import `GateOutcome`, does not know the closed set of legal verdicts, and stores
the outcome as an opaque string. Policing the outcome vocabulary would be a step
toward deciding it — that is the gate's authority. The receipt records "the gate
said X" as evidence; it does not judge whether X was right.

## Integrity (reuses the event log)

A receipt binds to an event by `(event_seq, event_content_hash)` and hashes its
own content (`receipt_hash`). Verification checks both: the receipt's content is
intact (payload tamper detection) and the bound event still exists with the same
content hash (orphan / log-tamper detection). No parallel chain — derives from
the event log's tamper-evidence.

## What it is NOT (discipline)

- **No kernel widening** — records outcomes, never produces/validates them.
- **No GateOutcome import** — does not know or police the verdict vocabulary.
- **No orchestration/observability coupling** — stdlib-only; binds to the
  event-log and lineage substrates by duck type, importing neither.

## Build order position

  event log -> lineage -> **receipts** -> replay strengthening -> state
  projection -> observability later.

We are here. Next is replay strengthening, which exercises event-log + lineage +
receipts together end-to-end and is the promotion path for all three to
IMPLEMENTED.
