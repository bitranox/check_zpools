"""Service status command implementation."""

from __future__ import annotations

import logging

import lib_log_rich.runtime

from ...service_install import show_service_status

logger = logging.getLogger(__name__)


def service_status_command() -> None:
    """Execute service-status command logic."""
    with lib_log_rich.runtime.bind(job_id="cli-service-status", extra={"command": "service-status"}):
        logger.info("Checking service status")
        show_service_status()
