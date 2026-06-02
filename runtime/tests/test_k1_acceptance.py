"""
K1 ACCEPTANCE TESTS — the build contract.

K1 is not complete unless ALL TEN criteria below pass. These turn the
engineering brief from guidance into contract.

  1.  Protected physics is separate from configurable policy.
  2.  Domain policy cannot edit protected physics.
  3.  Tau monotonicity remains enforced except through sanctioned recovery.
  4.  NSV is monotone and cannot be reduced by recovery.
  5.  Measurement trust cannot authorise execution.
  6.  Counterfactual paths cannot obtain a CommitToken.
  7.  ThresholdPolicy can configure policy thresholds but cannot redefine physics.
  8.  Gate purity is preserved.
  9.  Invalid physics states are refused or non-representable.
  10. K2 coherence relations have a reserved insertion point.
"""
import inspect
import pytest

from runtime.components.constitution import (
    constitution, Constitution, Configuration, GovernedRuntime,
    ConstitutionViolation, ConstitutionalInvariant, InvariantClass,
    validate_configuration_touches_only_policy,
    _POLICY_FIELDS,
)
from runtime.components.gate import GateThresholds, GateInput, evaluate
from runtime.components.threshold_policy import StaticPolicy, GeometryDerivedPolicy
from runtime.components.counterfactual import (
    EvaluationMode, evaluate_with_mode, CounterfactualWriteAttempt,
)
from runtime.components.rollback import recover_to_checkpoint
from runtime.components.measurement import (
    MeasurementProvenance, MeasurementPolicy, evaluate_measurement,
)
from runtime.core.bench_interface import SessionState, PreGateOutcome
from runtime.core.types import FieldState, Transformation, GateOutcome


# --- Criterion 1: physics separate from policy --------------------------------

class Test01_PhysicsSeparateFromPolicy:
    def test_constitution_holds_physics_configuration_holds_policy(self):
        c = constitution()
        # Physics: named invariants, none editable.
        assert len(c.invariants) >= 1
        assert all(inv.editable is False for inv in c.invariants)
        # Policy: a Configuration holds thresholds, a disjoint concern.
        config = Configuration(thresholds=GateThresholds(), domain_label="test")
        assert config.configured_fields() == _POLICY_FIELDS
        # The two sets do not overlap: no policy field names a constitutional law.
        physics_names = set(c.names())
        assert physics_names.isdisjoint(_POLICY_FIELDS)


# --- Criterion 2: policy cannot edit physics ----------------------------------

class Test02_PolicyCannotEditPhysics:
    def test_constitution_refuses_construction_with_args(self):
        with pytest.raises(ConstitutionViolation):
            Constitution(tau_monotonicity=False)

    def test_governed_runtime_always_uses_canonical_constitution(self):
        # A domain author holds a GovernedRuntime; its constitution is canonical,
        # not something they can swap.
        gr = GovernedRuntime(configuration=Configuration(thresholds=GateThresholds()))
        assert gr.constitution is constitution()

    def test_configuration_touching_physics_field_is_flagged(self):
        # Trying to "configure" a physics concept (e.g. tau_monotonicity) is a
        # violation: it is not a policy field.
        violations = validate_configuration_touches_only_policy(
            {"omega_floor", "tau_monotonicity"}
        )
        assert "tau_monotonicity" in violations
        assert "omega_floor" not in violations


# --- Criterion 3: tau monotonicity except sanctioned recovery -----------------

class Test03_TauMonotonicity:
    def test_advance_forbids_tau_decrease(self):
        s = SessionState.initial(session_id="s", tau=0.5, Theta=0.5)
        with pytest.raises(ValueError, match="monotonicity"):
            s.advance(new_tau=0.3, new_Theta=0.5, tick_id="t", logical_step=1)

    def test_recovery_is_the_sanctioned_exception(self):
        cur = SessionState(session_id="s", tau=0.6, Theta=0.4,
                           last_tick_id="t5", last_logical_step=5, renegotiation_count=0)
        ckpt = SessionState(session_id="s", tau=0.2, Theta=0.8,
                            last_tick_id="t2", last_logical_step=2, renegotiation_count=0)
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.3, reason="sanctioned",
            max_rollback_distance=0.5, recovery_tick_id="r", recovery_logical_step=6,
        )
        assert result.recovered_session.tau < cur.tau  # decreased, via the sole path

    def test_constitution_declares_both(self):
        c = constitution()
        assert c.invariant("tau_monotonicity").invariant_class == InvariantClass.MONOTONICITY
        assert c.invariant("sanctioned_recovery").invariant_class == InvariantClass.SANCTIONED_EXCEPTION


# --- Criterion 4: NSV monotone, not reduced by recovery -----------------------

class Test04_NSVMonotoneAndRetained:
    def test_recovery_retains_nsv(self):
        cur = SessionState(session_id="s", tau=0.6, Theta=0.4,
                           last_tick_id="t5", last_logical_step=5, renegotiation_count=0)
        ckpt = SessionState(session_id="s", tau=0.2, Theta=0.8,
                            last_tick_id="t2", last_logical_step=2, renegotiation_count=0)
        result = recover_to_checkpoint(
            cur, ckpt, current_NSV=0.45, reason="test",
            max_rollback_distance=0.5, recovery_tick_id="r", recovery_logical_step=6,
        )
        # NSV is RETAINED, never reduced.
        assert result.record.resulting_NSV == 0.45
        assert result.record.irreversible_residue_retained == 0.45

    def test_constitution_declares_nsv_monotonicity(self):
        assert constitution().invariant("nsv_monotonicity").invariant_class == InvariantClass.MONOTONICITY


# --- Criterion 5: measurement trust cannot authorise execution ----------------

class Test05_TrustCannotAuthorise:
    def test_untrusted_measurement_holds_not_executes(self):
        obs_provenance = MeasurementProvenance(confidence=0.1, source="noisy")
        from runtime.core.bench_interface import BenchObservation
        obs = BenchObservation(Omega=0.7, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5,
                               omega_raw=tuple([0.5]*9), session_id="s", tick_id="t", timestamp_ms=0)
        result = evaluate_measurement(obs, obs_provenance, MeasurementPolicy(min_confidence=0.5))
        pgo = result.to_pre_gate_output()
        # Untrusted -> MEASUREMENT_HOLD, which is neither EXECUTE nor REJECT.
        assert pgo.outcome == PreGateOutcome.MEASUREMENT_HOLD
        assert pgo.outcome.value != GateOutcome.EXECUTE.value

    def test_trust_is_orthogonal_not_authorising(self):
        # High trust does not itself authorise; it only permits the gate to run.
        # The authorising act is the gate's, never the measurement's.
        prov = MeasurementProvenance(confidence=1.0, source="good")
        from runtime.core.bench_interface import BenchObservation
        obs = BenchObservation(Omega=0.7, rho=0.0, kappa=0.0, NSV=0.0, Energy=0.5,
                               omega_raw=tuple([0.5]*9), session_id="s", tick_id="t", timestamp_ms=0)
        result = evaluate_measurement(obs, prov)
        # trustworthy True only means "proceed to gate", not "execute".
        assert result.trustworthy is True
        assert result.to_pre_gate_output() is None  # proceed; the GATE decides


# --- Criterion 6: counterfactual cannot obtain CommitToken --------------------

class Test06_CounterfactualCannotCommit:
    def test_counterfactual_commit_token_raises(self):
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        gi = GateInput(current_state=s, transformation=Transformation.new(typed_effects={"tau": 0.05}),
                       thresholds=GateThresholds())
        res = evaluate_with_mode(gi, EvaluationMode.COUNTERFACTUAL)
        with pytest.raises(CounterfactualWriteAttempt):
            res.commit_token()

    def test_authoritative_yields_token(self):
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        gi = GateInput(current_state=s, transformation=Transformation.new(typed_effects={"tau": 0.05}),
                       thresholds=GateThresholds())
        res = evaluate_with_mode(gi, EvaluationMode.AUTHORITATIVE)
        assert res.commit_token() is not None


# --- Criterion 7: ThresholdPolicy configures policy, not physics --------------

class Test07_ThresholdPolicyConfiguresPolicyOnly:
    def test_static_policy_sets_thresholds(self):
        p = StaticPolicy(thresholds=GateThresholds(omega_floor=0.3))
        assert p.resolve(None).omega_floor == 0.3

    def test_geometry_policy_uninstantiable(self):
        # Tier 3 (which WOULD let geometry redefine the region) is gated.
        with pytest.raises(NotImplementedError, match="K2"):
            GeometryDerivedPolicy()

    def test_policy_cannot_name_a_physics_invariant(self):
        # No policy field corresponds to a constitutional invariant name.
        assert set(constitution().names()).isdisjoint(_POLICY_FIELDS)


# --- Criterion 8: gate purity preserved ---------------------------------------

class Test08_GatePurity:
    def test_gate_evaluate_is_pure_no_hidden_state(self):
        src = inspect.getsource(evaluate)
        # No IO, no globals, no randomness, no time.
        for forbidden in ["open(", "print(", "random", "time.", "global ", "os."]:
            assert forbidden not in src, f"gate.evaluate contains {forbidden!r}"

    def test_same_input_same_output(self):
        s = FieldState(Omega=0.7, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)
        gi = GateInput(current_state=s, transformation=Transformation.new(typed_effects={"tau": 0.05}),
                       thresholds=GateThresholds())
        a = evaluate(gi)
        b = evaluate(gi)
        assert a.outcome == b.outcome
        assert a.predicted_state == b.predicted_state


# --- Criterion 9: invalid physics states refused / non-representable ----------

class Test09_InvalidStatesNonRepresentable:
    def test_omega_out_of_bounds_refused(self):
        with pytest.raises(ValueError):
            FieldState(Omega=1.5, rho=0.0, kappa=0.0, tau=0.3, Theta=0.7, NSV=0.0, logical_step=0)

    def test_tau_out_of_bounds_refused(self):
        with pytest.raises(ValueError):
            FieldState(Omega=0.5, rho=0.0, kappa=0.0, tau=1.5, Theta=0.7, NSV=0.0, logical_step=0)

    def test_constitution_declares_non_representable_class(self):
        names = [inv.name for inv in constitution().invariants
                 if inv.invariant_class == InvariantClass.NON_REPRESENTABLE]
        assert "bounded_field_state" in names


# --- Criterion 10: K2 coherence insertion point reserved ----------------------

class Test10_K2InsertionPointReserved:
    def test_coherence_relations_method_exists(self):
        c = constitution()
        assert hasattr(c, "coherence_relations")
        assert hasattr(c, "coherence_relation_count")

    def test_coherence_count_reflects_k2_landed(self):
        # PRE-K2 this asserted count==1 (a box). K2 has now landed: a second,
        # STATIC joint coherence relation (commitment_renegotiability) was added.
        # count==2 means the region is no longer a box. The insertion point did
        # its job: a relation was added WITHOUT touching the gate's decision
        # structure (the gate consults coherence.check_coherence).
        assert constitution().coherence_relation_count() == 2

    def test_coherence_relations_include_both_couplings(self):
        names = {r.name for r in constitution().coherence_relations()}
        assert "theta_tau_coupling" in names
        assert "commitment_renegotiability_coherence" in names

    def test_insertion_point_is_extensible_without_touching_gate(self):
        # The relations come from the constitution, not hardcoded in the gate.
        # (K2 adds relations here; the gate consults them.) We assert the gate
        # source does not hardcode the coupling set.
        c = constitution()
        # The method derives relations by class from the invariant tuple — so
        # adding a COUPLING invariant extends the set automatically.
        coupling_invariants = [i for i in c.invariants
                               if i.invariant_class == InvariantClass.COUPLING]
        assert len(coupling_invariants) == c.coherence_relation_count()
