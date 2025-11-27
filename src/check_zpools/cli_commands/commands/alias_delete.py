"""Alias delete command implementation."""

from __future__ import annotations

import logging
from typing import Optional

import lib_log_rich.runtime
import rich_click as click

from ...alias_manager import delete_alias

logger = logging.getLogger(__name__)


def alias_delete_command(user: Optional[str], all_users: bool = False) -> None:
    """Execute alias-delete command logic."""
    with lib_log_rich.runtime.bind(
        job_id="cli-alias-delete",
        extra={"command": "alias-delete", "user": user, "all_users": all_users},
    ):
        try:
            logger.info("Removing bash alias", extra={"user": user, "all_users": all_users})
            delete_alias(username=user, all_users=all_users)
        except PermissionError as exc:
            logger.error("Permission denied during alias removal", extra={"error": str(exc)})
            click.echo(f"\n{exc}", err=True)
            raise SystemExit(1)
        except KeyError as exc:
            logger.error("User not found", extra={"error": str(exc)})
            click.echo(f"\nError: {exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Alias removal failed",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Alias removal failed - {exc}", err=True)
            raise SystemExit(1)
