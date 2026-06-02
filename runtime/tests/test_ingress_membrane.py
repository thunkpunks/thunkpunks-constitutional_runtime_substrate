"""
Ingress membrane tests — REFUSAL FIRST.

The membrane's defining property is refusal. These tests lead with the
adversarial payloads it must refuse, then confirm clean observations are
admitted, then prove the critical separation (no shadow kernel).

Adversarial set (as specified):
- verdict fields / values
- authority fields (top-level and NESTED)
- fabricated confidence
- silent (undisclosed) compression
- missing / dishonest coordinate honesty
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_ING = Path(__file__).resolve().parent.parent / "layers" / "ingress-layer" / "ingress" / "ingress_membrane.py"
_spec = importlib.util.spec_from_file_location("ingress_membrane", _ING)
m = importlib.util.module_from_spec(_spec)
sys.modules["ingress_membrane"] = m
_spec.loader.exec_module(m)

admit = m.admit
try_admit = m.try_admit
AdmissionRefusal = m.AdmissionRefusal
RefusalReason = m.RefusalReason
COORDINATES = m.COORDINATES


def _clean(**overrides):
    """A clean, admissible observation."""
    coords = {n: {"populated": True, "value": 0.5, "confidence": 1.0} for n in COORDINATES}
    obs = {
        "coordinates": coords,
        "provenance": {"source": "bench-adapter", "modality": "symbolic"},
    }
    obs.update(overrides)
    return obs


# ---------------------------------------------------------------------------
# REFUSAL FIRST — the membrane must say no.
# ---------------------------------------------------------------------------

class TestRefusesAuthority:
    def test_refuses_top_level_authority_field(self):
        bad = _clean(); bad["authority"] = "admin"
        with pytest.raises(AdmissionRefusal, match="authority_field"):
            admit(bad)

    def test_refuses_nested_authority_field(self):
        # Authority hiding inside a sub-object must be caught recursively.
        bad = _clean()
        bad["coordinates"]["Omega"]["authority"] = "root"
        with pytest.raises(AdmissionRefusal, match="authority_field"):
            admit(bad)

    def test_refuses_deeply_nested_authority(self):
        bad = _clean()
        bad["provenance"]["meta"] = {"chain": [{"authority": "x"}]}
        with pytest.raises(AdmissionRefusal, match="authority_field"):
            admit(bad)

    def test_refuses_outcome_field(self):
        bad = _clean(); bad["outcome"] = "EXECUTE"
        with pytest.raises(AdmissionRefusal):
            admit(bad)


class TestRefusesVerdicts:
    def test_refuses_verdict_value_anywhere(self):
        bad = _clean()
        bad["coordinates"]["tau"]["note"] = "REJECT"  # verdict string as data
        with pytest.raises(AdmissionRefusal, match="verdict"):
            admit(bad)

    def test_refuses_nested_verdict_in_list(self):
        bad = _clean()
        bad["provenance"]["history"] = ["ok", "DEFER"]
        with pytest.raises(AdmissionRefusal, match="verdict"):
            admit(bad)


class TestRefusesFabricatedConfidence:
    def test_refuses_confidence_above_one(self):
        bad = _clean()
        bad["coordinates"]["Omega"] = {"populated": True, "value": 0.5, "confidence": 1.5}
        with pytest.raises(AdmissionRefusal, match="fabricated_confidence"):
            admit(bad)

    def test_refuses_confidence_zero_on_populated(self):
        bad = _clean()
        bad["coordinates"]["Omega"] = {"populated": True, "value": 0.5, "confidence": 0.0}
        with pytest.raises(AdmissionRefusal, match="fabricated_confidence"):
            admit(bad)

    def test_refuses_non_numeric_confidence(self):
        bad = _clean()
        bad["coordinates"]["Omega"] = {"populated": True, "value": 0.5, "confidence": "high"}
        with pytest.raises(AdmissionRefusal, match="fabricated_confidence"):
            admit(bad)


class TestRefusesSilentCompression:
    def test_refuses_undisclosed_compression(self):
        bad = _clean()
        bad["coordinates"]["NSV"] = {"populated": True, "value": 0.3, "confidence": 1.0, "compressed": True}
        # compression present but not disclosed -> refused
        with pytest.raises(AdmissionRefusal, match="compression"):
            admit(bad)

    def test_admits_disclosed_compression(self):
        ok = _clean(compression_disclosed=True, compression_note="9 raw signals -> NSV")
        ok["coordinates"]["NSV"] = {"populated": True, "value": 0.3, "confidence": 1.0, "compressed": True}
        admitted = admit(ok)
        assert admitted.compression_disclosed is True
        assert admitted.compression_note is not None


class TestRefusesDishonestCoordinates:
    def test_refuses_unpopulated_with_value(self):
        bad = _clean()
        bad["coordinates"]["kappa"] = {"populated": False, "value": 0.0, "confidence": 0.0}
        with pytest.raises(AdmissionRefusal, match="dishonest_coordinate"):
            admit(bad)

    def test_refuses_populated_without_value(self):
        bad = _clean()
        bad["coordinates"]["kappa"] = {"populated": True, "value": None, "confidence": 1.0}
        with pytest.raises(AdmissionRefusal, match="dishonest_coordinate"):
            admit(bad)

    def test_missing_coordinate_is_honest_blank_not_refusal(self):
        # An ABSENT coordinate is an honest unpopulated blank, admitted as such.
        ok = _clean()
        del ok["coordinates"]["NSV"]
        admitted = admit(ok)
        assert admitted.coordinates["NSV"]["populated"] is False
        assert admitted.coordinates["NSV"]["value"] is None


class TestMalformed:
    def test_refuses_non_dict(self):
        with pytest.raises(AdmissionRefusal):
            admit("not an observation")

    def test_refuses_missing_provenance(self):
        bad = {"coordinates": {n: {"populated": True, "value": 0.5, "confidence": 1.0} for n in COORDINATES}}
        with pytest.raises(AdmissionRefusal):
            admit(bad)


# ---------------------------------------------------------------------------
# ADMISSION — only clean observations cross.
# ---------------------------------------------------------------------------

class TestAdmitsClean:
    def test_clean_observation_admitted(self):
        admitted = admit(_clean())
        assert set(admitted.coordinates.keys()) == set(COORDINATES)
        assert all(admitted.coordinates[n]["populated"] for n in COORDINATES)

    def test_provenance_recorded_as_claim_not_truth(self):
        admitted = admit(_clean())
        d = admitted.provenance.to_dict()
        assert d["source_claimed"] == "bench-adapter"
        assert d["asserted_true"] is False        # memory != truth, at the boundary

    def test_authority_stripped_shape_is_canonical(self):
        # Admitted observation carries only canonical coordinate fields.
        admitted = admit(_clean())
        for n in COORDINATES:
            assert set(admitted.coordinates[n].keys()) == {"populated", "value", "confidence"}

    def test_try_admit_returns_value_on_refusal(self):
        bad = _clean(); bad["authority"] = "x"
        admitted, reason = try_admit(bad)
        assert admitted is None
        assert "authority" in reason


# ---------------------------------------------------------------------------
# NO SHADOW KERNEL — the critical separation.
# ---------------------------------------------------------------------------

class TestNoShadowKernel:
    def test_membrane_does_not_import_kernel(self):
        tree = ast.parse(_ING.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    imported.append(node.module)
                imported.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.extend(a.name for a in node.names)
        joined = " ".join(imported)
        for forbidden in ["gate", "constitution", "coherence", "horizon",
                          "evaluate", "GateOutcome", "GateInput", "FieldState"]:
            assert forbidden not in joined, f"membrane imports kernel: {forbidden}"

    def test_membrane_imports_only_stdlib(self):
        tree = ast.parse(_ING.read_text())
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                modules.extend(a.name.split(".")[0] for a in node.names)
        stdlib = {"dataclasses", "enum", "typing", "__future__"}
        for mod in modules:
            assert mod in stdlib, f"membrane has non-stdlib import: {mod}"

    def test_membrane_defines_no_evaluate(self):
        tree = ast.parse(_ING.read_text())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" not in funcs

    def test_membrane_judges_state_not_action(self):
        # The membrane admits an observation REGARDLESS of what the kernel would
        # later decide about a transformation. It never applies gate grounds
        # (tau/coherence/horizon). A high-tau coordinate is still admitted as
        # STATE — refusal is only for malformed/authority-bearing input.
        high_tau = _clean()
        high_tau["coordinates"]["tau"] = {"populated": True, "value": 0.99, "confidence": 1.0}
        admitted = admit(high_tau)            # admitted as state
        assert admitted.coordinates["tau"]["value"] == 0.99
        # The membrane has no verdict to give; admission is not an EXECUTE.
