"""
Counterfactual mode.

Constitutional invariant: counterfactual evaluations must never write through
the router, never advance session state, never append to the ledger.

ARCHITECTURAL DECISION — where the mode lives:

The gate's `evaluate` is already a pure function. It computes a verdict with no
side effects; it cannot write anything regardless of mode. So putting a mode
flag on the gate's evaluation would be decorative — the gate never writes either
way.

The side effects that matter happen AFTER evaluation: advancing the session,
appending to the ledger, emitting through the router. That is where
"counterfactual never writes" actually bites.

Therefore the mode lives at the COMMIT BOUNDARY, not on the pure gate. This
module provides an EvaluationContext that carries the mode and makes the
never-writes invariant STRUCTURAL rather than disciplinary:

- In AUTHORITATIVE mode, the context yields a CommitToken that the caller uses
  to advance session / append to ledger.
- In COUNTERFACTUAL mode, no CommitToken is issued. Attempting to obtain one
  raises CounterfactualWriteAttempt. The invariant is enforced by the type of
  thing the context produces, not by the caller remembering to check a flag.

This keeps the pure gate pure (it stays untouched and tested), and locates the
constitutional invariant exactly where writes occur.

Relationship to replay_live: replay_live already has a read-only what-if quality
(it re-evaluates without touching the original ledger). Counterfactual mode
generalizes that to the live decision path: you can evaluate a hypothetical
transformation against current state and inspect the verdict WITHOUT any
possibility of it leaking into authoritative state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..core.types import FieldState, Transformation, GateOutcome
from ..core.bench_interface import SessionState
from .gate import GateInput, GateOutput, GateThresholds, evaluate


COMPONENT_VERSION = "0.1.0"


class EvaluationMode(str, Enum):
    """
    AUTHORITATIVE: the single decision-binding path. Results may be committed.
    COUNTERFACTUAL: hypothetical evaluation. Results may NEVER be committed.
    """
    AUTHORITATIVE = "authoritative"
    COUNTERFACTUAL = "counterfactual"


class CounterfactualWriteAttempt(Exception):
    """
    Raised when code attempts to obtain a commit capability from a
    counterfactual evaluation. This is a constitutional violation: a
    hypothetical that tried to become real.
    """


@dataclass(frozen=True)
class CommitToken:
    """
    A capability object proving an evaluation was AUTHORITATIVE and may be
    committed. The session-advance and ledger-append paths require one of these.

    Counterfactual evaluations never produce a CommitToken. Code paths that
    write (advance session, append to ledger) take a CommitToken as a required
    argument, so it is structurally impossible to commit a counterfactual
    result: there is no token to pass.
    """
    mode: EvaluationMode
    gate_output: GateOutput

    def __post_init__(self) -> None:
        # A CommitToken can only exist for an authoritative evaluation.
        # This guards against constructing one by hand around the boundary.
        if self.mode is not EvaluationMode.AUTHORITATIVE:
            raise CounterfactualWriteAttempt(
                "CommitToken can only be created for AUTHORITATIVE evaluations. "
                "A counterfactual evaluation must never produce a commit capability."
            )


@dataclass(frozen=True)
class EvaluationResult:
    """
    Result of an evaluation through the counterfactual-aware boundary.

    Always carries the gate output (the verdict, available in both modes —
    you can always SEE the verdict). The commit_token is present ONLY in
    authoritative mode. In counterfactual mode it is None, and the
    `commit_token()` accessor raises rather than returning None, so that a
    caller cannot accidentally treat a counterfactual as committable.
    """
    mode: EvaluationMode
    gate_output: GateOutput
    _commit_token: Optional[CommitToken] = None

    def commit_token(self) -> CommitToken:
        """
        Return the commit capability. Raises in counterfactual mode.

        This is the structural enforcement point: a caller that wants to write
        MUST call this, and in counterfactual mode it raises rather than
        returning a usable token.
        """
        if self.mode is EvaluationMode.COUNTERFACTUAL or self._commit_token is None:
            raise CounterfactualWriteAttempt(
                "Cannot obtain a commit token from a counterfactual evaluation. "
                "Counterfactual results may be inspected but never committed."
            )
        return self._commit_token

    @property
    def is_committable(self) -> bool:
        """True iff this result may be committed (authoritative mode)."""
        return self.mode is EvaluationMode.AUTHORITATIVE and self._commit_token is not None

    @property
    def outcome(self) -> GateOutcome:
        """The verdict — always available, both modes."""
        return self.gate_output.outcome

    @property
    def predicted_state(self) -> FieldState:
        """The predicted S(t+1) — always available, both modes."""
        return self.gate_output.predicted_state


def evaluate_with_mode(
    gate_input: GateInput,
    mode: EvaluationMode,
) -> EvaluationResult:
    """
    Evaluate a transformation through the counterfactual-aware boundary.

    The verdict is computed identically in both modes (the gate is pure;
    a hypothetical and a real evaluation of the same inputs MUST agree —
    that is what makes counterfactual analysis trustworthy).

    The difference is purely in committability:
      - AUTHORITATIVE -> result carries a CommitToken; may be committed.
      - COUNTERFACTUAL -> result carries no token; commit_token() raises.
    """
    gate_output = evaluate(gate_input)

    if mode is EvaluationMode.AUTHORITATIVE:
        token = CommitToken(mode=mode, gate_output=gate_output)
        return EvaluationResult(mode=mode, gate_output=gate_output, _commit_token=token)
    else:
        return EvaluationResult(mode=mode, gate_output=gate_output, _commit_token=None)


def counterfactual_compare(
    current_state: FieldState,
    transformation: Transformation,
    threshold_variants: dict[str, GateThresholds],
) -> dict[str, GateOutcome]:
    """
    Convenience: evaluate the same transformation against multiple threshold
    regimes, counterfactually, and return the outcome under each.

    This is the "what would have happened under a different policy" primitive,
    applied at the single-decision level (the trajectory-level version lives in
    replay_live). None of these evaluations can be committed — they are all
    counterfactual by construction.
    """
    results: dict[str, GateOutcome] = {}
    for label, thresholds in threshold_variants.items():
        gi = GateInput(
            current_state=current_state,
            transformation=transformation,
            thresholds=thresholds,
        )
        res = evaluate_with_mode(gi, EvaluationMode.COUNTERFACTUAL)
        results[label] = res.outcome
    return results
