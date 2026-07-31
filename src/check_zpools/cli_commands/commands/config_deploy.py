"""Config deploy command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime

from ... import safe_console
from ...config_deploy import deploy_configuration

logger = logging.getLogger(__name__)


def config_deploy_command(*, targets: tuple[str, ...], force: bool) -> None:
    """Execute config-deploy command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-config-deploy",
        extra={"command": "config-deploy", "targets": targets, "force": force},
    ):
        logger.info("Deploying configuration", extra={"targets": targets, "force": force})

        try:
            deployed_paths = deploy_configuration(targets=list(targets), force=force)

            if deployed_paths:
                safe_console.echo("\nConfiguration deployed successfully:")
                for path in deployed_paths:
                    safe_console.echo(f"  ✓ {path}")
            else:
                safe_console.echo("\nNo files were created (all target files already exist).")
                safe_console.echo("Use --force to overwrite existing configuration files.")

        except PermissionError as exc:
            logger.error("Permission denied when deploying configuration", extra={"error": str(exc)})
            safe_console.echo(f"\nError: Permission denied. {exc}", err=True)
            safe_console.echo("Hint: System-wide deployment (--target app/host) may require sudo.", err=True)
            raise SystemExit(1) from exc
        except Exception as exc:
            logger.error(
                "Failed to deploy configuration",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            safe_console.echo(f"\nError: Failed to deploy configuration: {exc}", err=True)
            raise SystemExit(1) from exc
