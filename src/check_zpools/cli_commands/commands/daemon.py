"""Daemon command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime

from ...behaviors import run_daemon
from ...cli_errors import handle_generic_error, handle_zfs_not_available
from ...zfs_client import ZFSNotAvailableError

logger = logging.getLogger(__name__)


def daemon_command(foreground: bool) -> None:
    """Execute daemon command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-daemon",
        extra={"command": "daemon", "foreground": foreground},
    ):
        try:
            run_daemon(foreground=foreground)
        except ZFSNotAvailableError as exc:
            handle_zfs_not_available(exc, operation="Daemon")
        except Exception as exc:
            handle_generic_error(exc, operation="Daemon")
