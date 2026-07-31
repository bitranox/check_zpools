"""Service status command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime
import rich_click as click

from ...models import OutputFormat
from ...service_install import build_service_status_report, show_service_status

logger = logging.getLogger(__name__)


def service_status_command(*, output_format: OutputFormat = OutputFormat.TEXT) -> None:
    """Execute service-status command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-service-status",
        extra={"command": "service-status", "format": output_format.value},
    ):
        logger.info("Checking service status")
        if output_format is OutputFormat.JSON:
            click.echo(build_service_status_report().model_dump_json(indent=2))
        else:
            show_service_status()
