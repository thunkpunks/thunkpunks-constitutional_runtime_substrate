# Doctrine: Layer Boundary Discipline

## The invariant

**Build the boundary before the layer.**

When the architecture declares a new layer or a new separation between layers,
the enforcement that protects the boundary is implemented *before* the layer is
populated with modules — not after.

## Why

A boundary drawn after a layer fills is a boundary already violated. By the time
a layer has several modules, any cross-boundary leak among them has already
shipped, and enforcement becomes an audit of existing code rather than a
guarantee about future code.

Enforcing a boundary while the protected layer is still empty (or a single file)
costs almost nothing and converts the separation from a discipline anyone can
forget into a structural fact the build checks on every change.

## How it is realised here

`architecture/layer_map.py` declares forbidden import edges for ALL layers,
including layers that have no modules yet (Domain, Pedagogy, Symbolic). The
analyzer (`architecture/import_boundary.py`) enforces every edge. So the moment
a `domain/` module is added, the rule "domain may not redefine constitutional
invariants" is already enforced — the boundary preceded the layer.

This is the opposite of folder-first growth. The constraint exists before the
contents. A new layer does not get to define its own boundaries after the fact;
it inherits boundaries already declared and enforced.

## Consequence for how we build

The build order follows the substrate, not the excitement:

  boundary enforcement
  -> event log (append-only evidential trace)
  -> lineage
  -> receipts
  -> replay strengthening
  -> state projection
  -> only then domain / witness / pedagogy layers

Capabilities come later. The evidence substrate and the boundaries that protect
it come first. A capability layer is permitted only once the substrate it
depends on exists and the boundary that contains it is enforced.

## Status

BINDING as doctrine. The executable half (the import boundary enforcement) is
IMPLEMENTED and tested (see `architecture/README.md`). The doctrinal half (this
rule, applied to future layer declarations) is recorded here and in
`GOVERNING_DISCIPLINE.md` and `CONSTRAINT_REGISTER.md` (C15).
