"""ZFS command execution client.

Purpose
-------
Execute ZFS pool commands (`zpool status`) and return their JSON output.
Handles command discovery, execution, error handling, and timeout management.

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
- Uses `--json-int` flag for integer values (no string parsing needed)
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess  # nosec B404 - subprocess used safely with list arguments, not shell=True
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# Type variable for generic Pydantic model returns
T = TypeVar("T", bound=BaseModel)


class ZFSCommandResponse(BaseModel):
    """Base response from ZFS JSON commands.

    Why
        Provides type-safe wrapper for ZFS command outputs while maintaining
        flexibility for different ZFS versions with varying field structures.
        Supports dict-like access for backward compatibility with existing
        parser code.

    Notes
    -----
    - Allows extra fields for forward/backward compatibility with ZFS versions
    - Parser layer handles detailed validation and type conversion
    - This layer focuses on transport and basic structure
    - Supports dict-like interface (__getitem__, get, __contains__) for
      seamless integration with code expecting dict[str, Any]
    """

    model_config = ConfigDict(extra="allow")  # Allow unknown ZFS fields for version flexibility

    def __getitem__(self, key: str) -> Any:
        """Support dict-like item access for backward compatibility.

        Why
            Enables seamless integration with existing code that expects
            dict[str, Any] responses, particularly the ZFSParser.

        Parameters
        ----------
        key:
            Attribute/field name to access

        Returns
        -------
        Any:
            Field value

        Raises
        ------
        KeyError:
            When key doesn't exist

        Examples
        --------
        >>> response = ZpoolListResponse.model_validate({"pools": {}})  # doctest: +SKIP
        >>> response["pools"]  # doctest: +SKIP
        {}
        """
        try:
            return getattr(self, key)
        except AttributeError as exc:
            # Try model_extra for dynamic fields (extra="allow")
            extra_fields = self.__pydantic_extra__
            if extra_fields is not None and key in extra_fields:
                return extra_fields[key]
            raise KeyError(key) from exc

    def get(self, key: str, default: Any = None) -> Any:
        """Support dict-like get() method for backward compatibility.

        Why
            Enables seamless integration with existing code that uses
            dict.get() for safe field access with defaults.

        Parameters
        ----------
        key:
            Attribute/field name to access
        default:
            Default value if key doesn't exist

        Returns
        -------
        Any:
            Field value or default

        Examples
        --------
        >>> response = ZpoolListResponse.model_validate({"pools": {}})  # doctest: +SKIP
        >>> response.get("pools", {})  # doctest: +SKIP
        {}
        >>> response.get("nonexistent", "fallback")  # doctest: +SKIP
        'fallback'
        """
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator for backward compatibility.

        Why
            Enables seamless integration with existing code that uses
            'key in dict' checks.

        Parameters
        ----------
        key:
            Attribute/field name to check

        Returns
        -------
        bool:
            True if key exists, False otherwise

        Examples
        --------
        >>> response = ZpoolListResponse.model_validate({"pools": {}})  # doctest: +SKIP
        >>> "pools" in response  # doctest: +SKIP
        True
        >>> "nonexistent" in response  # doctest: +SKIP
        False
        """
        # Check if it's a defined field
        if hasattr(self, key):
            return True
        # Check if it's in extra fields
        extra_fields = self.__pydantic_extra__
        if extra_fields is not None and key in extra_fields:
            return True
        return False

    def keys(self) -> list[str]:
        """Support dict-like keys() method for backward compatibility.

        Why
            Enables seamless integration with existing code that iterates
            over dict.keys().

        Returns
        -------
        list[str]:
            List of all field names (both defined and extra)

        Examples
        --------
        >>> response = ZpoolListResponse.model_validate({"pools": {}})  # doctest: +SKIP
        >>> "pools" in response.keys()  # doctest: +SKIP
        True
        """
        result = list(self.__class__.model_fields.keys())
        extra_fields = self.__pydantic_extra__
        if extra_fields is not None:
            result.extend(extra_fields.keys())
        return result


class ZpoolStatusResponse(ZFSCommandResponse):
    """Response from 'zpool status -j --json-int' command.

    Why
        Type-safe wrapper for zpool status output. Maintains flexibility since
        ZFS JSON format varies by version, with detailed parsing handled
        by ZFSParser. With --json-int, all numeric values are integers.

    Examples
    --------
    >>> response = ZpoolStatusResponse.model_validate({"pools": {}})  # doctest: +SKIP
    >>> isinstance(response, ZpoolStatusResponse)  # doctest: +SKIP
    True
    """

    pass


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
    >>> data = client.get_pool_status()  # doctest: +SKIP
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
                    "zpool command not found. Please install ZFS utilities.\nOn Debian/Ubuntu: apt install zfsutils-linux\nOn RHEL/CentOS: yum install zfs"
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

    def get_pool_status(
        self,
        *,
        pool_name: str | None = None,
        timeout: int | None = None,
    ) -> ZpoolStatusResponse:
        """Execute `zpool status -j --json-int` and return parsed JSON.

        Why
            Gets complete pool information including capacity, error counts,
            scrub status, and health state. With --json-int, all numeric values
            are integers (bytes, timestamps) requiring no string parsing.

        Parameters
        ----------
        pool_name:
            Optional specific pool to query. If None, gets all pools.
        timeout:
            Command timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        ZpoolStatusResponse:
            Pydantic model wrapping parsed JSON output from zpool status command.
            Contains pools with vdevs having integer fields: alloc_space,
            total_space, read_errors, write_errors, checksum_errors, and
            scan_stats with integer timestamps.

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
        command = [str(self.zpool_path), "status", "-j", "--json-int"]

        if pool_name:
            command.append(pool_name)

        logger.debug(f"Executing: {' '.join(command)}")
        return self._execute_json_command(command, timeout=timeout, response_model=ZpoolStatusResponse)

    def get_pool_status_text(
        self,
        *,
        pool_name: str | None = None,
        timeout: int | None = None,
    ) -> str:
        """Execute `zpool status` and return plain text output.

        Why
            Gets human-readable pool status for inclusion in emails and reports.
            This is the same output administrators see when running zpool status
            manually.

        Parameters
        ----------
        pool_name:
            Optional specific pool to query. If None, gets all pools.
        timeout:
            Command timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        str:
            Plain text output from zpool status command.

        Raises
        ------
        ZFSCommandError:
            When command fails or returns non-zero exit code.

        Examples
        --------
        >>> client = ZFSClient()  # doctest: +SKIP
        >>> text = client.get_pool_status_text(pool_name="rpool")  # doctest: +SKIP
        >>> "pool: rpool" in text  # doctest: +SKIP
        True
        """
        command = [str(self.zpool_path), "status"]

        if pool_name:
            command.append(pool_name)

        logger.debug(f"Executing: {' '.join(command)}")
        return self._execute_text_command(command, timeout=timeout)

    def _execute_command(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute command and return result.

        Why
            Common implementation for both JSON and text commands, eliminating
            code duplication for subprocess execution, logging, and error handling.

        Parameters
        ----------
        command:
            Full command to execute as list of strings.
        timeout:
            Timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        subprocess.CompletedProcess:
            Completed process with stdout, stderr, and return code.

        Raises
        ------
        ZFSCommandError:
            When command fails (non-zero exit code).
        subprocess.TimeoutExpired:
            When command exceeds timeout.
        """
        actual_timeout = timeout if timeout is not None else self.default_timeout

        try:
            result = subprocess.run(  # nosec B603 - command is hardcoded zpool path with validated args
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

            return result

        except subprocess.TimeoutExpired:
            logger.error(
                "ZFS command timed out",
                extra={
                    "command": " ".join(command),
                    "timeout": actual_timeout,
                },
            )
            raise

    def _execute_json_command(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
        response_model: type[T],
    ) -> T:
        """Execute command and parse JSON output into Pydantic model.

        Why
            Provides type-safe JSON parsing with validation. Uses Pydantic
            models to ensure API contracts while maintaining flexibility
            for ZFS version variations.

        Parameters
        ----------
        command:
            Full command to execute as list of strings.
        timeout:
            Timeout in seconds. Uses default_timeout if None.
        response_model:
            Pydantic model class to parse response into.

        Returns
        -------
        T:
            Pydantic model instance containing parsed JSON from command stdout.

        Raises
        ------
        ZFSCommandError:
            When command fails.
        json.JSONDecodeError:
            When output is not valid JSON.
        subprocess.TimeoutExpired:
            When command exceeds timeout.
        """
        result = self._execute_command(command, timeout=timeout)

        # Parse JSON output into Pydantic model
        try:
            data = json.loads(result.stdout)
            logger.debug(f"Parsed JSON successfully, top-level keys: {list(data.keys())}")

            # Validate and wrap in Pydantic model
            model_instance = response_model.model_validate(data)
            logger.debug(f"Successfully validated response as {response_model.__name__}")
            return model_instance
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

    def _execute_text_command(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
    ) -> str:
        """Execute command and return text output.

        Parameters
        ----------
        command:
            Full command to execute as list of strings.
        timeout:
            Timeout in seconds. Uses default_timeout if None.

        Returns
        -------
        str:
            Text output from command stdout.

        Raises
        ------
        ZFSCommandError:
            When command fails.
        subprocess.TimeoutExpired:
            When command exceeds timeout.
        """
        result = self._execute_command(command, timeout=timeout)
        return result.stdout


__all__ = [
    "ZFSClient",
    "ZFSCommandError",
    "ZFSNotAvailableError",
    "ZFSCommandResponse",
    "ZpoolStatusResponse",
]
