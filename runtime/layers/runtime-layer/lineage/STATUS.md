# Lineage — Status

## Status: IMPLEMENTED

Lineage is built, classified as a runtime-layer module, and all acceptance
tests pass (20/20). It is marked EXPERIMENTALLY_BOUNDED (not IMPLEMENTED) per
the build instruction: lineage is a derived layer over the event-log substrate,
and it should hold the more cautious status until it has been exercised by a
real replay-strengthening pass and a wider tamper surface than its own unit
tests. The promotion criterion is recorded below.

## Acceptance criteria — all met

| Criterion | Mechanism | Verified by |
|-----------|-----------|-------------|
| Lineage schema exists | `LineageRecord` (transformation_id, event_seq, parent_ids, receipt hash) | test schema group |
| Links to event-log entries | event_seq points at a real entry; receipt hash matches entry content_hash | TestLinksToEventLog |
| Parent/child ancestry preserved | parents(), children(), ancestry() | TestAncestryPreserved |
| Tampering fails validation | unknown/self/future/duplicate parent rejected; tampered log fails first | TestTamperingFailsValidation |
| Replay reconstructs lineage order | replay_order() == seq order; reconstruction reproduces graph | TestReplayReconstruction |
| Kernel imports nothing from lineage | lineage is a leaf; stdlib-only | TestNoKernelCoupling |
| Lineage does not decide admissibility | no gate/evaluate/outcome/GateOutcome | test_lineage_does_not_decide_admissibility |

Test count: 20/20 passing.

## Promotion criterion (EXPERIMENTALLY_BOUNDED -> IMPLEMENTED)

Promote when lineage has been exercised by the replay-strengthening step (it
must reconstruct ancestry from a replayed event log end-to-end, not only from
hand-built records) AND the receipts step links lineage records to receipts as
first-class objects. Until both exist, lineage's integration surface is unproven
even though its unit behaviour is sound.

## Integrity model

Lineage maintains no hash-chain of its own. It DERIVES from the event log, whose
chain already makes tampering detectable: a lineage graph built from a tampered
log fails because the log fails `verify_integrity()` first (tested). Lineage's
own validation is STRUCTURAL: parents must be known, parents precede children in
seq order (ancestry flows forward), no cycles, append-only per transformation.

## Recorded explicitly

- **Lineage is runtime ancestry over the evidential trace.** It records what
  transformation was proposed, what it derived from (via `composed_from`), what
  event recorded it, and what receipt refers to it.
- **It does not decide admissibility.** No gate, no evaluation, no outcome. It
  answers ancestry questions; admissibility remains the kernel's sole concern.
- **It does not widen kernel authority.** It is a derived, read-oriented layer
  over the event log; it adds no decision capability to the constitutional core.

## Scope discipline

This step did not add observability, agents, Wolfram witness, Runtime
University, domain surfaces, or orchestration. Lineage builds only on the
event-log substrate and `Transformation.composed_from`, both already on disk.

Next in build order: receipts (first-class cross-event linkage), then replay
strengthening (which is also lineage's promotion path).

## Promotion record

Promoted EXPERIMENTALLY_BOUNDED -> IMPLEMENTED by the replay-strengthening step.
The replay integration (test_replay_integration, 15/15) exercised event-log,
lineage, and receipts together end-to-end: full chain reconstructs, and tampering
at any layer (event payload, lineage ancestry, receipt outcome/reasons, deletion,
reorder, orphan event/lineage bindings) fails validation. The integration surface
is now proven, not just the unit behaviour. This component is an evidential
substrate component: IMPLEMENTED.
