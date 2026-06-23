"""Config show command implementation."""

from __future__ import annotations

import logging
from typing import Optional

import lib_log_rich.runtime

from ...config_show import display_config

logger = logging.getLogger(__name__)


def config_show_command(format: str, section: Optional[str]) -> None:
    """Execute config command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-config",
        extra={"command": "config", "format": format},
    ):
        logger.info("Displaying configuration", extra={"format": format, "section": section})
        display_config(format=format, section=section)
