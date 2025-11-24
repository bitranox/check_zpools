"""Config deploy command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...config_deploy import deploy_configuration

logger = logging.getLogger(__name__)


def config_deploy_command(targets: tuple[str, ...], force: bool) -> None:
    """Execute config-deploy command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-config-deploy",
        extra={"command": "config-deploy", "targets": targets, "force": force},
    ):
        logger.info("Deploying configuration", extra={"targets": targets, "force": force})

        try:
            deployed_paths = deploy_configuration(targets=list(targets), force=force)

            if deployed_paths:
                click.echo("\nConfiguration deployed successfully:")
                for path in deployed_paths:
                    click.echo(f"  ✓ {path}")
            else:
                click.echo("\nNo files were created (all target files already exist).")
                click.echo("Use --force to overwrite existing configuration files.")

        except PermissionError as exc:
            logger.error("Permission denied when deploying configuration", extra={"error": str(exc)})
            click.echo(f"\nError: Permission denied. {exc}", err=True)
            click.echo("Hint: System-wide deployment (--target app/host) may require sudo.", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Failed to deploy configuration",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            click.echo(f"\nError: Failed to deploy configuration: {exc}", err=True)
            raise SystemExit(1)
