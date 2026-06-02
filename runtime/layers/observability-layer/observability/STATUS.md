# Read-Only Observability — Status

## Status: EXPERIMENTALLY_BOUNDED

Read-only observability is built, classified as the first OBSERVABILITY-layer
module, and all tests pass (17/17). Marked EXPERIMENTALLY_BOUNDED: it observes a
frozen circuit today, but its own promotion would come from being exercised
against a live stream of real circuit runs, not only fixtures.

This is the layer the whole build order was sequenced to reach last. Its
forbidden-edge rules were pre-declared in the layer map BEFORE this module
existed (build the boundary before the layer), so it inherited its boundary on
arrival.

## What it may do — all built

| Capability | Mechanism | Verified by |
|------------|-----------|-------------|
| read traces | summarize_trace(serialized snapshot) | TestReadsTraces |
| compare replay runs | compare_replay_runs(dict, dict) | TestComparesReplayRuns |
| detect drift | detect_drift(opaque outcome snapshots) | TestDetectsDrift |
| summarize anomalies | summarize_anomalies(observations) | TestSummarizesAnomalies |
| emit non-authoritative observations | Observation(authoritative=False) | TestNonAuthoritative |

## What it may not do — enforced, not promised

| Prohibition | How it is structurally impossible |
|-------------|-----------------------------------|
| decide admissibility | no GateOutcome; Severity vocab has no verdict; kernel cannot import it (layer boundary) | 
| mutate state | accepts SNAPSHOTS (strings/dicts), never live objects — no reference to write back |
| alter receipts | reads receipt dicts, never the ReceiptLog |
| write lineage | reads lineage dicts, never the LineageGraph |
| influence kernel outcomes | Observations are non-authoritative and consumed by nothing in the decision path |

Verified by TestStructuralReadOnly: no kernel/substrate import, stdlib-only, no
evaluate function, snapshot reads cannot mutate source.

## The discipline line

"Observe" is one careless step from "influence". The read-only property is made
structural, not promised:
- The kernel CANNOT import observability (enforced by the layer boundary:
  runtime -> observability and constitutional -> observability are forbidden
  edges). So no observation can reach a verdict — the path does not exist.
- Observability accepts SNAPSHOTS, not live objects. There is no reference
  through which it could write back to a trace, receipt, or lineage.
- Severity (INFO/NOTICE/ANOMALY) is advisory and deliberately contains NO
  admissibility outcome. There is no EXECUTE/TRANSFORM/DEFER/REJECT in this
  module.

## Recorded explicitly

- **Observability observes; it never authorizes.** It reads, compares, detects,
  summarizes, and emits non-authoritative observations.
- **It does not decide admissibility.** No verdict vocabulary; the kernel cannot
  import it; its output influences no outcome.
- **It does not widen kernel authority.** It is a read-only reader of a frozen
  circuit; it adds no decision capability anywhere.

## Scope discipline

This step added only read-only observation. It added no scoring that feeds a
decision, no domain semantics, no orchestration, no agency. Drift detection
reports that two recorded strings differ; it never recomputes a verdict.

## Build order position

  ... -> state projection -> closed circuit (frozen) -> **read-only
  observability**.

The circuit is observed, not altered. You observe a working circuit, not a
half-wired one — which is why this step came last.
