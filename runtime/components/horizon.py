"""
K3 — Horizon-Cumulative Admissibility. The last keystone, and the original goal.

This is the Wolfram-irreducibility limit made operational: a sequence of
individually-admissible steps can be COLLECTIVELY inadmissible. Per-step checks
cannot catch death-by-a-thousand-admissible-cuts; only a cumulative budget over
the trajectory can.

THE ARCHITECTURAL SIGNIFICANCE:
  Until K3, the gate was a function of the trajectory that IGNORED it (T2 widened
  the domain; nothing read it). K3 is where the gate actually READS a cumulative
  trajectory quantity and lets it condition the verdict. This is the moment
  history becomes constitutive IN FACT, not just in domain — the crossing from
  "step governance with memory" to "trajectory governance."

PHYSICS vs POLICY (the K1 discipline applied):
  - PHYSICS: that cumulative quantities CAN be inadmissible — the irreducibility
    principle. A bounded resource (irreversible residue, optionality) spent
    across a horizon can be exhausted even if no single step exhausted it. This
    is a law of the state space, not a preference.
  - POLICY: the BUDGET VALUES (how much cumulative NSV, how much cumulative
    Omega-erosion, what peak-tau ceiling). These are configurable, like other
    thresholds. So HorizonBudget is configuration; the principle it enforces is
    constitutional.

BACKWARD COMPATIBILITY (non-negotiable):
  K3 activates ONLY when a trajectory is supplied AND a budget is configured.
  With no trajectory (the default), behaviour is EXACTLY unchanged. The 264
  pre-K3 tests must stay green. K3 is purely additive to the trajectory path.

ROUTING:
  Cumulative exhaustion routes to DEFER, not REJECT. Rationale: a trajectory
  that has spent its horizon budget has not done anything individually
  catastrophic — it has run out of room. DEFER (escalate / HBTL) is the honest
  response: "this trajectory can no longer proceed without review," not "this
  step is forbidden." A configurable severity can escalate to REJECT for
  hard-exhaustion if a domain requires it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, TYPE_CHECKING

from ..core.types import GateReasonCode

if TYPE_CHECKING:
    from .trajectory import Trajectory


COMPONENT_VERSION = "0.1.0"


class HorizonExhaustion(str, Enum):
    """Which cumulative budget a trajectory has exhausted."""
    CUMULATIVE_NSV = "cumulative_nsv_budget_exhausted"
    CUMULATIVE_OMEGA_EROSION = "cumulative_omega_erosion_budget_exhausted"
    PEAK_TAU = "peak_tau_horizon_ceiling_exceeded"


@dataclass(frozen=True)
class HorizonBudget:
    """
    Configurable budgets on cumulative trajectory quantities.

    POLICY, not physics: the values are configurable. The PRINCIPLE that
    exhausting them is inadmissible is constitutional (declared in the
    Constitution as horizon_cumulative_admissibility).

    A None budget means "that dimension is not horizon-bounded" — so a domain
    can opt into only the cumulative checks it needs. All-None = K3 inactive
    (equivalent to no budget), preserving backward compatibility.
    """
    max_cumulative_NSV: Optional[float] = None
    max_cumulative_Omega_erosion: Optional[float] = None
    max_peak_tau: Optional[float] = None

    def is_active(self) -> bool:
        return any(b is not None for b in (
            self.max_cumulative_NSV,
            self.max_cumulative_Omega_erosion,
            self.max_peak_tau,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_cumulative_NSV": self.max_cumulative_NSV,
            "max_cumulative_Omega_erosion": self.max_cumulative_Omega_erosion,
            "max_peak_tau": self.max_peak_tau,
        }


@dataclass(frozen=True)
class HorizonFinding:
    """A cumulative budget exhaustion detected over a trajectory."""
    exhaustion: HorizonExhaustion
    cumulative_value: float
    budget: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "exhaustion": self.exhaustion.value,
            "cumulative_value": self.cumulative_value,
            "budget": self.budget,
            "detail": self.detail,
        }


def check_horizon(
    trajectory: "Optional[Trajectory]",
    budget: Optional[HorizonBudget],
    prospective_NSV_delta: float = 0.0,
    prospective_Omega_erosion: float = 0.0,
    prospective_tau: float = 0.0,
) -> list[HorizonFinding]:
    """
    Check whether a trajectory (plus the prospective step) would exhaust any
    cumulative horizon budget.

    Args:
        trajectory: the history. If None, NO horizon check runs (K3 inactive) —
            backward compatibility.
        budget: the configured budgets. If None or inactive, no check runs.
        prospective_NSV_delta: the committed NSV the current step would add.
        prospective_Omega_erosion: the Omega erosion the current step would add.
        prospective_tau: the tau the current step would reach.

    Returns:
        Findings (empty = within budget). The prospective step is INCLUDED so
        the check is "would committing this step exhaust the budget", not merely
        "has the budget already been exhausted."
    """
    if trajectory is None or budget is None or not budget.is_active():
        return []  # K3 inactive — exactly the pre-K3 behaviour

    findings: list[HorizonFinding] = []

    if budget.max_cumulative_NSV is not None:
        projected = trajectory.cumulative_NSV + max(0.0, prospective_NSV_delta)
        if projected > budget.max_cumulative_NSV:
            findings.append(HorizonFinding(
                exhaustion=HorizonExhaustion.CUMULATIVE_NSV,
                cumulative_value=projected,
                budget=budget.max_cumulative_NSV,
                detail=(
                    f"Cumulative irreversible residue would reach {projected:.3f} "
                    f"(horizon budget {budget.max_cumulative_NSV}). Individually "
                    f"admissible steps have collectively exhausted the residue budget."
                ),
            ))

    if budget.max_cumulative_Omega_erosion is not None:
        projected = trajectory.cumulative_Omega_erosion + max(0.0, prospective_Omega_erosion)
        if projected > budget.max_cumulative_Omega_erosion:
            findings.append(HorizonFinding(
                exhaustion=HorizonExhaustion.CUMULATIVE_OMEGA_EROSION,
                cumulative_value=projected,
                budget=budget.max_cumulative_Omega_erosion,
                detail=(
                    f"Cumulative optionality erosion would reach {projected:.3f} "
                    f"(horizon budget {budget.max_cumulative_Omega_erosion}). The "
                    f"trajectory has eroded too much optionality over the horizon."
                ),
            ))

    if budget.max_peak_tau is not None:
        projected = max(trajectory.peak_tau, prospective_tau)
        if projected > budget.max_peak_tau:
            findings.append(HorizonFinding(
                exhaustion=HorizonExhaustion.PEAK_TAU,
                cumulative_value=projected,
                budget=budget.max_peak_tau,
                detail=(
                    f"Peak commitment depth over the horizon would reach "
                    f"{projected:.3f} (horizon ceiling {budget.max_peak_tau})."
                ),
            ))

    return findings
