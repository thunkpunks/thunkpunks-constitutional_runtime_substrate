"""
Layer boundary map — the executable form of the declared four-layer separation.

This is NOT new capability. It is the structural enforcement of boundaries that
were already declared in the constitutional handoff. It adds no runtime concept;
it makes "the kernel may not absorb orchestration/pedagogy/domain/symbolic/
scoring/agency" a lint-checkable invariant instead of a discipline.

STATUS: this enforces boundaries among layers. Most adjacent layers do not yet
exist as directories (orchestration is one transport file; observability is
partially present; domain/pedagogy/symbolic are CONCEPTUAL). The map therefore:
  - classifies what exists today (kernel/runtime, flat in components/ + core/),
  - declares the forbidden edges for layers that will exist,
  so the rule is correct now and ready when adjacent layers acquire directories.

THE FOUR LAYERS (declared; only CONSTITUTIONAL + RUNTIME are substantially built):
  CONSTITUTIONAL — laws, invariants, admissibility, authority boundaries.
  RUNTIME        — state transitions, replay, composition, recovery, trajectory.
  ORCHESTRATION  — MCP transport, agents, skills, routing, tool coordination.
  OBSERVABILITY  — telemetry, calibration, trajectory analysis, spectral.
  (DOMAIN, PEDAGOGY, SYMBOLIC are CONCEPTUAL — no modules yet; rules pre-declared.)

CORE is the shared substrate (types, authority, bench_interface) that the
constitutional and runtime layers are built from; it is the most foundational
and may be imported by everything, importing nothing but stdlib.
"""
from __future__ import annotations

from enum import Enum


class Layer(str, Enum):
    CORE = "core"                    # shared substrate: types, authority, bench_interface
    CONSTITUTIONAL = "constitutional"  # laws, invariants, admissibility, authority
    RUNTIME = "runtime"              # state, replay, composition, recovery, trajectory
    ORCHESTRATION = "orchestration"  # MCP transport, routing, tools, agents
    OBSERVABILITY = "observability"  # calibration, measurement, telemetry, spectral
    INGRESS = "ingress"              # constitutional membrane: observations -> admissible state
    DOMAIN = "domain"                # admissibility surfaces, domain overlays (CONCEPTUAL)
    PEDAGOGY = "pedagogy"            # runtime university (CONCEPTUAL)
    SYMBOLIC = "symbolic"            # Wolfram witness (CONCEPTUAL)


# ---------------------------------------------------------------------------
# Module -> layer assignment. Keyed by module name (file stem) within the repo.
# This is the single source of truth. A module not listed here is UNCLASSIFIED
# and the analyzer flags it (so new files must be assigned a layer deliberately).
# ---------------------------------------------------------------------------

MODULE_LAYER: dict[str, Layer] = {
    # --- core (shared substrate) ---
    "types": Layer.CORE,
    "authority": Layer.CORE,
    "bench_interface": Layer.CORE,

    # --- constitutional ---
    "constitution": Layer.CONSTITUTIONAL,
    "coherence": Layer.CONSTITUTIONAL,
    "horizon": Layer.CONSTITUTIONAL,
    "lambda0": Layer.CONSTITUTIONAL,

    # --- runtime ---
    "gate": Layer.RUNTIME,
    "replay": Layer.RUNTIME,
    "rollback": Layer.RUNTIME,
    "session_manager": Layer.RUNTIME,
    "trajectory": Layer.RUNTIME,
    "counterfactual": Layer.RUNTIME,
    "threshold_policy": Layer.RUNTIME,
    "event_log": Layer.RUNTIME,
    "lineage": Layer.RUNTIME,
    "receipts": Layer.RUNTIME,
    "replay_integration": Layer.RUNTIME,
    "state_projection": Layer.RUNTIME,
    "evidential_loop": Layer.RUNTIME,

    # --- orchestration ---
    "mcp_router": Layer.ORCHESTRATION,

    # --- observability ---
    "calibration": Layer.OBSERVABILITY,
    "calibration_fixtures": Layer.OBSERVABILITY,
    "measurement": Layer.OBSERVABILITY,
    "observability": Layer.OBSERVABILITY,
    # Canonical proof artifact: the Constitutional Receipt Demonstration. A
    # read-only presentation coordinator that RUNS the existing closed circuit and
    # presents the auditor view. It is non-authoritative (observability): it adds
    # no decision capability; it only reads and displays genuine circuit output.
    "regulated_receipt_demo": Layer.OBSERVABILITY,
    # Third face: institutional decision lineage. Sequencing harness + read-only
    # lineage reconstruction + integrity surface. Reconstructs ancestry from
    # existing composed_from/event-log/receipts/replay only; no inference, no new
    # substrate, no authority. Non-authoritative (observability).
    "decision_lineage_demo": Layer.OBSERVABILITY,

    # --- ingress (constitutional membrane) ---
    "ingress_membrane": Layer.INGRESS,
    "ingress_wiring": Layer.INGRESS,
}


# ---------------------------------------------------------------------------
# Forbidden import edges. An edge (A, B) means: a module in layer A MAY NOT
# import a module in layer B. This encodes the handoff's mandatory separations.
#
# The governing principle: dependencies may point INWARD (toward core and
# constitution), never OUTWARD (the kernel must not depend on the layers that
# orchestrate, observe, teach, or specialize it).
# ---------------------------------------------------------------------------

FORBIDDEN_EDGES: set[tuple[Layer, Layer]] = {
    # CONSTITUTIONAL may not depend on anything less foundational than CORE.
    (Layer.CONSTITUTIONAL, Layer.RUNTIME),
    (Layer.CONSTITUTIONAL, Layer.ORCHESTRATION),
    (Layer.CONSTITUTIONAL, Layer.OBSERVABILITY),
    (Layer.CONSTITUTIONAL, Layer.DOMAIN),
    (Layer.CONSTITUTIONAL, Layer.PEDAGOGY),
    (Layer.CONSTITUTIONAL, Layer.SYMBOLIC),

    # RUNTIME may depend on CORE and CONSTITUTIONAL, but not on the layers that
    # sit ABOVE it (orchestration/observability/domain/pedagogy/symbolic).
    (Layer.RUNTIME, Layer.ORCHESTRATION),
    (Layer.RUNTIME, Layer.OBSERVABILITY),
    (Layer.RUNTIME, Layer.DOMAIN),
    (Layer.RUNTIME, Layer.PEDAGOGY),
    (Layer.RUNTIME, Layer.SYMBOLIC),

    # CORE depends on nothing in the repo (only stdlib). Everything inward of it.
    (Layer.CORE, Layer.CONSTITUTIONAL),
    (Layer.CORE, Layer.RUNTIME),
    (Layer.CORE, Layer.ORCHESTRATION),
    (Layer.CORE, Layer.OBSERVABILITY),
    (Layer.CORE, Layer.DOMAIN),
    (Layer.CORE, Layer.PEDAGOGY),
    (Layer.CORE, Layer.SYMBOLIC),

    # OBSERVABILITY may READ runtime/constitutional outputs (it imports their
    # types to inspect them) but may NOT drive orchestration or define domain.
    # Critically it must not be imported BY the kernel (covered by the RUNTIME/
    # CONSTITUTIONAL -> OBSERVABILITY edges above). Observability determining
    # admissibility is prevented structurally: the gate (RUNTIME) cannot import
    # observability, so an observability module cannot inject a verdict.
    (Layer.OBSERVABILITY, Layer.ORCHESTRATION),
    (Layer.OBSERVABILITY, Layer.DOMAIN),
    (Layer.OBSERVABILITY, Layer.PEDAGOGY),

    # ORCHESTRATION is a membrane: it may route to runtime/constitutional via
    # their interfaces, but must not BE the domain or pedagogy or redefine them.
    (Layer.ORCHESTRATION, Layer.DOMAIN),
    (Layer.ORCHESTRATION, Layer.PEDAGOGY),

    # DOMAIN may parameterize policy (import CORE/RUNTIME types) but may NOT
    # import CONSTITUTIONAL internals (it must not redefine physics/invariants).
    (Layer.DOMAIN, Layer.CONSTITUTIONAL),

    # INGRESS is the constitutional membrane: external observations -> admissible
    # substrate state. Its defining boundary (pre-declared before the module
    # exists): it may write observations to the substrate, but it MUST NOT reach
    # the kernel's decision machinery — no shadow kernel. The membrane decides
    # whether an observation becomes STATE; the kernel decides whether a
    # transformation becomes ACTION. These must not blur.
    (Layer.INGRESS, Layer.CONSTITUTIONAL),   # may not touch invariants/gate physics
    (Layer.INGRESS, Layer.ORCHESTRATION),
    (Layer.INGRESS, Layer.OBSERVABILITY),
    (Layer.INGRESS, Layer.DOMAIN),
    (Layer.INGRESS, Layer.PEDAGOGY),
    (Layer.INGRESS, Layer.SYMBOLIC),
    # And the kernel must not depend on ingress (the membrane is outside it):
    (Layer.CONSTITUTIONAL, Layer.INGRESS),
    (Layer.RUNTIME, Layer.INGRESS),
    (Layer.CORE, Layer.INGRESS),
}


def layer_of(module_stem: str) -> Layer | None:
    """Return the layer of a module by its file stem, or None if unclassified."""
    return MODULE_LAYER.get(module_stem)


# ---------------------------------------------------------------------------
# Declared shared-type exceptions.
#
# Some DATA types are defined in a module belonging to one layer but are
# semantically shared substrate (they carry no behaviour, only structure). An
# import of such a type does not constitute a true cross-layer dependency.
#
# Each exception is (importer_module, imported_module, justification). It is
# DELIBERATELY narrow: it names the specific edge and why it is not a real
# dependency, rather than broadly exempting a module. The honest long-term fix
# for each is to relocate the shared type to CORE; until then the edge is
# documented, not hidden.
# ---------------------------------------------------------------------------

DECLARED_SHARED_TYPE_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("constitution", "gate"): (
        "constitution imports GateThresholds, which is a POLICY DATA type (a "
        "bundle of configurable float bounds), not runtime behaviour. It is "
        "semantically CORE substrate currently defined in gate.py for historical "
        "reasons. The constitution depends on the threshold STRUCTURE, not on "
        "gate evaluation. Long-term fix: relocate GateThresholds to core. "
        "Until then this edge is a documented data-type dependency, not a "
        "constitutional dependency on runtime behaviour."
    ),
}


def is_declared_exception(importer_module: str, imported_module: str) -> bool:
    """True iff this specific edge is a documented shared-type exception."""
    return (importer_module, imported_module) in DECLARED_SHARED_TYPE_EXCEPTIONS


def is_forbidden(importer_layer: Layer, imported_layer: Layer) -> bool:
    """True iff a module in importer_layer may not import one in imported_layer."""
    return (importer_layer, imported_layer) in FORBIDDEN_EDGES
