# Ingress Membrane — Status

## Name

**The Ingress Membrane** — the constitutional boundary where external
observations become admissible substrate state without importing external
authority.

File: `runtime/layers/ingress-layer/ingress/ingress_membrane.py`
Tests: `runtime/tests/test_ingress_membrane.py` (24/24, refusal-first)

## Status: EXPERIMENTALLY_BOUNDED

Built; all tests pass. Remains EXPERIMENTALLY_BOUNDED until exercised against a
real (already-canonicalized) source stream and wired to record admitted
observations into a live event-log end to end. This step is the membrane +
refusal logic only — no vendor integration, no real-source streaming.

## Boundary first (build the boundary before the layer)

The INGRESS layer and its forbidden edges were declared in `layer_map.py` BEFORE
this module existed:
- INGRESS may not import CONSTITUTIONAL (no shadow kernel), nor orchestration/
  observability/domain/pedagogy/symbolic.
- CONSTITUTIONAL/RUNTIME/CORE may not import INGRESS (the membrane is outside the
  kernel).
Verified by test_layer_boundaries (test_ingress_membrane_cannot_reach_kernel).

## The membrane's defining act: refusal

It can refuse a well-formed, faithful observation because something would import
authority. Refusal is fail-closed (raises AdmissionRefusal). Adversarial payloads
refused (all tested):

| Payload | Refused as |
|---------|-----------|
| `authority` field (top-level) | authority_field_present |
| `authority` field (NESTED, any depth) | authority_field_present (recursive scan) |
| verdict value (EXECUTE/.../REJECT) anywhere | verdict_vocabulary_present |
| confidence > 1, = 0 on populated, non-numeric | fabricated_confidence |
| compressed coordinate, undisclosed | undisclosed_compression |
| unpopulated-with-value / populated-without-value | dishonest_coordinate |
| non-dict / missing provenance | malformed_observation |

Clean observations are admitted; an ABSENT coordinate is an honest unpopulated
blank (admitted as such), never a refusal and never a fabricated zero.

## The critical separation (no shadow kernel)

- The MEMBRANE decides whether an observation may become STATE.
- The KERNEL decides whether a transformation may become ACTION.

Tested (test_membrane_judges_state_not_action): a high-tau coordinate is admitted
as state — the membrane never applies gate grounds (tau/coherence/horizon) and
gives no verdict. If it refused on those grounds it would be a second authority.
It refuses only malformed or authority-bearing INPUT.

Structural guards: no kernel import, stdlib-only, no `evaluate` function.

## Memory != truth, at the boundary

Provenance enters as a CLAIM: `Provenance(source_claimed=..., asserted_true=False)`
— always False in the type. External provenance becomes internal EVIDENCE; it
never becomes internal AUTHORITY.

## Recorded explicitly

- **The ingress membrane converts external observations into admissible substrate
  state, stripping external authority.** It does not translate vendor formats
  (that stays outside); it admits or refuses already-canonicalized input.
- **It does not decide admissibility-as-action.** No gate, no verdict, no kernel
  grounds. It judges admissibility-as-state only.
- **It does not widen kernel authority or add a shadow kernel.** Its boundary is
  pre-declared and enforced; it may record observations, never reach the gate.

## Scope held

No vendor integration. No real-source streaming. No gate logic change. No
receipts/lineage mutation. No orchestration expansion. Membrane + refusal-first
tests only.

## Next (recorded, not built)

Wire admitted observations to record into a live event-log and re-project through
the existing circuit — the membrane's promotion path. Deliberately deferred.
