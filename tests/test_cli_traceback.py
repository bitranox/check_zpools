"""Tests for traceback management utilities.

This module validates:
- apply_traceback_preferences sets both traceback flags correctly
- snapshot_traceback_state captures current state as a tuple
- restore_traceback_state reapplies a previously captured state
- get_traceback_limit returns correct limits based on enabled flag

All tests use the isolated_traceback_config fixture to prevent
state leakage between tests.
"""

from __future__ import annotations

import lib_cli_exit_tools
import pytest

from check_zpools.cli_traceback import (
    TRACEBACK_SUMMARY_LIMIT,
    TRACEBACK_VERBOSE_LIMIT,
    apply_traceback_preferences,
    get_traceback_limit,
    restore_traceback_state,
    snapshot_traceback_state,
)


# ============================================================================
# Tests: apply_traceback_preferences
# ============================================================================


class TestApplyTracebackPreferencesEnablesBothFlags:
    """apply_traceback_preferences synchronizes traceback and color flags."""

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_enabling_sets_both_flags_to_true(self) -> None:
        """When enabled=True, both traceback and force_color are set."""
        apply_traceback_preferences(enabled=True)

        assert bool(lib_cli_exit_tools.config.traceback) is True
        assert bool(lib_cli_exit_tools.config.traceback_force_color) is True

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_disabling_sets_both_flags_to_false(self) -> None:
        """When enabled=False, both traceback and force_color are cleared."""
        apply_traceback_preferences(enabled=True)
        apply_traceback_preferences(enabled=False)

        assert bool(lib_cli_exit_tools.config.traceback) is False
        assert bool(lib_cli_exit_tools.config.traceback_force_color) is False


# ============================================================================
# Tests: snapshot_traceback_state
# ============================================================================


class TestSnapshotTracebackStateCapturesCurrentFlags:
    """snapshot_traceback_state returns a tuple of (traceback, force_color)."""

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_returns_two_element_tuple(self) -> None:
        """The snapshot is always a 2-tuple."""
        state = snapshot_traceback_state()

        assert isinstance(state, tuple)
        assert len(state) == 2

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_captures_disabled_state(self) -> None:
        """When both flags are False, snapshot captures (False, False)."""
        apply_traceback_preferences(enabled=False)

        state = snapshot_traceback_state()

        assert state == (False, False)

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_captures_enabled_state(self) -> None:
        """When both flags are True, snapshot captures (True, True)."""
        apply_traceback_preferences(enabled=True)

        state = snapshot_traceback_state()

        assert state == (True, True)


# ============================================================================
# Tests: restore_traceback_state
# ============================================================================


class TestRestoreTracebackStateReappliesCapturedFlags:
    """restore_traceback_state sets flags back to a previously captured state."""

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_restores_disabled_state_after_enabling(self) -> None:
        """After enabling tracebacks, restoring a disabled snapshot reverts both flags."""
        original = snapshot_traceback_state()
        apply_traceback_preferences(enabled=True)

        restore_traceback_state(original)

        assert bool(lib_cli_exit_tools.config.traceback) is False
        assert bool(lib_cli_exit_tools.config.traceback_force_color) is False

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_restores_enabled_state_after_disabling(self) -> None:
        """After disabling tracebacks, restoring an enabled snapshot reverts both flags."""
        apply_traceback_preferences(enabled=True)
        original = snapshot_traceback_state()
        apply_traceback_preferences(enabled=False)

        restore_traceback_state(original)

        assert bool(lib_cli_exit_tools.config.traceback) is True
        assert bool(lib_cli_exit_tools.config.traceback_force_color) is True


class TestSnapshotAndRestoreRoundTrip:
    """snapshot + restore forms a clean round-trip."""

    @pytest.mark.os_agnostic
    @pytest.mark.usefixtures("isolated_traceback_config")
    def test_round_trip_preserves_original_state(self) -> None:
        """Snapshot before change, modify, restore — state matches original."""
        apply_traceback_preferences(enabled=False)
        before = snapshot_traceback_state()

        apply_traceback_preferences(enabled=True)
        assert snapshot_traceback_state() != before

        restore_traceback_state(before)
        assert snapshot_traceback_state() == before


# ============================================================================
# Tests: get_traceback_limit
# ============================================================================


class TestGetTracebackLimitReturnsCorrectBudget:
    """get_traceback_limit returns the right character budget."""

    @pytest.mark.os_agnostic
    def test_verbose_limit_when_enabled(self) -> None:
        """When tracebacks are enabled, the verbose limit is used."""
        limit = get_traceback_limit(tracebacks_enabled=True)

        assert limit == TRACEBACK_VERBOSE_LIMIT
        assert limit == 10_000

    @pytest.mark.os_agnostic
    def test_summary_limit_when_disabled(self) -> None:
        """When tracebacks are disabled, the summary limit is used."""
        limit = get_traceback_limit(tracebacks_enabled=False)

        assert limit == TRACEBACK_SUMMARY_LIMIT
        assert limit == 500


class TestTracebackConstants:
    """The traceback limit constants have sensible values."""

    @pytest.mark.os_agnostic
    def test_verbose_limit_is_greater_than_summary(self) -> None:
        """The verbose limit should be much larger than the summary limit."""
        assert TRACEBACK_VERBOSE_LIMIT > TRACEBACK_SUMMARY_LIMIT

    @pytest.mark.os_agnostic
    def test_summary_limit_is_positive(self) -> None:
        """Even the summary limit allows some traceback output."""
        assert TRACEBACK_SUMMARY_LIMIT > 0
