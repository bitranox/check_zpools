"""Tests for configuration deployment functionality.

Tests cover:
- Deploying to user config location
- Deploying to multiple targets
- Force overwrite behavior
- Path validation
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from check_zpools.config_deploy import deploy_configuration


class TestDeployConfiguration:
    """Test configuration deployment."""

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_user(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should deploy configuration to user directory."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/home/user/.config/check_zpools/config.toml")]

        result = deploy_configuration(targets=["user"])

        # Verify deploy_config was called with correct arguments
        mock_deploy.assert_called_once()
        call_args = mock_deploy.call_args
        assert call_args.kwargs["source"] == mock_source
        assert "user" in call_args.kwargs["targets"]
        assert call_args.kwargs["force"] is False

        # Verify result
        assert len(result) == 1
        assert result[0].name == "config.toml"

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_multiple_targets(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should deploy to multiple targets when specified."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [
            Path("/etc/check_zpools/config.toml"),
            Path("/home/user/.config/check_zpools/config.toml"),
        ]

        result = deploy_configuration(targets=["app", "user"])

        # Verify deploy_config was called with both targets
        call_args = mock_deploy.call_args
        assert "app" in call_args.kwargs["targets"]
        assert "user" in call_args.kwargs["targets"]

        # Verify result contains both paths
        assert len(result) == 2

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_with_force(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should pass force flag to deploy_config."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/home/user/.config/check_zpools/config.toml")]

        result = deploy_configuration(targets=["user"], force=True)

        # Verify force=True was passed
        call_args = mock_deploy.call_args
        assert call_args.kwargs["force"] is True

        assert len(result) == 1

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_without_force(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should default to force=False."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        result = deploy_configuration(targets=["user"])

        # Verify force=False by default
        call_args = mock_deploy.call_args
        assert call_args.kwargs["force"] is False

        # Empty list when files already exist
        assert result == []

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_passes_package_metadata(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should pass vendor, app, and slug from package metadata."""
        from check_zpools import __init__conf__

        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = []

        deploy_configuration(targets=["user"])

        # Verify metadata was passed correctly
        call_args = mock_deploy.call_args
        assert call_args.kwargs["vendor"] == __init__conf__.LAYEREDCONF_VENDOR
        assert call_args.kwargs["app"] == __init__conf__.LAYEREDCONF_APP
        assert call_args.kwargs["slug"] == __init__conf__.LAYEREDCONF_SLUG

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_returns_deployed_paths(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should return the list of deployed paths from deploy_config."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source

        expected_paths = [
            Path("/home/user/.config/check_zpools/config.toml"),
            Path("/etc/check_zpools/config.toml"),
        ]
        mock_deploy.return_value = expected_paths

        result = deploy_configuration(targets=["user", "app"])

        assert result == expected_paths

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_host(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should deploy to host configuration directory."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/etc/check_zpools/config.toml")]

        result = deploy_configuration(targets=["host"])

        call_args = mock_deploy.call_args
        assert "host" in call_args.kwargs["targets"]
        assert len(result) == 1

    @patch("check_zpools.config_deploy.deploy_config")
    @patch("check_zpools.config_deploy.get_default_config_path")
    def test_deploy_to_app(self, mock_get_path: MagicMock, mock_deploy: MagicMock) -> None:
        """Should deploy to application configuration directory."""
        mock_source = Path("/fake/source/defaultconfig.toml")
        mock_get_path.return_value = mock_source
        mock_deploy.return_value = [Path("/usr/share/check_zpools/config.toml")]

        result = deploy_configuration(targets=["app"])

        call_args = mock_deploy.call_args
        assert "app" in call_args.kwargs["targets"]
        assert len(result) == 1
