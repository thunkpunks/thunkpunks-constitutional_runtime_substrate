# Institutional Decision Lineage — Status

## Name

**Institutional Decision Lineage** — the third face of the Constitutional Receipt
Demonstration: proof that a SEQUENCE of constitutional decisions forms a
provable, tamper-evident derivation chain.

File: `runtime/demos/decision_lineage_demo.py`
Tests: `runtime/tests/test_decision_lineage_demo.py` (11/11)

## Status: EXPERIMENTALLY_BOUNDED

Built and all tests pass. Remains EXPERIMENTALLY_BOUNDED until exercised by a
real sequence of circuit runs from an ingress path, not only the harness's own
fixture chain.

## What it is

A SEQUENCING HARNESS + READ-ONLY LINEAGE RECONSTRUCTION + INTEGRITY SURFACE.
Nothing more. It runs N decisions through the existing closed loop against ONE
shared substrate, establishes ancestry via the existing compose mechanic, and
reads back the derivation chain with integrity verification.

## Reconstructed exclusively from existing substrate

- **event-log** — the append-only hash chain (reload + verify_integrity).
- **receipts** — bind outcome to event + lineage (verify_against_log/lineage).
- **composed_from** — a composed decision's lineage parents ARE its composed_from
  ids. Ancestry is the recorded composition relation, NOT inferred.
- **replay substrate** — lineage replay-order validation.

No new substrate. No new integrity machinery (the demo reimplements no
verify_/hash_ function; it calls the substrate's). No inference-based lineage.

## Verification condition — met on all four axes

| Axis | Mechanism | Test |
|------|-----------|------|
| tamper | tampered event payload fails reload (chain broken) | test_tampered_event_fails |
| reorder | swapped events fail reload | test_reordered_events_fail |
| insertion | inserted forged event fails reload (seq/chain mismatch) | test_inserted_event_fails |
| ancestor corruption | unknown-parent ancestry fails reconstruction | test_ancestor_corruption_fails_reconstruction |

Plus: a tampered receipt in the chain fails closed on insertion.

## Demonstration result

A 3-decision chain (intake assessment A, support summary B, write-back C composed
from A+B) runs through the real gate; C's ancestry reconstructs to {A, B}; the
clean chain verifies; any corruption fails closed. Ancestry is the existing
composed_from relation — the harness composes C from A and B using
Transformation.compose, and that recorded composition IS the lineage.

## Read-only / no authority

- Classification: OBSERVABILITY (read-only). The lineage view returns integrity
  booleans + ancestry; it carries no verdict key and decides nothing (tested).
- No kernel change, no orchestration, no inference, no new authority surface.
- The kernel judges each decision independently via the existing loop; the
  harness only sequences and composes using existing mechanics.

## Recorded explicitly

- **Institutional decision lineage is a read-only reconstruction** of a decision
  chain from existing substrate.
- **It does not decide admissibility.** It reads recorded ancestry and verifies
  integrity; the kernel decided each step.
- **It does not widen authority or add substrate.** It is a harness + view over
  what was already built.

## Proof surface (now complete)

  receipt (single decision provable) -> paired (separation discriminates:
  EXECUTE vs DEFER) -> **lineage (decision history provable, tamper-evident)**.

The two faces the contract named (receipt, lineage) are both demonstrated. The
honest next phase is no longer more demos but driving the circuit from a real
ingress — a larger question to open deliberately, not drift into.
