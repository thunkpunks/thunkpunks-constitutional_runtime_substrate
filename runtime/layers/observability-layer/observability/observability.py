"""
Read-Only Observability — observing the evidential circuit without authorizing.

This is the layer the whole build order was sequenced to reach last, because
"observe" is one careless step from "influence". The discipline here is the
sharpest in the repo: observability must be able to read everything and change
nothing.

WHAT IT MAY DO:
  - read traces (event-log, receipts, lineage — as snapshots)
  - compare replay runs
  - detect drift
  - summarize anomalies
  - emit non-authoritative observations

WHAT IT MAY NOT DO (and cannot, structurally):
  - decide admissibility  — it produces no GateOutcome and the kernel cannot
                            import it (enforced by the layer boundary), so its
                            output is unreachable from any verdict.
  - mutate state          — it accepts SNAPSHOTS (dicts/strings), never live
                            mutable substrate objects, so it holds no reference
                            through which it could write back.
  - alter receipts        — same: it reads receipt dicts, never the ReceiptLog.
  - write lineage         — it reads lineage dicts, never the LineageGraph.
  - influence kernel outcomes — its Observation objects are typed as
                            non-authoritative and are consumed by nothing in the
                            decision path.

STRUCTURAL READ-ONLY GUARANTEE:
  The observer's functions take SNAPSHOTS (the serialized or to_dict() forms the
  substrate already exposes), not the live objects. A snapshot is a value copy;
  there is no path from the observer back to the source. Combined with the layer
  boundary (kernel cannot import observability), the read-only property is
  structural, not promised.

  An Observation is explicitly NON-AUTHORITATIVE: it carries a severity that is
  advisory only (INFO/NOTICE/ANOMALY), never a verdict. There is deliberately no
  EXECUTE/TRANSFORM/DEFER/REJECT in this module's vocabulary.

DISCIPLINE: layer = observability; stdlib-only; imports no kernel and no
write-capable substrate. Status EXPERIMENTALLY_BOUNDED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


COMPONENT_VERSION = "0.1.0"


class Severity(str, Enum):
    """
    Advisory severity for an observation. NOT a verdict. The absence of any
    admissibility outcome here is deliberate: observability describes, it does
    not decide.
    """
    INFO = "info"          # ordinary, expected
    NOTICE = "notice"      # worth attention, not necessarily wrong
    ANOMALY = "anomaly"    # something diverged from expectation


@dataclass(frozen=True)
class Observation:
    """
    A non-authoritative observation about the circuit.

    It carries a kind, a severity (advisory), a human-readable summary, and
    references to the evidence it observed (by id/seq/hash) — never the evidence
    objects themselves. It NEVER carries an admissibility outcome.
    """
    kind: str
    severity: Severity
    summary: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity.value,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "authoritative": False,  # always — recorded explicitly
        }


# ---------------------------------------------------------------------------
# Readers — accept SNAPSHOTS (dicts / serialized text), never live objects.
# ---------------------------------------------------------------------------

def summarize_trace(event_log_text: str) -> Observation:
    """
    Summarize an event-log trace from its serialized form.

    Reads the serialized lines (a value copy); counts events and event kinds.
    Produces an INFO observation. Cannot touch the live log.
    """
    lines = [l for l in event_log_text.splitlines() if l.strip()]
    kinds: dict[str, int] = {}
    import json
    for l in lines:
        d = json.loads(l)
        k = d.get("event_kind", "?")
        kinds[k] = kinds.get(k, 0) + 1
    summary = f"{len(lines)} events: " + ", ".join(f"{k}={n}" for k, n in sorted(kinds.items()))
    return Observation(
        kind="trace_summary", severity=Severity.INFO, summary=summary,
        evidence_refs=tuple(str(i) for i in range(len(lines))),
    )


def compare_replay_runs(
    run_a: dict[str, Any], run_b: dict[str, Any]
) -> Observation:
    """
    Compare two replay-run snapshots (dicts) and report whether they agree.

    Each run is a dict snapshot (e.g. a LoopResult.to_dict() or a ReplayResult
    .to_dict()). Drift = the snapshots differ. This DESCRIBES divergence; it does
    not act on it. Detecting that two runs differ is not the same as deciding
    anything about either — that remains the kernel's domain, untouched here.
    """
    if run_a == run_b:
        return Observation(
            kind="replay_comparison", severity=Severity.INFO,
            summary="replay runs are identical",
        )
    diffs = sorted(set(run_a.keys()) | set(run_b.keys()))
    changed = [k for k in diffs if run_a.get(k) != run_b.get(k)]
    return Observation(
        kind="replay_comparison", severity=Severity.ANOMALY,
        summary=f"replay runs diverge on: {', '.join(changed)}",
        evidence_refs=tuple(changed),
    )


def detect_drift(
    baseline_outcomes: dict[str, str], current_outcomes: dict[str, str]
) -> list[Observation]:
    """
    Detect drift between a baseline and a current set of recorded outcomes.

    Both are snapshots mapping {id: outcome_string}. Outcomes are OPAQUE strings
    (the observer does not know or police the verdict vocabulary — that is the
    gate's). It reports which ids changed outcome. This is observation of recorded
    evidence, not re-evaluation: the observer never recomputes a verdict, it only
    notices that two recorded strings differ.
    """
    observations: list[Observation] = []
    for key in sorted(set(baseline_outcomes) | set(current_outcomes)):
        b = baseline_outcomes.get(key)
        c = current_outcomes.get(key)
        if b is not None and c is not None and b != c:
            observations.append(Observation(
                kind="outcome_drift", severity=Severity.ANOMALY,
                summary=f"{key}: recorded outcome changed {b} -> {c}",
                evidence_refs=(key,),
            ))
        elif b is None or c is None:
            observations.append(Observation(
                kind="outcome_presence", severity=Severity.NOTICE,
                summary=f"{key}: present in only one run "
                        f"({'baseline' if c is None else 'current'} missing)",
                evidence_refs=(key,),
            ))
    return observations


def summarize_anomalies(observations: list[Observation]) -> Observation:
    """
    Roll up a list of observations into a single summary observation.

    Severity is the max present (ANOMALY > NOTICE > INFO). Purely descriptive.
    """
    order = {Severity.INFO: 0, Severity.NOTICE: 1, Severity.ANOMALY: 2}
    if not observations:
        return Observation(kind="anomaly_summary", severity=Severity.INFO,
                           summary="no observations")
    worst = max(observations, key=lambda o: order[o.severity]).severity
    n_anom = sum(1 for o in observations if o.severity is Severity.ANOMALY)
    return Observation(
        kind="anomaly_summary", severity=worst,
        summary=f"{len(observations)} observations, {n_anom} anomalies",
    )
