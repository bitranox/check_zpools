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


def _detect_uvx_from_process_tree() -> tuple[Path | None, str | None]:
    """Detect uvx installation and extract version from process tree.

    This is the single source of truth for uvx detection. It walks the process
    tree looking for the "uv tool uvx" pattern that uvx always uses, then
    extracts both the uvx path and version specifier in a single pass.

    Returns
        Tuple of (uvx_path, version_spec):
        - uvx_path: Path to uvx executable, or None if not running under uvx
        - version_spec: Version like '@latest', '@1.0.0', or None if no version

    Root Cause
        uvx execs to "uv tool uvx", so the process tree contains:
        ['/path/to/uv', 'tool', 'uvx', 'check_zpools@version', ...]
        We detect this pattern, find uvx as a sibling of uv, and extract
        the version in the same pass.

    Examples
        >>> # When invoked as: uvx check_zpools@latest service-install
        >>> uvx_path, version = _detect_uvx_from_process_tree()  # doctest: +SKIP
        >>> print(uvx_path, version)  # doctest: +SKIP
        Path('/usr/local/bin/uvx') '@latest'
    """
    try:
        import psutil
        import re

        version_pattern = re.compile(r"check_zpools(@[a-zA-Z0-9._-]+)")
        current_process = psutil.Process()
        ancestor = current_process.parent()

        # Walk up process tree (max 10 levels)
        for depth in range(10):
            if not ancestor:
                break

            try:
                cmdline = ancestor.cmdline()
                if not cmdline or len(cmdline) < 3:
                    ancestor = ancestor.parent()
                    continue

                # Look for "uv tool uvx" pattern
                if Path(cmdline[0]).name in ("uv", "uv.exe") and cmdline[1:3] == ["tool", "uvx"]:
                    # Found uvx! Now find the uvx executable and extract version
                    uv_path = Path(cmdline[0]).resolve()
                    uvx_path = uv_path.parent / "uvx"

                    if not uvx_path.exists():
                        logger.debug(f"Found 'uv tool uvx' but uvx not found at: {uvx_path}")
                        ancestor = ancestor.parent()
                        continue

                    # Extract version from any argument containing check_zpools@version
                    version_spec = None
                    for arg in cmdline:
                        if "check_zpools" in arg:
                            match = version_pattern.search(arg)
                            if match:
                                version_spec = match.group(1)
                                break

                    logger.info(f"Detected uvx: {uvx_path}, version: {version_spec or 'unspecified'}")
                    return (uvx_path, version_spec)

                ancestor = ancestor.parent()

            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.debug(f"Process access error at depth {depth}: {e}")
                break
            except Exception as e:
                logger.debug(f"Error checking ancestor at depth {depth}: {e}")
                ancestor = ancestor.parent()

    except Exception as e:
        logger.debug(f"Process tree detection failed: {e}")

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
        3. Otherwise: find check_zpools in PATH (direct installation)
        4. Fail if neither works

    Raises
        FileNotFoundError: When neither uvx nor direct installation detected.
    """
    # First, check if running under uvx (this is the source of truth)
    uvx_path, uvx_version = _detect_uvx_from_process_tree()
    if uvx_path:
        logger.info(f"Installation method: uvx ({uvx_path})")
        return ("uvx", uvx_path, uvx_version)

    # Not uvx - must be direct installation, find in PATH
    exec_path_str = shutil.which("check_zpools")
    if not exec_path_str:
        raise FileNotFoundError(
            "check_zpools not found in PATH and not running under uvx.\n"
            "Install with: pip install check_zpools\n"
            "Or run via: uvx check_zpools@latest service-install"
        )

    exec_path = Path(exec_path_str).resolve()
    logger.info(f"Installation method: direct ({exec_path})")
    return ("direct", exec_path, None)


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
            logger.debug(f"Directory already exists: {directory}")
            continue

        logger.info(f"Creating directory: {directory}")
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
Wants=network-online.target
Requires=zfs-mount.service

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

    # Detect installation method and find executable (unified call)
    method, executable_path, detected_version = _find_executable()

    # Use detected version if not manually specified (uvx only)
    if method == "uvx":
        if not uvx_version:
            uvx_version = detected_version

        if not uvx_version:
            logger.warning("uvx detected but no version specifier found.")
            logger.warning("Service will use 'uvx check_zpools' without version.")
            logger.warning("This may fail. Use explicit version: uvx check_zpools@2.0.4 service-install")
            logger.warning("Or use @latest for auto-updates (not recommended for production)")

    # Create directories
    _create_service_directories()

    # Install service file
    _install_service_file(executable_path, method, uvx_version)

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
