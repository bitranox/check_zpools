"""Systemd service installation and management.

Purpose
-------
Provide CLI commands to install, uninstall, and manage the check_zpools systemd
service for automatic ZFS monitoring.

Contents
--------
* :func:`install_service` – Install and enable systemd service
* :func:`uninstall_service` – Stop and remove systemd service
* :func:`get_service_status` – Check if service is installed and running

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

import logging
import os
import shutil
import subprocess  # nosec B404 - subprocess used safely with list arguments, not shell=True
from pathlib import Path

logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "check_zpools.service"
SYSTEMD_SYSTEM_DIR = Path("/etc/systemd/system")
SERVICE_FILE_PATH = SYSTEMD_SYSTEM_DIR / SERVICE_NAME

# Directories that service needs
CACHE_DIR = Path("/var/cache/check_zpools")
LIB_DIR = Path("/var/lib/check_zpools")


def _check_root_privileges() -> None:
    """Verify script is running with root privileges.

    Why
        Systemd service installation requires root access for writing to
        /etc/systemd/system and managing service state.

    Raises
        PermissionError: When not running as root.
        NotImplementedError: On Windows (systemd not supported).
    """
    import platform

    if platform.system() == "Windows":
        raise NotImplementedError("Systemd service installation is not supported on Windows")

    # Use hasattr check for type checker compatibility across platforms
    if not hasattr(os, "geteuid") or os.geteuid() != 0:  # type: ignore[attr-defined]
        logger.error("Service installation requires root privileges")
        raise PermissionError("This command must be run as root (use sudo).\nExample: sudo check_zpools install-service")


def _detect_invocation_method() -> tuple[str, Path | None]:
    """Detect how check_zpools was invoked (direct, venv, uv, uvx, etc.).

    Why
        Different installation methods require different systemd ExecStart
        configurations. We need to preserve the execution environment.

    Returns
        Tuple of (method, path):
        - ("direct", Path): Direct executable (pip install --user, system)
        - ("venv", Path): Virtual environment (path to venv/bin/check_zpools)
        - ("uv", None): UV-managed project (use 'uv run check_zpools')
        - ("uvx", None): UV tool runner (use 'uvx check_zpools')

    Examples
        >>> method, path = _detect_invocation_method()  # doctest: +SKIP
        >>> if method == "venv":  # doctest: +SKIP
        ...     print(f"Running from venv: {path}")
    """
    import sys

    # First, try to get the path from how we were invoked
    # This handles cases like './check_zpools' or '/path/to/check_zpools'
    invoked_path = Path(sys.argv[0]).resolve()
    if invoked_path.exists() and invoked_path.name in ("check_zpools", "__main__.py"):
        # We were invoked directly, use this path
        exec_path_str = str(invoked_path)
        logger.debug(f"Using invoked path: {invoked_path}")
    else:
        # Fall back to searching PATH
        exec_path_str = shutil.which("check_zpools")

    # Check if we can find check_zpools at all
    exec_path = exec_path_str

    # If check_zpools is not directly in PATH, it might be uvx-only
    if exec_path is None:
        # Check if uvx is available
        uvx_path = shutil.which("uvx")
        if uvx_path is not None:
            logger.info("check_zpools not in PATH, but uvx found - assuming uvx installation")
            return ("uvx", None)

        logger.error("Could not find check_zpools executable in PATH")
        raise FileNotFoundError("check_zpools executable not found in PATH.\nPlease ensure it is installed and accessible.")

    exec_path_resolved = Path(exec_path).resolve()

    # Check if this is actually a uvx shim/wrapper
    # uvx creates wrappers in ~/.local/bin that aren't real installations
    if exec_path_resolved.parent.name == ".local" and (exec_path_resolved.parent.parent / ".local" / "bin").exists():
        # Could be uvx or regular pip install --user
        # Check if there's actual package data or just a shim
        try:
            # If this is a uvx shim, it will be very small and just redirect
            if exec_path_resolved.stat().st_size < 1000:  # Real Python scripts are usually larger
                logger.info("Detected uvx shim in ~/.local/bin")
                return ("uvx", None)
        except OSError:
            pass

    # Check if the executable is in uvx cache BEFORE checking venv
    # IMPORTANT: uvx creates temporary venvs, so we must check cache path first!
    # uvx stores tools in ~/.cache/uv/ or %LOCALAPPDATA%/uv/ (Windows)
    exec_path_str = str(exec_path_resolved)
    if "cache/uv/" in exec_path_str or "cache\\uv\\" in exec_path_str:
        logger.info("Detected uvx cache installation (cache/uv/ in path)")
        return ("uvx", None)

    # Check if running from a virtual environment
    # This must come AFTER uvx check because uvx uses temporary venvs
    if hasattr(sys, "prefix") and sys.prefix != sys.base_prefix:
        # We're in a venv
        venv_root = Path(sys.prefix)
        logger.info(f"Detected virtual environment: {venv_root}")
        return ("venv", exec_path_resolved)

    # Check if UV project is being used (UV_PROJECT_ROOT or pyproject.toml with uv.lock)
    if os.environ.get("UV_PROJECT_ROOT"):
        logger.info("Detected UV environment (UV_PROJECT_ROOT set)")
        return ("uv", None)

    # Check if the executable is in a UV project cache (.uv directory)
    if ".uv" in str(exec_path_resolved.parent) or "uv/cache" in exec_path_str:
        logger.info("Detected UV project cache installation (.uv in path)")
        return ("uv", None)

    # Check for uv.lock in the current or parent directories (UV project)
    current_dir = Path.cwd()
    for parent in [current_dir] + list(current_dir.parents)[:3]:  # Check up to 3 levels
        if (parent / "uv.lock").exists():
            logger.info(f"Detected UV project (uv.lock found in {parent})")
            return ("uv", None)

    # Default to direct installation
    logger.info(f"Using direct executable path: {exec_path_resolved}")
    return ("direct", exec_path_resolved)


def _find_executable() -> Path:
    """Locate the check_zpools executable in PATH.

    Why
        Need absolute path to executable for systemd ExecStart directive.

    Returns
        Absolute path to check_zpools executable (or uv/uvx for UV installations).

    Raises
        FileNotFoundError: When check_zpools not found in PATH.
    """
    method, path = _detect_invocation_method()

    if method == "uvx":
        # For uvx, we need the uvx command
        uvx_path = shutil.which("uvx")
        if uvx_path is None:
            raise FileNotFoundError("uvx installation detected but 'uvx' command not found in PATH")
        return Path(uvx_path).resolve()

    if method == "uv":
        # For UV project, we'll use 'uv run check_zpools'
        uv_path = shutil.which("uv")
        if uv_path is None:
            raise FileNotFoundError("UV installation detected but 'uv' command not found in PATH")
        return Path(uv_path).resolve()

    if path is None:
        raise FileNotFoundError("Could not determine executable path")

    return path


def _create_service_directories() -> None:
    """Create required directories for service operation.

    Why
        Service needs writable directories for cache and state storage.

    Side Effects
        Creates /var/cache/check_zpools and /var/lib/check_zpools with
        appropriate permissions (755, owned by root).
    """
    for directory in [CACHE_DIR, LIB_DIR]:
        if not directory.exists():
            logger.info(f"Creating directory: {directory}")
            directory.mkdir(parents=True, mode=0o755, exist_ok=True)
        else:
            logger.debug(f"Directory already exists: {directory}")


def _generate_service_file_content(
    executable_path: Path,
    method: str,
    venv_path: Path | None = None,
    uvx_version: str | None = None,
) -> str:
    """Generate systemd service file content with correct executable path.

    Parameters
    ----------
    executable_path:
        Absolute path to check_zpools executable (or uv/uvx for UV installations).
    method:
        Installation method detected ("direct", "venv", "uv", "uvx").
    venv_path:
        Path to virtual environment root (for venv installations).
    uvx_version:
        Version specifier for uvx installations (e.g., '@latest', '@1.0.0').

    Returns
        Complete systemd service file content as string.
    """
    # Determine the correct ExecStart command based on installation method
    if method == "uvx":
        # uvx runs tools on-the-fly without permanent installation
        # Add version specifier if provided (e.g., check_zpools@latest)
        package_spec = f"check_zpools{uvx_version}" if uvx_version else "check_zpools"
        exec_start = f"{executable_path} {package_spec} daemon --foreground"
        working_dir_line = ""  # uvx doesn't need specific working directory
    elif method == "uv":
        # uv run needs the project directory
        exec_start = f"{executable_path} run check_zpools daemon --foreground"
        working_dir_line = f"WorkingDirectory={Path.cwd()}"
    elif method == "venv" and venv_path:
        exec_start = f"{executable_path} daemon --foreground"
        # For venv, we need to ensure the venv's bin directory is in PATH
        venv_bin = venv_path / "bin"
        working_dir_line = f'Environment="PATH={venv_bin}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"'
    else:
        # Direct installation
        exec_start = f"{executable_path} daemon --foreground"
        working_dir_line = ""

    service_content = f"""[Unit]
Description=ZFS Pool Monitoring Daemon
Documentation=https://github.com/bitranox/check_zpools
After=network-online.target zfs-mount.service zfs-import.target
Wants=network-online.target
Requires=zfs-mount.service

[Service]
Type=simple
User=root
Group=root

# Path to check_zpools executable ({method} installation)
ExecStart={exec_start}
{working_dir_line}

# Restart policy
Restart=on-failure
RestartSec=10s

# Resource limits
MemoryLimit=256M
CPUQuota=10%

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={CACHE_DIR} {LIB_DIR}

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=check_zpools

# Environment
Environment="LOG_CONSOLE_LEVEL=INFO"
Environment="LOG_ENABLE_JOURNALD=true"

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
    venv_path: Path | None = None,
    uvx_version: str | None = None,
) -> None:
    """Write systemd service file to /etc/systemd/system/.

    Parameters
    ----------
    executable_path:
        Absolute path to check_zpools executable (or uv/uvx for UV installations).
    method:
        Installation method detected ("direct", "venv", "uv", "uvx").
    venv_path:
        Path to virtual environment root (for venv installations).
    uvx_version:
        Version specifier for uvx installations (e.g., '@latest', '@1.0.0').

    Side Effects
        Creates {SERVICE_FILE_PATH} with mode 644.
    """
    content = _generate_service_file_content(executable_path, method, venv_path, uvx_version)
    logger.info(f"Installing service file: {SERVICE_FILE_PATH}")
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
    full_command = ["systemctl"] + command
    logger.debug(f"Running: {' '.join(full_command)}")
    return subprocess.run(  # nosec B603 - command is hardcoded systemctl with validated args
        full_command,
        check=check,
        capture_output=True,
        text=True,
    )


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

    # Verify prerequisites
    _check_root_privileges()

    # Detect installation method
    method, detected_path = _detect_invocation_method()
    logger.info(f"Detected installation method: {method}")

    # Get the executable path (might be uv for UV installations)
    executable_path = _find_executable()
    logger.info(f"Using executable: {executable_path}")

    # Determine venv path if applicable
    venv_path = None
    if method == "venv" and detected_path:
        import sys

        venv_path = Path(sys.prefix)
        logger.info(f"Virtual environment: {venv_path}")

    # Create directories
    _create_service_directories()

    # Install service file
    _install_service_file(executable_path, method, venv_path, uvx_version)

    # Reload systemd daemon
    logger.info("Reloading systemd daemon")
    _run_systemctl(["daemon-reload"])

    # Enable service (start on boot)
    if enable:
        logger.info("Enabling service (start on boot)")
        _run_systemctl(["enable", SERVICE_NAME])

    # Start service now
    if start:
        logger.info("Starting service")
        _run_systemctl(["start", SERVICE_NAME])

    # Show status
    logger.info("Service installation complete")
    print("\n✓ check_zpools service installed successfully\n")

    if enable:
        print("  • Service enabled (will start on boot)")
    if start:
        print("  • Service started")

    print("\nUseful commands:")
    print(f"  • View status:  systemctl status {SERVICE_NAME}")
    print(f"  • View logs:    journalctl -u {SERVICE_NAME} -f")
    print(f"  • Stop service: systemctl stop {SERVICE_NAME}")
    print(f"  • Disable:      systemctl disable {SERVICE_NAME}")
    print("  • Uninstall:    check_zpools uninstall-service")


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

    # Verify prerequisites
    _check_root_privileges()

    # Check if service file exists
    if not SERVICE_FILE_PATH.exists():
        logger.warning(f"Service file not found: {SERVICE_FILE_PATH}")
        print(f"⚠ Service file not found: {SERVICE_FILE_PATH}")
        print("Service may not be installed.")
        return

    # Stop service
    if stop:
        logger.info("Stopping service")
        result = _run_systemctl(["stop", SERVICE_NAME], check=False)
        if result.returncode != 0:
            logger.warning(f"Failed to stop service: {result.stderr}")

    # Disable service
    if disable:
        logger.info("Disabling service")
        result = _run_systemctl(["disable", SERVICE_NAME], check=False)
        if result.returncode != 0:
            logger.warning(f"Failed to disable service: {result.stderr}")

    # Remove service file
    logger.info(f"Removing service file: {SERVICE_FILE_PATH}")
    SERVICE_FILE_PATH.unlink(missing_ok=True)

    # Reload systemd daemon
    logger.info("Reloading systemd daemon")
    _run_systemctl(["daemon-reload"])

    logger.info("Service uninstallation complete")
    print("\n✓ check_zpools service uninstalled successfully\n")
    print("Note: Cache and state directories remain:")
    print(f"  • {CACHE_DIR}")
    print(f"  • {LIB_DIR}")
    print("\nTo remove these directories:")
    print(f"  sudo rm -rf {CACHE_DIR} {LIB_DIR}")


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
    ...     print(f"Service running: {status['running']}")
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


def show_service_status() -> None:
    """Display service status with rich formatting.

    Why
        Provides user-friendly status display for CLI.

    Side Effects
        Prints status information to stdout.
    """
    status = get_service_status()

    print("\ncheck_zpools Service Status")
    print("=" * 40)

    if status["installed"]:
        print(f"✓ Service file installed: {SERVICE_FILE_PATH}")
        print(f"  • Running:  {'✓ Yes' if status['running'] else '✗ No'}")
        print(f"  • Enabled:  {'✓ Yes (starts on boot)' if status['enabled'] else '✗ No'}")
        print("\nService Details:")
        print("-" * 40)
        print(status["status_text"])
    else:
        print("✗ Service not installed")
        print("\nTo install:")
        print("  sudo check_zpools install-service")


__all__ = [
    "install_service",
    "uninstall_service",
    "get_service_status",
    "show_service_status",
]
