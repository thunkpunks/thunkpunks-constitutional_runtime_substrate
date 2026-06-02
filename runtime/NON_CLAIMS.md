# NON_CLAIMS

**Snapshot:** 496 tests passing, `runtime/` tree. Items below may move from
non-claim to claim as the build advances; check `BUILD_LEDGER.md` for current
state.

What this repository does **not** claim. Read first.

The repository demonstrates five behaviours (HOLD, REFUSE, RECEIPT, REPLAY,
LINEAGE) with tests. It claims nothing beyond what those tests verify.

## Explicit non-claims

- **No execution sovereignty.** The runtime decides admissibility; it does not
  command, schedule, or coordinate external actions.
- **No workflow governance.** The repository is not a workflow engine and does
  not govern external workflows.
- **No constitutional geometry.** No geometric, topological, or differential
  claims about the state space. Field-state coordinates have ranges and
  monotonicity rules; that is the entire substantive claim.
- **No admissibility topology.** No claim that admissibility forms a topology,
  manifold, or other structured space.
- **No transformation topology.** Transformations compose via a bounded
  primitive. No claim about the structure of composed-transformation spaces
  beyond ancestry and integrity.
- **No governance-of-governance.** The constitution is not editable from
  inside the runtime. No protocol exists for constitutional revision.
- **No certification authority.** Receipts are tamper-evident records of what
  the kernel decided. They are not certifications recognised by any external
  body.
- **No operational authority.** The runtime is a substrate for demonstrating
  admissibility patterns. It is not deployed and carries no operational
  decisions.
- **No production enforcement.** Nothing in this repository enforces anything
  in production systems.
- **No agent framework.** Nothing here is an agent. Claude (the AI used in
  builds) is non-sovereign and decides nothing.
- **No external verification.** Receipts verify against themselves and the
  internal event-log chain. No independent external verifier exists yet.
- **No real-source ingress.** Ingress accepts synthetic canonical observations
  only. No vendor integration, no streaming.
- **No drift detection that acts.** Observability detects divergence between
  recorded outcomes. It never decides what should happen as a result.
- **No emergence claims.** Nothing in this repository is claimed to emerge,
  self-organise, or exceed the behaviours its tests verify.
- **No AGI relevance claim.** The repository is a constitutional runtime
  substrate. It is not positioned as a path to general intelligence.

## What is recorded but not built

Orientations and pressure tests appear in the build ledger under
`recorded-not-built`. Items there are explicitly **not claims**. They are
recorded so the repository does not rediscover them, not because the repository
demonstrates them.

If a property is not listed in `BUILD_LEDGER.md` under built or experimentally
bounded, it is not claimed.

## Falsifiability

The five behaviours fail closed:

- HOLD fails if an incomplete observation reaches the gate.
- REFUSE fails if an authority-bearing input enters the substrate.
- RECEIPT fails if a tampered receipt verifies.
- REPLAY fails if a tampered event reconstructs.
- LINEAGE fails if a corrupted ancestry reconstructs.

Each is a test in the repository. Run them.

## How to file a non-claim violation

If the repository (in documentation, code, or commit message) claims something
not present in `BUILD_LEDGER.md` under built or experimentally bounded, that is
a non-claim violation. Open an issue with the line and the missing footing.
