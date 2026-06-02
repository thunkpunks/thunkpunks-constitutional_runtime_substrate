# Synthetic Ingress Wiring — Status

## Status: EXPERIMENTALLY_BOUNDED

File: `ingress_wiring.py`. Tests: `test_ingress_wiring.py` (7/7).

Threads synthetic obs -> membrane -> event-log -> projection -> replay.

## Verified
- admitted obs reaches replay-valid circuit (READY and HOLD both replay-ok)
- refused obs never reaches substrate (event-log len 0 on refusal)
- replay reconstructs identical projection
- no shadow kernel: wiring imports no gate/constitution/receipts/lineage; no evaluate

## Discipline held
membrane records, circuit decides. Existing substrate only. No new authority,
no kernel change, no orchestration, no vendor, no streaming.

## Recorded, not built
Gate step in the wired path (obs -> ... -> gate -> receipt) is exercised by the
existing evidential-loop; full membrane-to-receipt wiring deferred until a
source-shape stream is named. This wiring proves admitted STATE reaches a
replay-valid projection without the membrane touching decision machinery.
