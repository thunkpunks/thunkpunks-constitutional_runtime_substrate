"""
Tests for core/authority.py.

Authority enforcement is constitutional. Any undeclared write is a violation,
not a warning.
"""
import pytest

from runtime.core.types import PayloadType
from runtime.core.authority import (
    AUTHORITY_MAP,
    check_read_authority,
    check_write_authority,
    AuthorityViolation,
)


class TestWriteAuthority:
    """Write authority is checked, not trusted."""

    def test_declared_write_passes(self):
        # algebraic_gate is declared to write GATE_OUTCOME
        check_write_authority("algebraic_gate", PayloadType.GATE_OUTCOME)  # no raise

    def test_undeclared_write_raises(self):
        # algebraic_gate writes only GATE_OUTCOME; cannot write FIELD_STATE
        with pytest.raises(AuthorityViolation, match="not authorized to write"):
            check_write_authority("algebraic_gate", PayloadType.FIELD_STATE)

    def test_forbidden_write_raises(self):
        # algebraic_gate is explicitly forbidden from writing DIAGNOSTIC
        with pytest.raises(AuthorityViolation, match="explicitly forbidden"):
            check_write_authority("algebraic_gate", PayloadType.DIAGNOSTIC)

    def test_unknown_component_raises(self):
        with pytest.raises(AuthorityViolation, match="no declared authority"):
            check_write_authority("unregistered_skill", PayloadType.FIELD_STATE)

    def test_diagnostics_cannot_modify_state(self):
        """Diagnostics module is constitutionally report-only."""
        with pytest.raises(AuthorityViolation, match="explicitly forbidden"):
            check_write_authority("diagnostics", PayloadType.FIELD_STATE)
        with pytest.raises(AuthorityViolation, match="explicitly forbidden"):
            check_write_authority("diagnostics", PayloadType.GATE_OUTCOME)

    def test_diagnostics_can_write_diagnostics(self):
        check_write_authority("diagnostics", PayloadType.DIAGNOSTIC)


class TestReadAuthority:
    """Read authority constrains what components may consume."""

    def test_declared_read_passes(self):
        check_read_authority("algebraic_gate", PayloadType.FIELD_STATE)

    def test_undeclared_read_raises(self):
        # field_projection reads SCENARIO and SCENARIO_VALIDATION, not GATE_OUTCOME
        with pytest.raises(AuthorityViolation, match="not authorized to read"):
            check_read_authority("field_projection", PayloadType.GATE_OUTCOME)


class TestAuthorityMapCompleteness:
    """Every component in the map declares its full authority surface."""

    def test_all_components_registered(self):
        # These are the components specified in handoff four's authority map.
        required = {
            "scenario_synthesis",
            "scenario_validator",
            "field_projection",
            "transformation_candidate",
            "algebraic_gate",
            "reshape_operator",
            "surface_assignment",
            "hbtl",
            "diagnostics",
        }
        assert required.issubset(AUTHORITY_MAP.keys())

    def test_no_component_reads_nothing_and_writes_nothing(self):
        """A component with no reads and no writes serves no constitutional role."""
        for cid, auth in AUTHORITY_MAP.items():
            assert auth.reads or auth.writes, (
                f"Component '{cid}' declares no reads and no writes; "
                f"it has no constitutional role."
            )
