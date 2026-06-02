# Runtime Layer — The Evidential Circuit

**Kernel decides, substrate remembers.**

This layer holds the evidential substrate and the coordinators that close the
first working constitutional runtime circuit:

```
observation -> event-log -> state projection -> FieldState
            -> gate (the kernel decides) -> receipt -> lineage -> replay
```

The kernel is the only thing that produces a verdict
(EXECUTE / TRANSFORM / DEFER / REJECT). Every layer here only **records** what
happened — immutably (event-log), traceably (lineage), attributably (receipts),
and replayably (replay-integration, evidential-loop). The outcome crosses from
kernel to substrate as an opaque string; no substrate layer evaluates, derives,
or polices it.

## Modules

| Module | Role | Status |
|--------|------|--------|
| event-log | append-only, hash-chained evidential trace | IMPLEMENTED |
| lineage | lawful, replayable transformation ancestry | IMPLEMENTED |
| receipts | outcome bound to substrate as opaque evidence | IMPLEMENTED |
| state-projection | observation -> FieldState (honest); decides nothing | IMPLEMENTED |
| replay-integration | binds event-log + lineage + receipts into one chain | EXPERIMENTALLY_BOUNDED |
| evidential-loop | closes the circuit through the real kernel | EXPERIMENTALLY_BOUNDED |

## The boundary

No substrate module imports the kernel; no kernel component imports the
substrate. The coordinators wire them from outside, passing a FieldState across
the declared boundary. The separation is proven by construction, not asserted.

See `CLOSED_CIRCUIT_REPORT.md` (repo root) for the freeze report and
`tests/test_closed_circuit_fixture.py` for the canonical runnable demonstration.
