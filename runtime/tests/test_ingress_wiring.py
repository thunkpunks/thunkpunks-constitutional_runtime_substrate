"""
Synthetic ingress wiring tests.

- admitted observation reaches replay-valid circuit
- refused observation never reaches substrate
- replay reconstructs identical projection
- membrane boundary intact / no shadow kernel
"""
import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_ING = Path(__file__).resolve().parent.parent / "layers" / "ingress-layer" / "ingress"
_LAYERS = Path(__file__).resolve().parent.parent / "layers" / "runtime-layer"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


membrane = _load("ingress_membrane", _ING / "ingress_membrane.py")
event_log_mod = _load("event_log", _LAYERS / "event-log/event_log.py")
sp_mod = _load("state_projection", _LAYERS / "state-projection/state_projection.py")
wiring = _load("ingress_wiring", _ING / "ingress_wiring.py")

COORDINATES = membrane.COORDINATES
_WIRING_PATH = _ING / "ingress_wiring.py"


def _clean(**ov):
    obs = {
        "coordinates": {n: {"populated": True, "value": 0.5, "confidence": 1.0} for n in COORDINATES},
        "provenance": {"source": "synthetic-fixture", "modality": "symbolic"},
    }
    obs.update(ov)
    return obs


def _wire(obs):
    return wiring.wire_observation(
        obs, logical_step=0, min_confidence=0.5,
        membrane_module=membrane, event_log=event_log_mod.EventLog(),
        state_projection_module=sp_mod,
    )


class TestAdmittedReachesCircuit:
    def test_admitted_reaches_replay_valid_circuit(self):
        r = _wire(_clean())
        assert r.admitted is True
        assert r.reached_substrate is True
        assert r.projection_status == "READY"
        assert r.replay_ok is True

    def test_admitted_with_hold_still_replay_valid(self):
        obs = _clean()
        del obs["coordinates"]["NSV"]   # honest blank -> projection holds
        r = _wire(obs)
        assert r.admitted is True
        assert r.projection_status == "MEASUREMENT_HOLD"
        assert r.replay_ok is True


class TestRefusedNeverReachesSubstrate:
    def test_authority_refused_no_substrate(self):
        bad = _clean(); bad["authority"] = "root"
        log = event_log_mod.EventLog()
        r = wiring.wire_observation(
            bad, logical_step=0, min_confidence=0.5,
            membrane_module=membrane, event_log=log, state_projection_module=sp_mod,
        )
        assert r.admitted is False
        assert r.reached_substrate is False
        assert len(log) == 0          # substrate untouched

    def test_verdict_refused_no_substrate(self):
        bad = _clean(); bad["coordinates"]["tau"]["note"] = "REJECT"
        log = event_log_mod.EventLog()
        r = wiring.wire_observation(
            bad, logical_step=0, min_confidence=0.5,
            membrane_module=membrane, event_log=log, state_projection_module=sp_mod,
        )
        assert r.admitted is False
        assert len(log) == 0


class TestReplayIdentical:
    def test_replay_reconstructs_identical_projection(self):
        # Two independent wirings of the same obs -> same projection status.
        r1 = _wire(_clean())
        r2 = _wire(_clean())
        assert r1.projection_status == r2.projection_status
        assert r1.replay_ok and r2.replay_ok


class TestNoShadowKernel:
    def test_wiring_does_not_import_kernel(self):
        tree = ast.parse(_WIRING_PATH.read_text())
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    names.append(node.module)
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
        joined = " ".join(names)
        for forbidden in ["gate", "constitution", "coherence", "horizon",
                          "evaluate", "GateOutcome", "receipts", "lineage"]:
            assert forbidden not in joined, f"wiring imports {forbidden}"

    def test_wiring_defines_no_evaluate(self):
        tree = ast.parse(_WIRING_PATH.read_text())
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        assert "evaluate" not in funcs
