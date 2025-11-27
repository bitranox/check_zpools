"""Domain-level behaviors for ZFS pool monitoring.

Purpose
-------
Implement core ZFS monitoring behaviors that the CLI adapter exposes, including
one-shot pool checks and daemon mode execution. Each behavior is self-contained
and delegates to domain services for actual work.

Contents
--------
Legacy Template Functions (Deprecated):
* :func:`emit_greeting` – success-path helper that writes the canonical scaffold
  message.
* :func:`raise_intentional_failure` – deterministic error hook used by tests and
  CLI flows to validate traceback handling.
* :func:`noop_main` – placeholder entry used when callers expect a ``main``
  callable despite the domain layer being stubbed today.

ZFS Monitoring Functions:
* :func:`check_pools_once` – perform one-shot check of all pools
* :func:`run_daemon` – start daemon mode for continuous monitoring

System Role
-----------
Acts as the behavior layer in Clean Architecture, delegating to domain services
(ZFSClient, PoolMonitor, EmailAlerter, etc.) while providing CLI-friendly
interfaces.
"""

from __future__ import annotations

from typing import Any, TextIO

import logging
import sys
from pathlib import Path

from .alert_state import AlertStateManager
from .alerting import EmailAlerter
from .config import get_config
from .daemon import ZPoolDaemon
from .mail import load_email_config_from_dict
from .models import CheckResult
from .monitor import MonitorConfig, PoolMonitor
from .zfs_client import ZFSClient, ZFSNotAvailableError
from .zfs_parser import ZFSParser


CANONICAL_GREETING = "Hello World"

#: Module logger using standard logging interface.
logger = logging.getLogger(__name__)


def _target_stream(preferred: TextIO | None) -> TextIO:
    """Return the stream that should hear the greeting."""

    return preferred if preferred is not None else sys.stdout


def _greeting_line() -> str:
    """Return the greeting exactly as it should appear."""

    return f"{CANONICAL_GREETING}\n"


def _flush_if_possible(stream: TextIO) -> None:
    """Flush the stream when the stream knows how to flush."""

    flush = getattr(stream, "flush", None)
    if callable(flush):
        flush()


def emit_greeting(*, stream: TextIO | None = None) -> None:
    """Write the canonical greeting to the provided text stream.

    Why
        Provide a deterministic success path that the documentation, smoke
        tests, and packaging checks can rely on while the real logging helpers
        are developed.

    What
        Writes :data:`CANONICAL_GREETING` followed by a newline to the target
        stream.

    Parameters
    ----------
    stream:
        Optional text stream receiving the greeting. Defaults to
        :data:`sys.stdout` when ``None``.

    Side Effects
        Writes to the target stream and flushes it when a ``flush`` attribute is
        available. Emits an INFO-level log message.

    Examples
    --------
    >>> from io import StringIO
    >>> buffer = StringIO()
    >>> emit_greeting(stream=buffer)
    >>> buffer.getvalue() == "Hello World\\n"
    True
    """

    logger.info("Emitting canonical greeting", extra={"greeting": CANONICAL_GREETING})
    target = _target_stream(stream)
    target.write(_greeting_line())
    _flush_if_possible(target)


def raise_intentional_failure() -> None:
    """Raise ``RuntimeError`` so transports can exercise failure flows.

    Why
        CLI commands and tests need a guaranteed failure scenario to ensure the
        shared exit-code helpers and traceback toggles remain correct.

    What
        Always raises ``RuntimeError`` with the message ``"I should fail"``.

    Side Effects
        Emits an ERROR-level log message before raising the exception.

    Raises
        RuntimeError: Regardless of input.

    Examples
    --------
    >>> raise_intentional_failure()
    Traceback (most recent call last):
    ...
    RuntimeError: I should fail
    """

    logger.error("About to raise intentional failure for testing", extra={"test_mode": True})
    raise RuntimeError("I should fail")


def noop_main() -> None:
    """Explicit placeholder callable for transports without domain logic yet.

    Why
        Some tools expect a module-level ``main`` even when the underlying
        feature set is still stubbed out. Exposing this helper makes that
        contract obvious and easy to replace later.

    What
        Performs no work and returns immediately.

    Side Effects
        Emits a DEBUG-level log message indicating the no-op execution.

    Examples
    --------
    >>> noop_main()
    """

    logger.debug("Executing noop_main placeholder")
    return None


def check_pools_once(config: dict[str, Any] | None = None) -> CheckResult:
    """Perform one-shot check of all ZFS pools against configured thresholds.

    Why
    ---
    Administrators need to check pool health on-demand without running a
    daemon, either for manual inspection or integration with external
    monitoring tools.

    What
    ---
    1. Loads configuration
    2. Queries ZFS pools
    3. Checks against thresholds
    4. Returns structured result

    Parameters
    ----------
    config:
        Optional configuration dict. If None, loads from layered config.

    Returns
    -------
    CheckResult
        Structured result containing pools and issues.

    Raises
    ------
    ZFSNotAvailableError
        When zpool command is not available.
    RuntimeError
        When ZFS commands fail or parsing errors occur.
    """
    if config is None:
        config = get_config().as_dict()

    logger.info("Performing one-shot pool check")

    # Initialize components
    client = ZFSClient()
    parser = ZFSParser()
    monitor_config = _build_monitor_config(config)
    monitor = PoolMonitor(monitor_config)

    # Fetch and parse pool data (single command with --json-int provides all data)
    try:
        status_data = client.get_pool_status()
        pools = parser.parse_pool_status(status_data)

        logger.info("Fetched pool data", extra={"pool_count": len(pools)})

    except ZFSNotAvailableError:
        logger.error("ZFS not available on this system")
        raise
    except Exception as exc:
        logger.error(
            "Failed to fetch/parse pool data",
            extra={"error": str(exc), "error_type": type(exc).__name__},
            exc_info=True,
        )
        raise RuntimeError(f"Failed to check pools: {exc}") from exc

    # Check pools against thresholds
    result = monitor.check_all_pools(pools)

    logger.info(
        "Pool check completed",
        extra={
            "pools_checked": len(pools),
            "issues_found": len(result.issues),
            "severity": result.overall_severity.value,
        },
    )

    return result


def _load_config_with_logging(config: dict[str, Any] | None) -> dict[str, Any]:
    """Load and log configuration sources.

    Why
    ---
    Centralizes configuration loading and diagnostic logging.
    """
    if config is not None:
        return config

    config_obj = get_config()
    config = config_obj.as_dict()

    # Log configuration sources for debugging
    logger.info(
        "Configuration loaded from layered sources",
        extra={
            "config_keys": list(config.keys()),
            "has_email": "email" in config,
            "has_alerts": "alerts" in config,
            "has_monitoring": "monitoring" in config,
            "has_daemon": "daemon" in config,
        },
    )

    # Log expected config file paths for troubleshooting
    logger.info(
        "Configuration file search paths (Linux)",
        extra={
            "app_layer": "/etc/check_zpools/config.toml",
            "host_layer": "/etc/xdg/check_zpools/config.toml",
            "user_layer": "~/.config/check_zpools/config.toml",
            "precedence": "defaults → app → host → user → dotenv → env",
        },
    )

    return config


def _initialize_daemon_components(
    config: dict[str, Any],
) -> tuple[ZFSClient, PoolMonitor, EmailAlerter, AlertStateManager, dict[str, Any]]:
    """Initialize all daemon components.

    Why
    ---
    Separates component initialization from daemon lifecycle management.
    """
    # Validate ZFS availability
    client = ZFSClient()
    if not client.check_zpool_available():
        raise ZFSNotAvailableError("zpool command not found - is ZFS installed?")

    # Initialize monitoring
    monitor_config = _build_monitor_config(config)
    monitor = PoolMonitor(monitor_config)

    # Initialize alerting with threshold values from monitor config
    email_config = load_email_config_from_dict(config)
    alert_config = config.get("alerts", {})
    alerter = EmailAlerter(
        email_config,
        alert_config,
        capacity_warning_percent=monitor_config.capacity_warning_percent,
        capacity_critical_percent=monitor_config.capacity_critical_percent,
        scrub_max_age_days=monitor_config.scrub_max_age_days,
        zfs_client=client,
    )

    # Initialize state management
    state_file = _get_state_file_path(config)
    resend_interval = config.get("daemon", {}).get("alert_resend_interval_hours", 24)
    state_manager = AlertStateManager(state_file, resend_interval)

    daemon_config = config.get("daemon", {})

    return client, monitor, alerter, state_manager, daemon_config


def run_daemon(config: dict[str, Any] | None = None, foreground: bool = False) -> None:
    """Start daemon mode for continuous ZFS pool monitoring.

    Why
    ---
    Proactive monitoring requires a long-running process that periodically
    checks pools and sends alerts when issues are detected.

    What
    ---
    1. Loads configuration
    2. Initializes all components (client, monitor, alerter, state manager)
    3. Starts daemon loop
    4. Runs until SIGTERM/SIGINT received

    Parameters
    ----------
    config:
        Optional configuration dict. If None, loads from layered config.
    foreground:
        If True, run in foreground (don't daemonize). Useful for systemd
        Type=simple services and debugging.

    Raises
    ------
    ZFSNotAvailableError
        When zpool command is not available.
    RuntimeError
        When daemon initialization fails.
    """
    config = _load_config_with_logging(config)
    logger.info("Starting daemon mode", extra={"foreground": foreground})

    client, monitor, alerter, state_manager, daemon_config = _initialize_daemon_components(config)

    # Create and start daemon
    daemon = ZPoolDaemon(
        zfs_client=client,
        monitor=monitor,
        alerter=alerter,
        state_manager=state_manager,
        config=daemon_config,
    )

    try:
        daemon.start()
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as exc:
        logger.error(
            "Daemon failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
            exc_info=True,
        )
        raise


def _build_monitor_config(config: dict[str, Any]) -> MonitorConfig:
    """Build MonitorConfig from layered configuration dict.

    Parameters
    ----------
    config:
        Configuration dict from layered config system.

    Returns
    -------
    MonitorConfig
        Monitor configuration object.

    Raises
    ------
    ValueError
        If configuration values are invalid or inconsistent.
    """
    zfs_config = config.get("zfs", {})

    # Extract values with defaults (keys are at zfs root level)
    warning = zfs_config.get("capacity_warning_percent", 80)
    critical = zfs_config.get("capacity_critical_percent", 90)
    scrub_age = zfs_config.get("scrub_max_age_days", 30)
    read_errors = zfs_config.get("read_errors_warning", 1)
    write_errors = zfs_config.get("write_errors_warning", 1)
    checksum_errors = zfs_config.get("checksum_errors_warning", 1)

    # Validate capacity thresholds
    if not (0 < warning < 100):
        raise ValueError(f"zfs.capacity_warning_percent must be between 0 and 100, got {warning}")
    if not (0 < critical <= 100):
        raise ValueError(f"zfs.capacity_critical_percent must be between 0 and 100, got {critical}")
    if warning >= critical:
        raise ValueError(f"zfs.capacity_warning_percent ({warning}%) must be less than capacity_critical_percent ({critical}%)")

    # Validate scrub age
    if scrub_age < 0:
        raise ValueError(f"zfs.scrub_max_age_days must be non-negative, got {scrub_age}")

    # Validate error thresholds
    if read_errors < 0:
        raise ValueError(f"zfs.read_errors_warning must be non-negative, got {read_errors}")
    if write_errors < 0:
        raise ValueError(f"zfs.write_errors_warning must be non-negative, got {write_errors}")
    if checksum_errors < 0:
        raise ValueError(f"zfs.checksum_errors_warning must be non-negative, got {checksum_errors}")

    return MonitorConfig(
        capacity_warning_percent=warning,
        capacity_critical_percent=critical,
        scrub_max_age_days=scrub_age,
        read_errors_warning=read_errors,
        write_errors_warning=write_errors,
        checksum_errors_warning=checksum_errors,
    )


def _get_state_file_path(config: dict[str, Any]) -> Path:
    """Get path to alert state file from configuration.

    Parameters
    ----------
    config:
        Configuration dict from layered config system.

    Returns
    -------
    Path
        Path to state file. Defaults to platform-specific cache directory.
    """
    daemon_config = config.get("daemon", {})
    state_path = daemon_config.get("state_file")

    if state_path:
        return Path(state_path)

    # Default to platform-specific cache directory
    if sys.platform == "linux":
        base_dir = Path("/var/cache/check_zpools")
    elif sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Caches" / "check_zpools"
    else:
        base_dir = Path.home() / ".cache" / "check_zpools"

    return base_dir / "alert_state.json"


__all__ = [
    "CANONICAL_GREETING",
    "emit_greeting",
    "raise_intentional_failure",
    "noop_main",
    "check_pools_once",
    "run_daemon",
]
