"""CLI commands for configuration management.

Commands
--------
show-config         Pretty-print the current (loaded) configuration.
validate-config     Validate a config file and report errors.
reload-config       Re-read config file (V1: log warning, no hot-reload).
"""

from __future__ import annotations

import logging
import sys

import click
import yaml
from pydantic import BaseModel

from pinterest_agent.cli.main import cli
from pinterest_agent.config.loader import AppConfig, ConfigLoader

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_loader(config_path: str) -> ConfigLoader:
    """Build a config loader for the given path."""
    return ConfigLoader(config_path)


def _pretty_print_section(title: str, data: object, indent: int = 0) -> None:
    """Recursively pretty-print a config section."""
    prefix = "  " * indent
    if isinstance(data, dict):
        click.echo(f"{prefix}{title}:")
        for key, value in data.items():
            _pretty_print_section(str(key), value, indent + 1)
    elif isinstance(data, list):
        click.echo(f"{prefix}{title}:")
        for i, item in enumerate(data):
            _pretty_print_section(f"[{i}]", item, indent + 1)
    elif isinstance(data, BaseModel):
        click.echo(f"{prefix}{title}:")
        for field_name in data.model_fields:
            _pretty_print_section(field_name, getattr(data, field_name), indent + 1)
    else:
        click.echo(f"{prefix}{title}: {data}")


# ------------------------------------------------------------------
# show-config
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--section",
    default=None,
    type=click.Choice(
        [
            "pinterest",
            "publishing",
            "generator",
            "retry",
            "boards",
            "logging",
            "accounts",
            "niches",
            "db_path",
        ],
        case_sensitive=False,
    ),
    help="Show only this config section.",
)
@click.option(
    "--config",
    "config_path",
    default="config.yaml",
    show_default=True,
    help="Path to YAML config file.",
)
def show_config(section: str | None, config_path: str) -> None:
    """Pretty-print the current (loaded) configuration.

    If --section is provided, only that section is shown.
    """
    try:
        loader = _build_loader(config_path)
        config = loader.load(config_path)
    except FileNotFoundError:
        click.echo(f"Config file not found: {config_path}", err=True)
        sys.exit(1)
    except (ValueError, yaml.YAMLError) as exc:
        click.echo(f"Config load error: {exc}", err=True)
        sys.exit(1)

    if section:
        # Handle special case: db_path is a flat field
        if section == "db_path":
            click.echo(f"db_path: {config.db_path}")
            return

        data = getattr(config, section, None)
        if data is None:
            click.echo(f"Section '{section}' not found in config.")
            sys.exit(1)
        click.echo(f"=== {section} ===")
        _pretty_print_section("", data)
    else:
        # Print full config
        click.echo("=== Full Configuration ===")
        _pretty_print_section("pinterest", config.pinterest)
        click.echo("")
        _pretty_print_section("publishing", config.publishing)
        click.echo("")
        _pretty_print_section("generator", config.generator)
        click.echo("")
        _pretty_print_section("retry", config.retry)
        click.echo("")
        _pretty_print_section("boards", config.boards)
        click.echo("")
        _pretty_print_section("logging", config.logging)
        click.echo("")
        click.echo(f"  db_path: {config.db_path}")
        click.echo("")
        _pretty_print_section("accounts", config.accounts)
        click.echo("")
        _pretty_print_section("niches", config.niches)


# ------------------------------------------------------------------
# validate-config
# ------------------------------------------------------------------


@cli.command()
@click.argument(
    "config_path",
    default="config.yaml",
    required=False,
    type=click.Path(exists=True, dir_okay=False),
)
def validate_config(config_path: str) -> None:
    """Validate a YAML config file and report errors.

    Loads the file, resolves environment variables, and runs Pydantic
    validation. Exits with code 0 on success, 1 on validation errors.
    """
    try:
        loader = _build_loader(config_path)
        config = loader.load(config_path)
        click.echo(f"✓ Configuration valid: {config_path}")
        click.echo(f"  Accounts: {len(config.accounts)}")
        click.echo(f"  Niches: {len(config.niches)}")
        click.echo(f"  DB path: {config.db_path}")
        click.echo(f"  Pins/day: {config.publishing.pins_per_day}")
    except FileNotFoundError:
        click.echo(f"✗ Config file not found: {config_path}", err=True)
        sys.exit(1)
    except ValueError as exc:
        click.echo(f"✗ Configuration validation failed:", err=True)
        click.echo(str(exc), err=True)
        sys.exit(1)
    except yaml.YAMLError as exc:
        click.echo(f"✗ Malformed YAML: {exc}", err=True)
        sys.exit(1)


# ------------------------------------------------------------------
# reload-config
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.yaml",
    show_default=True,
    help="Path to YAML config file.",
)
def reload_config(config_path: str) -> None:
    """Re-read the config file.

    In V1, this validates the config file but does NOT hot-reload running
    components (generators, scheduler, etc.). A restart is required for
    config changes to take full effect.
    """
    try:
        loader = _build_loader(config_path)
        config = loader.load(config_path)
        click.echo(f"✓ Config re-loaded: {config_path}")

        # Log warnings about what requires restart
        changes_detected = False
        click.echo("")
        click.echo("NOTE: Full hot-reload is not supported in V1.")
        click.echo("The following components need a restart for config changes:")
        click.echo("  - Image generators (generator section)")
        click.echo("  - Publishing scheduler (publishing section)")
        click.echo("  - Pinterest API client (pinterest/auth section)")
        click.echo("  - Logging configuration (logging section)")
        click.echo("")
        click.echo("To apply changes, restart the application.")
    except FileNotFoundError:
        click.echo(f"✗ Config file not found: {config_path}", err=True)
        sys.exit(1)
    except (ValueError, yaml.YAMLError) as exc:
        click.echo(f"✗ Config reload failed: {exc}", err=True)
        sys.exit(1)
