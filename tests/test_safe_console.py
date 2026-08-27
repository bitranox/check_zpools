"""Tests for the encode-safe console adapter.

These pin the behaviour that a legacy-codepage console (the Windows default,
cp1252) must never turn a successful command into a crash.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rich.console import Console

from check_zpools import safe_console

SRC = Path(__file__).resolve().parent.parent / "src" / "check_zpools"


def _cp1252_stream() -> io.TextIOWrapper:
    """Build the stream shape a Windows cp1252 console hands to Python."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")


def _read_back(stream: io.TextIOWrapper) -> str:
    stream.flush()
    buffer = stream.buffer
    assert isinstance(buffer, io.BytesIO)
    return buffer.getvalue().decode("cp1252")


class TestEchoOnALegacyCodepage:
    """A cp1252 console must degrade the glyph, not raise."""

    def test_check_mark_does_not_raise(self) -> None:
        stream = _cp1252_stream()
        safe_console.echo("✓ Alias created for 'check_zpools'", file=stream)
        assert "[OK]" in _read_back(stream)

    @pytest.mark.parametrize(
        ("glyph", "expected"),
        [
            ("✓", "[OK]"),
            ("✗", "[X]"),
            ("⚠", "[!]"),
            ("≥", ">="),
            ("→", "->"),
        ],
    )
    def test_a_glyph_cp1252_lacks_degrades_to_its_ascii_form(self, glyph: str, expected: str) -> None:
        stream = _cp1252_stream()
        safe_console.echo(f"{glyph} status", file=stream)
        assert expected in _read_back(stream)

    @pytest.mark.parametrize("glyph", ["•", "…", "\u2019"])
    def test_a_glyph_cp1252_has_is_left_alone(self, glyph: str) -> None:
        """Degrade only what the stream cannot take; cp1252 has these."""
        stream = _cp1252_stream()
        safe_console.echo(f"{glyph} status", file=stream)
        assert glyph in _read_back(stream)

    @pytest.mark.parametrize(
        ("glyph", "expected"),
        [("✓", "[OK]"), ("✗", "[X]"), ("⚠", "[!]"), ("•", "-"), ("≥", ">="), ("→", "->"), ("…", "..."), ("\u2019", "'")],
    )
    def test_every_mapped_glyph_degrades_on_a_pure_ascii_stream(self, glyph: str, expected: str) -> None:
        assert expected in safe_console.encode_safe(f"{glyph} status", "ascii")

    def test_an_unmapped_character_is_replaced_rather_than_raising(self) -> None:
        stream = _cp1252_stream()
        safe_console.echo("pool 中文 name", file=stream)
        assert "pool" in _read_back(stream)

    def test_the_message_is_written_exactly_once(self) -> None:
        """A retry-after-failure would emit the surviving prefix twice."""
        stream = _cp1252_stream()
        safe_console.echo("\n✓ done", file=stream)
        assert _read_back(stream).count("done") == 1


class TestEchoOnAUtf8Console:
    """The common case must be untouched: the glyph survives verbatim."""

    def test_glyph_is_preserved(self) -> None:
        stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", errors="strict", newline="")
        safe_console.echo("✓ Alias created", file=stream)
        stream.flush()
        buffer = stream.buffer
        assert isinstance(buffer, io.BytesIO)
        assert "✓" in buffer.getvalue().decode("utf-8")


class TestTheDefaultTargetFollowsTheStreamEchoWritesTo:
    """With no `file`, the encoding must come from the stream `echo` lands on.

    click resolves that target itself from ``sys.stdout``/``sys.stderr``. Judge
    the wrong stream and a legacy-codepage console gets exactly the crash this
    module exists to prevent, while every test passing an explicit `file` stays
    green and says nothing about it.
    """

    def test_a_cp1252_stdout_degrades_the_glyph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stream = _cp1252_stream()
        monkeypatch.setattr(sys, "stdout", stream)
        safe_console.echo("✓ deployed")
        assert "[OK]" in _read_back(stream)

    def test_err_is_judged_against_stderr_not_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stdout that could take the glyph must not excuse a cp1252 stderr."""
        stream = _cp1252_stream()
        monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline=""))
        monkeypatch.setattr(sys, "stderr", stream)
        safe_console.echo("✓ deployed", err=True)
        assert "[OK]" in _read_back(stream)


class TestSafeStreamProtectsRich:
    """Rich raises on a legacy codepage too; it renders through its own writer."""

    def test_rich_output_degrades_instead_of_raising(self) -> None:
        stream = _cp1252_stream()
        Console(file=safe_console.safe_stream(stream), legacy_windows=False, width=80).print("check ✓ done ≥ 90%")
        written = _read_back(stream)
        assert "[OK]" in written
        assert ">= 90%" in written

    def test_the_default_check_console_is_wrapped(self) -> None:
        """The regression: display_check_result_text built an unwrapped Console."""
        source = (SRC / "formatters.py").read_text(encoding="utf-8")
        assert "Console(file=sys.stdout" not in source
        assert "Console(file=safe_stream(sys.stdout)" in source


class TestNoModuleBypassesTheAdapter:
    """The guard that keeps this fixed for the next output line someone adds."""

    def test_no_src_module_calls_click_echo_directly(self) -> None:
        offenders = [
            f"{path.relative_to(SRC)}:{number}"
            for path in sorted(SRC.rglob("*.py"))
            if path.name != "safe_console.py"
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if "click.echo(" in line
        ]
        assert not offenders, f"these call click.echo directly and will crash on a cp1252 console; use check_zpools.safe_console.echo instead: {offenders}"


class TestTheRealCliSurvivesALegacyCodepage:
    """End-to-end: the packaged CLI on a cp1252 stdout, as Windows runs it."""

    def test_help_runs_under_a_cp1252_stdout(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-X", "utf8=0", "-m", "check_zpools", "--help"],
            capture_output=True,
            # Inherit the real environment: replacing it outright leaves a Windows
            # child with no SYSTEMROOT and no usable PATH, so python.exe never starts.
            env={**os.environ, "PYTHONIOENCODING": "cp1252:strict"},
            check=False,
        )
        assert completed.returncode == 0, completed.stderr.decode("cp1252", "replace")
        assert b"UnicodeEncodeError" not in completed.stderr
