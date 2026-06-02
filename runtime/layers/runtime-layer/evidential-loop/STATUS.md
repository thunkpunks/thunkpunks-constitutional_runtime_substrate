# End-to-End Evidential Kernel Loop — Status

## Status: EXPERIMENTALLY_BOUNDED

The loop is built and all tests pass (15/15). It remains EXPERIMENTALLY_BOUNDED:
it is the integration coordinator that closes the circuit, and its own promotion
would come from being driven by a real ingress/orchestration pipeline, not only
its own fixtures. Its passing is, however, the gate that promotes STATE
PROJECTION to IMPLEMENTED (recorded there), and it exercises the replay backbone.

## What it proves

The substrate carries a typed observation all the way through the kernel and
back into evidence, with no authority leakage:

  observation -> event-log -> state projection -> FieldState
              -> gate evaluation (the REAL kernel) -> receipt -> lineage -> replay

## Acceptance criteria — all met (test_evidential_loop, 15/15)

| Criterion | Verified by |
|-----------|-------------|
| typed observation recorded as an event | test_observation_recorded_as_event |
| observation projects deterministically into FieldState | TestProjectionDeterminism |
| FieldState passed to kernel only through declared boundary | run_loop hands FieldState to gate.evaluate; no other path |
| kernel evaluates without importing substrate | test_kernel_does_not_import_substrate |
| receipt records outcome and reason codes | test_receipt_records_outcome_and_reasons |
| lineage links observation, projection, transformation, receipt | test_lineage_links_transformation_and_event |
| replay reconstructs the full loop deterministically | test_full_loop_replays_deterministically |
| tampering (event/projection/lineage/receipt) invalidates replay | TestTamperingInvalidatesReplay |
| substrate layers do not decide admissibility | test_loop_imports_no_kernel_in_substrate_modules |
| real gate genuinely decides | test_real_gate_rejects_catastrophic (REJECT) + EXECUTE on clean |

## The structural proof of non-leakage

The loop is a coordinator OUTSIDE both kernel and substrate:
- No substrate module imports the kernel (tested across all five substrate
  modules).
- No kernel component imports any substrate layer (tested across gate,
  constitution, coherence, horizon).
- The loop imports both and wires them by passing a FieldState across the
  declared boundary; the verdict crosses back as an OPAQUE STRING on a receipt.

Because the loop connects them without either importing the other, the
separation is proven by construction. The kernel is the only thing that calls
evaluate and produces a verdict; every substrate layer only records.

## Honest hold

If projection does not yield a complete, trusted FieldState (an unpopulated or
low-confidence coordinate), the loop STOPS before the gate — no FieldState is
fabricated and the gate is never called. Tested: an incomplete observation
produces a MEASUREMENT_HOLD, no receipt, and only the observation event.

## Recorded explicitly

- **The evidential loop is a runtime-integration coordinator.** It orchestrates
  existing substrate + kernel pieces; it adds no new substrate and no capability.
- **It does not decide admissibility.** The REAL gate decides; the loop records
  the verdict as opaque evidence.
- **It does not widen kernel authority.** The kernel remains the sole authority;
  the loop proves the substrate feeds it without reaching across the boundary.

## Build order position

  event log -> lineage -> receipts -> replay strengthening -> state projection
  -> **end-to-end loop (circuit closed)** -> observability later.

The circuit is closed. The evidence substrate demonstrably carries an
observation through the real kernel and back into replayable, tamper-evident
evidence. Observability (scoring/analysis over this proven circuit) is the next
permitted step — and only now, because you observe a working circuit, not a
half-wired one.
