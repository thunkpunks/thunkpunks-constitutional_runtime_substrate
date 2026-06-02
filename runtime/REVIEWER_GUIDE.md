# REVIEWER_GUIDE

A first-time reviewer should be able to determine, for each major artifact, the
eight fields below, without reading source code or speaking to anyone.

## The eight fields

| Field | Question it answers |
|-------|---------------------|
| purpose | what is this for |
| scope | what is in |
| boundaries | what is out |
| non-claims | what this is not |
| authority model | who decides what |
| admissibility basis | on what grounds something is admitted or refused |
| refusal conditions | when it stops |
| correction path | how a wrong decision is revisited |

## Per-artifact reviewer surface

### gate (kernel)

- **purpose:** decide admissibility-as-action for a proposed transformation
- **scope:** evaluates a typed transformation against a FieldState and thresholds
- **boundaries:** does not record, does not orchestrate, does not observe
- **non-claims:** no scoring, no probability, no commentary on the transformation
- **authority model:** the ONLY producer of verdicts (EXECUTE/TRANSFORM/DEFER/REJECT)
- **admissibility basis:** state bounds; coherence relations between commitment depth τ and renegotiability Θ (K2); cumulative horizon quantities — NSV, Ω-erosion, peak τ (K3)
- **refusal conditions:** REJECT for inadmissible; DEFER for hold-for-human-review
- **correction path:** rollback (sole sanctioned τ-decrement, NSV-honest)

### ingress membrane

- **purpose:** decide admissibility-as-state for an external observation
- **scope:** already-canonicalized observation dicts only
- **boundaries:** no vendor translation; no gate access; no shadow kernel
- **non-claims:** does not judge the transformation; does not produce verdicts
- **authority model:** can refuse, cannot decide
- **admissibility basis:** structural shape; recursive authority-stripping; coordinate honesty; compression disclosure
- **refusal conditions:** verdict vocabulary, authority fields, fabricated confidence, silent compression, dishonest coordinates
- **correction path:** the refused observation is rejected; the caller may resubmit with corrected payload

### event-log (substrate)

- **purpose:** append-only, hash-chained record of events
- **scope:** records what happened; verifies integrity on reload
- **boundaries:** does not decide anything; does not import the kernel
- **non-claims:** not a database, not a queue, not external storage
- **authority model:** none — records only
- **admissibility basis:** structural (logical_step strictly increases per session)
- **refusal conditions:** ordering violations on append; tamper on deserialize
- **correction path:** forward-only. Events are immutable by design; corrections are issued as new events.

### lineage (substrate)

- **purpose:** record transformation ancestry as a graph
- **scope:** parent ids from `Transformation.composed_from`, bound to events
- **boundaries:** does not infer ancestry; reads only the recorded composition
- **non-claims:** no semantic interpretation of derivations
- **authority model:** none
- **admissibility basis:** parents must precede children, no cycles, no duplicates, no future parents
- **refusal conditions:** any of the above violated
- **correction path:** forward-only. Ancestry is immutable by design; corrections appear as new transformations and new lineage records.

### receipts (substrate)

- **purpose:** evidence binding a verdict to its event and lineage
- **scope:** records (opaque outcome string, reason codes, event binding, lineage id, evidence refs)
- **boundaries:** does not import GateOutcome; does not police verdict vocabulary
- **non-claims:** does not produce, validate, or recompute verdicts
- **authority model:** none — evidence only
- **admissibility basis:** self-hash + bound-event hash + known lineage id
- **refusal conditions:** tampered payload; orphan event; unknown lineage
- **correction path:** forward-only. Receipts are immutable evidence of decisions made; corrections are issued as new decisions and new receipts.

### observability

- **purpose:** read traces, compare runs, detect drift, summarize anomalies
- **scope:** accepts snapshots (serialized text, dicts); emits non-authoritative observations
- **boundaries:** never writes; never injected by the kernel
- **non-claims:** no scoring, no action, no verdict vocabulary
- **authority model:** read-only; severity (INFO/NOTICE/ANOMALY) is advisory only
- **admissibility basis:** N/A (observation, not decision)
- **refusal conditions:** N/A
- **correction path:** N/A — observations are descriptive, not corrective

### boundary analyzer

- **purpose:** enforce inward-only cross-layer dependencies
- **scope:** every `.py` module in the repo, classified to a layer
- **boundaries:** fails the build on a forbidden edge or unclassified module
- **non-claims:** no claim about non-Python dependencies, process/network seams
- **authority model:** structural rule, no runtime authority
- **admissibility basis:** declared forbidden edges in `architecture/layer_map.py`
- **refusal conditions:** any forbidden import; any unclassified module
- **correction path:** classify the module, or remove the edge

## Founder-removal test

This guide should remain sufficient if:
- the founder is unreachable
- no meetings are held
- no verbal explanation is provided
- private context is unavailable

If any field above cannot be answered from the artifacts alone, that is a
reviewability gap. Open an issue with the artifact and the missing field.

## Reading order for a 30-minute review

1. `README.md` (5 min) — what this is, how to verify in 30 seconds
2. `NON_CLAIMS.md` (5 min) — what this is not
3. `PROOF_SURFACES.md` (5 min) — the five demonstrations
4. Run `pytest runtime/tests -q` and
   `python runtime/tests/test_closed_circuit_fixture.py` (2 min)
5. This guide, for any artifact in question (variable)
6. `BUILD_LEDGER.md` and `CONSTRAINT_REGISTER.md` for full picture
