"""CLI adapter wiring the behavior helpers into a rich-click interface.

Purpose
-------
Expose a stable command-line surface so tooling, documentation, and packaging
automation can be exercised while the richer logging helpers are being built.
By delegating to :mod:`check_zpools.behaviors` the transport stays
aligned with the Clean Code rules captured in
``docs/systemdesign/module_reference.md``.

Contents
--------
* :data:`CLICK_CONTEXT_SETTINGS` – shared Click settings ensuring consistent
  ``--help`` behavior across commands.
* :func:`apply_traceback_preferences` – helper that synchronises the shared
  traceback configuration flags.
* :func:`snapshot_traceback_state` / :func:`restore_traceback_state` – utilities
  for preserving and reapplying the global traceback preference.
* :func:`cli` – root command group wiring the global options.
* :func:`cli_main` – default action when no subcommand is provided.
* :func:`cli_info`, :func:`cli_hello`, :func:`cli_fail` – subcommands covering
  metadata printing, success path, and failure path.
* :func:`_record_traceback_choice`, :func:`_announce_traceback_choice` – persist
  traceback preferences across context and shared tooling.
* :func:`_invoke_cli`, :func:`_current_traceback_mode`, :func:`_traceback_limit`,
  :func:`_print_exception`, :func:`_run_cli_via_exit_tools` – isolate the error
  handling and delegation path.
* :func:`_restore_when_requested` – restores tracebacks when ``main`` finishes.
* :func:`main` – composition helper delegating to ``lib_cli_exit_tools`` while
  honouring the shared traceback preferences.

System Role
-----------
The CLI is the primary adapter for local development workflows; packaging
targets register the console script defined in :mod:`check_zpools.__init__conf__`.
Other transports (including ``python -m`` execution) reuse the same helpers so
behaviour remains consistent regardless of entry point.
"""

from __future__ import annotations
import logging
from typing import Final, Optional, Sequence, Tuple

import rich_click as click

import lib_cli_exit_tools
import lib_log_rich.runtime
from click.core import ParameterSource

from . import __init__conf__
from .behaviors import emit_greeting, noop_main, raise_intentional_failure
from .config import get_config
from .config_deploy import deploy_configuration
from .config_show import display_config
from .logging_setup import init_logging
from .mail import EmailConfig, load_email_config_from_dict, send_email, send_notification
from .service_install import install_service, show_service_status, uninstall_service

#: Shared Click context flags so help output stays consistent across commands.
CLICK_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}  # noqa: C408
#: Character budget used when printing truncated tracebacks.
TRACEBACK_SUMMARY_LIMIT: Final[int] = 500
#: Character budget used when verbose tracebacks are enabled.
TRACEBACK_VERBOSE_LIMIT: Final[int] = 10_000
TracebackState = Tuple[bool, bool]

logger = logging.getLogger(__name__)


def apply_traceback_preferences(enabled: bool) -> None:
    """Synchronise shared traceback flags with the requested preference.

    Why
        ``lib_cli_exit_tools`` inspects global flags to decide whether tracebacks
        should be truncated and whether colour should be forced. Updating both
        attributes together ensures the ``--traceback`` flag behaves the same for
        console scripts and ``python -m`` execution.

    Parameters
    ----------
    enabled:
        ``True`` enables full tracebacks with colour. ``False`` restores the
        compact summary mode.

    Examples
    --------
    >>> apply_traceback_preferences(True)
    >>> bool(lib_cli_exit_tools.config.traceback)
    True
    >>> bool(lib_cli_exit_tools.config.traceback_force_color)
    True
    """

    lib_cli_exit_tools.config.traceback = bool(enabled)
    lib_cli_exit_tools.config.traceback_force_color = bool(enabled)


def snapshot_traceback_state() -> TracebackState:
    """Capture the current traceback configuration for later restoration.

    Returns
    -------
    TracebackState
        Tuple of ``(traceback_enabled, force_color)``.

    Examples
    --------
    >>> snapshot = snapshot_traceback_state()
    >>> isinstance(snapshot, tuple)
    True
    """

    return (
        bool(getattr(lib_cli_exit_tools.config, "traceback", False)),
        bool(getattr(lib_cli_exit_tools.config, "traceback_force_color", False)),
    )


def restore_traceback_state(state: TracebackState) -> None:
    """Reapply a previously captured traceback configuration.

    Parameters
    ----------
    state:
        Tuple returned by :func:`snapshot_traceback_state`.

    Examples
    --------
    >>> prev = snapshot_traceback_state()
    >>> apply_traceback_preferences(True)
    >>> restore_traceback_state(prev)
    >>> snapshot_traceback_state() == prev
    True
    """

    lib_cli_exit_tools.config.traceback = bool(state[0])
    lib_cli_exit_tools.config.traceback_force_color = bool(state[1])


def _record_traceback_choice(ctx: click.Context, *, enabled: bool) -> None:
    """Remember the chosen traceback mode inside the Click context.

    Why
        Downstream commands need to know whether verbose tracebacks were
        requested so they can honour the user's preference without re-parsing
        flags.

    What
        Ensures the context has a dict backing store and persists the boolean
        under the ``"traceback"`` key.

    Inputs
        ctx:
            Click context associated with the current invocation.
        enabled:
            ``True`` when verbose tracebacks were requested; ``False`` otherwise.

    Side Effects
        Mutates ``ctx.obj``.
    """

    ctx.ensure_object(dict)
    ctx.obj["traceback"] = enabled


def _announce_traceback_choice(enabled: bool) -> None:
    """Keep ``lib_cli_exit_tools`` in sync with the selected traceback mode.

    Why
        ``lib_cli_exit_tools`` reads global configuration to decide how to print
        tracebacks; we mirror the user's choice into that configuration.

    Inputs
        enabled:
            ``True`` when verbose tracebacks should be shown; ``False`` when the
            summary view is desired.

    Side Effects
        Mutates ``lib_cli_exit_tools.config``.
    """

    apply_traceback_preferences(enabled)


def _no_subcommand_requested(ctx: click.Context) -> bool:
    """Return ``True`` when the invocation did not name a subcommand.

    Why
        The CLI defaults to calling ``noop_main`` when no subcommand appears; we
        need a readable predicate to capture that intent.

    Inputs
        ctx:
            Click context describing the current CLI invocation.

    Outputs
        bool:
            ``True`` when no subcommand was invoked; ``False`` otherwise.
    """

    return ctx.invoked_subcommand is None


def _invoke_cli(argv: Optional[Sequence[str]]) -> int:
    """Ask ``lib_cli_exit_tools`` to execute the Click command.

    Why
        ``lib_cli_exit_tools`` normalises exit codes and exception handling; we
        centralise the call so tests can stub it cleanly.

    Inputs
        argv:
            Optional sequence of command-line arguments. ``None`` delegates to
            ``sys.argv`` inside ``lib_cli_exit_tools``.

    Outputs
        int:
            Exit code returned by the CLI execution.
    """

    return lib_cli_exit_tools.run_cli(
        cli,
        argv=list(argv) if argv is not None else None,
        prog_name=__init__conf__.shell_command,
    )


def _current_traceback_mode() -> bool:
    """Return the global traceback preference as a boolean.

    Why
        Error handling logic needs to know whether verbose tracebacks are active
        so it can pick the right character budget and ensure colouring is
        consistent.

    Outputs
        bool:
            ``True`` when verbose tracebacks are enabled; ``False`` otherwise.
    """

    return bool(getattr(lib_cli_exit_tools.config, "traceback", False))


def _traceback_limit(tracebacks_enabled: bool, *, summary_limit: int, verbose_limit: int) -> int:
    """Return the character budget that matches the current traceback mode.

    Why
        Verbose tracebacks should show the full story while compact ones keep the
        terminal tidy. This helper makes that decision explicit.

    Inputs
        tracebacks_enabled:
            ``True`` when verbose tracebacks are active.
        summary_limit:
            Character budget for truncated output.
        verbose_limit:
            Character budget for the full traceback.

    Outputs
        int:
            The applicable character limit.
    """

    return verbose_limit if tracebacks_enabled else summary_limit


def _print_exception(exc: BaseException, *, tracebacks_enabled: bool, length_limit: int) -> int:
    """Render the exception through ``lib_cli_exit_tools`` and return its exit code.

    Why
        All transports funnel errors through ``lib_cli_exit_tools`` so that exit
        codes and formatting stay consistent; this helper keeps the plumbing in
        one place.

    Inputs
        exc:
            Exception raised by the CLI.
        tracebacks_enabled:
            ``True`` when verbose tracebacks should be shown.
        length_limit:
            Maximum number of characters to print.

    Outputs
        int:
            Exit code to surface to the shell.

    Side Effects
        Writes the formatted exception to stderr via ``lib_cli_exit_tools``.
    """

    lib_cli_exit_tools.print_exception_message(
        trace_back=tracebacks_enabled,
        length_limit=length_limit,
    )
    return lib_cli_exit_tools.get_system_exit_code(exc)


def _traceback_option_requested(ctx: click.Context) -> bool:
    """Return ``True`` when the user explicitly requested ``--traceback``.

    Why
        Determines whether a no-command invocation should run the default
        behaviour or display the help screen.

    Inputs
        ctx:
            Click context associated with the current invocation.

    Outputs
        bool:
            ``True`` when the user provided ``--traceback`` or ``--no-traceback``;
            ``False`` when the default value is in effect.
    """

    source = ctx.get_parameter_source("traceback")
    return source not in (ParameterSource.DEFAULT, None)


def _show_help(ctx: click.Context) -> None:
    """Render the command help to stdout."""

    click.echo(ctx.get_help())


def _run_cli_via_exit_tools(
    argv: Optional[Sequence[str]],
    *,
    summary_limit: int,
    verbose_limit: int,
) -> int:
    """Run the command while narrating the failure path with care.

    Why
        Consolidates the call to ``lib_cli_exit_tools`` so happy paths and error
        handling remain consistent across the application and tests.

    Inputs
        argv:
            Optional sequence of CLI arguments.
        summary_limit / verbose_limit:
            Character budgets steering exception output length.

    Outputs
        int:
            Exit code produced by the command.

    Side Effects
        Delegates to ``lib_cli_exit_tools`` which may write to stderr.
    """

    try:
        return _invoke_cli(argv)
    except BaseException as exc:  # noqa: BLE001 - handled by shared printers
        tracebacks_enabled = _current_traceback_mode()
        apply_traceback_preferences(tracebacks_enabled)
        return _print_exception(
            exc,
            tracebacks_enabled=tracebacks_enabled,
            length_limit=_traceback_limit(
                tracebacks_enabled,
                summary_limit=summary_limit,
                verbose_limit=verbose_limit,
            ),
        )


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
    """Root command storing global flags and syncing shared traceback state.

    Why
        The CLI must provide a switch for verbose tracebacks so developers can
        toggle diagnostic depth without editing configuration files.

    What
        Ensures a dict-based context, stores the ``traceback`` flag, and mirrors
        the value into ``lib_cli_exit_tools.config`` so downstream helpers observe
        the preference. When no subcommand (or options) are provided, the command
        prints help instead of running the domain stub; otherwise the default
        action delegates to :func:`cli_main`.

    Side Effects
        Mutates :mod:`lib_cli_exit_tools.config` to reflect the requested
        traceback mode, including ``traceback_force_color`` when tracebacks are
        enabled. Initializes lib_log_rich runtime if needed.

    Examples
    --------
    >>> from click.testing import CliRunner
    >>> runner = CliRunner()
    >>> result = runner.invoke(cli, ["hello"])
    >>> result.exit_code
    0
    >>> "Hello World" in result.output
    True
    """

    # Initialize logging before any commands execute
    init_logging()

    _record_traceback_choice(ctx, enabled=traceback)
    _announce_traceback_choice(traceback)
    if _no_subcommand_requested(ctx):
        if _traceback_option_requested(ctx):
            cli_main()
        else:
            _show_help(ctx)


def cli_main() -> None:
    """Run the placeholder domain entry when callers opt into execution.

    Why
        Maintains compatibility with tooling that expects the original
        "do-nothing" behaviour by explicitly opting in via options (e.g.
        ``--traceback`` without subcommands).

    Side Effects
        Delegates to :func:`noop_main`.

    Examples
    --------
    >>> cli_main()
    """

    noop_main()


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
    help="Show only a specific configuration section (e.g., 'lib_log_rich')",
)
def cli_config(format: str, section: Optional[str]) -> None:
    """Display the current merged configuration from all sources.

    Shows configuration loaded from:
    - Default config (built-in)
    - Application config (/etc/xdg/bitranox-template-cli-app-config-log/config.toml)
    - User config (~/.config/bitranox-template-cli-app-config-log/config.toml)
    - .env files
    - Environment variables (BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_*)

    Precedence: defaults → app → host → user → dotenv → env
    """

    with lib_log_rich.runtime.bind(job_id="cli-config", extra={"command": "config", "format": format}):
        logger.info("Displaying configuration", extra={"format": format, "section": section})
        display_config(format=format, section=section)


@cli.command("config-deploy", context_settings=CLICK_CONTEXT_SETTINGS)
@click.option(
    "--target",
    "targets",
    type=click.Choice(["app", "host", "user"], case_sensitive=False),
    multiple=True,
    required=True,
    help="Target configuration layer(s) to deploy to (can specify multiple)",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing configuration files",
)
def cli_config_deploy(targets: tuple[str, ...], force: bool) -> None:
    """Deploy default configuration to system or user directories.

    Creates configuration files in platform-specific locations:

    \b
    - app:  System-wide application config (requires privileges)
    - host: System-wide host config (requires privileges)
    - user: User-specific config (~/.config on Linux)

    By default, existing files are not overwritten. Use --force to overwrite.

    Examples:

    \b
    # Deploy to user config directory
    $ bitranox-template-cli-app-config-log config-deploy --target user

    \b
    # Deploy to both app and user directories
    $ bitranox-template-cli-app-config-log config-deploy --target app --target user

    \b
    # Force overwrite existing config
    $ bitranox-template-cli-app-config-log config-deploy --target user --force
    """

    with lib_log_rich.runtime.bind(job_id="cli-config-deploy", extra={"command": "config-deploy", "targets": targets, "force": force}):
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
            logger.error("Failed to deploy configuration", extra={"error": str(exc), "error_type": type(exc).__name__})
            click.echo(f"\nError: Failed to deploy configuration: {exc}", err=True)
            raise SystemExit(1)


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    restore_traceback: bool = True,
    summary_limit: int = TRACEBACK_SUMMARY_LIMIT,
    verbose_limit: int = TRACEBACK_VERBOSE_LIMIT,
) -> int:
    """Execute the CLI with deliberate error handling and return the exit code.

    Why
        Provides the single entry point used by console scripts and
        ``python -m`` execution so that behaviour stays identical across
        transports.

    Inputs
        argv:
            Optional sequence of CLI arguments. ``None`` lets Click consume
            ``sys.argv`` directly.
        restore_traceback:
            ``True`` to restore the prior ``lib_cli_exit_tools`` traceback
            configuration after execution.
        summary_limit / verbose_limit:
            Character budgets used when formatting exceptions.

    Outputs
        int:
            Exit code reported by the CLI run.

    Side Effects
        Mutates the global traceback configuration while the CLI runs.
        Initializes and shuts down the lib_log_rich runtime.
    """

    init_logging()
    previous_state = snapshot_traceback_state()
    try:
        return _run_cli_via_exit_tools(
            argv,
            summary_limit=summary_limit,
            verbose_limit=verbose_limit,
        )
    finally:
        _restore_when_requested(previous_state, restore_traceback)
        lib_log_rich.runtime.shutdown()


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
    help="HTML email body (sent as multipart with plain text)",
)
@click.option(
    "--from",
    "from_address",
    default=None,
    help="Override sender address (uses config default if not specified)",
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
    """Send an email using configured SMTP settings.

    Loads email configuration from layered config sources:
    - Default config (built-in)
    - Application/User config files
    - Environment variables (BITRANOX_TEMPLATE_CLI_APP_CONFIG_LOG_MAIL_EMAIL_*)

    Examples:

    \b
    # Send simple text email
    $ bitranox-template-cli-app-config-log-mail send-email \\
        --to recipient@example.com \\
        --subject "Test Email" \\
        --body "Hello from CLI"

    \b
    # Send to multiple recipients with HTML
    $ bitranox-template-cli-app-config-log-mail send-email \\
        --to user1@example.com \\
        --to user2@example.com \\
        --subject "HTML Email" \\
        --body "Plain text version" \\
        --body-html "<h1>HTML Version</h1>"

    \b
    # Send with attachments
    $ bitranox-template-cli-app-config-log-mail send-email \\
        --to admin@example.com \\
        --subject "Report" \\
        --body "See attached" \\
        --attachment report.pdf \\
        --attachment data.csv
    """
    from pathlib import Path

    with lib_log_rich.runtime.bind(
        job_id="cli-send-email",
        extra={"command": "send-email", "recipients": list(recipients), "subject": subject},
    ):
        try:
            # Load and validate email configuration
            email_config = _load_and_validate_email_config()

            # Convert attachment paths
            attachment_paths = [Path(p) for p in attachments] if attachments else None

            logger.info(
                "Sending email",
                extra={
                    "recipients": list(recipients),
                    "subject": subject,
                    "has_html": bool(body_html),
                    "attachment_count": len(attachments) if attachments else 0,
                },
            )

            # Send email
            result = send_email(
                config=email_config,
                recipients=list(recipients),
                subject=subject,
                body=body,
                body_html=body_html,
                from_address=from_address,
                attachments=attachment_paths,
            )

            if result:
                click.echo("\nEmail sent successfully!")
                logger.info("Email sent via CLI", extra={"recipients": list(recipients)})
            else:
                click.echo("\nEmail sending failed.", err=True)
                raise SystemExit(1)

        except ValueError as exc:
            logger.error("Invalid email parameters", extra={"error": str(exc)})
            click.echo(f"\nError: Invalid email parameters - {exc}", err=True)
            raise SystemExit(1)
        except FileNotFoundError as exc:
            logger.error("Attachment file not found", extra={"error": str(exc)})
            click.echo(f"\nError: Attachment file not found - {exc}", err=True)
            raise SystemExit(1)
        except RuntimeError as exc:
            logger.error("SMTP delivery failed", extra={"error": str(exc)})
            click.echo(f"\nError: Failed to send email - {exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Unexpected error sending email",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Unexpected error - {exc}", err=True)
            raise SystemExit(1)


@cli.command("send-notification", context_settings=CLICK_CONTEXT_SETTINGS)
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
    help="Notification subject line",
)
@click.option(
    "--message",
    required=True,
    help="Notification message (plain text)",
)
def cli_send_notification(
    recipients: tuple[str, ...],
    subject: str,
    message: str,
) -> None:
    """Send a simple plain-text notification email.

    Convenience command for sending simple notifications without HTML or attachments.
    Uses the same configuration as send-email.

    Examples:

    \b
    # Send simple notification
    $ bitranox-template-cli-app-config-log-mail send-notification \\
        --to admin@example.com \\
        --subject "System Alert" \\
        --message "Deployment completed successfully"

    \b
    # Send to multiple recipients
    $ bitranox-template-cli-app-config-log-mail send-notification \\
        --to ops@example.com \\
        --to dev@example.com \\
        --subject "Service Status" \\
        --message "All services operational"
    """

    with lib_log_rich.runtime.bind(
        job_id="cli-send-notification",
        extra={"command": "send-notification", "recipients": list(recipients), "subject": subject},
    ):
        try:
            # Load and validate email configuration
            email_config = _load_and_validate_email_config()

            logger.info(
                "Sending notification",
                extra={"recipients": list(recipients), "subject": subject},
            )

            # Send notification
            result = send_notification(
                config=email_config,
                recipients=list(recipients),
                subject=subject,
                message=message,
            )

            if result:
                click.echo("\nNotification sent successfully!")
                logger.info("Notification sent via CLI", extra={"recipients": list(recipients)})
            else:
                click.echo("\nNotification sending failed.", err=True)
                raise SystemExit(1)

        except ValueError as exc:
            logger.error("Invalid notification parameters", extra={"error": str(exc)})
            click.echo(f"\nError: Invalid notification parameters - {exc}", err=True)
            raise SystemExit(1)
        except RuntimeError as exc:
            logger.error("SMTP delivery failed", extra={"error": str(exc)})
            click.echo(f"\nError: Failed to send notification - {exc}", err=True)
            raise SystemExit(1)
        except Exception as exc:
            logger.error(
                "Unexpected error sending notification",
                extra={"error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            click.echo(f"\nError: Unexpected error - {exc}", err=True)
            raise SystemExit(1)


@cli.command("install-service", context_settings=CLICK_CONTEXT_SETTINGS)
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
def cli_install_service(no_enable: bool, no_start: bool) -> None:
    """Install check_zpools as a systemd service (requires root).

    Installs the check_zpools daemon as a systemd service that will:
    - Run continuously to monitor ZFS pools
    - Start automatically on system boot (unless --no-enable)
    - Log to journald for centralized monitoring
    - Restart automatically on failure

    The service will be installed to /etc/systemd/system/check_zpools.service
    and will run with root privileges (required for ZFS access).

    Examples:

    \b
    # Install, enable, and start service
    $ sudo check_zpools install-service

    \b
    # Install but don't start yet
    $ sudo check_zpools install-service --no-start

    \b
    # Install but don't enable for boot
    $ sudo check_zpools install-service --no-enable
    """

    with lib_log_rich.runtime.bind(
        job_id="cli-install-service",
        extra={"command": "install-service", "enable": not no_enable, "start": not no_start},
    ):
        try:
            logger.info("Installing systemd service", extra={"enable": not no_enable, "start": not no_start})
            install_service(enable=not no_enable, start=not no_start)
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


@cli.command("uninstall-service", context_settings=CLICK_CONTEXT_SETTINGS)
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
    """Uninstall check_zpools systemd service (requires root).

    Removes the check_zpools systemd service:
    - Stops the running service (unless --no-stop)
    - Disables automatic start on boot (unless --no-disable)
    - Removes service file from /etc/systemd/system/

    Note: This does not remove cache and state directories.
    Use 'sudo rm -rf /var/cache/check_zpools /var/lib/check_zpools'
    to remove these directories if needed.

    Examples:

    \b
    # Uninstall service completely
    $ sudo check_zpools uninstall-service

    \b
    # Uninstall but leave service running
    $ sudo check_zpools uninstall-service --no-stop
    """

    with lib_log_rich.runtime.bind(
        job_id="cli-uninstall-service",
        extra={"command": "uninstall-service", "stop": not no_stop, "disable": not no_disable},
    ):
        try:
            logger.info("Uninstalling systemd service", extra={"stop": not no_stop, "disable": not no_disable})
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


@cli.command("service-status", context_settings=CLICK_CONTEXT_SETTINGS)
def cli_service_status() -> None:
    """Show status of check_zpools systemd service.

    Displays whether the service is:
    - Installed (service file exists)
    - Running (currently active)
    - Enabled (starts on boot)

    Also shows full systemctl status output for detailed diagnostics.

    Examples:

    \b
    # Check service status
    $ check_zpools service-status
    """

    with lib_log_rich.runtime.bind(job_id="cli-service-status", extra={"command": "service-status"}):
        logger.info("Checking service status")
        show_service_status()


def _load_and_validate_email_config() -> EmailConfig:
    """Load email config and validate SMTP hosts are configured.

    Why
        Centralizes the common pattern of loading email configuration and
        validating that SMTP hosts are configured. Used by both send-email
        and send-notification commands.

    Returns
        EmailConfig with validated SMTP configuration.

    Raises
        SystemExit: When SMTP hosts are not configured (exit code 1).

    Side Effects
        Logs error and prints user-friendly message to stderr when
        configuration is invalid.
    """
    config = get_config()
    email_config = load_email_config_from_dict(config.as_dict())

    if not email_config.smtp_hosts:
        logger.error("No SMTP hosts configured")
        click.echo(
            "\nError: No SMTP hosts configured. Please configure email.smtp_hosts in your config file.",
            err=True,
        )
        click.echo(
            "See: bitranox-template-cli-app-config-log-mail config-deploy --target user",
            err=True,
        )
        raise SystemExit(1)

    return email_config


def _restore_when_requested(state: TracebackState, should_restore: bool) -> None:
    """Restore the prior traceback configuration when requested.

    Why
        CLI execution may toggle verbose tracebacks for the duration of the run.
        Once the command ends we restore the previous configuration so other
        code paths continue with their expected defaults.

    Inputs
        state:
            Tuple captured by :func:`snapshot_traceback_state` describing the
            prior configuration.
        should_restore:
            ``True`` to reapply the stored configuration; ``False`` to keep the
            current settings.

    Side Effects
        May mutate ``lib_cli_exit_tools.config``.
    """

    if should_restore:
        restore_traceback_state(state)
