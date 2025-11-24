"""Traceback management utilities for CLI commands.

Purpose
-------
Centralize traceback enable/disable state management that was previously
scattered throughout cli.py. This module provides context managers and
utilities for controlling Python's traceback display behavior.

Why
    Extracted from cli.py to follow Single Responsibility Principle.
    Traceback state management is an orthogonal concern from CLI command
    routing and should be independently testable.

Contents
--------
* :func:`apply_traceback_preferences` - synchronize shared traceback flags
* :func:`snapshot_traceback_state` - capture current traceback settings
* :func:`restore_traceback_state` - restore previous traceback settings
* :const:`TracebackState` - type alias for traceback state tuple
"""

from __future__ import annotations

from typing import Final, Tuple

import lib_cli_exit_tools

#: Type alias for traceback state (traceback_enabled, force_color_enabled)
TracebackState = Tuple[bool, bool]

#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500

#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000


def apply_traceback_preferences(enabled: bool) -> None:
    """Synchronise shared traceback flags with the requested preference.

    Why
        ``lib_cli_exit_tools`` inspects global flags to decide whether tracebacks
        should be truncated and whether colour should be forced. Updating both
        attributes together ensures the ``--traceback`` flag behaves the same for
        console scripts and ``python -m`` execution.

    Parameters
    ----------
    enabled:
        ``True`` enables full tracebacks with colour. ``False`` restores the
        compact summary mode.

    Examples
    --------
    >>> apply_traceback_preferences(True)
    >>> bool(lib_cli_exit_tools.config.traceback)
    True
    >>> bool(lib_cli_exit_tools.config.traceback_force_color)
    True
    >>> apply_traceback_preferences(False)
    >>> bool(lib_cli_exit_tools.config.traceback)
    False
    """
    lib_cli_exit_tools.config.traceback = enabled
    lib_cli_exit_tools.config.traceback_force_color = enabled


def snapshot_traceback_state() -> TracebackState:
    """Record the current traceback preferences so they can be restored later.

    Why
        Because ``lib_cli_exit_tools`` manages global traceback flags, helpers
        that modify these settings must capture the original state before making
        changes. Returning a tuple simplifies passing the state along to
        restoration helpers without requiring complex data structures.

    Returns
    -------
    TracebackState
        A 2-tuple ``(traceback, traceback_force_color)`` reflecting the current
        lib_cli_exit_tools configuration.

    Examples
    --------
    >>> state = snapshot_traceback_state()
    >>> isinstance(state, tuple)
    True
    >>> len(state)
    2
    """
    return (
        bool(lib_cli_exit_tools.config.traceback),
        bool(lib_cli_exit_tools.config.traceback_force_color),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback preference.

    Why
        After temporarily enabling verbose tracebacks for a specific command,
        the CLI must restore the original configuration to avoid leaking state
        into subsequent commands or test runs.

    Parameters
    ----------
    state:
        The tuple returned by :func:`snapshot_traceback_state` capturing
        the traceback preference to restore.

    Examples
    --------
    >>> original = snapshot_traceback_state()
    >>> apply_traceback_preferences(True)
    >>> restore_traceback_state(original)
    >>> bool(lib_cli_exit_tools.config.traceback) == original[0]
    True
    """
    lib_cli_exit_tools.config.traceback = state[0]
    lib_cli_exit_tools.config.traceback_force_color = state[1]


def get_traceback_limit(tracebacks_enabled: bool) -> int:
    """Calculate the character limit for traceback rendering.

    Parameters
    ----------
    tracebacks_enabled:
        Whether verbose tracebacks are enabled.

    Returns
    -------
    int
        Character limit for traceback output.
    """
    return TRACEBACK_VERBOSE_LIMIT if tracebacks_enabled else TRACEBACK_SUMMARY_LIMIT
