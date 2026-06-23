"""Service install command implementation."""

from __future__ import annotations

import logging
from typing import Optional

import lib_log_rich.runtime
import rich_click as click

from ...service_install import install_service

logger = logging.getLogger(__name__)


def service_install_command(no_enable: bool, no_start: bool, uvx_version: Optional[str]) -> None:
    """Execute service-install command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-service-install",
        extra={"command": "service-install", "enable": not no_enable, "start": not no_start},
    ):
        try:
            logger.info(
                "Installing systemd service",
                extra={"enable": not no_enable, "start": not no_start, "uvx_version": uvx_version},
            )
            install_service(enable=not no_enable, start=not no_start, uvx_version=uvx_version)
        except PermissionError as exc:
            logger.error("Permission denied during service installation", extra={"error": str(exc)})
            click.echo(f"\n{exc}", err=True)
            raise SystemExit(1)
        except FileNotFoundError as exc:
            logger.error("Required file not found", extra={"error": str(exc)})
            click.echo(f"\n{exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Service installation failed",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Service installation failed - {exc}", err=True)
            raise SystemExit(1)
