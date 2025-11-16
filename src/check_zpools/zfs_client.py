"""ZFS command execution client.

Purpose
-------
Execute ZFS pool commands (`zpool list`, `zpool status`) and return their JSON
output. Handles command discovery, execution, error handling, and timeout
management.

Contents
--------
* :class:`ZFSCommandError` – Exception raised when ZFS commands fail
* :class:`ZFSNotAvailableError` – Exception raised when ZFS tools not found
* :class:`ZFSClient` – Main interface for executing ZFS commands

System Role
-----------
Serves as the boundary between check_zpools and the ZFS system. Encapsulates
all subprocess execution, providing clean error handling and timeouts. Parsers
consume the JSON output from this layer.

Architecture Notes
------------------
- Separate command execution from parsing (Single Responsibility)
- Synchronous execution with configurable timeouts
- Comprehensive error handling with detailed messages
- All methods are pure (no persistent state between calls)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ZFSCommandError(RuntimeError):
    """Exception raised when ZFS command execution fails.

    Why
        Distinguishes ZFS command failures from other runtime errors, enabling
        targeted exception handling.

    Attributes
    ----------
    command:
        The command that failed
    exit_code:
        Process exit code
    stderr:
        Standard error output from the command
    """

    def __init__(self, command: list[str], exit_code: int, stderr: str):
        """Initialize with command details.

        Parameters
        ----------
        command:
            Full command that was executed
        exit_code:
            Non-zero exit code from process
        stderr:
            Error output from command
        """
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(f"ZFS command failed (exit {exit_code}): {' '.join(command)}\n{stderr}")


class ZFSNotAvailableError(RuntimeError):
    """Exception raised when ZFS tools are not found.

    Why
        Distinguishes missing ZFS from other errors, enabling helpful error
        messages about installation.
    """

    pass


class ZFSClient:
    """Execute ZFS commands and return JSON output.

    Why
        Centralize ZFS command execution with consistent error handling,
        logging, and timeout management.

    Attributes
    ----------
    zpool_path:
        Path to zpool executable
    default_timeout:
        Default command timeout in seconds

    Examples
    --------
    >>> client = ZFSClient()  # doctest: +SKIP
    >>> data = client.get_pool_list()  # doctest: +SKIP
    >>> print(data["pools"].keys())  # doctest: +SKIP
    dict_keys(['rpool', 'zpool-data'])
    """

    def __init__(self, zpool_path: str | Path | None = None, default_timeout: int = 30):
        """Initialize ZFS client.

        Parameters
        ----------
        zpool_path:
            Path to zpool executable. If None, searches PATH.
        default_timeout:
            Default timeout for commands in seconds.

        Raises
        ------
        ZFSNotAvailableError:
            When zpool executable not found.
        """
        if zpool_path is None:
            found_path = shutil.which("zpool")
            if found_path is None:
                logger.error("zpool command not found in PATH")
                raise ZFSNotAvailableError(
                    "zpool command not found. Please install ZFS utilities.\n"
                    "On Debian/Ubuntu: apt install zfsutils-linux\n"
                    "On RHEL/CentOS: yum install zfs"
                )
            self.zpool_path = Path(found_path)
        else:
            self.zpool_path = Path(zpool_path)

        self.default_timeout = default_timeout
        logger.debug(f"ZFSClient initialized with zpool at {self.zpool_path}")

    def check_zpool_available(self) -> bool:
        """Verify zpool command is available and executable.

        Why
            Allows pre-flight checking before attempting commands.

        Returns
        -------
        bool:
            True if zpool exists and is executable.

        Examples
        --------
        >>> client = ZFSClient()  # doctest: +SKIP
        >>> client.check_zpool_available()  # doctest: +SKIP
        True
        """
        return self.zpool_path.exists() and self.zpool_path.is_file()

    def get_pool_list(
        self,
        *,
        pool_name: str | None = None,
        properties: list[str] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute `zpool list -j` and return parsed JSON.

        Why
            Gets high-level pool information including size, capacity, and
            health state. This is faster than `zpool status` and sufficient
            for capacity monitoring.

        Parameters
        ----------
        pool_name:
            Optional specific pool to query. If None, gets all pools.
        properties:
            Optional list of properties to retrieve. If None, uses ZFS defaults.
        timeout:
            Command timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        dict:
            Parsed JSON output from zpool list command.

        Raises
        ------
        ZFSCommandError:
            When command fails or returns non-zero exit code.
        json.JSONDecodeError:
            When command output is not valid JSON.

        Examples
        --------
        >>> client = ZFSClient()  # doctest: +SKIP
        >>> data = client.get_pool_list()  # doctest: +SKIP
        >>> "pools" in data  # doctest: +SKIP
        True
        """
        command = [str(self.zpool_path), "list", "-j"]

        if properties:
            command.extend(["-o", ",".join(properties)])

        if pool_name:
            command.append(pool_name)

        logger.debug(f"Executing: {' '.join(command)}")
        return self._execute_json_command(command, timeout=timeout)

    def get_pool_status(
        self,
        *,
        pool_name: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute `zpool status -j` and return parsed JSON.

        Why
            Gets detailed pool status including vdev layout, error counts,
            scrub status, and resilver progress. More comprehensive but slower
            than `zpool list`.

        Parameters
        ----------
        pool_name:
            Optional specific pool to query. If None, gets all pools.
        timeout:
            Command timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        dict:
            Parsed JSON output from zpool status command.

        Raises
        ------
        ZFSCommandError:
            When command fails or returns non-zero exit code.
        json.JSONDecodeError:
            When command output is not valid JSON.

        Examples
        --------
        >>> client = ZFSClient()  # doctest: +SKIP
        >>> data = client.get_pool_status()  # doctest: +SKIP
        >>> "pools" in data  # doctest: +SKIP
        True
        """
        command = [str(self.zpool_path), "status", "-j"]

        if pool_name:
            command.append(pool_name)

        logger.debug(f"Executing: {' '.join(command)}")
        return self._execute_json_command(command, timeout=timeout)

    def _execute_json_command(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Execute command and parse JSON output.

        Parameters
        ----------
        command:
            Full command to execute as list of strings.
        timeout:
            Timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        dict:
            Parsed JSON from command stdout.

        Raises
        ------
        ZFSCommandError:
            When command fails.
        json.JSONDecodeError:
            When output is not valid JSON.
        subprocess.TimeoutExpired:
            When command exceeds timeout.
        """
        actual_timeout = timeout if timeout is not None else self.default_timeout

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                check=False,
            )

            # Log command execution
            logger.debug(
                "Command completed",
                extra={
                    "command": " ".join(command),
                    "exit_code": result.returncode,
                    "stdout_length": len(result.stdout),
                    "stderr_length": len(result.stderr),
                },
            )

            # Check for command failure
            if result.returncode != 0:
                logger.error(
                    "ZFS command failed",
                    extra={
                        "command": " ".join(command),
                        "exit_code": result.returncode,
                        "stderr": result.stderr,
                    },
                )
                raise ZFSCommandError(command, result.returncode, result.stderr)

            # Parse JSON output
            try:
                data = json.loads(result.stdout)
                logger.debug(f"Parsed JSON successfully, top-level keys: {list(data.keys())}")
                return data
            except json.JSONDecodeError as exc:
                logger.error(
                    "Failed to parse JSON output",
                    extra={
                        "command": " ".join(command),
                        "stdout_preview": result.stdout[:500],
                        "error": str(exc),
                    },
                )
                raise

        except subprocess.TimeoutExpired as exc:
            logger.error(
                "ZFS command timed out",
                extra={
                    "command": " ".join(command),
                    "timeout": actual_timeout,
                },
            )
            raise


__all__ = [
    "ZFSClient",
    "ZFSCommandError",
    "ZFSNotAvailableError",
]
