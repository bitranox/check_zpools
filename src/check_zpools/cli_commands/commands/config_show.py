"""Config show command implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import lib_log_rich.runtime

from ...config_show import display_config

if TYPE_CHECKING:
    from ...models import ConfigOutputFormat

logger = logging.getLogger(__name__)


def config_show_command(output_format: ConfigOutputFormat, section: str | None) -> None:
    """Execute config command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-config",
        extra={"command": "config", "format": output_format},
    ):
        logger.info("Displaying configuration", extra={"format": output_format, "section": section})
        display_config(output_format=output_format, section=section)
