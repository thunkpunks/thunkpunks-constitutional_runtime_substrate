# Constraint Register

The enumerated set of binding constraints. Each row names the constraint, how it
is enforced (test / structure / recorded), and its status. A constraint with no
enforcement mechanism is RECORDED, not BINDING.

| # | Constraint | Enforcement | Status |
|---|-----------|-------------|--------|
| C1 | Only the gate authorises commitment-state change | authority map (deny-by-default) + CommitToken absent for counterfactuals + tests | BINDING |
| C2 | The gate is pure (no IO, global, randomness, time) | test_k1_acceptance (source inspection) | BINDING |
| C3 | tau monotone non-decreasing except sanctioned recovery | SessionState.advance raises + test | BINDING |
| C4 | NSV monotone; recovery retains residue | apply_delta clamp + rollback + test | BINDING |
| C5 | Measurement trust cannot authorise execution | measurement layer -> MEASUREMENT_HOLD + test | BINDING |
| C6 | Composition != admission; composite still judged by gate | Transformation.compose + test_composition | BINDING |
| C7 | Composition fail-closed; agrees with sequential application | test_composition proof obligations | BINDING |
| C8 | Closed outcome space {EXECUTE,TRANSFORM,DEFER,REJECT} | GateOutcome enum + precedence + test | BINDING |
| C9 | Field-state coordinates out of domain are non-representable | FieldState.__post_init__ + test | BINDING |
| C10 | Coherence relations are joint, irreducible to per-dim bounds (K2) | coherence.py + test_coherence | BINDING |
| C11 | Cumulative horizon quantities can be inadmissible (K3) | horizon.py + test_horizon | BINDING |
| C12 | Physics/policy split: domains parameterize, never redefine | constitution.py + validate_configuration_touches_only_policy | BINDING |
| C13 | Inward-only dependencies; kernel imports no outer layer | architecture/import_boundary.py + test_layer_boundaries | BINDING |
| C14 | Every module is assigned a layer (no accidental membership) | test_no_unclassified_modules | BINDING |
| C15 | Build the boundary before the layer | doctrine + C13 (pre-declared edges for CONCEPTUAL layers) | BINDING (doctrine) |
| C16 | Append-only evidential trace; records never mutated | TraceLedger + event-log hardening + tests | BINDING |
| C17 | Recorded != built; cosmology may not outrun invariants | build-log discipline + this register | DOCTRINE |
| C18 | Lineage: transformations have lawful, replayable ancestry | lineage.py + test_lineage (20) | BINDING |
| C19 | Receipts record outcomes as opaque evidence, never produce verdicts | receipts.py (no GateOutcome import) + test_receipts (19) | BINDING |
| C20 | State projection maps observations to FieldState honestly (measured-zero != blank); decides nothing | state_projection.py + test_state_projection (18) | BINDING |
| C21 | Closed circuit: observation -> kernel -> evidence with no authority leakage | test_evidential_loop (15) + test_closed_circuit_fixture | BINDING |
| C22 | Kernel decides, substrate remembers: kernel and substrate import neither the other | structural import tests in test_evidential_loop | BINDING |
| C23 | Constitutional Receipt Demonstration is the canonical proof artifact (paired EXECUTE/DEFER, one circuit, tamper-fails-closed); receipts genuine, never synthetic | demos/regulated_receipt_demo.py + test (15) | BOUNDED (canonical) |
| C24 | Institutional decision lineage: a decision chain is reconstructed from existing substrate only (composed_from/event-log/receipts/replay), no inference; tamper/reorder/insertion/ancestor-corruption fail closed | demos/decision_lineage_demo.py + test (11) | EXPERIMENTALLY_BOUNDED |

## Conceptual layers (rules pre-declared, no modules yet)

| Layer | Forbidden edges pre-declared | Status |
|-------|------------------------------|--------|
| Domain (admissibility surfaces) | domain -> constitutional (may not redefine physics) | CONCEPTUAL |
| Pedagogy (Runtime University) | pedagogy may not alter admissibility/authority | CONCEPTUAL |
| Symbolic (Wolfram witness) | symbolic outputs must be evidence-attached, bounded, replayable | CONCEPTUAL |

These have enforcement rules in `architecture/layer_map.py` that activate the
moment they acquire modules — the boundary precedes the layer (C15).
