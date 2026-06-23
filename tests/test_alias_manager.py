"""Tests for bash alias management functionality.

Tests cover:
- Alias block generation with correct markers
- Alias creation in bashrc files
- Alias removal from bashrc files
- User resolution (sudo user, specified user, current user)
- Root privilege checking
- Edge cases (missing files, existing aliases, etc.)

All tests mock external dependencies (file I/O, os.geteuid, pwd module).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from check_zpools import __init__conf__
from check_zpools.alias_manager import (
    ALIAS_MARKER_END,
    ALIAS_MARKER_START,
    _build_exec_command,
    _generate_alias_block,
    _get_bashrc_path_for_user,
    _get_user_info,
    _has_existing_alias,
    _remove_existing_alias,
    create_alias,
    delete_alias,
)


# ============================================================================
# Tests for _generate_alias_block
# ============================================================================


class TestGenerateAliasBlock:
    """Tests for alias block generation."""

    def test_contains_start_marker(self) -> None:
        """Block should start with correct marker."""
        result = _generate_alias_block("/usr/bin/check_zpools")
        assert ALIAS_MARKER_START in result

    def test_contains_end_marker(self) -> None:
        """Block should end with correct marker."""
        result = _generate_alias_block("/usr/bin/check_zpools")
        assert ALIAS_MARKER_END in result

    def test_contains_function_definition(self) -> None:
        """Block should contain shell function definition."""
        result = _generate_alias_block("/usr/bin/check_zpools")
        assert f"{__init__conf__.shell_command}()" in result

    def test_contains_exec_command(self) -> None:
        """Block should contain the execution command."""
        exec_cmd = "/path/to/venv/bin/check_zpools"
        result = _generate_alias_block(exec_cmd)
        assert exec_cmd in result

    def test_forwards_all_arguments(self) -> None:
        """Block should forward all arguments via $@."""
        result = _generate_alias_block("/usr/bin/check_zpools")
        assert '"$@"' in result

    def test_uvx_command_included(self) -> None:
        """Block should handle uvx command paths correctly."""
        result = _generate_alias_block("/home/user/.local/bin/uvx check_zpools@2.0.0")
        assert "/home/user/.local/bin/uvx check_zpools@2.0.0" in result


# ============================================================================
# Tests for _has_existing_alias
# ============================================================================


class TestHasExistingAlias:
    """Tests for alias detection in bashrc content."""

    def test_returns_true_when_marker_present(self) -> None:
        """Should return True when marker is in content."""
        content = f"some content\n{ALIAS_MARKER_START}\nfunction...\n{ALIAS_MARKER_END}\n"
        assert _has_existing_alias(content) is True

    def test_returns_false_when_no_marker(self) -> None:
        """Should return False when no marker present."""
        content = "alias ls='ls -la'\nexport PATH=$PATH:/usr/local/bin\n"
        assert _has_existing_alias(content) is False

    def test_returns_false_for_empty_content(self) -> None:
        """Should return False for empty content."""
        assert _has_existing_alias("") is False


# ============================================================================
# Tests for _remove_existing_alias
# ============================================================================


class TestRemoveExistingAlias:
    """Tests for alias block removal from bashrc content."""

    def test_removes_alias_block(self) -> None:
        """Should remove the entire alias block."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        content = f"# some config\n{alias_block}# more config\n"
        result = _remove_existing_alias(content)
        assert ALIAS_MARKER_START not in result
        assert ALIAS_MARKER_END not in result
        assert "# some config" in result
        assert "# more config" in result

    def test_preserves_other_content(self) -> None:
        """Should preserve content outside the alias block."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        content = f"export PATH=/bin\n{alias_block}alias vim=nvim\n"
        result = _remove_existing_alias(content)
        assert "export PATH=/bin" in result
        assert "alias vim=nvim" in result

    def test_handles_no_alias_block(self) -> None:
        """Should return content unchanged when no alias block."""
        content = "export PATH=/bin\nalias vim=nvim\n"
        result = _remove_existing_alias(content)
        assert result == content

    def test_handles_empty_content(self) -> None:
        """Should return empty string for empty content."""
        assert _remove_existing_alias("") == ""


# ============================================================================
# Tests for _get_user_info
# ============================================================================


@pytest.mark.linux_only
class TestGetUserInfo:
    """Tests for user information retrieval."""

    def test_returns_specified_user_info(self) -> None:
        """Should return info for specified username."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = "/home/testuser"

        with patch("pwd.getpwnam", return_value=mock_pw):
            username, home_dir = _get_user_info("testuser")

        assert username == "testuser"
        assert home_dir == Path("/home/testuser")

    def test_uses_sudo_user_when_available(self) -> None:
        """Should use SUDO_USER env var when username is None."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "sudouser"
        mock_pw.pw_dir = "/home/sudouser"

        with (
            patch.dict(os.environ, {"SUDO_USER": "sudouser"}),
            patch("pwd.getpwnam", return_value=mock_pw),
        ):
            username, home_dir = _get_user_info(None)

        assert username == "sudouser"
        assert home_dir == Path("/home/sudouser")

    def test_raises_keyerror_for_unknown_user(self) -> None:
        """Should raise KeyError for non-existent user."""
        with patch("pwd.getpwnam", side_effect=KeyError("unknown")):
            with pytest.raises(KeyError, match="User not found"):
                _get_user_info("nonexistent")


# ============================================================================
# Tests for _get_bashrc_path_for_user
# ============================================================================


@pytest.mark.linux_only
class TestGetBashrcPathForUser:
    """Tests for bashrc path resolution."""

    def test_returns_bashrc_in_home_directory(self) -> None:
        """Should return .bashrc path in user's home directory."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = "/home/testuser"

        with patch("pwd.getpwnam", return_value=mock_pw):
            bashrc_path, username = _get_bashrc_path_for_user("testuser")

        assert bashrc_path == Path("/home/testuser/.bashrc")
        assert username == "testuser"


# ============================================================================
# Tests for _build_exec_command
# ============================================================================


@pytest.mark.linux_only
class TestBuildExecCommand:
    """Tests for executable command building."""

    def test_direct_install_returns_path(self) -> None:
        """Direct installation should return executable path."""
        with patch(
            "check_zpools.service_install._find_executable",
            return_value=("direct", Path("/usr/local/bin/check_zpools"), None),
        ):
            result = _build_exec_command()

        assert result == "/usr/local/bin/check_zpools"

    def test_uvx_install_includes_version(self) -> None:
        """uvx installation should include version specifier."""
        with patch(
            "check_zpools.service_install._find_executable",
            return_value=("uvx", Path("/home/user/.local/bin/uvx"), "@2.0.0"),
        ):
            result = _build_exec_command()

        assert "/home/user/.local/bin/uvx" in result
        assert "check_zpools@2.0.0" in result

    def test_uvx_install_without_version(self) -> None:
        """uvx installation without version should use package name only."""
        with patch(
            "check_zpools.service_install._find_executable",
            return_value=("uvx", Path("/home/user/.local/bin/uvx"), None),
        ):
            result = _build_exec_command()

        assert "/home/user/.local/bin/uvx" in result
        assert "check_zpools" in result
        assert "@" not in result


# ============================================================================
# Tests for create_alias
# ============================================================================


class TestCreateAliasRootCheck:
    """Tests for root privilege verification in create_alias."""

    @pytest.mark.linux_only
    def test_requires_root_privileges(self) -> None:
        """Should raise PermissionError when not root."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="root"):
                create_alias()

    @pytest.mark.linux_only
    def test_user_flag_requires_root_with_specific_message(self) -> None:
        """Should show specific error when --user used without root."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="--user flag requires root"):
                create_alias(username="someuser")


class TestCreateAliasSuccess:
    """Tests for successful alias creation."""

    @pytest.mark.linux_only
    def test_creates_alias_in_bashrc(self, tmp_path: Path) -> None:
        """Should create alias block in bashrc file."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# existing content\n")

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias()

        content = bashrc.read_text()
        assert ALIAS_MARKER_START in content
        assert ALIAS_MARKER_END in content
        assert "/usr/bin/check_zpools" in content

    @pytest.mark.linux_only
    def test_replaces_existing_alias(self, tmp_path: Path) -> None:
        """Should replace existing alias block with new one."""
        bashrc = tmp_path / ".bashrc"
        old_alias = _generate_alias_block("/old/path/check_zpools")
        bashrc.write_text(f"# config\n{old_alias}# more config\n")

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/new/path/check_zpools"), None),
            ),
        ):
            create_alias()

        content = bashrc.read_text()
        assert "/new/path/check_zpools" in content
        assert "/old/path/check_zpools" not in content
        assert content.count(ALIAS_MARKER_START) == 1

    @pytest.mark.linux_only
    def test_creates_bashrc_if_missing(self, tmp_path: Path) -> None:
        """Should create bashrc file if it doesn't exist."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        bashrc = tmp_path / ".bashrc"
        assert not bashrc.exists()

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias()

        assert bashrc.exists()
        content = bashrc.read_text()
        assert ALIAS_MARKER_START in content


class TestCreateAliasForSpecificUser:
    """Tests for creating alias for a specific user."""

    @pytest.mark.linux_only
    def test_creates_alias_for_specified_user(self, tmp_path: Path) -> None:
        """Should create alias in specified user's bashrc."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("")

        mock_pw = MagicMock()
        mock_pw.pw_name = "otheruser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias(username="otheruser")

        content = bashrc.read_text()
        assert ALIAS_MARKER_START in content


# ============================================================================
# Tests for delete_alias
# ============================================================================


class TestDeleteAliasRootCheck:
    """Tests for root privilege verification in delete_alias."""

    @pytest.mark.linux_only
    def test_requires_root_privileges(self) -> None:
        """Should raise PermissionError when not root."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="root"):
                delete_alias()

    @pytest.mark.linux_only
    def test_user_flag_requires_root_with_specific_message(self) -> None:
        """Should show specific error when --user used without root."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="--user flag requires root"):
                delete_alias(username="someuser")


class TestDeleteAliasSuccess:
    """Tests for successful alias removal."""

    @pytest.mark.linux_only
    def test_removes_alias_from_bashrc(self, tmp_path: Path) -> None:
        """Should remove alias block from bashrc file."""
        bashrc = tmp_path / ".bashrc"
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        bashrc.write_text(f"# config\n{alias_block}# more config\n")

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
        ):
            delete_alias()

        content = bashrc.read_text()
        assert ALIAS_MARKER_START not in content
        assert ALIAS_MARKER_END not in content
        assert "# config" in content
        assert "# more config" in content

    @pytest.mark.linux_only
    def test_handles_no_existing_alias(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print message when no alias exists."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("# just config\n")

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
        ):
            delete_alias()

        captured = capsys.readouterr()
        assert "No" in captured.out and "alias" in captured.out

    @pytest.mark.linux_only
    def test_handles_missing_bashrc(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print message when bashrc doesn't exist."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
        ):
            delete_alias()

        captured = capsys.readouterr()
        assert "not found" in captured.out


# ============================================================================
# Tests for CLI integration
# ============================================================================


class TestAliasCreateCLI:
    """Tests for alias-create CLI command."""

    def test_command_registered(self) -> None:
        """Command should be registered in CLI."""
        from check_zpools.cli import cli

        assert "alias-create" in [cmd for cmd in cli.commands]

    def test_user_option_available(self) -> None:
        """--user option should be available."""
        from check_zpools.cli import cli

        cmd = cli.commands["alias-create"]
        param_names = [p.name for p in cmd.params]
        assert "user" in param_names


class TestAliasDeleteCLI:
    """Tests for alias-delete CLI command."""

    def test_command_registered(self) -> None:
        """Command should be registered in CLI."""
        from check_zpools.cli import cli

        assert "alias-delete" in [cmd for cmd in cli.commands]

    def test_user_option_available(self) -> None:
        """--user option should be available."""
        from check_zpools.cli import cli

        cmd = cli.commands["alias-delete"]
        param_names = [p.name for p in cmd.params]
        assert "user" in param_names


# ============================================================================
# Tests for CLI command handlers
# ============================================================================


class TestAliasCreateCommandHandler:
    """Tests for alias_create_command function."""

    @pytest.mark.linux_only
    def test_exits_with_code_1_on_permission_error(self) -> None:
        """Should exit with code 1 when not root."""
        from check_zpools.cli_commands.commands.alias_create import alias_create_command
        from check_zpools.logging_setup import init_logging

        init_logging()

        with (
            patch("os.geteuid", return_value=1000),
            pytest.raises(SystemExit) as exc_info,
        ):
            alias_create_command(user=None)

        assert exc_info.value.code == 1

    @pytest.mark.linux_only
    def test_exits_with_code_1_on_user_not_found(self) -> None:
        """Should exit with code 1 when user not found."""
        from check_zpools.cli_commands.commands.alias_create import alias_create_command
        from check_zpools.logging_setup import init_logging

        init_logging()

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", side_effect=KeyError("unknown")),
            pytest.raises(SystemExit) as exc_info,
        ):
            alias_create_command(user="nonexistent")

        assert exc_info.value.code == 1


class TestAliasDeleteCommandHandler:
    """Tests for alias_delete_command function."""

    @pytest.mark.linux_only
    def test_exits_with_code_1_on_permission_error(self) -> None:
        """Should exit with code 1 when not root."""
        from check_zpools.cli_commands.commands.alias_delete import alias_delete_command
        from check_zpools.logging_setup import init_logging

        init_logging()

        with (
            patch("os.geteuid", return_value=1000),
            pytest.raises(SystemExit) as exc_info,
        ):
            alias_delete_command(user=None)

        assert exc_info.value.code == 1

    @pytest.mark.linux_only
    def test_exits_with_code_1_on_user_not_found(self) -> None:
        """Should exit with code 1 when user not found."""
        from check_zpools.cli_commands.commands.alias_delete import alias_delete_command
        from check_zpools.logging_setup import init_logging

        init_logging()

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", side_effect=KeyError("unknown")),
            pytest.raises(SystemExit) as exc_info,
        ):
            alias_delete_command(user="nonexistent")

        assert exc_info.value.code == 1


# ============================================================================
# Tests for edge cases
# ============================================================================


class TestAliasBlockEdgeCases:
    """Tests for edge cases in alias block handling."""

    def test_alias_block_at_start_of_file(self) -> None:
        """Should handle alias block at the very start of file."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        content = f"{alias_block}# other content\n"
        result = _remove_existing_alias(content)
        assert ALIAS_MARKER_START not in result
        assert "# other content" in result

    def test_alias_block_at_end_of_file(self) -> None:
        """Should handle alias block at the very end of file."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        content = f"# other content\n{alias_block}"
        result = _remove_existing_alias(content)
        assert ALIAS_MARKER_START not in result
        assert "# other content" in result

    def test_alias_block_only_content(self) -> None:
        """Should handle file containing only alias block."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        result = _remove_existing_alias(alias_block)
        assert ALIAS_MARKER_START not in result
        assert result.strip() == ""

    def test_multiline_bashrc_content_preserved(self) -> None:
        """Should preserve complex multiline bashrc content."""
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        content = f"""# .bashrc
export PATH=$PATH:/usr/local/bin
export EDITOR=vim

# Custom aliases
alias ll='ls -la'
alias gs='git status'

{alias_block}# Functions
function greet() {{
    echo "Hello, $1"
}}

# End of file
"""
        result = _remove_existing_alias(content)
        assert ALIAS_MARKER_START not in result
        assert "export PATH" in result
        assert "alias ll='ls -la'" in result
        assert "function greet()" in result
        assert "# End of file" in result


class TestUserInfoEdgeCases:
    """Tests for edge cases in user info resolution."""

    @pytest.mark.linux_only
    def test_falls_back_to_current_user_without_sudo_user(self) -> None:
        """Should use current user when SUDO_USER not set."""
        mock_pw = MagicMock()
        mock_pw.pw_name = "currentuser"
        mock_pw.pw_dir = "/home/currentuser"

        # Need to patch at the module level where it's imported
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("check_zpools.alias_manager.pwd.getpwuid", return_value=mock_pw),
            patch("check_zpools.alias_manager.pwd.getpwnam", return_value=mock_pw),
            patch("check_zpools.alias_manager.os.getuid", return_value=1000),
        ):
            username, home_dir = _get_user_info(None)

        assert username == "currentuser"
        assert home_dir == Path("/home/currentuser")


class TestCreateAliasOutputMessages:
    """Tests for output messages during alias creation."""

    @pytest.mark.linux_only
    def test_prints_success_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print success message with details."""
        bashrc = tmp_path / ".bashrc"
        bashrc.write_text("")

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias()

        captured = capsys.readouterr()
        assert "Alias created" in captured.out
        assert "testuser" in captured.out
        assert ".bashrc" in captured.out
        assert "source" in captured.out


class TestDeleteAliasOutputMessages:
    """Tests for output messages during alias deletion."""

    @pytest.mark.linux_only
    def test_prints_success_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print success message with details."""
        bashrc = tmp_path / ".bashrc"
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        bashrc.write_text(alias_block)

        mock_pw = MagicMock()
        mock_pw.pw_name = "testuser"
        mock_pw.pw_dir = str(tmp_path)

        with (
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", return_value=mock_pw),
            patch.dict(os.environ, {"SUDO_USER": "testuser"}),
        ):
            delete_alias()

        captured = capsys.readouterr()
        assert "Alias removed" in captured.out
        assert "testuser" in captured.out
        assert "unset -f" in captured.out


# ============================================================================
# Tests for CLI invocation via Click runner
# ============================================================================


class TestAliasCreateCLIRunner:
    """Tests for alias-create command via Click test runner."""

    @pytest.mark.linux_only
    def test_help_shows_user_option(self, cli_runner: CliRunner) -> None:
        """Help output should document --user option."""
        from check_zpools.cli import cli

        result = cli_runner.invoke(cli, ["alias-create", "--help"])
        assert result.exit_code == 0
        assert "--user" in result.output
        assert "username" in result.output.lower()

    @pytest.mark.linux_only
    def test_requires_root_via_cli(self, cli_runner: CliRunner) -> None:
        """Should fail when invoked without root."""
        from check_zpools.cli import cli

        with patch("os.geteuid", return_value=1000):
            result = cli_runner.invoke(cli, ["alias-create"])

        assert result.exit_code == 1
        assert "root" in result.output.lower() or "sudo" in result.output.lower()


class TestAliasDeleteCLIRunner:
    """Tests for alias-delete command via Click test runner."""

    @pytest.mark.linux_only
    def test_help_shows_user_option(self, cli_runner: CliRunner) -> None:
        """Help output should document --user option."""
        from check_zpools.cli import cli

        result = cli_runner.invoke(cli, ["alias-delete", "--help"])
        assert result.exit_code == 0
        assert "--user" in result.output
        assert "username" in result.output.lower()

    @pytest.mark.linux_only
    def test_requires_root_via_cli(self, cli_runner: CliRunner) -> None:
        """Should fail when invoked without root."""
        from check_zpools.cli import cli

        with patch("os.geteuid", return_value=1000):
            result = cli_runner.invoke(cli, ["alias-delete"])

        assert result.exit_code == 1
        assert "root" in result.output.lower() or "sudo" in result.output.lower()


# ============================================================================
# Tests for unsupported platform handling
# ============================================================================


class TestUnsupportedPlatformHandling:
    """Tests for unsupported platform detection and error handling."""

    def test_create_alias_raises_on_windows(self) -> None:
        """Should raise NotImplementedError on Windows."""
        with patch("platform.system", return_value="Windows"):
            with pytest.raises(NotImplementedError, match="Windows"):
                create_alias()

    def test_delete_alias_raises_on_windows(self) -> None:
        """Should raise NotImplementedError on Windows."""
        with patch("platform.system", return_value="Windows"):
            with pytest.raises(NotImplementedError, match="Windows"):
                delete_alias()

    def test_create_alias_raises_on_macos(self) -> None:
        """Should raise NotImplementedError on macOS."""
        with patch("platform.system", return_value="Darwin"):
            with pytest.raises(NotImplementedError, match="macOS"):
                create_alias()

    def test_delete_alias_raises_on_macos(self) -> None:
        """Should raise NotImplementedError on macOS."""
        with patch("platform.system", return_value="Darwin"):
            with pytest.raises(NotImplementedError, match="macOS"):
                delete_alias()


# ============================================================================
# Tests for --all-users (system-wide) alias management
# ============================================================================


class TestCreateAliasAllUsers:
    """Tests for creating system-wide alias in /etc/bash.bashrc."""

    @pytest.mark.linux_only
    def test_creates_alias_in_system_bashrc(self, tmp_path: Path) -> None:
        """Should create alias block in /etc/bash.bashrc when all_users=True."""
        system_bashrc = tmp_path / "bash.bashrc"
        system_bashrc.write_text("# existing system content\n")

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias(all_users=True)

        content = system_bashrc.read_text()
        assert ALIAS_MARKER_START in content
        assert ALIAS_MARKER_END in content
        assert "/usr/bin/check_zpools" in content
        assert "# existing system content" in content

    @pytest.mark.linux_only
    def test_all_users_ignores_username_parameter(self, tmp_path: Path) -> None:
        """When all_users=True, username parameter should be ignored."""
        system_bashrc = tmp_path / "bash.bashrc"
        system_bashrc.write_text("")

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            # Should not raise KeyError even with invalid username
            create_alias(username="nonexistent_user", all_users=True)

        content = system_bashrc.read_text()
        assert ALIAS_MARKER_START in content

    @pytest.mark.linux_only
    def test_all_users_requires_root(self) -> None:
        """Should raise PermissionError when not root with all_users=True."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="root"):
                create_alias(all_users=True)

    @pytest.mark.linux_only
    def test_all_users_success_message(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print correct success message for all users."""
        system_bashrc = tmp_path / "bash.bashrc"
        system_bashrc.write_text("")

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
            patch(
                "check_zpools.service_install._find_executable",
                return_value=("direct", Path("/usr/bin/check_zpools"), None),
            ),
        ):
            create_alias(all_users=True)

        captured = capsys.readouterr()
        assert "Alias created" in captured.out
        assert "all users" in captured.out
        assert "source" in captured.out


class TestDeleteAliasAllUsers:
    """Tests for removing system-wide alias from /etc/bash.bashrc."""

    @pytest.mark.linux_only
    def test_removes_alias_from_system_bashrc(self, tmp_path: Path) -> None:
        """Should remove alias block from /etc/bash.bashrc when all_users=True."""
        system_bashrc = tmp_path / "bash.bashrc"
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        system_bashrc.write_text(f"# system config\n{alias_block}# more config\n")

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
        ):
            delete_alias(all_users=True)

        content = system_bashrc.read_text()
        assert ALIAS_MARKER_START not in content
        assert ALIAS_MARKER_END not in content
        assert "# system config" in content
        assert "# more config" in content

    @pytest.mark.linux_only
    def test_all_users_delete_ignores_username_parameter(self, tmp_path: Path) -> None:
        """When all_users=True, username parameter should be ignored."""
        system_bashrc = tmp_path / "bash.bashrc"
        alias_block = _generate_alias_block("/usr/bin/check_zpools")
        system_bashrc.write_text(alias_block)

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
        ):
            # Should not raise KeyError even with invalid username
            delete_alias(username="nonexistent_user", all_users=True)

        content = system_bashrc.read_text()
        assert ALIAS_MARKER_START not in content

    @pytest.mark.linux_only
    def test_all_users_delete_requires_root(self) -> None:
        """Should raise PermissionError when not root with all_users=True."""
        with patch("os.geteuid", return_value=1000):
            with pytest.raises(PermissionError, match="root"):
                delete_alias(all_users=True)

    @pytest.mark.linux_only
    def test_all_users_delete_handles_no_alias(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print message when no alias exists in system bashrc."""
        system_bashrc = tmp_path / "bash.bashrc"
        system_bashrc.write_text("# just system config\n")

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
        ):
            delete_alias(all_users=True)

        captured = capsys.readouterr()
        assert "No" in captured.out and "alias" in captured.out

    @pytest.mark.linux_only
    def test_all_users_delete_handles_missing_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print message when /etc/bash.bashrc doesn't exist."""
        system_bashrc = tmp_path / "nonexistent_bash.bashrc"

        with (
            patch("os.geteuid", return_value=0),
            patch("check_zpools.alias_manager.SYSTEM_BASHRC", system_bashrc),
        ):
            delete_alias(all_users=True)

        captured = capsys.readouterr()
        assert "not found" in captured.out


class TestAliasCreateAllUsersCLI:
    """Tests for alias-create --all-users CLI option."""

    def test_all_users_option_available(self) -> None:
        """--all-users option should be available."""
        from check_zpools.cli import cli

        cmd = cli.commands["alias-create"]
        param_names = [p.name for p in cmd.params]
        assert "all_users" in param_names

    @pytest.mark.linux_only
    def test_help_shows_all_users_option(self, cli_runner: CliRunner) -> None:
        """Help output should document --all-users option."""
        from check_zpools.cli import cli

        result = cli_runner.invoke(cli, ["alias-create", "--help"])
        assert result.exit_code == 0
        assert "--all-users" in result.output
        assert "/etc/bash.bashrc" in result.output


class TestAliasDeleteAllUsersCLI:
    """Tests for alias-delete --all-users CLI option."""

    def test_all_users_option_available(self) -> None:
        """--all-users option should be available."""
        from check_zpools.cli import cli

        cmd = cli.commands["alias-delete"]
        param_names = [p.name for p in cmd.params]
        assert "all_users" in param_names

    @pytest.mark.linux_only
    def test_help_shows_all_users_option(self, cli_runner: CliRunner) -> None:
        """Help output should document --all-users option."""
        from check_zpools.cli import cli

        result = cli_runner.invoke(cli, ["alias-delete", "--help"])
        assert result.exit_code == 0
        assert "--all-users" in result.output
        assert "/etc/bash.bashrc" in result.output
