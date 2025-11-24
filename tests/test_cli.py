"""CLI stories: every invocation a single beat."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from click.testing import CliRunner, Result

import lib_cli_exit_tools

from check_zpools import cli as cli_mod
from check_zpools import __init__conf__


@dataclass(slots=True)
class CapturedRun:
    """Record of a single ``lib_cli_exit_tools.run_cli`` invocation.

    Attributes
    ----------
    command:
        Command object passed to ``run_cli``.
    argv:
        Argument vector forwarded to the command, when any.
    prog_name:
        Program name announced in the help output.
    signal_specs:
        Signal handlers registered by the runner.
    install_signals:
        ``True`` when the runner installed default signal handlers.
    """

    command: Any
    argv: Sequence[str] | None
    prog_name: str | None
    signal_specs: Any
    install_signals: bool


def _capture_run_cli(target: list[CapturedRun]) -> Callable[..., int]:
    """Return a stub that records ``lib_cli_exit_tools.run_cli`` invocations.

    Why
        Tests assert that the CLI delegates to ``lib_cli_exit_tools`` with the
        expected arguments; recording each call keeps those assertions readable.

    Inputs
        target:
            Mutable list that will collect :class:`CapturedRun` entries.

    Outputs
        Callable[..., int]:
            Replacement for ``lib_cli_exit_tools.run_cli``.
    """

    def _run(
        command: Any,
        argv: Sequence[str] | None = None,
        *,
        prog_name: str | None = None,
        signal_specs: Any = None,
        install_signals: bool = True,
    ) -> int:
        target.append(
            CapturedRun(
                command=command,
                argv=argv,
                prog_name=prog_name,
                signal_specs=signal_specs,
                install_signals=install_signals,
            )
        )
        return 42

    return _run


@pytest.mark.os_agnostic
def test_when_we_snapshot_traceback_the_initial_state_is_quiet(isolated_traceback_config: None) -> None:
    assert cli_mod.snapshot_traceback_state() == (False, False)


@pytest.mark.os_agnostic
def test_when_we_enable_traceback_the_config_sings_true(isolated_traceback_config: None) -> None:
    cli_mod.apply_traceback_preferences(True)

    assert lib_cli_exit_tools.config.traceback is True
    assert lib_cli_exit_tools.config.traceback_force_color is True


@pytest.mark.os_agnostic
def test_when_we_restore_traceback_the_config_whispers_false(isolated_traceback_config: None) -> None:
    previous = cli_mod.snapshot_traceback_state()
    cli_mod.apply_traceback_preferences(True)

    cli_mod.restore_traceback_state(previous)

    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_info_runs_with_traceback_the_choice_is_shared(
    monkeypatch: pytest.MonkeyPatch,
    isolated_traceback_config: None,
    preserve_traceback_state: None,
) -> None:
    notes: list[tuple[bool, bool]] = []

    def record() -> None:
        notes.append(
            (
                lib_cli_exit_tools.config.traceback,
                lib_cli_exit_tools.config.traceback_force_color,
            )
        )

    monkeypatch.setattr(cli_mod.__init__conf__, "print_info", record)

    exit_code = cli_mod.main(["--traceback", "info"])

    assert exit_code == 0
    assert notes == [(True, True)]
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_main_is_called_it_delegates_to_run_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger: list[CapturedRun] = []
    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", _capture_run_cli(ledger))

    result = cli_mod.main(["info"])

    assert result == 42
    assert ledger == [
        CapturedRun(
            command=cli_mod.cli,
            argv=["info"],
            prog_name=__init__conf__.shell_command,
            signal_specs=None,
            install_signals=True,
        )
    ]


@pytest.mark.os_agnostic
def test_when_cli_runs_without_arguments_help_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    calls: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    result = cli_runner.invoke(cli_mod.cli, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert calls == []


@pytest.mark.os_agnostic
def test_when_main_receives_no_arguments_cli_main_is_exercised(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
    isolated_traceback_config: None,
) -> None:
    calls: list[str] = []
    outputs: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    def fake_run_cli(
        command: Any,
        argv: Sequence[str] | None = None,
        *,
        prog_name: str | None = None,
        signal_specs: Any = None,
        install_signals: bool = True,
    ) -> int:
        args = [] if argv is None else list(argv)
        result: Result = cli_runner.invoke(command, args)
        if result.exception is not None:
            raise result.exception
        outputs.append(result.output)
        return result.exit_code

    monkeypatch.setattr(lib_cli_exit_tools, "run_cli", fake_run_cli)

    exit_code = cli_mod.main([])

    assert exit_code == 0
    assert calls == []
    assert outputs and "Usage:" in outputs[0]


@pytest.mark.os_agnostic
def test_when_traceback_is_requested_without_command_the_domain_runs(
    monkeypatch: pytest.MonkeyPatch,
    cli_runner: CliRunner,
) -> None:
    calls: list[str] = []

    def remember() -> None:
        calls.append("called")

    monkeypatch.setattr(cli_mod, "noop_main", remember)

    result = cli_runner.invoke(cli_mod.cli, ["--traceback"])

    assert result.exit_code == 0
    assert calls == ["called"]
    assert "Usage:" not in result.output


@pytest.mark.os_agnostic
def test_when_traceback_flag_is_passed_the_full_story_is_printed(
    isolated_traceback_config: None,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    exit_code = cli_mod.main(["--traceback", "fail"])

    plain_err = strip_ansi(capsys.readouterr().err)

    assert exit_code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: I should fail" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_hello_is_invoked_the_cli_smiles(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["hello"])

    assert result.exit_code == 0
    assert "Hello World" in result.output


@pytest.mark.os_agnostic
def test_when_fail_is_invoked_the_cli_raises(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["fail"])

    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)


@pytest.mark.os_agnostic
def test_when_info_is_invoked_the_metadata_is_displayed(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["info"])

    assert result.exit_code == 0
    assert f"Info for {__init__conf__.name}:" in result.output
    assert __init__conf__.version in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_it_displays_configuration(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["config"])

    assert result.exit_code == 0
    # With default config (all commented), output may be empty or show only log messages


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_it_outputs_json(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json"])

    assert result.exit_code == 0
    # JSON output should be valid (empty object if no config)
    assert "{" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_nonexistent_section_it_fails(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--section", "nonexistent_section_that_does_not_exist"])

    assert result.exit_code != 0
    assert "not found or empty" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_mocked_data_it_displays_sections(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lib_layered_config import Config
    from lib_layered_config.domain.config import SourceInfo

    # Create a mock Config with test data
    test_config_data = {
        "test_section": {
            "setting1": "value1",
            "setting2": 42,
        }
    }

    class MockConfig(Config):
        def __init__(self) -> None:
            # Initialize parent with empty meta since we override all methods
            from types import MappingProxyType

            super().__init__(_data=MappingProxyType(test_config_data), _meta={})

        def as_dict(self) -> dict[str, Any]:
            return test_config_data

        def to_json(self, *, indent: int | None = None) -> str:
            import json

            return json.dumps(test_config_data, indent=indent)

        def get(self, key: str, default: Any = None) -> Any:
            return test_config_data.get(key, default)

        def origin(self, key: str) -> SourceInfo | None:
            # Mock origin - return None since we don't track sources in tests
            return None

    # Clear the lru_cache on get_config
    from check_zpools import config as config_mod
    from check_zpools import config_show

    config_mod.get_config.cache_clear()

    # Mock get_config to return our test config
    def mock_get_config(**kwargs: Any) -> Config:
        return MockConfig()

    # Patch in both modules to ensure the mock is used
    monkeypatch.setattr(config_mod, "get_config", mock_get_config)
    monkeypatch.setattr(config_show, "get_config", mock_get_config)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config"])

    assert result.exit_code == 0
    assert "test_section" in result.output
    assert "setting1" in result.output
    assert "value1" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_and_section_it_shows_section(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test JSON format with specific section."""
    from lib_layered_config import Config
    from lib_layered_config.domain.config import SourceInfo

    test_config_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "from_address": "test@example.com",
        }
    }

    class MockConfig(Config):
        def __init__(self) -> None:
            from types import MappingProxyType

            super().__init__(_data=MappingProxyType(test_config_data), _meta={})

        def get(self, key: str, default: Any = None) -> Any:
            return test_config_data.get(key, default)

        def origin(self, key: str) -> SourceInfo | None:
            return None

    from check_zpools import config as config_mod
    from check_zpools import config_show

    config_mod.get_config.cache_clear()

    def mock_get_config(**kwargs: Any) -> Config:
        return MockConfig()

    monkeypatch.setattr(config_mod, "get_config", mock_get_config)
    monkeypatch.setattr(config_show, "get_config", mock_get_config)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json", "--section", "email"])

    assert result.exit_code == 0
    assert "email" in result.output
    assert "smtp_hosts" in result.output
    assert "smtp.test.com:587" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_json_format_and_nonexistent_section_it_fails(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test JSON format with nonexistent section returns error."""
    from lib_layered_config import Config
    from lib_layered_config.domain.config import SourceInfo

    test_config_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
        }
    }

    class MockConfig(Config):
        def __init__(self) -> None:
            from types import MappingProxyType

            super().__init__(_data=MappingProxyType(test_config_data), _meta={})

        def get(self, key: str, default: Any = None) -> Any:
            return test_config_data.get(key, default)

        def origin(self, key: str) -> SourceInfo | None:
            return None

    from check_zpools import config as config_mod
    from check_zpools import config_show

    config_mod.get_config.cache_clear()

    def mock_get_config(**kwargs: Any) -> Config:
        return MockConfig()

    monkeypatch.setattr(config_mod, "get_config", mock_get_config)
    monkeypatch.setattr(config_show, "get_config", mock_get_config)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--format", "json", "--section", "nonexistent"])

    assert result.exit_code != 0
    assert "not found or empty" in result.output


@pytest.mark.os_agnostic
def test_when_config_is_invoked_with_section_showing_complex_values(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test human format with section containing lists and dicts."""
    from lib_layered_config import Config
    from lib_layered_config.domain.config import SourceInfo

    test_config_data = {
        "email": {
            "smtp_hosts": ["smtp1.test.com:587", "smtp2.test.com:587"],
            "from_address": "test@example.com",
            "metadata": {"key1": "value1", "key2": "value2"},
            "timeout": 60.0,
        }
    }

    class MockConfig(Config):
        def __init__(self) -> None:
            from types import MappingProxyType

            super().__init__(_data=MappingProxyType(test_config_data), _meta={})

        def get(self, key: str, default: Any = None) -> Any:
            return test_config_data.get(key, default)

        def origin(self, key: str) -> SourceInfo | None:
            return None

    from check_zpools import config as config_mod
    from check_zpools import config_show

    config_mod.get_config.cache_clear()

    def mock_get_config(**kwargs: Any) -> Config:
        return MockConfig()

    monkeypatch.setattr(config_mod, "get_config", mock_get_config)
    monkeypatch.setattr(config_show, "get_config", mock_get_config)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config", "--section", "email"])

    assert result.exit_code == 0
    assert "[email]" in result.output
    assert "smtp_hosts" in result.output
    # List should be JSON formatted
    assert '["smtp1.test.com:587", "smtp2.test.com:587"]' in result.output or "smtp1.test.com:587" in result.output
    # Dict should be JSON formatted
    assert "metadata" in result.output
    # String should be quoted
    assert '"test@example.com"' in result.output
    # Number should not be quoted
    assert "60.0" in result.output


@pytest.mark.os_agnostic
def test_when_config_shows_all_sections_with_complex_values(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test human format showing all sections with lists and dicts."""
    from lib_layered_config import Config
    from lib_layered_config.domain.config import SourceInfo

    test_config_data = {
        "email": {
            "smtp_hosts": ["smtp.test.com:587"],
            "tags": {"environment": "test", "version": "1.0"},
        },
        "logging": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
        },
    }

    class MockConfig(Config):
        def __init__(self) -> None:
            from types import MappingProxyType

            super().__init__(_data=MappingProxyType(test_config_data), _meta={})

        def as_dict(self) -> dict[str, Any]:
            return test_config_data

        def origin(self, key: str) -> SourceInfo | None:
            return None

    from check_zpools import config as config_mod
    from check_zpools import config_show

    config_mod.get_config.cache_clear()

    def mock_get_config(**kwargs: Any) -> Config:
        return MockConfig()

    monkeypatch.setattr(config_mod, "get_config", mock_get_config)
    monkeypatch.setattr(config_show, "get_config", mock_get_config)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config"])

    assert result.exit_code == 0
    assert "[email]" in result.output
    assert "[logging]" in result.output
    # Lists should be JSON formatted
    assert "smtp_hosts" in result.output
    assert "handlers" in result.output
    # Dicts should be JSON formatted
    assert "tags" in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_without_target_it_fails(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy"])

    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()


@pytest.mark.os_agnostic
def test_when_config_deploy_is_invoked_it_deploys_configuration(
    cli_runner: CliRunner,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    # Mock deploy_configuration to return a test path without actually deploying
    deployed_path = tmp_path / "config.toml"
    deployed_path.touch()

    def mock_deploy(*, targets: Any, force: bool = False) -> list[Path]:
        return [deployed_path]

    # Patch in the config_deploy command module where the function is used
    from check_zpools.cli_commands.commands import config_deploy

    monkeypatch.setattr(config_deploy, "deploy_configuration", mock_deploy)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"])

    assert result.exit_code == 0
    assert "Configuration deployed successfully" in result.output
    assert str(deployed_path) in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_finds_no_files_to_create_it_informs_user(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    def mock_deploy(*, targets: Any, force: bool = False) -> list[Path]:
        return []  # No files created

    from check_zpools.cli_commands.commands import config_deploy

    monkeypatch.setattr(config_deploy, "deploy_configuration", mock_deploy)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user"])

    assert result.exit_code == 0
    assert "No files were created" in result.output
    assert "--force" in result.output


@pytest.mark.os_agnostic
def test_when_config_deploy_encounters_permission_error_it_handles_gracefully(
    cli_runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mock_deploy(*, targets: Any, force: bool = False) -> list[Any]:
        raise PermissionError("Permission denied")

    from check_zpools.cli_commands.commands import config_deploy

    monkeypatch.setattr(config_deploy, "deploy_configuration", mock_deploy)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "app"])

    assert result.exit_code != 0
    assert "Permission denied" in result.output
    assert "sudo" in result.output.lower()


@pytest.mark.os_agnostic
def test_when_config_deploy_supports_multiple_targets(
    cli_runner: CliRunner,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    path1 = tmp_path / "config1.toml"
    path2 = tmp_path / "config2.toml"
    path1.touch()
    path2.touch()

    def mock_deploy(*, targets: Any, force: bool = False) -> list[Path]:
        assert len(targets) == 2
        assert "user" in targets
        assert "host" in targets
        return [path1, path2]

    from check_zpools.cli_commands.commands import config_deploy

    monkeypatch.setattr(config_deploy, "deploy_configuration", mock_deploy)

    result: Result = cli_runner.invoke(cli_mod.cli, ["config-deploy", "--target", "user", "--target", "host"])

    assert result.exit_code == 0
    assert str(path1) in result.output
    assert str(path2) in result.output


@pytest.mark.os_agnostic
def test_when_an_unknown_command_is_used_a_helpful_error_appears(cli_runner: CliRunner) -> None:
    result: Result = cli_runner.invoke(cli_mod.cli, ["does-not-exist"])

    assert result.exit_code != 0
    assert "No such command" in result.output


@pytest.mark.os_agnostic
def test_when_restore_is_disabled_the_traceback_choice_remains(
    isolated_traceback_config: None,
    preserve_traceback_state: None,
) -> None:
    cli_mod.apply_traceback_preferences(False)

    cli_mod.main(["--traceback", "hello"], restore_traceback=False)

    assert lib_cli_exit_tools.config.traceback is True
    assert lib_cli_exit_tools.config.traceback_force_color is True


# ======================== Email Command Tests ========================


@pytest.mark.os_agnostic
def test_when_send_email_is_invoked_without_smtp_hosts_it_fails(
    cli_runner: CliRunner,
) -> None:
    """When SMTP hosts are not configured, send-email should exit with error."""
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-email",
            "--to",
            "recipient@test.com",
            "--subject",
            "Test",
            "--body",
            "Hello",
        ],
    )

    assert result.exit_code == 1
    assert "No SMTP hosts configured" in result.output


@pytest.mark.os_agnostic
def test_when_send_email_is_invoked_with_valid_config_it_sends(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """When SMTP is configured, send-email should successfully send."""
    from unittest.mock import patch, MagicMock

    # Create test config with SMTP settings
    config_path = tmp_path / "test_config.toml"
    config_path.write_text('[email]\nsmtp_hosts = ["smtp.test.com:587"]\nfrom_address = "sender@test.com"\n')

    with patch("check_zpools.cli_commands.commands.send_email.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            # Mock config
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "sender@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-email",
                    "--to",
                    "recipient@test.com",
                    "--subject",
                    "Test Subject",
                    "--body",
                    "Test body",
                ],
            )

            assert result.exit_code == 0
            assert "Email sent successfully" in result.output


@pytest.mark.os_agnostic
def test_when_send_email_receives_multiple_recipients_it_accepts_them(
    cli_runner: CliRunner,
) -> None:
    """When multiple --to flags are provided, send-email should accept them."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_email.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "sender@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-email",
                    "--to",
                    "user1@test.com",
                    "--to",
                    "user2@test.com",
                    "--subject",
                    "Test",
                    "--body",
                    "Hello",
                ],
            )

            assert result.exit_code == 0


@pytest.mark.os_agnostic
def test_when_send_email_includes_html_body_it_sends(
    cli_runner: CliRunner,
) -> None:
    """When HTML body is provided, send-email should include it."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_email.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "sender@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-email",
                    "--to",
                    "recipient@test.com",
                    "--subject",
                    "Test",
                    "--body",
                    "Plain text",
                    "--body-html",
                    "<h1>HTML</h1>",
                ],
            )

            assert result.exit_code == 0


@pytest.mark.os_agnostic
def test_when_send_email_has_attachments_it_sends(
    cli_runner: CliRunner,
    tmp_path: Any,
) -> None:
    """When attachments are provided, send-email should include them."""
    from unittest.mock import patch, MagicMock

    # Create test attachment
    attachment = tmp_path / "test.txt"
    attachment.write_text("Test content")

    with patch("check_zpools.cli_commands.commands.send_email.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "sender@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-email",
                    "--to",
                    "recipient@test.com",
                    "--subject",
                    "Test",
                    "--body",
                    "See attachment",
                    "--attachment",
                    str(attachment),
                ],
            )

            assert result.exit_code == 0


@pytest.mark.os_agnostic
def test_when_send_email_smtp_fails_it_reports_error(
    cli_runner: CliRunner,
) -> None:
    """When SMTP connection fails, send-email should show error message."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_email.get_config") as mock_get_config:
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionError("Cannot connect")

            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "sender@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-email",
                    "--to",
                    "recipient@test.com",
                    "--subject",
                    "Test",
                    "--body",
                    "Hello",
                ],
            )

            assert result.exit_code == 1
            assert "Error" in result.output


@pytest.mark.os_agnostic
def test_when_send_notification_is_invoked_without_smtp_hosts_it_fails(
    cli_runner: CliRunner,
) -> None:
    """When SMTP hosts are not configured, send-notification should exit with error."""
    result: Result = cli_runner.invoke(
        cli_mod.cli,
        [
            "send-notification",
            "--to",
            "admin@test.com",
            "--subject",
            "Alert",
            "--message",
            "System notification",
        ],
    )

    assert result.exit_code == 1
    assert "No SMTP hosts configured" in result.output


@pytest.mark.os_agnostic
def test_when_send_notification_is_invoked_with_valid_config_it_sends(
    cli_runner: CliRunner,
) -> None:
    """When SMTP is configured, send-notification should successfully send."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_notification.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "alerts@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-notification",
                    "--to",
                    "admin@test.com",
                    "--subject",
                    "Alert",
                    "--message",
                    "System notification",
                ],
            )

            assert result.exit_code == 0
            assert "Notification sent successfully" in result.output


@pytest.mark.os_agnostic
def test_when_send_notification_receives_multiple_recipients_it_accepts_them(
    cli_runner: CliRunner,
) -> None:
    """When multiple --to flags are provided, send-notification should accept them."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_notification.get_config") as mock_get_config:
        with patch("smtplib.SMTP"):
            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "alerts@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-notification",
                    "--to",
                    "admin1@test.com",
                    "--to",
                    "admin2@test.com",
                    "--subject",
                    "Alert",
                    "--message",
                    "System notification",
                ],
            )

            assert result.exit_code == 0


@pytest.mark.os_agnostic
def test_when_send_notification_smtp_fails_it_reports_error(
    cli_runner: CliRunner,
) -> None:
    """When SMTP connection fails, send-notification should show error message."""
    from unittest.mock import patch, MagicMock

    with patch("check_zpools.cli_commands.commands.send_notification.get_config") as mock_get_config:
        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.side_effect = ConnectionError("Cannot connect")

            mock_config_obj = MagicMock()
            mock_config_obj.as_dict.return_value = {
                "email": {
                    "smtp_hosts": ["smtp.test.com:587"],
                    "from_address": "alerts@test.com",
                }
            }
            mock_get_config.return_value = mock_config_obj

            result: Result = cli_runner.invoke(
                cli_mod.cli,
                [
                    "send-notification",
                    "--to",
                    "admin@test.com",
                    "--subject",
                    "Alert",
                    "--message",
                    "System notification",
                ],
            )

            assert result.exit_code == 1
            assert "Error" in result.output
