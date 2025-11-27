"""CLI adapter wiring the behavior helpers into a rich-click interface.

Purpose
-------
Expose a stable command-line surface so tooling, documentation, and packaging
automation can be exercised. This module contains ONLY Click decorators and
thin wrappers that delegate to command implementations in cli/commands/.

All business logic has been extracted to external modules, keeping this file
minimal (orchestration only, <300 lines).

System Role
-----------
The CLI is the primary adapter for local development workflows; packaging
targets register the console script defined in :mod:`check_zpools.__init__conf__`.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import rich_click as click

import lib_cli_exit_tools
import lib_log_rich.runtime
from click.core import ParameterSource

from . import __init__conf__
from .behaviors import emit_greeting, noop_main, raise_intentional_failure
from .cli_commands.commands import (
    alias_create_command,
    alias_delete_command,
    check_command,
    config_deploy_command,
    config_show_command,
    daemon_command,
    send_email_command,
    send_notification_command,
    service_install_command,
    service_status_command,
    service_uninstall_command,
)
from .cli_traceback import (
    TRACEBACK_SUMMARY_LIMIT,
    TRACEBACK_VERBOSE_LIMIT,
    apply_traceback_preferences,
    restore_traceback_state,
    snapshot_traceback_state,
)
from .logging_setup import init_logging

#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}  # noqa: C408

logger = logging.getLogger(__name__)


@click.group(
    help=__init__conf__.title,
    context_settings=CLICK_CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.version_option(
    version=__init__conf__.version,
    prog_name=__init__conf__.shell_command,
    message=f"{__init__conf__.shell_command} version {__init__conf__.version}",
)
@click.option(
    "--traceback/--no-traceback",
    is_flag=True,
    default=False,
    help="Show full Python traceback on errors",
)
@click.pass_context
def cli(ctx: click.Context, traceback: bool) -> None:
    """Root command storing global flags and syncing shared traceback state."""
    init_logging()

    ctx.ensure_object(dict)
    ctx.obj["traceback"] = traceback
    apply_traceback_preferences(traceback)

    if ctx.invoked_subcommand is None:
        source = ctx.get_parameter_source("traceback")
        if source not in (ParameterSource.DEFAULT, None):
            noop_main()
        else:
            click.echo(ctx.get_help())


@cli.command("info", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_info() -> None:
    """Print resolved metadata so users can inspect installation details."""
    with lib_log_rich.runtime.bind(job_id="cli-info", extra={"command": "info"}):
        logger.info("Displaying package information")
        __init__conf__.print_info()


@cli.command("hello", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_hello() -> None:
    """Demonstrate the success path by emitting the canonical greeting."""
    with lib_log_rich.runtime.bind(job_id="cli-hello", extra={"command": "hello"}):
        logger.info("Executing hello command")
        emit_greeting()


@cli.command("fail", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_fail() -> None:
    """Trigger the intentional failure helper to test error handling."""
    with lib_log_rich.runtime.bind(job_id="cli-fail", extra={"command": "fail"}):
        logger.warning("Executing intentional failure command")
        raise_intentional_failure()


@cli.command("config", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--format",
    type=click.Choice(["human", "json"], case_sensitive=False),
    default="human",
    help="Output format (human-readable or JSON)",
)
@click.option(
    "--section",
    type=str,
    default=None,
    help="Show only a specific configuration section",
)
def cli_config(format: str, section: Optional[str]) -> None:
    """Display the current merged configuration from all sources."""
    config_show_command(format, section)


@cli.command("config-deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--target",
    "targets",
    type=click.Choice(["app", "host", "user"], case_sensitive=False),
    multiple=True,
    required=True,
    help="Target configuration layer(s) to deploy to",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing configuration files",
)
def cli_config_deploy(targets: tuple[str, ...], force: bool) -> None:
    """Deploy default configuration to system or user directories."""
    config_deploy_command(targets, force)


@cli.command("send-email", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--to",
    "recipients",
    multiple=True,
    required=True,
    help="Recipient email address (can specify multiple)",
)
@click.option(
    "--subject",
    required=True,
    help="Email subject line",
)
@click.option(
    "--body",
    default="",
    help="Plain-text email body",
)
@click.option(
    "--body-html",
    default="",
    help="HTML email body",
)
@click.option(
    "--from",
    "from_address",
    default=None,
    help="Override sender address",
)
@click.option(
    "--attachment",
    "attachments",
    multiple=True,
    type=click.Path(exists=True, path_type=str),
    help="File to attach (can specify multiple)",
)
def cli_send_email(
    recipients: tuple[str, ...],
    subject: str,
    body: str,
    body_html: str,
    from_address: Optional[str],
    attachments: tuple[str, ...],
) -> None:
    """Send an email using configured SMTP settings."""
    send_email_command(recipients, subject, body, body_html, from_address, attachments)


@cli.command("send-notification", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--to",
    "recipients",
    multiple=True,
    required=True,
    help="Recipient email address",
)
@click.option(
    "--subject",
    required=True,
    help="Notification subject line",
)
@click.option(
    "--message",
    required=True,
    help="Notification message",
)
def cli_send_notification(
    recipients: tuple[str, ...],
    subject: str,
    message: str,
) -> None:
    """Send a simple plain-text notification email."""
    send_notification_command(recipients, subject, message)


@cli.command("service-install", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--no-enable",
    is_flag=True,
    default=False,
    help="Don't enable service to start on boot",
)
@click.option(
    "--no-start",
    is_flag=True,
    default=False,
    help="Don't start service immediately",
)
@click.option(
    "--uvx-version",
    type=str,
    default=None,
    help="Version specifier for uvx installations",
)
def cli_install_service(no_enable: bool, no_start: bool, uvx_version: Optional[str]) -> None:
    """Install check_zpools as a systemd service (requires root)."""
    service_install_command(no_enable, no_start, uvx_version)


@cli.command("service-uninstall", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--no-stop",
    is_flag=True,
    default=False,
    help="Don't stop running service",
)
@click.option(
    "--no-disable",
    is_flag=True,
    default=False,
    help="Don't disable service",
)
def cli_uninstall_service(no_stop: bool, no_disable: bool) -> None:
    """Uninstall check_zpools systemd service (requires root)."""
    service_uninstall_command(no_stop, no_disable)


@cli.command("service-status", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_service_status() -> None:
    """Show status of check_zpools systemd service."""
    service_status_command()


@cli.command("alias-create", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--user",
    type=str,
    default=None,
    help="Target username for alias creation (defaults to sudo user or current user)",
)
@click.option(
    "--all-users",
    is_flag=True,
    default=False,
    help="Create alias in /etc/bash.bashrc for all users (requires root)",
)
def cli_alias_create(user: Optional[str], all_users: bool) -> None:
    """Create bash alias for check_zpools CLI (requires root)."""
    alias_create_command(user, all_users)


@cli.command("alias-delete", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--user",
    type=str,
    default=None,
    help="Target username for alias removal (defaults to sudo user or current user)",
)
@click.option(
    "--all-users",
    is_flag=True,
    default=False,
    help="Remove alias from /etc/bash.bashrc (system-wide, requires root)",
)
def cli_alias_delete(user: Optional[str], all_users: bool) -> None:
    """Remove bash alias for check_zpools CLI (requires root)."""
    alias_delete_command(user, all_users)


@cli.command("check", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format for results",
)
def cli_check(format: str) -> None:
    """Perform one-shot check of all ZFS pools."""
    check_command(format)


@cli.command("daemon", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--foreground",
    is_flag=True,
    default=False,
    help="Run in foreground (don't daemonize)",
)
def cli_daemon(foreground: bool) -> None:
    """Start daemon mode for continuous ZFS pool monitoring."""
    daemon_command(foreground)


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    restore_traceback: bool = True,
    summary_limit: int = TRACEBACK_SUMMARY_LIMIT,
    verbose_limit: int = TRACEBACK_VERBOSE_LIMIT,
) -> int:
    """Execute the CLI with deliberate error handling and return the exit code."""
    init_logging()
    previous_state = snapshot_traceback_state()
    try:
        return _run_cli_via_exit_tools(argv, summary_limit=summary_limit, verbose_limit=verbose_limit)
    finally:
        if restore_traceback:
            restore_traceback_state(previous_state)
        lib_log_rich.runtime.shutdown()


def _run_cli_via_exit_tools(
    argv: Optional[Sequence[str]],
    *,
    summary_limit: int,
    verbose_limit: int,
) -> int:
    """Run the command while narrating the failure path with care."""
    try:
        return lib_cli_exit_tools.run_cli(
            cli,
            argv=list(argv) if argv is not None else None,
            prog_name=__init__conf__.shell_command,
        )
    except BaseException as exc:  # noqa: BLE001
        tracebacks_enabled = bool(getattr(lib_cli_exit_tools.config, "traceback", False))
        apply_traceback_preferences(tracebacks_enabled)
        length_limit = verbose_limit if tracebacks_enabled else summary_limit
        lib_cli_exit_tools.print_exception_message(
            trace_back=tracebacks_enabled,
            length_limit=length_limit,
        )
        return lib_cli_exit_tools.get_system_exit_code(exc)
