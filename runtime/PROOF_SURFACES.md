# PROOF_SURFACES

Five demonstrations. Each runnable. Each fails closed on regression.

The repository's claims are exactly these surfaces and nothing else. If a
surface stops failing closed on the negative case, the corresponding claim is
falsified.

## 1. HOLD — incomplete or low-confidence observation stops before evaluation

**Claim:** An observation with missing, unpopulated, or low-confidence
coordinates does not produce a FieldState. The gate is not called. No
fabricated zeros. ("Ambiguity" elsewhere in the doctrine is broader; this
demo covers structural incompleteness only.)

**Runnable:**
```
pytest runtime/tests/test_state_projection.py::TestDeterministicProjection -q
pytest runtime/tests/test_evidential_loop.py::TestHonestHold -q
```

**Falsifiable by:** any path where an unpopulated or missing coordinate causes
a READY projection. The tests assert MEASUREMENT_HOLD on unpopulated,
low-confidence, or missing coordinates.

## 2. REFUSE — authority-bearing input is rejected at the boundary

**Claim:** The ingress membrane refuses verdict vocabulary, authority fields
(at any nesting depth), fabricated confidence, silent compression, and
dishonest coordinates. Refused observations never enter the substrate.

**Runnable:**
```
pytest runtime/tests/test_ingress_membrane.py -q     # 24 refusal cases
pytest runtime/tests/test_ingress_wiring.py::TestRefusedNeverReachesSubstrate -q
```

**Falsifiable by:** any payload listed in the refusal table that crosses the
membrane, or any refused payload that produces a substrate entry (event-log
length > 0 after refusal).

## 3. RECEIPT — every decision is bound to its event

**Claim:** Every gate verdict is recorded as a receipt that binds outcome and
reason codes to the event that recorded it. The outcome is the gate's
verdict, recorded as opaque evidence; the receipt module does not produce
verdicts.

**Runnable:**
```
pytest runtime/tests/test_receipts.py -q
python runtime/demos/regulated_receipt_demo.py        # auditor view
```

**Falsifiable by:** any receipt that verifies after its outcome, reason codes,
or bound event content hash has been altered.

## 4. REPLAY — every decision reconstructs deterministically

**Claim:** The full circuit (observation → projection → gate → receipt →
lineage) reconstructs from serialized form. Tampering anywhere breaks
reconstruction.

**Runnable:**
```
python runtime/tests/test_closed_circuit_fixture.py   # prints VERIFIED
pytest runtime/tests/test_replay_integration.py -q
pytest runtime/tests/test_evidential_loop.py::TestTamperingInvalidatesReplay -q
```

**Falsifiable by:** any tampered serialized log, receipt, or lineage record
that successfully reconstructs.

## 5. LINEAGE — decision chains reconstruct from existing ancestry

**Claim:** A sequence of decisions linked via `Transformation.compose` forms a
reconstructable derivation chain. Tamper, reorder, insertion, or
ancestor-corruption fails closed.

**Runnable:**
```
pytest runtime/tests/test_decision_lineage_demo.py -q
```

**Falsifiable by:** any of the four tamper axes succeeding without detection.

## Aggregate check

```
pytest runtime/tests -q              # expect: 496 passed
```

A failure here is a regression in at least one of the five surfaces.

## What this is NOT a proof of

See `NON_CLAIMS.md`. These five surfaces do not prove constitutional geometry,
admissibility topology, governance-of-governance, certification authority, or
any other property not on this page. If a property is not testable here, it is
not claimed here.
