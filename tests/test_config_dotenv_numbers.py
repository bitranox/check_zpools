"""Digit-only ``.env`` values reach every text setting as the text the operator wrote.

lib_layered_config reads an unquoted ``.env`` or environment value as an int whenever that number
reads back as the same text (``123456`` -> ``123456``). A text setting must accept such a number and
keep its digits, otherwise an ordinary ``.env`` line makes the daemon refuse its configuration at
startup.

Each test loads a real ``.env`` through the real loader and asserts the library hands over an int
first, so a change in its coercion shows up here rather than on a deployed host.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from check_zpools.config import get_config, load_settings
from check_zpools.logging_setup import _build_runtime_config  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from lib_layered_config import Config

pytestmark = pytest.mark.os_agnostic


@pytest.fixture(autouse=True)
def _fresh_config_cache() -> Iterator[None]:
    get_config.cache_clear()
    yield
    get_config.cache_clear()


def _config_from_dotenv(tmp_path: Path, body: str) -> Config:
    (tmp_path / ".env").write_text(body, encoding="utf-8")
    return get_config(start_dir=str(tmp_path))


@pytest.mark.parametrize("key", ["smtp_password", "smtp_username"])
def test_a_digit_only_smtp_credential_reaches_the_email_settings_as_its_text(tmp_path: Path, key: str) -> None:
    config = _config_from_dotenv(tmp_path, f"EMAIL__{key.upper()}=123456\n")
    # Premise: the library hands the value over as a number. Without it the test proves nothing.
    assert isinstance(config.get("email", default={})[key], int)

    settings = load_settings(start_dir=str(tmp_path))

    assert getattr(settings.email, key) == "123456"


@pytest.mark.parametrize(
    ("section", "key"),
    [("daemon", "state_file"), ("alerts", "subject_prefix")],
)
def test_a_digit_only_text_setting_is_read_as_its_text(tmp_path: Path, section: str, key: str) -> None:
    config = _config_from_dotenv(tmp_path, f"{section.upper()}__{key.upper()}=2026\n")
    assert isinstance(config.get(section, default={})[key], int)

    settings = load_settings(start_dir=str(tmp_path))

    assert getattr(getattr(settings, section), key) == "2026"


@pytest.mark.parametrize("key", ["service", "environment"])
def test_a_digit_only_logging_name_reaches_lib_log_rich_as_its_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.chdir(tmp_path)
    config = _config_from_dotenv(tmp_path, f"LIB_LOG_RICH__{key.upper()}=4711\n")
    assert isinstance(config.get("lib_log_rich", default={})[key], int)

    assert getattr(_build_runtime_config(), key) == "4711"


def test_a_numeric_setting_still_reads_as_a_number(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__TIMEOUT=45\n")
    assert isinstance(config.get("email", default={})["timeout"], int)

    assert load_settings(start_dir=str(tmp_path)).email.timeout == 45.0


def test_a_boolean_is_still_refused_as_a_text_setting(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "ALERTS__SUBJECT_PREFIX=true\n")
    assert config.get("alerts", default={})["subject_prefix"] is True

    with pytest.raises(ValueError, match="subject_prefix"):
        load_settings(start_dir=str(tmp_path))


def test_a_digit_only_sender_is_read_as_text_and_then_refused_as_an_address(tmp_path: Path) -> None:
    config = _config_from_dotenv(tmp_path, "EMAIL__FROM_ADDRESS=2026\n")
    assert isinstance(config.get("email", default={})["from_address"], int)

    with pytest.raises(ValueError, match="from_address must contain @, got '2026'"):
        load_settings(start_dir=str(tmp_path))
