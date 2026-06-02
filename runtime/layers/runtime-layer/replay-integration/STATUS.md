# Replay Integration — Status

## Status: EXPERIMENTALLY_BOUNDED

Replay strengthening is built and all integration tests pass (15/15). It remains
EXPERIMENTALLY_BOUNDED per instruction: it is the integration coordinator, and
while it proves the three substrates compose today, its own promotion would come
from being exercised by a real end-to-end pipeline (state projection and beyond),
not only by its own fixtures.

Note: replay integration being EXPERIMENTALLY_BOUNDED does not hold back the
substrates it validates. The three substrate layers (event-log, lineage,
receipts) ARE promoted to IMPLEMENTED, because the integration proof is the gate
their promotion criteria named, and that proof passed.

## What this is

**Integration proof, not new substrate.** It exercises event-log + lineage +
receipts together as one evidential chain. It reinvents no integrity machinery —
it coordinates the three layers' existing verification:
- event log: `EventLog.deserialize` re-verifies its hash-chain.
- lineage: `build_lineage_from_records` re-validates structural ancestry.
- receipts: `ReceiptLog.deserialize` re-verifies self-hashes;
  `verify_receipt_against_log` / `verify_receipt_lineage` cross-check bindings.

If it added its own hash or ordering rule, it would be new substrate disguised
as integration. It does not.

## Acceptance criteria — all met (test_replay_integration, 15/15)

| Criterion | Verified by |
|-----------|-------------|
| replay integration fixture exists | _build_chain |
| event-log + lineage + receipts replay together | test_full_chain_replays |
| replay reconstructs full evidential chain | test_full_chain_replays (counts) |
| detects tampered event payload | TestTamperedEventPayload |
| detects tampered lineage ancestry | TestTamperedLineageAncestry |
| detects tampered receipt outcome/reasons | TestTamperedReceipt |
| detects deleted/reordered entries | TestDeletedReordered |
| rejects orphan receipts | TestOrphans (event + lineage binding) |
| rejects orphan lineage | test_orphan_lineage_event_reference_fails |
| kernel imports no substrate layer | (substrate is leaf; kernel unchanged) |
| substrates do not decide admissibility | test_replay_does_not_decide_admissibility |
| replay order deterministic | test_replay_is_deterministic |

## Discipline

- **No new substrate** — coordinates existing layers via dependency injection
  (modules passed in), coupling to public surfaces, not import paths.
- **No admissibility decision** — validates evidence; no GateOutcome/gate/
  evaluate import; outcomes travel through as opaque evidence on receipts.
- **No kernel widening** — the kernel imports none of this; this imports no
  kernel.
- Layer: runtime.

## Recorded explicitly

- **Replay integration is evidence-chain validation**, binding the three
  substrate layers into one tamper-evident, replayable whole.
- **It does not decide admissibility.** It proves the evidence chain holds; it
  produces no verdict.
- **It does not widen kernel authority.** It is a coordinator over substrate
  layers, adding no decision capability to the constitutional core.

## Build order position

  event log -> lineage -> receipts -> **replay strengthening** -> state
  projection -> observability later.

We are here. The evidence substrate is complete and proven as one chain. Next is
state projection (mapping observations into the kernel's FieldState), which is
where the evidence chain begins feeding the kernel's actual evaluation — and the
first step that touches the kernel's input boundary again.
