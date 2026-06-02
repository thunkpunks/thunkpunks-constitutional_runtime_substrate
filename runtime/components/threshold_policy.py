"""
ThresholdPolicy — the wired insertion point for history-conditioned geometry,
and the type-level encoding of the three-tier admissibility distinction.

WHY THIS EXISTS (fossilisation audit, precondition #5):
Thresholds are passed INTO the gate, not hardcoded. That made history-conditioned
admissibility POSSIBLE. ThresholdPolicy makes it WIRED: thresholds can now be
resolved through a policy that may (later) depend on the trajectory. No threshold
actually depends on history yet — the CAPABILITY is built and tested, the
geometry tier is gated.

THE THREE TIERS (encoded as types, so the distinction is structural, not
marketing — a caller literally cannot present a Tier-1 profile as a Tier-3
surface, because the Tier-3 type refuses to construct):

  Tier 1  StaticPolicy
          A configured GateThresholds bundle. Ignores trajectory. Always
          available. This is the "admissibility profile" — what a self-service
          builder can export TODAY. It is a PROFILE, not a kernel.

  Tier 2  TrajectoryTestedPolicy
          A static policy PLUS recorded evidence that it was tested against
          replay / recoverability / regime-stress conditions. Still resolves to
          static thresholds — the evidence is what distinguishes "configured"
          from "validated." This is the "recoverability-tested profile."

  Tier 3  GeometryDerivedPolicy
          Thresholds DERIVED from trajectory geometry (the admissible region's
          structure conditioning the bounds). This is where history would
          actually alter admissible geometry. It REQUIRES K2 (a coherence
          relation -> a real region). Until K2, this type exists (the insertion
          point is wired) but CANNOT be instantiated — construction raises.
          The capability is gated at the type level, not by discipline.

PRODUCT NOTE: "kernel" is the Tier-3/Tier-4 word. Tiers 1-2 export a PROFILE.
Selling "kernel" at Tier 1 is configuration dressed as constitution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable, TYPE_CHECKING

from .gate import GateThresholds

if TYPE_CHECKING:
    from .trajectory import Trajectory


COMPONENT_VERSION = "0.1.0"


@runtime_checkable
class ThresholdPolicy(Protocol):
    """
    A policy that resolves the thresholds to use for a gate evaluation.

    resolve() may consult the trajectory (Tier 3) or ignore it (Tiers 1-2).
    The gate calls resolve() to obtain a GateThresholds; this is the single
    insertion point through which history could condition admissibility.
    """
    tier: int

    def resolve(self, trajectory: "Optional[Trajectory]") -> GateThresholds:
        ...


@dataclass(frozen=True)
class StaticPolicy:
    """
    Tier 1: a configured threshold bundle. Ignores the trajectory.

    This is today's behaviour, now named. It is the admissibility PROFILE a
    self-service builder can configure and export now.
    """
    thresholds: GateThresholds
    tier: int = 1

    def resolve(self, trajectory: "Optional[Trajectory]") -> GateThresholds:
        # Tier 1 ignores history entirely.
        return self.thresholds


@dataclass(frozen=True)
class RecoverabilityEvidence:
    """
    Recorded evidence that a policy was tested against trajectory conditions.

    This is deliberately minimal: it records THAT testing happened and its
    headline result, not a full report. The presence of this evidence is what
    promotes a Tier-1 profile to Tier-2.
    """
    replay_status: str          # e.g. "passed" | "diverged"
    recoverable: bool           # did recovery remain within bound across the test?
    tested_trajectory_hash: str # lineage hash of the trajectory tested against
    notes: str = ""


@dataclass(frozen=True)
class TrajectoryTestedPolicy:
    """
    Tier 2: a static policy plus evidence it was tested against trajectory /
    replay / recoverability conditions.

    Still resolves to static thresholds — history does NOT yet condition the
    verdict here. The difference from Tier 1 is the EVIDENCE: this profile has
    been validated, not merely configured. That distinction is what a buyer is
    actually paying for.
    """
    thresholds: GateThresholds
    evidence: RecoverabilityEvidence
    tier: int = 2

    def resolve(self, trajectory: "Optional[Trajectory]") -> GateThresholds:
        # Tier 2 still resolves to static thresholds. The evidence rides
        # alongside; it does not (yet) change the resolved thresholds.
        return self.thresholds


class GeometryDerivedPolicy:
    """
    Tier 3: thresholds DERIVED from trajectory geometry.

    This is where traversal history would actually alter the admissible
    geometry. It requires K2 (a coherence relation defining a region with
    internal structure). Until K2 exists, this type is present — the insertion
    point is wired — but it CANNOT be instantiated.

    The gating is at the TYPE LEVEL: construction raises. A self-service builder
    cannot export a geometry-backed surface because the object that would
    represent one refuses to exist yet. This is how the three-tier honesty is
    enforced in the kernel rather than in marketing copy.
    """
    tier = 3

    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "GeometryDerivedPolicy (Tier 3) requires K2 (a coherence relation "
            "defining an admissible region with internal structure). No geometry "
            "exists yet — the admissible region is a box, not a manifold. This "
            "type is the wired insertion point; it is intentionally "
            "uninstantiable until K2 lands. Use StaticPolicy or "
            "TrajectoryTestedPolicy."
        )

    def resolve(self, trajectory: "Optional[Trajectory]") -> GateThresholds:
        raise NotImplementedError("GeometryDerivedPolicy requires K2.")


def resolve_thresholds(
    policy_or_thresholds: "ThresholdPolicy | GateThresholds",
    trajectory: "Optional[Trajectory]" = None,
) -> GateThresholds:
    """
    Resolve thresholds from either a policy or a bare GateThresholds.

    Backward-compatible: a bare GateThresholds (today's call style) is treated
    as an implicit StaticPolicy. A policy is resolved against the trajectory.

    This is the function the gate (or its caller) uses to obtain thresholds,
    so the policy mechanism is a strict superset of the static path.
    """
    if isinstance(policy_or_thresholds, GateThresholds):
        return policy_or_thresholds
    return policy_or_thresholds.resolve(trajectory)
