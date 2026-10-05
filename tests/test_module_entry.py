"""Module entry stories ensuring `python -m` runs exactly `cli.main`."""

from __future__ import annotations

import importlib
import runpy
import sys
from typing import TYPE_CHECKING

import lib_cli_exit_tools
import pytest

from check_zpools import cli as cli_mod

if TYPE_CHECKING:
    from collections.abc import Callable


def _run_module_entry(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    """Run ``python -m check_zpools`` in-process and return its exit code."""
    monkeypatch.setattr(sys, "argv", ["check_zpools", *argv])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("check_zpools.__main__", run_name="__main__")
    code = exc.value.code
    assert isinstance(code, int)
    return code


@pytest.mark.os_agnostic
@pytest.mark.parametrize("argv", [["--bogus"], ["no-such-command"], ["info", "--bogus"], ["--help"], ["info"]])
def test_module_entry_exits_with_the_code_the_console_script_gives(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None, argv: list[str]) -> None:
    script_code = cli_mod.main(argv)

    assert _run_module_entry(monkeypatch, argv) == script_code


@pytest.mark.os_agnostic
def test_a_usage_error_exits_two_under_module_entry(monkeypatch: pytest.MonkeyPatch, isolated_traceback_config: None) -> None:
    assert _run_module_entry(monkeypatch, ["no-such-command"]) == 2


def _raise_boom() -> None:
    """Stand in for a callable that fails before any handler is installed."""
    raise RuntimeError("boom")


@pytest.mark.os_agnostic
def test_when_traceback_flag_is_used_via_module_entry_the_full_poem_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    strip_ansi: Callable[[str], str],
) -> None:
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback", False, raising=False)
    monkeypatch.setattr(lib_cli_exit_tools.config, "traceback_force_color", False, raising=False)
    # info has no error handler of its own, so this reaches the traceback
    # printer the way an unexpected failure would.
    monkeypatch.setattr("check_zpools.__init__conf__.print_info", _raise_boom)

    code = _run_module_entry(monkeypatch, ["--traceback", "info"])

    plain_err = strip_ansi(capsys.readouterr().err)
    assert code != 0
    assert "Traceback (most recent call last)" in plain_err
    assert "RuntimeError: boom" in plain_err
    assert "[TRUNCATED" not in plain_err
    assert lib_cli_exit_tools.config.traceback is False
    assert lib_cli_exit_tools.config.traceback_force_color is False


@pytest.mark.os_agnostic
def test_when_the_module_is_imported_it_runs_nothing() -> None:
    # Left imported, every later runpy of check_zpools.__main__ warns that it is already loaded.
    previous = sys.modules.pop("check_zpools.__main__", None)
    try:
        module = importlib.import_module("check_zpools.__main__")

        assert module.cli is cli_mod
    finally:
        sys.modules.pop("check_zpools.__main__", None)
        if previous is not None:
            sys.modules["check_zpools.__main__"] = previous
