"""Service uninstall command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...service_install import uninstall_service

logger = logging.getLogger(__name__)


def service_uninstall_command(no_stop: bool, no_disable: bool) -> None:
    """Execute service-uninstall command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-service-uninstall",
        extra={"command": "service-uninstall", "stop": not no_stop, "disable": not no_disable},
    ):
        try:
            logger.info(
                "Uninstalling systemd service",
                extra={"stop": not no_stop, "disable": not no_disable},
            )
            uninstall_service(stop=not no_stop, disable=not no_disable)
        except PermissionError as exc:
            logger.error("Permission denied during service uninstallation", extra={"error": str(exc)})
            click.echo(f"\n{exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Service uninstallation failed",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Service uninstallation failed - {exc}", err=True)
            raise SystemExit(1)
