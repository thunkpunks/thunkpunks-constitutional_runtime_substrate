# Read-Only Observability

**Observability observes; it never authorizes.**

This layer reads the evidential circuit and reports on it, without the power to
change anything in it. It is read-only by construction, not by promise.

## What it does

- **read traces** — summarize an event-log trace from its serialized form.
- **compare replay runs** — report whether two replay-run snapshots agree.
- **detect drift** — notice where recorded outcomes changed between a baseline
  and a current run (outcomes treated as opaque strings — it does not know or
  police the verdict vocabulary).
- **summarize anomalies** — roll observations up by advisory severity.
- **emit non-authoritative observations** — every `Observation` is marked
  `authoritative: False`.

## What it cannot do (structurally)

- **decide admissibility** — there is no verdict in its vocabulary
  (severity is INFO/NOTICE/ANOMALY only), and the kernel cannot import this
  layer (the layer boundary forbids runtime/constitutional -> observability), so
  no observation can reach an outcome.
- **mutate state / alter receipts / write lineage** — it accepts SNAPSHOTS
  (serialized text, dicts), never the live substrate objects. It holds no
  reference through which it could write back.
- **influence kernel outcomes** — its output is consumed by nothing in the
  decision path.

## Why it came last

"Observe" is one careless step from "influence". The whole build order —
boundary enforcement, then evidence substrate, then the closed circuit — was
sequenced so that observability arrives to a *frozen, working* circuit it can
only read. You observe a working circuit, not a half-wired one. And because the
boundary was pre-declared before this module existed, it inherited its
read-only edge on arrival (build the boundary before the layer).

See `STATUS.md` for the enforced-prohibition table and test references.
