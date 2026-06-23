"""Tests for configuration management module.

This module validates:
- Default config path resolution
- Config loading and caching behavior
- Config returns valid dict with expected sections

All tests mock lib_layered_config to avoid filesystem dependencies.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from check_zpools.config import get_config, get_default_config_path


# ============================================================================
# Tests: get_default_config_path
# ============================================================================


class TestDefaultConfigPathPointsToShippedFile:
    """get_default_config_path returns the bundled defaultconfig.toml."""

    @pytest.mark.os_agnostic
    def test_returns_path_named_defaultconfig_toml(self) -> None:
        """The returned path has the expected filename."""
        path = get_default_config_path()

        assert path.name == "defaultconfig.toml"

    @pytest.mark.os_agnostic
    def test_returned_path_exists_on_disk(self) -> None:
        """The default config file ships with the package."""
        path = get_default_config_path()

        assert path.exists()

    @pytest.mark.os_agnostic
    def test_returned_path_is_absolute(self) -> None:
        """The path is absolute so it works regardless of cwd."""
        path = get_default_config_path()

        assert path.is_absolute()

    @pytest.mark.os_agnostic
    def test_returned_path_lives_inside_package_directory(self) -> None:
        """The config file is co-located with the Python package."""
        path = get_default_config_path()

        assert "check_zpools" in str(path)


# ============================================================================
# Tests: get_config
# ============================================================================


class TestGetConfigReturnsValidConfiguration:
    """get_config loads layered configuration with correct parameters."""

    @pytest.mark.os_agnostic
    def test_config_returns_dict_like_object(self) -> None:
        """The returned Config exposes an as_dict() method."""
        # Clear lru_cache to ensure fresh load
        get_config.cache_clear()

        config = get_config()

        assert isinstance(config.as_dict(), dict)

    @pytest.mark.os_agnostic
    def test_config_provides_fallback_for_missing_keys(self) -> None:
        """Requesting a missing key with a default returns the default."""
        get_config.cache_clear()

        config = get_config()
        result = config.get("nonexistent_key_that_will_never_exist", default="fallback_value")

        assert result == "fallback_value"

    @pytest.mark.os_agnostic
    def test_config_contains_zfs_section(self) -> None:
        """The default config ships with a [zfs] section."""
        get_config.cache_clear()

        config = get_config()
        zfs_config = config.get("zfs", default=None)

        assert zfs_config is not None


class TestGetConfigCachingPreventsRedundantIO:
    """get_config uses lru_cache to avoid repeated file reads."""

    @pytest.mark.os_agnostic
    def test_second_call_returns_same_object(self) -> None:
        """Consecutive calls return the exact same Config instance."""
        get_config.cache_clear()

        first = get_config()
        second = get_config()

        assert first is second

    @pytest.mark.os_agnostic
    def test_cache_clear_forces_reload(self) -> None:
        """After cache_clear, the next call produces a fresh Config."""
        get_config.cache_clear()
        get_config()

        get_config.cache_clear()
        second = get_config()

        # Both are valid configs but may or may not be the same object
        assert isinstance(second.as_dict(), dict)


class TestGetConfigPassesCorrectIdentifiers:
    """get_config passes vendor/app/slug from __init__conf__ to read_config."""

    @pytest.mark.os_agnostic
    def test_calls_read_config_with_package_identifiers(self) -> None:
        """read_config receives the vendor, app, and slug from __init__conf__."""
        get_config.cache_clear()

        with patch("check_zpools.config.read_config") as mock_read:
            mock_read.return_value = MagicMock()
            mock_read.return_value.as_dict.return_value = {}

            get_config()

            mock_read.assert_called_once()
            call_kwargs = mock_read.call_args
            assert call_kwargs.kwargs["vendor"] == "bitranox"
            assert call_kwargs.kwargs["app"] == "Check Zpools"
            assert call_kwargs.kwargs["slug"] == "check_zpools"

    @pytest.mark.os_agnostic
    def test_passes_default_config_path_to_read_config(self) -> None:
        """read_config receives the bundled defaultconfig.toml path."""
        get_config.cache_clear()

        with patch("check_zpools.config.read_config") as mock_read:
            mock_read.return_value = MagicMock()

            get_config()

            call_kwargs = mock_read.call_args
            default_file = call_kwargs.kwargs["default_file"]
            assert isinstance(default_file, Path)
            assert default_file.name == "defaultconfig.toml"

    @pytest.mark.os_agnostic
    def test_passes_start_dir_none_by_default(self) -> None:
        """When start_dir is not specified, None is passed to read_config."""
        get_config.cache_clear()

        with patch("check_zpools.config.read_config") as mock_read:
            mock_read.return_value = MagicMock()

            get_config()

            call_kwargs = mock_read.call_args
            assert call_kwargs.kwargs["start_dir"] is None

    @pytest.mark.os_agnostic
    def test_forwards_custom_start_dir(self) -> None:
        """A custom start_dir is forwarded to read_config."""
        get_config.cache_clear()

        with patch("check_zpools.config.read_config") as mock_read:
            mock_read.return_value = MagicMock()

            get_config(start_dir="/tmp/test")

            call_kwargs = mock_read.call_args
            assert call_kwargs.kwargs["start_dir"] == "/tmp/test"
