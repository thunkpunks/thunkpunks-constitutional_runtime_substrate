# Constitutional Runtime Substrate

Research artifact. Single-process synchronous Python runtime that demonstrates
admissibility evaluation, refusal, receipts, replay, and lineage. Not
production. Not an agent framework. Not deployed.

The runtime and its documentation live in `runtime/`.

## Start here

```
runtime/README.md           # what this is, verify in 30 seconds
runtime/NON_CLAIMS.md       # what this is not (read second)
runtime/PROOF_SURFACES.md   # five runnable demonstrations
runtime/REVIEWER_GUIDE.md   # eight reviewer fields per artifact
runtime/BUILD_LEDGER.md     # built / experimentally-bounded / recorded-not-built
runtime/CONSTRAINT_REGISTER.md
```

## Verify

```
pytest runtime/tests -q                              # expect: 496 passed
python runtime/tests/test_closed_circuit_fixture.py   # expect: VERIFIED
```
