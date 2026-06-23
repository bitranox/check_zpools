"""Tests for centralized logging initialization.

This module validates:
- _build_runtime_config constructs RuntimeConfig with correct defaults
- init_logging is idempotent (only initializes once)
- Configuration values flow from layered config to RuntimeConfig

All tests mock lib_log_rich to avoid side effects on the global logging state.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# Tests: _build_runtime_config
# ============================================================================


class TestBuildRuntimeConfigSetsServiceDefaults:
    """_build_runtime_config provides sensible defaults for required parameters."""

    @pytest.mark.os_agnostic
    def test_defaults_service_to_package_name(self) -> None:
        """When [lib_log_rich] has no 'service' key, the package name is used."""
        mock_config = MagicMock()
        mock_config.get.return_value = {}

        with (
            patch("check_zpools.logging_setup.get_config", return_value=mock_config),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.RuntimeConfig") as mock_rc,
        ):
            from check_zpools.logging_setup import _build_runtime_config

            _build_runtime_config()

            call_kwargs = mock_rc.call_args.kwargs
            assert call_kwargs["service"] == "check_zpools"

    @pytest.mark.os_agnostic
    def test_defaults_environment_to_prod(self) -> None:
        """When [lib_log_rich] has no 'environment' key, 'prod' is used."""
        mock_config = MagicMock()
        mock_config.get.return_value = {}

        with (
            patch("check_zpools.logging_setup.get_config", return_value=mock_config),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.RuntimeConfig") as mock_rc,
        ):
            from check_zpools.logging_setup import _build_runtime_config

            _build_runtime_config()

            call_kwargs = mock_rc.call_args.kwargs
            assert call_kwargs["environment"] == "prod"


class TestBuildRuntimeConfigForwardsUserSettings:
    """_build_runtime_config passes user-provided settings to RuntimeConfig."""

    @pytest.mark.os_agnostic
    def test_forwards_custom_service_name(self) -> None:
        """A user-configured service name overrides the default."""
        mock_config = MagicMock()
        mock_config.get.return_value = {"service": "my-custom-service"}

        with (
            patch("check_zpools.logging_setup.get_config", return_value=mock_config),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.RuntimeConfig") as mock_rc,
        ):
            from check_zpools.logging_setup import _build_runtime_config

            _build_runtime_config()

            call_kwargs = mock_rc.call_args.kwargs
            assert call_kwargs["service"] == "my-custom-service"

    @pytest.mark.os_agnostic
    def test_forwards_console_level(self) -> None:
        """Console level from config is passed through to RuntimeConfig."""
        mock_config = MagicMock()
        mock_config.get.return_value = {"console_level": "DEBUG"}

        with (
            patch("check_zpools.logging_setup.get_config", return_value=mock_config),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.RuntimeConfig") as mock_rc,
        ):
            from check_zpools.logging_setup import _build_runtime_config

            _build_runtime_config()

            call_kwargs = mock_rc.call_args.kwargs
            assert call_kwargs["console_level"] == "DEBUG"


# ============================================================================
# Tests: init_logging
# ============================================================================


class TestInitLoggingIsIdempotent:
    """init_logging only initializes the runtime once."""

    @pytest.mark.os_agnostic
    def test_skips_initialization_when_already_initialized(self) -> None:
        """When lib_log_rich reports it is initialized, init_logging does nothing."""
        with (
            patch("check_zpools.logging_setup.lib_log_rich.runtime.is_initialised", return_value=True),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.init") as mock_init,
        ):
            from check_zpools.logging_setup import init_logging

            init_logging()

            mock_init.assert_not_called()

    @pytest.mark.os_agnostic
    def test_initializes_runtime_when_not_yet_initialized(self) -> None:
        """When lib_log_rich is not initialized, init_logging calls init()."""
        mock_runtime_config = MagicMock()

        with (
            patch("check_zpools.logging_setup.lib_log_rich.runtime.is_initialised", return_value=False),
            patch("check_zpools.logging_setup.lib_log_rich.config.enable_dotenv"),
            patch("check_zpools.logging_setup._build_runtime_config", return_value=mock_runtime_config),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.init") as mock_init,
            patch("check_zpools.logging_setup.lib_log_rich.runtime.attach_std_logging"),
        ):
            from check_zpools.logging_setup import init_logging

            init_logging()

            mock_init.assert_called_once_with(mock_runtime_config)


class TestInitLoggingEnablesDotenv:
    """init_logging loads .env files before initializing the runtime."""

    @pytest.mark.os_agnostic
    def test_enables_dotenv_before_runtime_init(self) -> None:
        """enable_dotenv is called so LOG_* variables from .env are available."""
        call_order: list[str] = []

        def track_dotenv() -> None:
            call_order.append("dotenv")

        def track_init(config: object) -> None:
            call_order.append("init")

        with (
            patch("check_zpools.logging_setup.lib_log_rich.runtime.is_initialised", return_value=False),
            patch("check_zpools.logging_setup.lib_log_rich.config.enable_dotenv", side_effect=track_dotenv),
            patch("check_zpools.logging_setup._build_runtime_config", return_value=MagicMock()),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.init", side_effect=track_init),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.attach_std_logging"),
        ):
            from check_zpools.logging_setup import init_logging

            init_logging()

            assert call_order == ["dotenv", "init"]


class TestInitLoggingAttachesStandardLogging:
    """init_logging bridges standard Python logging to lib_log_rich."""

    @pytest.mark.os_agnostic
    def test_attaches_std_logging_after_init(self) -> None:
        """attach_std_logging is called so domain code using stdlib logging works."""
        with (
            patch("check_zpools.logging_setup.lib_log_rich.runtime.is_initialised", return_value=False),
            patch("check_zpools.logging_setup.lib_log_rich.config.enable_dotenv"),
            patch("check_zpools.logging_setup._build_runtime_config", return_value=MagicMock()),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.init"),
            patch("check_zpools.logging_setup.lib_log_rich.runtime.attach_std_logging") as mock_attach,
        ):
            from check_zpools.logging_setup import init_logging

            init_logging()

            mock_attach.assert_called_once()
