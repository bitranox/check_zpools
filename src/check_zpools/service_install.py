"""Systemd service installation and management.

Purpose
-------
Provide CLI commands to install, uninstall, and manage the check_zpools systemd
service for automatic ZFS monitoring.

Contents
--------
* :func:`install_service` - Install and enable systemd service
* :func:`uninstall_service` - Stop and remove systemd service
* :func:`get_service_status` - Check if service is installed and running

System Role
-----------
Manages systemd service lifecycle, including file installation, daemon reload,
and service enable/start operations.

Security Considerations
-----------------------
- Requires root privileges (sudo) for systemd operations
- Service file installed to /etc/systemd/system/
- Creates necessary directories with appropriate permissions
- Validates paths and permissions before installation
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess  # nosec B404 - subprocess used safely with list arguments, not shell=True
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import rich_click as click

if TYPE_CHECKING:
    import psutil

logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "check_zpools.service"
SYSTEMD_SYSTEM_DIR = Path("/etc/systemd/system")
SERVICE_FILE_PATH = SYSTEMD_SYSTEM_DIR / SERVICE_NAME

# Directories that service needs
CACHE_DIR = Path("/var/cache/check_zpools")
LIB_DIR = Path("/var/lib/check_zpools")

#: Minimum cmdline length to contain the "<uv> tool uvx" pattern.
MIN_UVX_CMDLINE_LENGTH = 3

#: Expected number of parts when splitting a systemd timestamp off its trailing timezone name.
TIMESTAMP_PARTS_WITH_TIMEZONE = 2

#: Maximum number of issues listed individually before summarizing the rest.
MAX_ISSUES_DISPLAYED = 5


def _check_root_privileges() -> None:
    """Verify script is running with root privileges.

    Why
        Systemd service installation requires root access for writing to
        /etc/systemd/system and managing service state.

    Raises
        PermissionError: When not running as root.
        NotImplementedError: On Windows (systemd not supported).
    """
    if platform.system() == "Windows":
        raise NotImplementedError("Systemd service installation is not supported on Windows")

    # Use hasattr check for type checker compatibility across platforms
    if not hasattr(os, "geteuid") or os.geteuid() != 0:  # type: ignore[attr-defined]
        logger.error("Service installation requires root privileges")
        raise PermissionError("This command must be run as root (use sudo).\nExample: sudo check_zpools install-service")


def _is_uvx_process(cmdline: list[str]) -> bool:
    """Check if command line matches uvx process pattern.

    Parameters
    ----------
    cmdline:
        Process command line arguments.

    Returns
    -------
    bool:
        True if command line is "uv tool uvx" pattern.
    """
    if not cmdline or len(cmdline) < MIN_UVX_CMDLINE_LENGTH:
        return False
    return Path(cmdline[0]).name in ("uv", "uv.exe") and cmdline[1:3] == ["tool", "uvx"]


def _find_uvx_executable(uv_path: Path) -> Path | None:
    """Find uvx executable as sibling of uv.

    Parameters
    ----------
    uv_path:
        Path to the uv executable.

    Returns
    -------
    Path | None:
        Path to uvx executable if it exists, None otherwise.
    """
    uvx_path = uv_path.parent / "uvx"
    if uvx_path.exists():
        return uvx_path
    logger.debug("uvx not found at expected location: %s", uvx_path)
    return None


def _extract_version_from_cmdline(cmdline: list[str]) -> str | None:
    """Extract version specifier from command line arguments.

    Parameters
    ----------
    cmdline:
        Process command line arguments.

    Returns
    -------
    str | None:
        Version specifier like '@latest' or '@1.0.0', or None if not found.
    """
    version_pattern = re.compile(r"check_zpools(@[a-zA-Z0-9._-]+)")
    for arg in cmdline:
        if "check_zpools" in arg:
            match = version_pattern.search(arg)
            if match:
                return match.group(1)
    return None


def _check_ancestor_for_uvx(ancestor: psutil.Process, cmdline: list[str]) -> tuple[Path | None, str | None]:
    """Check if ancestor process is uvx and extract details.

    Parameters
    ----------
    ancestor:
        Process to check.
    cmdline:
        Command line arguments of the process.

    Returns
    -------
    tuple[Path | None, str | None]:
        Tuple of (uvx_path, version_spec) if uvx found, otherwise (None, None).
    """
    if not _is_uvx_process(cmdline):
        return (None, None)

    uv_path = Path(cmdline[0]).resolve()
    uvx_path = _find_uvx_executable(uv_path)

    if not uvx_path:
        return (None, None)

    version_spec = _extract_version_from_cmdline(cmdline)
    logger.info("Detected uvx: %s, version: %s", uvx_path, version_spec or "unspecified")
    return (uvx_path, version_spec)


def _walk_process_ancestors(start_process: psutil.Process) -> tuple[Path | None, str | None]:
    """Walk process tree looking for uvx.

    Parameters
    ----------
    start_process:
        Starting process to walk from.

    Returns
    -------
    tuple[Path | None, str | None]:
        Tuple of (uvx_path, version_spec) if uvx found, otherwise (None, None).
    """
    # Deferred: mirrors the try/except ImportError guard in the caller so this
    # process-tree walk degrades gracefully if psutil is unavailable at runtime.
    import psutil  # noqa: PLC0415

    ancestor = start_process.parent()

    # Walk up process tree (max 10 levels)
    for depth in range(10):
        if not ancestor:
            break

        try:
            cmdline = ancestor.cmdline()
            uvx_result = _check_ancestor_for_uvx(ancestor, cmdline)
            if uvx_result[0]:  # uvx_path found
                return uvx_result

            ancestor = ancestor.parent()

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.debug("Process access error at depth %s: %s", depth, e)
            break
        except (psutil.Error, OSError, ValueError) as e:
            logger.debug("Error checking ancestor at depth %s: %s", depth, e)
            ancestor = ancestor.parent()

    return (None, None)


def _detect_uvx_from_process_tree() -> tuple[Path | None, str | None]:
    """Detect uvx installation and extract version from process tree.

    This is the single source of truth for uvx detection. It walks the process
    tree looking for the "uv tool uvx" pattern that uvx always uses, then
    extracts both the uvx path and version specifier in a single pass.

    Returns
    -------
    tuple[Path | None, str | None]:
        Tuple of (uvx_path, version_spec):
        - uvx_path: Path to uvx executable, or None if not running under uvx
        - version_spec: Version like '@latest', '@1.0.0', or None if no version

    Root Cause
    ----------
    uvx execs to "uv tool uvx", so the process tree contains:
    ['/path/to/uv', 'tool', 'uvx', 'check_zpools@version', ...]
    We detect this pattern, find uvx as a sibling of uv, and extract
    the version in the same pass.

    Examples
    --------
    >>> # When invoked as: uvx check_zpools@latest service-install
    >>> uvx_path, version = _detect_uvx_from_process_tree()  # doctest: +SKIP
    >>> print(uvx_path, version)  # doctest: +SKIP
    Path('/usr/local/bin/uvx') '@latest'
    """
    try:
        import psutil  # noqa: PLC0415 - deferred so ImportError below can be caught if psutil is unavailable

        current_process = psutil.Process()
        return _walk_process_ancestors(current_process)

    except (ImportError, OSError, RuntimeError) as e:  # psutil may not be installed (ImportError) or fail at runtime
        logger.debug("Process tree detection failed: %s", e)
        return (None, None)


def _find_executable() -> tuple[str, Path, str | None]:
    """Detect installation method and find executable path.

    This is the unified entry point for detecting how check_zpools is installed
    and locating the appropriate executable for the systemd service file.

    Returns
        Tuple of (method, executable_path, uvx_version):
        - method: "uvx" or "direct"
        - executable_path: Path to uvx or check_zpools executable
        - uvx_version: Version specifier like '@latest', or None

    Simplified Logic
        1. Check process tree for uvx (via "uv tool uvx" pattern)
        2. If uvx found: return uvx details
        3. Otherwise: use current executable path (sys.argv[0] or sys.executable)
        4. Fail if neither works

    Raises
        FileNotFoundError: When neither uvx nor direct installation detected.
    """
    # First, check if running under uvx (this is the source of truth)
    uvx_path, uvx_version = _detect_uvx_from_process_tree()
    if uvx_path:
        logger.info("Installation method: uvx (%s)", uvx_path)
        return ("uvx", uvx_path, uvx_version)

    # Not uvx - use the current executable path
    # Try sys.argv[0] first (the command that was run)
    if sys.argv[0] and Path(sys.argv[0]).exists():
        exec_path = Path(sys.argv[0]).resolve()
        logger.info("Installation method: direct (from sys.argv[0]: %s)", exec_path)
        return ("direct", exec_path, None)

    # Fallback: try to find in PATH
    exec_path_str = shutil.which("check_zpools")
    if exec_path_str:
        exec_path = Path(exec_path_str).resolve()
        logger.info("Installation method: direct (from PATH: %s)", exec_path)
        return ("direct", exec_path, None)

    # Last resort: use the Python executable with -m
    python_path = Path(sys.executable).resolve()
    logger.info("Installation method: direct (using python -m: %s)", python_path)
    return ("direct", python_path, None)


def _create_service_directories() -> None:
    """Create required directories for service operation.

    Why
        Service needs writable directories for cache and state storage.

    Side Effects
        Creates /var/cache/check_zpools and /var/lib/check_zpools with
        appropriate permissions (755, owned by root).
    """
    for directory in [CACHE_DIR, LIB_DIR]:
        if directory.exists():
            logger.debug("Directory already exists: %s", directory)
            continue

        logger.info("Creating directory: %s", directory)
        directory.mkdir(parents=True, mode=0o755, exist_ok=True)


def _generate_service_file_content(
    executable_path: Path,
    method: str,
    uvx_version: str | None = None,
) -> str:
    """Generate systemd service file content with correct executable path.

    Simplified to only support two installation methods:
    - "uvx": uvx-based installation (requires cache directory access)
    - "direct": Direct pip install (system or user)

    Parameters
    ----------
    executable_path:
        Absolute path to uvx executable or check_zpools executable.
    method:
        Installation method detected ("direct" or "uvx").
    uvx_version:
        Version specifier for uvx installations (e.g., '@latest', '@1.0.0').

    Returns
        Complete systemd service file content as string.
    """
    # Build ExecStart command based on installation method
    if method == "uvx":
        # uvx runs tools on-the-fly, creating temporary venvs in cache
        package_spec = f"check_zpools{uvx_version}" if uvx_version else "check_zpools"
        exec_start = f"{executable_path} {package_spec} daemon --foreground"
        # uvx needs write access to its cache directory (blocked by ProtectSystem=strict)
        extra_writable_paths = " /root/.cache/uv"
    else:
        # Direct installation - executable is already in PATH
        exec_start = f"{executable_path} daemon --foreground"
        extra_writable_paths = ""

    service_content = f"""[Unit]
Description=ZFS Pool Monitoring Daemon
Documentation=https://github.com/bitranox/check_zpools
After=network-online.target zfs-mount.service zfs-import.target
Wants=network-online.target zfs-mount.service

[Service]
Type=simple
User=root
Group=root

# Installation method: {method}
ExecStart={exec_start}

# Restart policy
Restart=on-failure
RestartSec=10s

# Resource limits
MemoryMax=256M
CPUQuota=10%

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={CACHE_DIR} {LIB_DIR}{extra_writable_paths}
ReadOnlyPaths=/etc/check_zpools /etc/xdg/check_zpools

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=check_zpools

# Environment
Environment="LOG_CONSOLE_LEVEL=INFO"
Environment="LOG_ENABLE_JOURNALD=true"
# This removes the emoji {{level_icon}} from the log format template, so journald logs will show clean text without the Unicode characters.
Environment="CHECK_ZPOOLS___LIB_LOG_RICH__CONSOLE_FORMAT_TEMPLATE={{timestamp}} {{LEVEL:>8}} {{logger_name}} - {{message}} {{context_fields}}"
# This forces console output without colors
Environment="CHECK_ZPOOLS___LIB_LOG_RICH__NO_COLOR=true"

# Graceful shutdown
TimeoutStopSec=30s
KillMode=mixed
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
"""
    return service_content


def _install_service_file(
    executable_path: Path,
    method: str,
    uvx_version: str | None = None,
) -> None:
    """Write systemd service file to /etc/systemd/system/.

    Parameters
    ----------
    executable_path:
        Absolute path to check_zpools executable or uvx for uvx installations.
    method:
        Installation method detected ("direct" or "uvx").
    uvx_version:
        Version specifier for uvx installations (e.g., '@latest', '@1.0.0').

    Side Effects
        Creates {SERVICE_FILE_PATH} with mode 644.
    """
    content = _generate_service_file_content(executable_path, method, uvx_version)
    logger.info("Installing service file: %s", SERVICE_FILE_PATH)
    SERVICE_FILE_PATH.write_text(content, encoding="utf-8")
    SERVICE_FILE_PATH.chmod(0o644)


def _run_systemctl(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute systemctl command.

    Parameters
    ----------
    command:
        Systemctl command arguments (e.g., ["daemon-reload"]).
    check:
        Whether to raise exception on non-zero exit code.

    Returns
        CompletedProcess with stdout/stderr captured.

    Raises
        subprocess.CalledProcessError: When check=True and command fails.
    """
    full_command = ["systemctl", *command]
    logger.debug("Running: %s", " ".join(full_command))
    return subprocess.run(  # noqa: S603  # nosec B603 - command is hardcoded systemctl with validated args
        full_command,
        check=check,
        capture_output=True,
        text=True,
    )


def _handle_uvx_version(method: str, detected_version: str | None, uvx_version: str | None) -> str | None:
    """Determine final uvx version to use and log warnings.

    Parameters
    ----------
    method:
        Installation method ('uvx' or 'direct').
    detected_version:
        Version detected from process tree.
    uvx_version:
        Version specified by user.

    Returns
    -------
    str | None:
        Final version to use, or None.
    """
    if method != "uvx":
        return None

    final_version = uvx_version or detected_version

    if not final_version:
        logger.warning("uvx detected but no version specifier found.")
        logger.warning("Service will use 'uvx check_zpools' without version.")
        logger.warning("This may fail. Use explicit version: uvx check_zpools@2.0.4 service-install")
        logger.warning("Or use @latest for auto-updates (not recommended for production)")

    return final_version


def _enable_and_start_service(*, enable: bool, start: bool) -> None:
    """Enable and/or start the systemd service.

    Parameters
    ----------
    enable:
        Whether to enable service on boot.
    start:
        Whether to start service immediately.
    """
    if enable:
        logger.info("Enabling service (start on boot)")
        _run_systemctl(["enable", SERVICE_NAME])

    if start:
        logger.info("Starting service")
        _run_systemctl(["start", SERVICE_NAME])


def _print_installation_summary(*, enable: bool, start: bool) -> None:
    """Print installation success message and useful commands.

    Parameters
    ----------
    enable:
        Whether service was enabled.
    start:
        Whether service was started.
    """
    click.echo("\n✓ check_zpools service installed successfully\n")

    if enable:
        click.echo("  • Service enabled (will start on boot)")
    if start:
        click.echo("  • Service started")

    click.echo("\nUseful commands:")
    click.echo(f"  • View status:  systemctl status {SERVICE_NAME}")
    click.echo(f"  • View logs:    journalctl -u {SERVICE_NAME} -f")
    click.echo(f"  • Stop service: systemctl stop {SERVICE_NAME}")
    click.echo(f"  • Disable:      systemctl disable {SERVICE_NAME}")
    click.echo("  • Uninstall:    check_zpools uninstall-service")


def install_service(*, enable: bool = True, start: bool = True, uvx_version: str | None = None) -> None:
    """Install check_zpools as a systemd service.

    Why
        Automates service installation, eliminating manual file copying and
        systemctl commands.

    What
        - Verifies root privileges
        - Locates check_zpools executable
        - Creates required directories
        - Installs service file to /etc/systemd/system/
        - Reloads systemd daemon
        - Optionally enables service (start on boot)
        - Optionally starts service immediately

    Parameters
    ----------
    enable:
        Enable service to start on boot (default: True).
    start:
        Start service immediately after installation (default: True).
    uvx_version:
        Version specifier for uvx installations (e.g., '@latest', '@1.0.0').
        Only used when installation method is detected as uvx. If None and
        uvx is detected, uses package name without version specifier.

    Side Effects
        - Creates service file in /etc/systemd/system/
        - Creates /var/cache/check_zpools and /var/lib/check_zpools
        - Reloads systemd daemon
        - Enables and/or starts service if requested
        - Logs all operations

    Raises
        PermissionError: When not running as root.
        FileNotFoundError: When check_zpools executable not found.
        subprocess.CalledProcessError: When systemctl command fails.

    Examples
    --------
    Install, enable, and start service:

    >>> install_service()  # doctest: +SKIP

    Install without starting:

    >>> install_service(start=False)  # doctest: +SKIP
    """
    logger.info("Installing check_zpools systemd service")
    _check_root_privileges()

    # Detect installation method and find executable
    method, executable_path, detected_version = _find_executable()
    final_uvx_version = _handle_uvx_version(method, detected_version, uvx_version)

    # Install service
    _create_service_directories()
    _install_service_file(executable_path, method, final_uvx_version)

    # Configure systemd
    logger.info("Reloading systemd daemon")
    _run_systemctl(["daemon-reload"])
    _enable_and_start_service(enable=enable, start=start)

    # Report completion
    logger.info("Service installation complete")
    _print_installation_summary(enable=enable, start=start)


def _check_service_file_exists() -> bool:
    """Check if service file exists and warn if not.

    Returns
    -------
    bool:
        True if service file exists, False otherwise.

    Side Effects
        Logs warning and prints message if file not found.
    """
    if SERVICE_FILE_PATH.exists():
        return True

    logger.warning("Service file not found: %s", SERVICE_FILE_PATH)
    click.echo(f"⚠ Service file not found: {SERVICE_FILE_PATH}")
    click.echo("Service may not be installed.")
    return False


def _run_systemctl_with_logging(action: str) -> None:
    """Run systemctl command with automatic error logging.

    Parameters
    ----------
    action:
        Systemctl action to perform (e.g., 'stop', 'disable').

    Side Effects
        Runs systemctl command and logs warnings on failure.
    """
    logger.info("%sing service", action.capitalize())
    result = _run_systemctl([action, SERVICE_NAME], check=False)
    if result.returncode != 0:
        logger.warning("Failed to %s service: %s", action, result.stderr)


def _stop_service_if_requested(*, stop: bool) -> None:
    """Stop service if requested.

    Parameters
    ----------
    stop:
        Whether to stop the service.

    Side Effects
        Runs systemctl stop command if stop=True. Logs warnings on failure.
    """
    if stop:
        _run_systemctl_with_logging("stop")


def _disable_service_if_requested(*, disable: bool) -> None:
    """Disable service if requested.

    Parameters
    ----------
    disable:
        Whether to disable the service.

    Side Effects
        Runs systemctl disable command if disable=True. Logs warnings on failure.
    """
    if disable:
        _run_systemctl_with_logging("disable")


def _remove_service_file() -> None:
    """Remove service file and reload systemd.

    Side Effects
        Deletes service file and runs systemctl daemon-reload.
    """
    logger.info("Removing service file: %s", SERVICE_FILE_PATH)
    SERVICE_FILE_PATH.unlink(missing_ok=True)

    logger.info("Reloading systemd daemon")
    _run_systemctl(["daemon-reload"])


def _print_uninstall_summary() -> None:
    """Print uninstallation completion message.

    Side Effects
        Prints success message and cleanup instructions to stdout.
    """
    click.echo("\n✓ check_zpools service uninstalled successfully\n")
    click.echo("Note: Cache and state directories remain:")
    click.echo(f"  • {CACHE_DIR}")
    click.echo(f"  • {LIB_DIR}")
    click.echo("\nTo remove these directories:")
    click.echo(f"  sudo rm -rf {CACHE_DIR} {LIB_DIR}")


def uninstall_service(*, stop: bool = True, disable: bool = True) -> None:
    """Uninstall check_zpools systemd service.

    Why
        Provides clean removal of service and associated files.

    What
        - Verifies root privileges
        - Optionally stops running service
        - Optionally disables service (remove from boot)
        - Removes service file from /etc/systemd/system/
        - Reloads systemd daemon

    Parameters
    ----------
    stop:
        Stop service before uninstalling (default: True).
    disable:
        Disable service before uninstalling (default: True).

    Side Effects
        - Stops service if requested
        - Disables service if requested
        - Removes service file from /etc/systemd/system/
        - Reloads systemd daemon
        - Logs all operations

    Raises
        PermissionError: When not running as root.
        subprocess.CalledProcessError: When systemctl command fails.

    Examples
    --------
    >>> uninstall_service()  # doctest: +SKIP
    """
    logger.info("Uninstalling check_zpools systemd service")
    _check_root_privileges()

    if not _check_service_file_exists():
        return

    _stop_service_if_requested(stop=stop)
    _disable_service_if_requested(disable=disable)
    _remove_service_file()

    logger.info("Service uninstallation complete")
    _print_uninstall_summary()


def get_service_status() -> dict[str, bool | str]:
    """Get current status of check_zpools service.

    Why
        Provides programmatic access to service state for diagnostics and
        monitoring.

    Returns
        Dictionary with status information:
        - installed: Whether service file exists
        - running: Whether service is currently running
        - enabled: Whether service starts on boot
        - status_text: Output from systemctl status

    Examples
    --------
    >>> status = get_service_status()  # doctest: +SKIP
    >>> if status["installed"]:  # doctest: +SKIP
    ...     click.echo(f"Service running: {status['running']}")
    """
    status = {
        "installed": SERVICE_FILE_PATH.exists(),
        "running": False,
        "enabled": False,
        "status_text": "",
    }

    if not status["installed"]:
        return status

    # Check if service is running
    result = _run_systemctl(["is-active", SERVICE_NAME], check=False)
    status["running"] = result.returncode == 0

    # Check if service is enabled
    result = _run_systemctl(["is-enabled", SERVICE_NAME], check=False)
    status["enabled"] = result.returncode == 0

    # Get full status text
    result = _run_systemctl(["status", SERVICE_NAME], check=False)
    status["status_text"] = result.stdout

    return status


def _get_service_start_time() -> datetime | None:
    """Get service start time from systemctl.

    Returns
    -------
    datetime | None
        Service start time in local timezone, or None if not available.
    """
    try:
        result = _run_systemctl(
            ["show", SERVICE_NAME, "--property=ActiveEnterTimestamp"],
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            # Output: ActiveEnterTimestamp=Wed 2025-11-26 10:30:00 CET
            match = re.search(r"ActiveEnterTimestamp=(.+)", result.stdout.strip())
            if match and match.group(1) and match.group(1) != "n/a":
                timestamp_str = match.group(1).strip()
                # Parse systemd timestamp - strip timezone name and parse datetime part
                # Format: "Wed 2025-11-26 10:30:00 CET" -> parse "Wed 2025-11-26 10:30:00"
                try:
                    # Remove the timezone abbreviation (last word) for parsing
                    parts = timestamp_str.rsplit(" ", 1)
                    if len(parts) == TIMESTAMP_PARTS_WITH_TIMEZONE:
                        datetime_part = parts[0]
                        # Parse without timezone, result is naive datetime in local time
                        parsed = datetime.strptime(datetime_part, "%a %Y-%m-%d %H:%M:%S")
                        # Make it timezone-aware using local timezone
                        return parsed.astimezone()
                except ValueError:
                    # Timestamp format didn't match, return None
                    logger.debug("Could not parse systemd timestamp: %s", timestamp_str)
    except (subprocess.SubprocessError, OSError) as exc:
        # Systemctl command failed or other error - not critical for status display
        logger.debug("Could not get service start time: %s", exc)
    return None


def _format_duration(delta: timedelta) -> str:
    """Format a timedelta as human-readable duration.

    Parameters
    ----------
    delta:
        Time duration to format.

    Returns
    -------
    str
        Formatted duration (e.g., "2d 3h 15m" or "45m 30s").
    """
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "0s"

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")

    return " ".join(parts[:3])  # Show at most 3 components


def _load_alert_state() -> dict[str, Any]:
    """Load alert state from the state file.

    Returns
    -------
    dict
        Alert state data with 'alerts' key, or empty dict on error.
    """
    state_file = CACHE_DIR / "alert_state.json"
    if not state_file.exists():
        return {}

    try:
        with state_file.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _get_daemon_config() -> dict[str, Any]:
    """Load daemon configuration from layered config.

    Why
        Uses the project's existing config adapter to read the daemon section,
        ensuring service status displays the same thresholds used at runtime.

    Returns
    -------
    dict
        Daemon configuration section, or empty dict on error.
    """
    try:
        # Deferred: isolates config-loading failures to the status display path
        # instead of risking install/uninstall on an unrelated config import error.
        from .config import get_config  # noqa: PLC0415

        config_dict = get_config().as_dict()
        return config_dict.get("daemon", {})
    except (ImportError, KeyError, OSError):
        return {}


def _get_pool_status_summary() -> tuple[int, int, list[str]]:
    """Get current ZFS pool and device status.

    Returns
    -------
    tuple[int, int, list[str]]
        (pool_count, faulted_device_count, list of issue descriptions)
    """
    try:
        # Deferred: avoids pulling in behaviors' full dependency graph (alerting,
        # mail, daemon, monitor, zfs client/parser) for install/uninstall commands
        # that never call this status-display helper.
        from .behaviors import check_pools_once  # noqa: PLC0415

        result = check_pools_once()
        pool_count = len(result.pools)
        faulted_count = sum(len(p.faulted_devices) for p in result.pools)

        issues = [f"{issue.pool_name}: {issue.message}" for issue in result.issues]

        return pool_count, faulted_count, issues
    except (RuntimeError, OSError, ValueError) as e:
        return 0, 0, [f"Error getting pool status: {e}"]


def _display_service_uptime(status: dict[str, bool | str]) -> None:
    """Print the service uptime line when the service is running.

    Why
        Extracted from show_service_status to keep that function's branch
        and statement count within the project's ruff (PLR0912/PLR0915)
        thresholds; pure display logic with no behavior change.
    """
    if not status["running"]:
        return

    start_time = _get_service_start_time()
    if not start_time:
        return

    # Use timezone-aware now() for proper comparison
    now = datetime.now(start_time.tzinfo) if start_time.tzinfo else datetime.now()
    uptime = now - start_time
    # Display in local timezone
    tz_name = start_time.strftime("%Z") or "local"
    click.echo(f"  • Started:  {start_time.strftime('%Y-%m-%d %H:%M:%S')} {tz_name} (uptime: {_format_duration(uptime)})")


def _display_daemon_config() -> float:
    """Print the daemon configuration section and return the alert resend hours.

    Why
        Extracted from show_service_status (see _display_service_uptime);
        the resend interval is also needed by _display_alert_states_section.
    """
    daemon_config = _get_daemon_config()
    check_interval = daemon_config.get("check_interval_seconds", 300)
    resend_hours = daemon_config.get("alert_resend_interval_hours", 2)

    click.echo("\nDaemon Configuration:")
    click.echo("-" * 56)
    click.echo(f"  • Check interval:     {check_interval}s ({check_interval // 60}m)")
    click.echo(f"  • Alert resend:       {resend_hours}h (email silencing period)")

    return resend_hours


def _display_pool_status_section() -> None:
    """Print the current pool status section.

    Why
        Extracted from show_service_status (see _display_service_uptime).
    """
    click.echo("\nCurrent Pool Status:")
    click.echo("-" * 56)
    pool_count, faulted_count, issues = _get_pool_status_summary()

    if pool_count == 0:
        click.echo("  • Could not retrieve pool status")
        return

    device_status = "✓ All OK" if faulted_count == 0 else f"✗ {faulted_count} FAULTED"
    click.echo(f"  • Pools monitored:    {pool_count}")
    click.echo(f"  • Device status:      {device_status}")

    if not issues:
        click.echo("  • Active issues:      None")
        return

    click.echo(f"  • Active issues:      {len(issues)}")
    for issue in issues[:MAX_ISSUES_DISPLAYED]:  # Show first N issues
        click.echo(f"      -> {issue}")
    if len(issues) > MAX_ISSUES_DISPLAYED:
        click.echo(f"      ... and {len(issues) - MAX_ISSUES_DISPLAYED} more")


def _format_alert_remaining(last_alerted_str: str | None, resend_hours: float, now: datetime) -> str:
    """Compute the human-readable "next email in" string for one alert state.

    Why
        Extracted from show_service_status (see _display_service_uptime).
    """
    if not last_alerted_str:
        return "unknown"

    try:
        last_alerted = datetime.fromisoformat(last_alerted_str.replace("Z", "+00:00"))
        next_alert = last_alerted + timedelta(hours=resend_hours)
        time_remaining = next_alert - now
    except (ValueError, TypeError):
        return "unknown"

    if time_remaining.total_seconds() > 0:
        return _format_duration(time_remaining)
    return "now (will send on next check)"


def _display_alert_states_section(resend_hours: float) -> None:
    """Print the active alert states section.

    Why
        Extracted from show_service_status (see _display_service_uptime).
    """
    alert_data = _load_alert_state()
    alerts = alert_data.get("alerts", {})

    if not alerts:
        click.echo("\nAlert State: No active alerts being tracked")
        return

    click.echo("\nActive Alert States:")
    click.echo("-" * 56)
    now = datetime.now(timezone.utc)

    for state in alerts.values():
        pool_name = state.get("pool_name", "unknown")
        category = state.get("issue_category", "unknown")
        alert_count = state.get("alert_count", 0)
        severity = state.get("last_severity", "UNKNOWN")
        remaining_str = _format_alert_remaining(state.get("last_alerted"), resend_hours, now)

        click.echo(f"  [{severity}] {pool_name}:{category}")
        click.echo(f"      Alerts sent: {alert_count}, Next email in: {remaining_str}")


def show_service_status() -> None:
    """Display service status with rich formatting.

    Why
        Provides user-friendly status display for CLI.

    Side Effects
        Prints status information to stdout.
    """
    status = get_service_status()

    click.echo("\ncheck_zpools Service Status")
    click.echo("=" * 56)

    if not status["installed"]:
        click.echo("✗ Service not installed")
        click.echo("\nTo install:")
        click.echo("  sudo check_zpools install-service")
        return

    click.echo(f"✓ Service file installed: {SERVICE_FILE_PATH}")
    click.echo(f"  • Running:  {'✓ Yes' if status['running'] else '✗ No'}")
    click.echo(f"  • Enabled:  {'✓ Yes (starts on boot)' if status['enabled'] else '✗ No'}")

    _display_service_uptime(status)
    resend_hours = _display_daemon_config()
    _display_pool_status_section()
    _display_alert_states_section(resend_hours)

    click.echo()  # Final newline


__all__ = [
    "get_service_status",
    "install_service",
    "show_service_status",
    "uninstall_service",
]
