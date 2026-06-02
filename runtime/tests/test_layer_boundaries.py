"""
Layer boundary enforcement tests.

These make the declared four-layer separation an executable invariant:
- the real repo respects every declared boundary (no violations, none unclassified)
- a DELIBERATELY illegal import is caught (the forbidden-import fixture)
- a legal import path passes (the allowed-dependency fixture)
- the analyzer correctly excludes TYPE_CHECKING imports and declared exceptions

This is boundary ENFORCEMENT, not implementation of adjacent layers. Adjacent
layers (domain, pedagogy, symbolic) have rules pre-declared but no modules yet.
"""
import textwrap
from pathlib import Path

import pytest

from runtime.architecture.layer_map import (
    Layer, layer_of, is_forbidden, is_declared_exception,
)
from runtime.architecture.import_boundary import (
    analyze_dirs, analyze_file, _imported_stems, Violation,
)


REPO_DIRS = [
    Path(__file__).resolve().parent.parent / "components",
    Path(__file__).resolve().parent.parent / "core",
]


class TestRepoRespectsBoundaries:
    """The real repo must respect every declared boundary."""

    def test_no_violations_in_repo(self):
        violations, _ = analyze_dirs(REPO_DIRS)
        assert violations == [], "\n".join(v.detail for v in violations)

    def test_no_unclassified_modules(self):
        # Every module must be deliberately assigned a layer. A new file with no
        # assignment is flagged so layer membership is never accidental.
        _, unclassified = analyze_dirs(REPO_DIRS)
        assert unclassified == [], (
            "Unclassified modules (assign a layer in MODULE_LAYER): "
            + ", ".join(u.module for u in unclassified)
        )


class TestForbiddenImportIsCaught:
    """FIXTURE: a deliberately illegal import must fail."""

    def test_constitutional_importing_orchestration_is_violation(self, tmp_path):
        # A fake CONSTITUTIONAL module that imports an ORCHESTRATION module.
        # 'constitution' is constitutional; 'mcp_router' is orchestration;
        # constitutional -> orchestration is a forbidden edge.
        illegal = tmp_path / "constitution.py"
        illegal.write_text(textwrap.dedent("""
            from .mcp_router import something
        """))
        violations, _ = analyze_file(illegal)
        assert len(violations) == 1
        assert violations[0].importer_layer == "constitutional"
        assert violations[0].imported_layer == "orchestration"

    def test_runtime_importing_observability_is_violation(self, tmp_path):
        # 'gate' is runtime; 'calibration' is observability;
        # runtime -> observability is forbidden (the gate must not depend on
        # the thing that observes it — prevents observability injecting verdicts).
        illegal = tmp_path / "gate.py"
        illegal.write_text("from .calibration import run_suite\n")
        violations, _ = analyze_file(illegal)
        assert len(violations) == 1
        assert violations[0].imported_layer == "observability"

    def test_runtime_importing_domain_is_violation(self, tmp_path):
        # Pre-declared: even though domain has no modules yet, the rule exists.
        # We simulate by adding a domain module to the map temporarily via a
        # known domain stem. Here we assert the EDGE rule directly.
        assert is_forbidden(Layer.RUNTIME, Layer.DOMAIN)
        assert is_forbidden(Layer.CONSTITUTIONAL, Layer.DOMAIN)


class TestAllowedImportPasses:
    """FIXTURE: a legal dependency path must pass."""

    def test_runtime_importing_constitutional_is_allowed(self, tmp_path):
        # 'gate' (runtime) importing 'coherence' (constitutional) is INWARD —
        # allowed. Dependencies may point toward the constitutional center.
        legal = tmp_path / "gate.py"
        legal.write_text("from .coherence import check_coherence\n")
        violations, _ = analyze_file(legal)
        assert violations == []

    def test_runtime_importing_core_is_allowed(self, tmp_path):
        legal = tmp_path / "session_manager.py"
        legal.write_text("from .types import FieldState\n")
        violations, _ = analyze_file(legal)
        assert violations == []

    def test_observability_importing_runtime_types_is_allowed(self, tmp_path):
        # Observability READING runtime outputs (importing gate types to inspect
        # them) is allowed — observability may read traces/receipts/ledgers.
        legal = tmp_path / "calibration.py"
        legal.write_text("from .gate import GateThresholds, evaluate\n")
        violations, _ = analyze_file(legal)
        assert violations == []


class TestTypeCheckingExcluded:
    """TYPE_CHECKING imports are annotation-only and create no runtime edge."""

    def test_type_checking_import_not_counted(self, tmp_path):
        # A constitutional module annotating a runtime type under TYPE_CHECKING
        # is NOT a violation (no runtime dependency).
        src = textwrap.dedent("""
            from typing import TYPE_CHECKING
            if TYPE_CHECKING:
                from .gate import GateOutput
        """)
        f = tmp_path / "horizon.py"
        f.write_text(src)
        violations, _ = analyze_file(f)
        assert violations == []

    def test_runtime_import_still_counted_outside_type_checking(self, tmp_path):
        # The same import OUTSIDE TYPE_CHECKING in a constitutional module IS a
        # violation — proving the exclusion is specific to TYPE_CHECKING.
        src = "from .calibration import run_suite\n"  # constitutional -> observability
        f = tmp_path / "constitution.py"
        f.write_text(src)
        violations, _ = analyze_file(f)
        assert len(violations) == 1


class TestDeclaredException:
    """The GateThresholds shared-type exception is honoured and documented."""

    def test_constitution_gate_edge_is_declared_exception(self):
        assert is_declared_exception("constitution", "gate")

    def test_exception_does_not_leak_to_other_edges(self):
        # The exception is narrow: it does not exempt constitution from importing
        # OTHER runtime modules (e.g. replay).
        assert not is_declared_exception("constitution", "replay")

    def test_real_constitution_passes_via_exception(self, tmp_path):
        # The real constitution imports GateThresholds from gate; that specific
        # edge is exempt, so constitution.py is clean.
        f = tmp_path / "constitution.py"
        f.write_text("from .gate import GateThresholds\n")
        violations, _ = analyze_file(f)
        assert violations == []


class TestInwardDependencyDirection:
    """The governing principle: dependencies point inward, never outward."""

    def test_core_depends_on_nothing_in_repo(self):
        for layer in [Layer.CONSTITUTIONAL, Layer.RUNTIME, Layer.ORCHESTRATION,
                      Layer.OBSERVABILITY, Layer.DOMAIN]:
            assert is_forbidden(Layer.CORE, layer)

    def test_constitutional_cannot_depend_outward(self):
        for layer in [Layer.RUNTIME, Layer.ORCHESTRATION, Layer.OBSERVABILITY,
                      Layer.DOMAIN, Layer.PEDAGOGY, Layer.SYMBOLIC]:
            assert is_forbidden(Layer.CONSTITUTIONAL, layer)

    def test_runtime_may_depend_on_constitutional_and_core(self):
        # These are NOT forbidden (inward dependencies).
        assert not is_forbidden(Layer.RUNTIME, Layer.CONSTITUTIONAL)
        assert not is_forbidden(Layer.RUNTIME, Layer.CORE)

    def test_domain_cannot_redefine_constitutional(self):
        # Domains may parameterize policy but not import constitutional internals.
        assert is_forbidden(Layer.DOMAIN, Layer.CONSTITUTIONAL)

    def test_ingress_membrane_cannot_reach_kernel(self):
        # No shadow kernel: the membrane may not touch the kernel's decision
        # machinery (constitutional), and the kernel may not import ingress.
        assert is_forbidden(Layer.INGRESS, Layer.CONSTITUTIONAL)
        assert is_forbidden(Layer.CONSTITUTIONAL, Layer.INGRESS)
        assert is_forbidden(Layer.RUNTIME, Layer.INGRESS)
        assert is_forbidden(Layer.CORE, Layer.INGRESS)
