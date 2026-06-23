"""Bash alias management for check_zpools CLI.

Purpose
-------
Provide functions to create and remove shell function aliases in bashrc files,
enabling CLI access to venv-installed commands without activating the virtual
environment.

Contents
--------
* :func:`create_alias` - Create shell function alias in bashrc
* :func:`delete_alias` - Remove shell function alias from bashrc
* :func:`get_bashrc_path` - Get appropriate bashrc path for a user

System Role
-----------
Manages bashrc modifications with marked blocks for safe creation and removal
of shell function aliases.

Security Considerations
-----------------------
- Requires root privileges for system-wide /etc/bash.bashrc modifications
- User-specific aliases modify ~/.bashrc
- Uses marked blocks to safely identify and remove aliases
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# pwd module is only available on Unix-like systems
if sys.platform != "win32":
    import pwd
else:
    pwd = None  # type: ignore[assignment]

if TYPE_CHECKING:
    pass

from . import __init__conf__

logger = logging.getLogger(__name__)

# Marker format for identifying managed alias blocks
ALIAS_MARKER_START = f"# [ALIAS FOR {__init__conf__.shell_command}]"
ALIAS_MARKER_END = f"# [/ALIAS FOR {__init__conf__.shell_command}]"

# System-wide bashrc path
SYSTEM_BASHRC = Path("/etc/bash.bashrc")


def _check_root_privileges(username: str | None = None) -> None:
    """Verify script is running with root privileges.

    Parameters
    ----------
    username:
        If provided, indicates --user flag was used.

    Raises
        PermissionError: When not running as root.
        NotImplementedError: On Windows.
    """
    import platform

    system = platform.system()
    if system == "Windows":
        raise NotImplementedError("Alias management is not supported on Windows")
    if system == "Darwin":
        raise NotImplementedError("Alias management is not supported on macOS")

    if not hasattr(os, "geteuid") or os.geteuid() != 0:  # type: ignore[attr-defined]
        if username is not None:
            logger.error("--user flag requires root privileges")
            raise PermissionError(f"The --user flag requires root privileges.\nExample: sudo {__init__conf__.shell_command} alias-create --user {username}")
        logger.error("Alias management requires root privileges")
        raise PermissionError(f"This command must be run as root (use sudo).\nExample: sudo {__init__conf__.shell_command} alias-create")


def _get_user_info(username: str | None) -> tuple[str, Path]:
    """Get user information and home directory.

    Parameters
    ----------
    username:
        Username to look up, or None for current user.

    Returns
    -------
    tuple[str, Path]:
        Tuple of (username, home_directory).

    Raises
    ------
    KeyError:
        When username not found in passwd database.
    """
    if username is None:
        # Get the real user who invoked sudo (if applicable)
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user:
            username = sudo_user
        else:
            username = pwd.getpwuid(os.getuid()).pw_name  # type: ignore[union-attr, attr-defined]

    # At this point username is guaranteed to be str (either from parameter, SUDO_USER, or getpwuid)
    # Cast for pyright on Windows where pwd functions have Unknown return types
    resolved_username: str = str(username)

    try:
        pw_entry = pwd.getpwnam(resolved_username)  # type: ignore[union-attr, attr-defined]
        return (resolved_username, Path(pw_entry.pw_dir))
    except KeyError as exc:
        raise KeyError(f"User not found: {username}") from exc


def _get_bashrc_path_for_user(username: str | None) -> tuple[Path, str]:
    """Get bashrc path for specified user.

    Parameters
    ----------
    username:
        Username, or None for current/sudo user.

    Returns
    -------
    tuple[Path, str]:
        Tuple of (bashrc_path, resolved_username).
    """
    resolved_username, home_dir = _get_user_info(username)
    bashrc_path = home_dir / ".bashrc"
    return (bashrc_path, resolved_username)


def _build_exec_command() -> str:
    """Build the full execution command for the alias.

    Returns
    -------
    str:
        Full command string to execute check_zpools.
    """
    from .service_install import _find_executable

    method, executable_path, uvx_version = _find_executable()

    if method == "uvx":
        package_spec = f"{__init__conf__.shell_command}{uvx_version}" if uvx_version else __init__conf__.shell_command
        return f"{executable_path} {package_spec}"

    return str(executable_path)


def _generate_alias_block(exec_command: str) -> str:
    """Generate the shell function block for bashrc.

    Parameters
    ----------
    exec_command:
        Full command to execute check_zpools.

    Returns
    -------
    str:
        Complete shell function block with markers.
    """
    shell_command = __init__conf__.shell_command
    return f"""{ALIAS_MARKER_START}
{shell_command}() {{
    {exec_command} "$@"
}}
{ALIAS_MARKER_END}
"""


def _remove_existing_alias(content: str) -> str:
    """Remove existing alias block from bashrc content.

    Parameters
    ----------
    content:
        Current bashrc content.

    Returns
    -------
    str:
        Content with alias block removed.
    """
    # Escape special regex characters in markers
    start_escaped = re.escape(ALIAS_MARKER_START)
    end_escaped = re.escape(ALIAS_MARKER_END)

    # Pattern matches the entire block including markers and newlines
    pattern = rf"{start_escaped}.*?{end_escaped}\n?"

    return re.sub(pattern, "", content, flags=re.DOTALL)


def _has_existing_alias(content: str) -> bool:
    """Check if bashrc content contains our alias block.

    Parameters
    ----------
    content:
        Bashrc content to check.

    Returns
    -------
    bool:
        True if alias block exists.
    """
    return ALIAS_MARKER_START in content


def _ensure_file_exists(path: Path) -> None:
    """Ensure bashrc file exists, creating if necessary.

    Parameters
    ----------
    path:
        Path to bashrc file.
    """
    if not path.exists():
        logger.info(f"Creating bashrc file: {path}")
        path.touch(mode=0o644)


def _read_bashrc(path: Path) -> str:
    """Read bashrc content.

    Parameters
    ----------
    path:
        Path to bashrc file.

    Returns
    -------
    str:
        File content, or empty string if file doesn't exist.
    """
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _write_bashrc(path: Path, content: str) -> None:
    """Write content to bashrc file.

    Parameters
    ----------
    path:
        Path to bashrc file.
    content:
        Content to write.
    """
    path.write_text(content, encoding="utf-8")
    logger.debug(f"Updated bashrc: {path}")


def create_alias(username: str | None = None, all_users: bool = False) -> None:
    """Create shell function alias in user's bashrc or system-wide bashrc.

    Creates a marked block in the appropriate bashrc file containing a shell
    function that forwards all arguments to the check_zpools executable.

    Parameters
    ----------
    username:
        Target username for alias creation. If None, uses the user who
        invoked sudo (via SUDO_USER env var) or the current user.
        Ignored if all_users is True.
    all_users:
        If True, create alias in /etc/bash.bashrc for all users instead
        of a specific user's ~/.bashrc.

    Side Effects
        - Requires root privileges
        - Modifies ~/.bashrc for the target user OR /etc/bash.bashrc if all_users
        - Creates bashrc if it doesn't exist
        - Removes existing alias block before adding new one

    Raises
        PermissionError: When not running as root.
        KeyError: When username not found.
        FileNotFoundError: When executable not found.

    Examples
    --------
    Create alias for current user (via sudo):

    >>> create_alias()  # doctest: +SKIP

    Create alias for specific user:

    >>> create_alias(username="john")  # doctest: +SKIP

    Create alias for all users (system-wide):

    >>> create_alias(all_users=True)  # doctest: +SKIP
    """
    logger.info("Creating bash alias for check_zpools")
    _check_root_privileges(username if not all_users else None)

    # Determine target bashrc path
    if all_users:
        bashrc_path = SYSTEM_BASHRC
        resolved_username = "all users"
        logger.info(f"Target: system-wide, bashrc: {bashrc_path}")
    else:
        bashrc_path, resolved_username = _get_bashrc_path_for_user(username)
        logger.info(f"Target user: {resolved_username}, bashrc: {bashrc_path}")

    # Build execution command
    exec_command = _build_exec_command()
    logger.info(f"Executable command: {exec_command}")

    # Ensure bashrc exists
    _ensure_file_exists(bashrc_path)

    # Read current content
    content = _read_bashrc(bashrc_path)

    # Remove existing alias if present
    if _has_existing_alias(content):
        logger.info("Removing existing alias block")
        content = _remove_existing_alias(content)

    # Generate and append new alias block
    alias_block = _generate_alias_block(exec_command)

    # Ensure content ends with newline before adding block
    if content and not content.endswith("\n"):
        content += "\n"

    content += alias_block

    # Write updated content
    _write_bashrc(bashrc_path, content)

    _print_create_success(resolved_username, bashrc_path, exec_command, all_users)


def _print_create_success(username: str, bashrc_path: Path, exec_command: str, all_users: bool = False) -> None:
    """Print success message after alias creation.

    Parameters
    ----------
    username:
        Username the alias was created for, or "all users" for system-wide.
    bashrc_path:
        Path to the modified bashrc file.
    exec_command:
        The executable command configured.
    all_users:
        If True, alias was created for all users in /etc/bash.bashrc.
    """
    shell_command = __init__conf__.shell_command
    print(f"\n✓ Alias created for '{shell_command}'\n")
    print(f"  Target:   {username}")
    print(f"  File:     {bashrc_path}")
    print(f"  Command:  {exec_command}")
    print("\nTo activate the alias in current shell:")
    print(f"  source {bashrc_path}")
    print("\nOr open a new terminal session.")


def delete_alias(username: str | None = None, all_users: bool = False) -> None:
    """Remove shell function alias from user's bashrc or system-wide bashrc.

    Removes the marked block containing the check_zpools shell function
    from the appropriate bashrc file.

    Parameters
    ----------
    username:
        Target username for alias removal. If None, uses the user who
        invoked sudo (via SUDO_USER env var) or the current user.
        Ignored if all_users is True.
    all_users:
        If True, remove alias from /etc/bash.bashrc (system-wide).

    Side Effects
        - Requires root privileges
        - Modifies ~/.bashrc for the target user OR /etc/bash.bashrc if all_users
        - Only removes our marked block, preserves other content

    Raises
        PermissionError: When not running as root.
        KeyError: When username not found.

    Examples
    --------
    Remove alias for current user (via sudo):

    >>> delete_alias()  # doctest: +SKIP

    Remove alias for specific user:

    >>> delete_alias(username="john")  # doctest: +SKIP

    Remove alias for all users (system-wide):

    >>> delete_alias(all_users=True)  # doctest: +SKIP
    """
    logger.info("Removing bash alias for check_zpools")
    _check_root_privileges(username if not all_users else None)

    # Determine target bashrc path
    if all_users:
        bashrc_path = SYSTEM_BASHRC
        resolved_username = "all users"
        logger.info(f"Target: system-wide, bashrc: {bashrc_path}")
    else:
        bashrc_path, resolved_username = _get_bashrc_path_for_user(username)
        logger.info(f"Target user: {resolved_username}, bashrc: {bashrc_path}")

    # Check if bashrc exists
    if not bashrc_path.exists():
        logger.warning(f"Bashrc file not found: {bashrc_path}")
        print(f"\n⚠ Bashrc file not found: {bashrc_path}")
        print("No alias to remove.")
        return

    # Read current content
    content = _read_bashrc(bashrc_path)

    # Check if alias exists
    if not _has_existing_alias(content):
        logger.info("No alias block found in bashrc")
        print(f"\n⚠ No {__init__conf__.shell_command} alias found in {bashrc_path}")
        print("Nothing to remove.")
        return

    # Remove alias block
    new_content = _remove_existing_alias(content)

    # Write updated content
    _write_bashrc(bashrc_path, new_content)

    _print_delete_success(resolved_username, bashrc_path)


def _print_delete_success(username: str, bashrc_path: Path) -> None:
    """Print success message after alias removal.

    Parameters
    ----------
    username:
        Username the alias was removed for.
    bashrc_path:
        Path to the modified bashrc file.
    """
    shell_command = __init__conf__.shell_command
    print(f"\n✓ Alias removed for '{shell_command}'\n")
    print(f"  User:     {username}")
    print(f"  File:     {bashrc_path}")
    print("\nThe alias will no longer be available in new terminal sessions.")
    print("To remove from current shell, run:")
    print(f"  unset -f {shell_command}")


__all__ = [
    "create_alias",
    "delete_alias",
]
