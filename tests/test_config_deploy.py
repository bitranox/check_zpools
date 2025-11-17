"""Tests for configuration deployment functionality.

Tests cover:
- Deploying to user config location
- Deploying to multiple targets
- Force overwrite behavior
- Path validation
- Package metadata passing

All tests are OS-agnostic because they test the deployment orchestration logic
with mocked filesystem operations, not actual platform-specific paths.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.config_deploy import deploy_configuration


# ============================================================================
# Tests: Single Target Deployment
# ============================================================================


@pytest.mark.os_agnostic
class TestDeployToUserTarget:
    """Deploying to user target creates config in user directory."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_user_calls_deploy_config_with_user_target(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to user target,
        deploy_config is called with 'user' in targets."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/home/user/.config/check_zpools/config.toml")]

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert "user" in call_args.kwargs["targets"]

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_user_returns_deployed_path(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to user target,
        the function returns the deployed config path."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/home/user/.config/check_zpools/config.toml")]

        result = deploy_configuration(targets=["user"])

        assert len(result) == 1
        assert result[0].name == "config.toml"


@pytest.mark.os_agnostic
class TestDeployToHostTarget:
    """Deploying to host target creates config in system directory."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_host_calls_deploy_config_with_host_target(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to host target,
        deploy_config is called with 'host' in targets."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/etc/check_zpools/config.toml")]

        deploy_configuration(targets=["host"])

        call_args = mock_deploy.call_args
        assert "host" in call_args.kwargs["targets"]

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_host_returns_system_path(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to host target,
        the function returns the system config path."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/etc/check_zpools/config.toml")]

        result = deploy_configuration(targets=["host"])

        assert len(result) == 1


@pytest.mark.os_agnostic
class TestDeployToAppTarget:
    """Deploying to app target creates config in application directory."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_app_calls_deploy_config_with_app_target(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to app target,
        deploy_config is called with 'app' in targets."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/usr/share/check_zpools/config.toml")]

        deploy_configuration(targets=["app"])

        call_args = mock_deploy.call_args
        assert "app" in call_args.kwargs["targets"]

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_app_returns_application_path(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to app target,
        the function returns the application config path."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/usr/share/check_zpools/config.toml")]

        result = deploy_configuration(targets=["app"])

        assert len(result) == 1


# ============================================================================
# Tests: Multiple Target Deployment
# ============================================================================


@pytest.mark.os_agnostic
class TestDeployToMultipleTargets:
    """Deploying to multiple targets creates configs in all locations."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_app_and_user_includes_both_targets(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to both app and user targets,
        deploy_config is called with both targets."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [
            Path("/etc/check_zpools/config.toml"),
            Path("/home/user/.config/check_zpools/config.toml"),
        ]

        deploy_configuration(targets=["app", "user"])

        call_args = mock_deploy.call_args
        assert "app" in call_args.kwargs["targets"]
        assert "user" in call_args.kwargs["targets"]

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_multiple_targets_returns_all_paths(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying to multiple targets,
        the function returns all deployed paths."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source

        expected_paths = [
            Path("/home/user/.config/check_zpools/config.toml"),
            Path("/etc/check_zpools/config.toml"),
        ]
        mock_deploy.return_value = expected_paths

        result = deploy_configuration(targets=["user", "app"])

        assert result == expected_paths
        assert len(result) == 2


# ============================================================================
# Tests: Force Overwrite Behavior
# ============================================================================


@pytest.mark.os_agnostic
class TestForceOverwriteBehavior:
    """Force flag controls whether existing configs are overwritten."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_without_force_defaults_to_false(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When force is not specified,
        deploy_config is called with force=False."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert call_args.kwargs["force"] is False

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_with_force_passes_true_to_deploy_config(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When force=True is specified,
        deploy_config is called with force=True."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/home/user/.config/check_zpools/config.toml")]

        deploy_configuration(targets=["user"], force=True)

        call_args = mock_deploy.call_args
        assert call_args.kwargs["force"] is True

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_returns_empty_list_when_files_exist_without_force(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying without force and files already exist,
        the function returns an empty list."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        result = deploy_configuration(targets=["user"])

        assert result == []


# ============================================================================
# Tests: Package Metadata Integration
# ============================================================================


@pytest.mark.os_agnostic
class TestPackageMetadataIntegration:
    """Deploy configuration passes package metadata to deploy_config."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_passes_vendor_from_package_metadata(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying configuration,
        the LAYEREDCONF_VENDOR is passed to deploy_config."""
        from check_zpools import __init__conf__

        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert call_args.kwargs["vendor"] == __init__conf__.LAYEREDCONF_VENDOR

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_passes_app_from_package_metadata(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying configuration,
        the LAYEREDCONF_APP is passed to deploy_config."""
        from check_zpools import __init__conf__

        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert call_args.kwargs["app"] == __init__conf__.LAYEREDCONF_APP

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_passes_slug_from_package_metadata(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying configuration,
        the LAYEREDCONF_SLUG is passed to deploy_config."""
        from check_zpools import __init__conf__

        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert call_args.kwargs["slug"] == __init__conf__.LAYEREDCONF_SLUG


# ============================================================================
# Tests: Source Path Resolution
# ============================================================================


@pytest.mark.os_agnostic
class TestSourcePathResolution:
    """Deploy configuration resolves source path from package config."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_uses_default_config_path_as_source(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """When deploying configuration,
        the default config path is used as the source."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        call_args = mock_deploy.call_args
        assert call_args.kwargs["source"] == mock_source
