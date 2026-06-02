# Receipts — Status

## Status: IMPLEMENTED

Receipts are built, classified as a runtime-layer module, and all acceptance
tests pass (19/19). Marked EXPERIMENTALLY_BOUNDED per instruction, until receipt
fixtures, replay tests, tamper tests, and lineage promotion tests are exercised
together by the replay-strengthening step (the integration surface, not just
unit behaviour).

## Acceptance criteria — all met

| Criterion | Mechanism | Verified by |
|-----------|-----------|-------------|
| Receipt schema exists | `Receipt` (7 bindings + receipt_hash) | TestSchemaExists |
| Links to event-log entry | event_seq + event_content_hash; verify_against_log | TestLinksToEventLog |
| Links to lineage entry | lineage_transformation_id; verify_receipt_lineage | TestLinksToLineage |
| Records outcome + reason codes | opaque strings, recorded verbatim | TestRecordsOutcomeAndReasons |
| Payload tampering fails | self-hash mismatch detected; ReceiptLog rejects on add/load | TestPayloadTamperingFails |
| Orphan receipt fails | bad event_seq or unknown lineage id fails verification | TestOrphanReceiptFails |
| Replay recovers receipt chain | ReceiptLog serialize/deserialize preserves order; re-verifies | TestReplayRecoversChain |
| Kernel does not import receipts | receipts is a stdlib-only leaf | TestNoKernelCoupling |
| Receipt does not decide admissibility | no GateOutcome/gate/evaluate import; no evaluate fn | test_receipts_does_not_decide_admissibility |

Test count: 19/19 passing.

## The sharp discipline line

Receipts are the FIRST substrate object that holds an outcome (EXECUTE /
TRANSFORM / DEFER / REJECT). The discipline that keeps this from widening kernel
authority:

- The receipt module **does not import `GateOutcome`** and does not know the
  closed set of legal outcomes. The outcome is stored as an OPAQUE STRING the
  caller supplies. (Tested: an arbitrary outcome string is recorded without
  complaint — the receipt is not the gate and does not police verdicts.)
- Validating "is this a legal verdict" would be a step toward deciding it. That
  is the gate's authority. The receipt records "the gate said X" as evidence;
  whether X was correct is not the receipt's question.

## Integrity model

Reuses the event log; invents no new crypto. A receipt binds to an event by
(event_seq, event_content_hash). Verification checks the receipt's own content
hashes to receipt_hash (payload tamper detection) AND the bound event still
exists with the same content_hash (log tamper / orphan detection). No parallel
chain.

## Recorded explicitly

- **Receipts are runtime evidence objects** binding an admissibility outcome to
  the event-log and lineage substrate.
- **Receipts do not decide admissibility.** They record outcomes the gate
  produced; they never produce, validate, or police a verdict.
- **Receipts do not widen kernel authority.** They are a derived, evidence-only
  layer; they add no decision capability to the constitutional core.

## Scope discipline

This step added no observability, domain surfaces, Wolfram witness, Runtime
University, agents, or orchestration. Receipts build only on the event-log and
lineage substrates, both already on disk.

Next in build order: replay strengthening — which exercises event-log, lineage,
and receipts together end-to-end, and is the promotion path for all three
EXPERIMENTALLY_BOUNDED layers.

## Promotion record

Promoted EXPERIMENTALLY_BOUNDED -> IMPLEMENTED by the replay-strengthening step.
The replay integration (test_replay_integration, 15/15) exercised event-log,
lineage, and receipts together end-to-end: full chain reconstructs, and tampering
at any layer (event payload, lineage ancestry, receipt outcome/reasons, deletion,
reorder, orphan event/lineage bindings) fails validation. The integration surface
is now proven, not just the unit behaviour. This component is an evidential
substrate component: IMPLEMENTED.
