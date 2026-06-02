# BUILD_LEDGER

## 1. Tests
496 passed

## 2. Built (IMPLEMENTED)
- core: types, authority, bench_interface
- constitutional: constitution, coherence, horizon, lambda0
- runtime: gate, replay, rollback, session_manager, trajectory, counterfactual, threshold_policy
- runtime: event_log, lineage, receipts, state_projection
- observability: calibration, measurement, observability
- architecture: layer_map, import_boundary
- demos: regulated_receipt (canonical, BOUNDED)

## 3. Experimentally bounded
- replay_integration
- evidential_loop
- state_projection (promoted, retained loop-bounded status in coordinator role)
- observability
- decision_lineage_demo
- ingress_membrane
- ingress_wiring

## 4. Recorded, not built
- identity_continuity
- representation_lock_in_governance
- adaptive_topology_primitives
- legitimacy_correction_capacity_law
- graph_level_admissibility
- graph_level_corrigibility
- graph_level_transformability
- external_verifier_primitive
- governance_of_capability_growth_law

## 5. Enforced boundaries
- inward-only dependency (boundary analyzer, 0 violations)
- no shadow kernel (ingress -> constitutional forbidden; kernel -> ingress forbidden)
- kernel imports no substrate; substrate imports no kernel
- observability: read-only, no verdict vocabulary
- membrane: recursive authority-strip; refuses verdicts/authority/fabricated confidence/silent compression/dishonest coordinates
- every module classified (0 unclassified)

## 6. Proof surfaces
- closed_circuit_fixture: observation -> ... -> replay VERIFIED
- regulated_receipt_demo: EXECUTE + DEFER paired, tamper-fails-closed
- decision_lineage_demo: chain reconstruction + tamper/reorder/insertion/ancestor-corruption fail closed
- ingress_membrane: refusal-first; 24 adversarial payloads refused
- ingress_wiring: admitted -> replay-valid; refused -> substrate untouched

## 7. Active build queue
1. current: synthetic obs -> membrane -> event-log -> projection -> gate -> receipt -> replay (existing evidential loop)
2. after: implementation decision log primitive (repo-doc, verifier-gated)

## 8. Prohibited expansions
- kernel widening
- new authority surfaces
- orchestration expansion
- observability -> action loop
- agent expansion
- domain semantics in kernel
- vendor integration
- real-source streaming
- synthetic receipts / fabricated provenance
- inference-based lineage
- new ontologies
- cosmology inflation

## 9. Standing orientations (RECORDED, NOT LAW, NOT BUILD TARGET)
- transformation_graphs_as_unit_of_analysis
- governance_of_composed_execution
- governance_of_capability_growth
- preserve_future_possibility_of_legitimate_correction
- workflow_can_still_become_otherwise

Invariant: orientation != doctrine; doctrine != build_target; recorded != built.
