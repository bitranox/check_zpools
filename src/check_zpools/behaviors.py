"""Domain-level behaviors for ZFS pool monitoring.

Purpose
-------
Implement core ZFS monitoring behaviors that the CLI adapter exposes, including
one-shot pool checks and daemon mode execution. Each behavior is self-contained
and delegates to domain services for actual work.

Contents
--------
* :func:`check_pools_once` - perform one-shot check of all pools
* :func:`run_daemon` - start daemon mode for continuous monitoring
* :func:`scrub_pools` - start scrubs and wait for them to finish
* :func:`deliver_scrub_summary` - email the result of a scrub cycle

System Role
-----------
Acts as the behavior layer in Clean Architecture, delegating to domain services
(ZFSClient, PoolMonitor, EmailAlerter, etc.) while providing CLI-friendly
interfaces.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .alert_state import AlertStateManager
from .alerting import EmailAlerter
from .config import load_settings
from .daemon import ZPoolDaemon
from .models import CheckResult, CheckZpoolsConfig, DaemonConfig, ScrubCycleResult, ScrubRunOptions
from .monitor import PoolMonitor
from .scrub_report import send_scrub_summary
from .scrub_runner import run_scrub_cycle
from .zfs_client import ZFSClient, ZFSNotAvailableError
from .zfs_parser import ZFSParser

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Module logger using standard logging interface.
logger = logging.getLogger(__name__)


def check_pools_once(config: CheckZpoolsConfig | None = None) -> CheckResult:
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
    settings = config if config is not None else load_settings()

    logger.info("Performing one-shot pool check")

    # Initialize components
    client = ZFSClient()
    parser = ZFSParser()
    monitor = PoolMonitor(settings.zfs)

    # Fetch and parse pool data (single command with --json-int provides all data)
    try:
        status_data = client.get_pool_status()
        pools = parser.parse_pool_status(status_data)

        logger.info("Fetched pool data", extra={"pool_count": len(pools)})

    except ZFSNotAvailableError:
        logger.error("ZFS not available on this system")
        raise
    except Exception as exc:
        logger.exception(
            "Failed to fetch/parse pool data",
            extra={"error": str(exc), "error_type": type(exc).__name__},
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


def scrub_pools(
    config: CheckZpoolsConfig | None = None,
    *,
    pools: Sequence[str] | None = None,
    wait: bool = True,
    poll_interval_seconds: float | None = None,
    dry_run: bool = False,
) -> ScrubCycleResult:
    """Start a scrub on the configured pools and wait for it to finish.

    Why
        Scrubbing is normally driven by a timer, and the classic shell version
        of this (a `sleep` loop with a hard timeout) reports a healthy but slow
        pool as a failure once the pool outgrows the timeout. This waits for
        the scrub itself instead of for a clock.

    Parameters
    ----------
    config:
        Optional configuration dict. If None, loads from layered config.
    pools:
        Pools to scrub. None falls back to the configured list, which in turn
        defaults to every pool on the host.
    wait:
        When False, start the scrubs and return without waiting.
    poll_interval_seconds:
        Override the configured polling cadence.
    dry_run:
        Report what would happen without starting anything.

    Returns
    -------
    ScrubCycleResult
        Per-pool outcomes and cycle timing.

    Raises
    ------
    ZFSNotAvailableError
        When the zpool command is not available.
    """
    scrub = (config if config is not None else load_settings()).scrub
    options = ScrubRunOptions(
        pools=tuple(pools) if pools else tuple(scrub.pools),
        wait=wait,
        poll_interval_seconds=poll_interval_seconds if poll_interval_seconds is not None else scrub.poll_interval_seconds,
        skip_if_other_scan_running=scrub.skip_if_other_scan_running,
        dry_run=dry_run,
    )

    return run_scrub_cycle(ZFSClient(), options, parser=ZFSParser())


def deliver_scrub_summary(result: ScrubCycleResult, config: CheckZpoolsConfig | None = None) -> bool:
    """Email the summary of a finished scrub cycle, if configuration asks for it.

    Why
        Keeps the "should this be mailed at all" policy (scrub.send_email,
        scrub.email_on_success) out of the CLI adapter.

    Parameters
    ----------
    result:
        The finished scrub cycle.
    config:
        Optional configuration dict. If None, loads from layered config.

    Returns
    -------
    bool
        True when a mail was sent, False when configuration suppressed it.

    Raises
    ------
    RuntimeError
        When SMTP delivery fails.
    """
    settings = config if config is not None else load_settings()

    if not settings.scrub.send_email:
        logger.info("Scrub summary email disabled by configuration")
        return False
    if not result.has_problems() and not settings.scrub.email_on_success:
        logger.info("Scrub completed without problems and email_on_success is off, not sending")
        return False

    return send_scrub_summary(
        result,
        email_config=settings.email,
        recipients=settings.alerts.alert_recipients,
        subject_prefix=settings.alerts.subject_prefix,
    )


def _load_config_with_logging(config: CheckZpoolsConfig | None) -> CheckZpoolsConfig:
    """Load and log configuration sources.

    Why
    ---
    Centralizes configuration loading and diagnostic logging.
    """
    if config is not None:
        return config

    settings = load_settings()

    # Log expected config file paths for troubleshooting
    logger.info(
        "Configuration loaded from layered sources",
        extra={
            "app_layer": "/etc/check_zpools/config.toml",
            "host_layer": "/etc/xdg/check_zpools/config.toml",
            "user_layer": "~/.config/check_zpools/config.toml",
            "precedence": "defaults -> app -> host -> user -> dotenv -> env",
        },
    )

    return settings


def _initialize_daemon_components(
    settings: CheckZpoolsConfig,
) -> tuple[ZFSClient, PoolMonitor, EmailAlerter, AlertStateManager, DaemonConfig]:
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
    monitor = PoolMonitor(settings.zfs)

    # Initialize alerting with threshold values from the monitoring section
    alerter = EmailAlerter(
        settings.email,
        settings.alerts,
        capacity_warning_percent=settings.zfs.capacity_warning_percent,
        capacity_critical_percent=settings.zfs.capacity_critical_percent,
        scrub_max_age_days=settings.zfs.scrub_max_age_days,
        zfs_client=client,
    )

    # Initialize state management
    state_manager = AlertStateManager(_get_state_file_path(settings), settings.daemon.alert_resend_interval_hours)

    return client, monitor, alerter, state_manager, settings.daemon


def run_daemon(config: CheckZpoolsConfig | None = None, *, foreground: bool = False) -> None:
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
    settings = _load_config_with_logging(config)
    logger.info("Starting daemon mode", extra={"foreground": foreground})

    client, monitor, alerter, state_manager, daemon_config = _initialize_daemon_components(settings)

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
        logger.exception(
            "Daemon failed",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        raise


def _get_state_file_path(settings: CheckZpoolsConfig) -> Path:
    """Get path to alert state file from configuration.

    Parameters
    ----------
    settings:
        The parsed configuration.

    Returns
    -------
    Path
        Path to state file. Defaults to platform-specific cache directory.
    """
    if settings.daemon.state_file:
        return Path(settings.daemon.state_file)

    # Default to platform-specific cache directory
    if sys.platform == "linux":
        base_dir = Path("/var/cache/check_zpools")
    elif sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Caches" / "check_zpools"
    else:
        base_dir = Path.home() / ".cache" / "check_zpools"

    return base_dir / "alert_state.json"


__all__ = [
    "check_pools_once",
    "run_daemon",
]
