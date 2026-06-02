# Architecture — Layer Boundary Enforcement

**Status: IMPLEMENTED** (the boundary rule is executable; tests pass).

This directory makes the declared four-layer separation an **executable repo
invariant**. It adds no runtime capability. It only refuses dependency edges the
architecture has declared illegal, turning "the kernel may not absorb
orchestration / pedagogy / domain semantics / symbolic reasoning / scoring /
agent autonomy" from a discipline into a lint-checkable fact.

## What this is NOT

This is **boundary enforcement, not implementation of the adjacent layers.**
The adjacent layers remain unbuilt:

| Layer | Status | On disk |
|-------|--------|---------|
| Constitutional | BUILT | constitution, coherence, horizon, lambda0 |
| Runtime | BUILT | gate, replay, rollback, session_manager, trajectory, counterfactual, threshold_policy |
| Orchestration | EXPERIMENTALLY_BOUNDED | mcp_router (transport only) |
| Observability | PARTIAL | calibration, measurement, trajectory (spectral is CONCEPTUAL) |
| Domain (admissibility surfaces) | CONCEPTUAL | none — rules pre-declared |
| Pedagogy (Runtime University) | CONCEPTUAL | none — rules pre-declared |
| Symbolic (Wolfram witness) | CONCEPTUAL | none — rules pre-declared |

The CONCEPTUAL layers have **forbidden-edge rules pre-declared** so that the
moment they acquire modules, the boundary is already enforced. They have no
runtime authority until they have folders, files, fixtures, tests, and runtime
obligations.

## The governing principle

**Dependencies point inward, never outward.** The constitutional center may not
depend on the layers that orchestrate, observe, teach, or specialize it.

```
        (most foundational)
              CORE
               ^
        CONSTITUTIONAL
               ^
            RUNTIME
               ^
   ORCHESTRATION / OBSERVABILITY / DOMAIN / PEDAGOGY / SYMBOLIC
        (may depend inward; may not be depended upon by the kernel)
```

## The rules (enforced)

1. **Constitutional** may import only CORE. Not runtime, orchestration,
   observability, domain, pedagogy, or symbolic.
2. **Runtime** may import CORE and CONSTITUTIONAL. Not the layers above it.
3. **Core** imports nothing in the repo (stdlib only).
4. **Observability** may read runtime/constitutional types (to inspect outputs)
   but the kernel may not import observability — so observability **cannot inject
   a verdict**. It may not drive orchestration or define domain.
5. **Orchestration** is a membrane: routes to the kernel via interfaces, must not
   BE the domain or pedagogy.
6. **Domain** may parameterize policy (CORE/RUNTIME types) but may **not** import
   CONSTITUTIONAL internals — it cannot redefine physics/invariants.

## How it works

- `layer_map.py` — single source of truth: module → layer, plus the set of
  forbidden layer→layer edges, plus narrow documented shared-type exceptions.
- `import_boundary.py` — parses each module's imports via the AST and checks
  every cross-layer edge. `TYPE_CHECKING`-guarded imports are excluded
  (annotation-only, no runtime dependency).
- `tests/test_layer_boundaries.py` — asserts the repo is clean, a deliberately
  illegal import fails, a legal import passes, and the exclusion/exception
  mechanisms behave.

## Known documented exception

`constitution → gate` for `GateThresholds`. This is a POLICY DATA type (a bundle
of configurable float bounds), not runtime behaviour; it is semantically CORE
substrate currently defined in `gate.py`. The edge is a documented data-type
dependency, **not** a constitutional dependency on runtime behaviour. Long-term
fix: relocate `GateThresholds` to core, after which the exception can be removed.

## Adding a new module

Every new module must be assigned a layer in `MODULE_LAYER`. An unclassified
module fails `test_no_unclassified_modules` — layer membership is never
accidental. If a new module needs an edge the rules forbid, the edge is wrong,
not the rule: re-examine which layer the module belongs to.
