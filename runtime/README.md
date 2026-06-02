# Constitutional Runtime Substrate

A research artifact: a single-process synchronous Python runtime that
demonstrates admissibility evaluation, refusal, receipts, replay, and lineage.
Not production. Not an agent framework. Not deployed.

This README demonstrates five things, with tests:

- **HOLD** — incomplete observations stop before evaluation. No fabricated state.
- **REFUSE** — authority-bearing input is rejected at the boundary. Recursively.
- **RECEIPT** — every decision is recorded as evidence bound to its event.
- **REPLAY** — every decision reconstructs deterministically.
- **LINEAGE** — a chain of decisions reconstructs from existing ancestry; tampering fails closed.

That is what this repository is. The sections below show how to verify it
without reading source code.

## Verify in 30 seconds

```
pytest runtime/tests -q                              # expect: 496 passed
python runtime/tests/test_closed_circuit_fixture.py   # expect: VERIFIED
```

The fixture runs one observation through the full circuit:

```
observation -> event-log -> projection -> FieldState
            -> gate -> receipt -> lineage -> replay
```

If the line `replay: VERIFIED` does not print, the proof surface has regressed.

## What this is not

See `NON_CLAIMS.md`. The repository does not claim execution sovereignty,
workflow governance, certification authority, production enforcement, or any
form of constitutional or topological theory. It demonstrates the five
behaviours above and nothing more.

## What may execute, what may be refused

- **The gate** decides admissibility-as-action. Verdicts: EXECUTE, TRANSFORM,
  DEFER, REJECT. Tested.
- **The membrane** decides admissibility-as-state. It refuses verdict
  vocabulary, authority fields (at any nesting depth), fabricated confidence,
  silent compression, and dishonest coordinates. Tested with 24 adversarial
  payloads.
- Nothing else decides anything.

## Where the system stops

- Incomplete observation → MEASUREMENT_HOLD (no gate call).
- Authority-bearing input → AdmissionRefusal (no substrate entry).
- High-commitment proposal with low renegotiability → DEFER (held for human review).
- Tampered event / receipt / lineage → replay fails closed.

Each "stop" is a test. See `PROOF_SURFACES.md`.

## How authority is bounded

- The kernel imports no substrate module.
- No substrate module imports the kernel.
- The membrane imports no kernel module (no shadow kernel).
- Observability imports no kernel module (no observer-as-governor).

Verified by an import analyzer that fails the build on any violation. Zero
violations today.

## How to review without trusting the founder

`REVIEWER_GUIDE.md` lists, per artifact, the eight fields a reviewer needs:
purpose, scope, boundaries, non-claims, authority model, admissibility basis,
refusal conditions, correction path. Source code is not required reading.

## Reading order

1. `NON_CLAIMS.md` — what this is not, before anything else
2. `PROOF_SURFACES.md` — five demonstrations, each runnable
3. `REVIEWER_GUIDE.md` — per-artifact reviewer fields
4. `BUILD_LEDGER.md` — built / experimentally-bounded / recorded-not-built / prohibited
5. `CONSTRAINT_REGISTER.md` — enumerated constraints, each with enforcement and status
