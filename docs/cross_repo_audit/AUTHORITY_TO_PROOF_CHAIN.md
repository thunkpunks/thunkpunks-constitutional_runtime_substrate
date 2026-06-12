\# Authority to Proof Chain



Status: draft v0



\## Purpose



Records how an admissibility decision becomes evidential proof.



\## Core boundary



Authority decides. Proof records. Replay verifies evidence.



No proof layer decides admissibility.



\## Chain



| Step | Layer | Owner | Status |

|---|---|---|---|

| 1 | Gate evaluation | runtime/components/gate.py | BUILT |

| 2 | Outcome selection | GateOutcome | BUILT |

| 3 | Event append | EventLog | BUILT |

| 4 | Lineage record | LineageGraph | BUILT |

| 5 | Receipt issuance | issue\_receipt / ReceiptLog | BUILT |

| 6 | Evidential bundle | EvidentialBundle | BUILT |

| 7 | Replay validation | replay\_evidential\_chain | BUILT |



\## Flow



GateInput -> predicted FieldState -> GateOutput -> EventLog.append(...) -> LineageRecord -> issue\_receipt(...) -> ReceiptLog -> EvidentialBundle -> replay\_evidential\_chain(...)



\## Verified footing



\- admissibility-kernel: 23 tests passing

\- constitutional\_runtime\_substrate: 496 tests passing

\- event log: append-only hash-chain verified

\- receipts: self-hash and event/log binding verified

\- lineage: replayable ancestry verified

\- replay integration: composed evidential chain verified



\## Current ruling



The architecture is source-footed as authority layer -> proof layer -> replay layer.



The proof layer records and verifies evidence. It does not decide admissibility.

