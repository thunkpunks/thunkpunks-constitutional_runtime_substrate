"""
Import boundary analyzer — the executable enforcement of layer separation.

Parses each module's imports (via the AST, not regex) and checks every
cross-layer edge against FORBIDDEN_EDGES. Adds no capability; it only refuses
dependency edges the architecture has declared illegal.

Usage:
  analyze_repo(components_dir, core_dir) -> list[Violation]
  An empty list means the dependency graph respects every declared boundary.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .layer_map import (
    Layer, layer_of, is_forbidden, MODULE_LAYER, is_declared_exception,
)


@dataclass(frozen=True)
class Violation:
    importer_module: str
    importer_layer: str
    imported_module: str
    imported_layer: str
    detail: str


@dataclass(frozen=True)
class UnclassifiedModule:
    module: str
    path: str


def _imported_stems(source: str) -> list[str]:
    """
    Extract the imported module stems from a source file's AST.

    Handles `from .gate import X` (stem 'gate'), `from ..core.types import Y`
    (stem 'types'), and `from .coherence import Z` (stem 'coherence'). We take
    the LAST dotted component of the module path as the stem, which matches the
    file-stem keys in MODULE_LAYER.

    Imports guarded by `if TYPE_CHECKING:` are SKIPPED: they are annotation-only
    and create no runtime dependency edge. A type annotation cannot carry
    behaviour or authority across a layer boundary, so it is not a boundary
    violation. (This is why the gate can annotate a Trajectory without depending
    on the runtime trajectory module at runtime.)
    """
    stems: list[str] = []
    tree = ast.parse(source)

    # Collect line ranges of `if TYPE_CHECKING:` blocks to exclude.
    type_checking_ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
                or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_tc:
                start = node.lineno
                end = max(
                    (n.end_lineno or n.lineno) for n in ast.walk(node)
                    if hasattr(n, "lineno")
                )
                type_checking_ranges.append((start, end))

    def in_type_checking(lineno: int) -> bool:
        return any(start <= lineno <= end for start, end in type_checking_ranges)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if in_type_checking(node.lineno):
                continue
            if node.module is None:
                for alias in node.names:
                    stems.append(alias.name.split(".")[-1])
            else:
                stems.append(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            if in_type_checking(node.lineno):
                continue
            for alias in node.names:
                stems.append(alias.name.split(".")[-1])
    return stems


def analyze_file(path: Path) -> tuple[list[Violation], list[UnclassifiedModule]]:
    """Analyze a single module file for boundary violations."""
    module_stem = path.stem
    importer_layer = layer_of(module_stem)

    violations: list[Violation] = []
    unclassified: list[UnclassifiedModule] = []

    if importer_layer is None:
        unclassified.append(UnclassifiedModule(module=module_stem, path=str(path)))
        return violations, unclassified

    source = path.read_text()
    for imported_stem in _imported_stems(source):
        imported_layer = layer_of(imported_stem)
        if imported_layer is None:
            # Imported thing isn't a classified repo module (stdlib, third-party,
            # or a within-module name). Not a cross-layer edge; skip.
            continue
        if is_forbidden(importer_layer, imported_layer):
            if is_declared_exception(module_stem, imported_stem):
                # Documented shared-type edge — not a true cross-layer dependency.
                continue
            violations.append(Violation(
                importer_module=module_stem,
                importer_layer=importer_layer.value,
                imported_module=imported_stem,
                imported_layer=imported_layer.value,
                detail=(
                    f"{importer_layer.value} module '{module_stem}' may not import "
                    f"{imported_layer.value} module '{imported_stem}' — forbidden "
                    f"cross-layer edge ({importer_layer.value} -> {imported_layer.value})."
                ),
            ))
    return violations, unclassified


def analyze_dirs(dirs: list[Path]) -> tuple[list[Violation], list[UnclassifiedModule]]:
    """Analyze all .py modules under the given directories."""
    all_violations: list[Violation] = []
    all_unclassified: list[UnclassifiedModule] = []
    for d in dirs:
        for path in sorted(d.glob("*.py")):
            if path.stem == "__init__":
                continue
            v, u = analyze_file(path)
            all_violations.extend(v)
            all_unclassified.extend(u)
    return all_violations, all_unclassified
