"""Configuration display functionality for CLI config command.

Purpose
-------
Provides the business logic for displaying merged configuration from all
sources in human-readable or JSON format. Keeps CLI layer thin by handling
all formatting and display logic here.

Contents
--------
* :func:`display_config` – displays configuration in requested format

System Role
-----------
Lives in the behaviors layer. The CLI command delegates to this module for
all configuration display logic, keeping presentation concerns separate from
command-line argument parsing.
"""

from __future__ import annotations

import json
from typing import Any, cast

import click

from .config import get_config


def _collect_dotted_keys(data: dict[str, Any], prefix: str = "") -> list[str]:
    """Recursively collect all dotted keys from a nested dictionary.

    Parameters
    ----------
    data:
        Dictionary to traverse
    prefix:
        Current dotted prefix

    Returns
    -------
    list[str]
        List of dotted keys (e.g., ["db.host", "db.port"])

    Examples
    --------
    >>> _collect_dotted_keys({"db": {"host": "localhost", "port": 5432}})
    ['db.host', 'db.port']
    """
    keys: list[str] = []
    for key, value in data.items():
        dotted_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            # Recurse into nested dicts
            keys.extend(_collect_dotted_keys(value, prefix=dotted_key))
        else:
            # Leaf value
            keys.append(dotted_key)
    return keys


def _format_source_info(layer: str | None, path: str | None) -> str:
    """Format source information into a human-readable string.

    Parameters
    ----------
    layer:
        Configuration layer name (e.g., "app", "user", "env")
    path:
        File path or None for environment variables

    Returns
    -------
    str
        Formatted source string

    Examples
    --------
    >>> _format_source_info("app", "/etc/xdg/app/config.toml")
    '[app: /etc/xdg/app/config.toml]'
    >>> _format_source_info("env", None)
    '[env]'
    """
    if layer is None:
        return "[unknown]"
    if path is None:
        return f"[{layer}]"
    return f"[{layer}: {path}]"


def _display_value_with_source(
    key: str,
    value: Any,
    dotted_key: str,
    config: Any,
    indent: str = "  ",
) -> None:
    """Display a configuration value with its source information.

    Parameters
    ----------
    key:
        The configuration key name
    value:
        The configuration value
    dotted_key:
        Full dotted path to this key
    config:
        The Config object (for querying origin)
    indent:
        Indentation string for nested values
    """
    # Get source info for this key (if config.origin is available)
    source_str = ""
    if hasattr(config, "origin"):
        source_info = config.origin(dotted_key)
        if source_info:
            source_str = f"  # {_format_source_info(source_info.get('layer'), source_info.get('path'))}"

    if isinstance(value, dict):
        # For nested dicts, show the header and recurse
        click.echo(f"{indent}{key}:")
        for nested_key, nested_value in value.items():
            nested_dotted_key = f"{dotted_key}.{nested_key}"
            _display_value_with_source(
                nested_key,
                nested_value,
                nested_dotted_key,
                config,
                indent=indent + "  ",
            )
    elif isinstance(value, list):
        # For lists, show as JSON with source
        click.echo(f"{indent}{key} = {json.dumps(value)}{source_str}")
    elif isinstance(value, str):
        click.echo(f'{indent}{key} = "{value}"{source_str}')
    else:
        click.echo(f"{indent}{key} = {value}{source_str}")


def _display_json_section(config: Any, section: str | None) -> None:
    """Display configuration section(s) in JSON format.

    Parameters
    ----------
    config:
        Configuration object with get() and to_json() methods
    section:
        Optional section name to display. If None, displays all configuration.

    Raises
    ------
    SystemExit:
        Exit code 1 if requested section doesn't exist.
    """
    if section:
        section_data = config.get(section, default={})
        if section_data:
            click.echo(json.dumps({section: section_data}, indent=2))
        else:
            click.echo(f"Section '{section}' not found or empty", err=True)
            raise SystemExit(1)
    else:
        click.echo(config.to_json(indent=2))


def _display_human_section_data(section_name: str, section_data: Any, config: Any) -> None:
    """Display a single section's data in human-readable format.

    Parameters
    ----------
    section_name:
        Name of the section being displayed
    section_data:
        Section data (dict or scalar value)
    config:
        Configuration object for source lookup
    """
    click.echo(f"\n[{section_name}]")
    if isinstance(section_data, dict):
        dict_data = cast(dict[str, Any], section_data)
        for key, value in dict_data.items():
            dotted_key = f"{section_name}.{key}"
            _display_value_with_source(key, value, dotted_key, config, indent="  ")
    else:
        click.echo(f"  {section_data}")


def _display_human_section(config: Any, section: str | None) -> None:
    """Display configuration section(s) in human-readable format.

    Parameters
    ----------
    config:
        Configuration object with get() and as_dict() methods
    section:
        Optional section name to display. If None, displays all configuration.

    Raises
    ------
    SystemExit:
        Exit code 1 if requested section doesn't exist.
    """
    if section:
        section_data = config.get(section, default={})
        if section_data:
            _display_human_section_data(section, section_data, config)
        else:
            click.echo(f"Section '{section}' not found or empty", err=True)
            raise SystemExit(1)
    else:
        data: dict[str, Any] = config.as_dict()
        for section_name in data:
            section_data: Any = data[section_name]
            _display_human_section_data(section_name, section_data, config)


def display_config(*, format: str = "human", section: str | None = None) -> None:
    """Display the current merged configuration from all sources.

    Why
    ---
    Users need visibility into the effective configuration loaded from
    defaults, app configs, host configs, user configs, .env files, and
    environment variables.

    What
    ----
    Loads configuration via get_config() and outputs it in the requested
    format. Supports filtering to a specific section and both human-readable
    and JSON output formats.

    Parameters
    ----------
    format:
        Output format: "human" for TOML-like display or "json" for JSON.
        Defaults to "human".
    section:
        Optional section name to display only that section. When None, displays
        all configuration.

    Side Effects
    ------------
    Writes formatted configuration to stdout via click.echo().
    Raises SystemExit(1) if requested section doesn't exist.

    Notes
    -----
    The human-readable format mimics TOML syntax for consistency with the
    configuration file format. JSON format provides machine-readable output
    suitable for parsing by other tools.

    Examples
    --------
    >>> display_config()  # doctest: +SKIP
    [lib_log_rich]
      service = "check_zpools"
      environment = "prod"

    >>> display_config(format="json")  # doctest: +SKIP
    {
      "lib_log_rich": {
        "service": "check_zpools",
        "environment": "prod"
      }
    }
    """
    config = get_config()

    if format.lower() == "json":
        _display_json_section(config, section)
    else:
        _display_human_section(config, section)


__all__ = [
    "display_config",
]
