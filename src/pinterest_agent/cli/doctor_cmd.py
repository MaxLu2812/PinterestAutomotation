"""CLI command: ``doctor`` — run diagnostics and report issues.

Checks config, database, directories, environment variables, provider
imports, and API connectivity. Supports ``--fix`` to auto-create missing
directories.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import click
import yaml

from pinterest_agent.cli.main import cli

logger = logging.getLogger(__name__)


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.yaml",
    show_default=True,
    help="Path to YAML config file.",
)
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Auto-create missing directories.",
)
def doctor(config_path: str, db: str, fix: bool) -> None:
    """Run system diagnostics and report issues.

    Checks configuration validity, database connectivity, required
    directories, environment variables, provider imports, and API
    availability. Use --fix to auto-create missing directories.

    Exits with code 0 if all checks pass, 1 if warnings exist.
    """
    click.echo("Running diagnostics...\n")

    passed = 0
    warnings = 0

    # --- 1. Config check ---
    try:
        from pinterest_agent.config.loader import ConfigLoader

        loader = ConfigLoader(config_path)
        config = loader.load(config_path)

        # Count top-level config sections
        sections = sum(
            1
            for f in [
                "pinterest",
                "publishing",
                "generator",
                "retry",
                "boards",
                "logging",
                "accounts",
                "niches",
                "db_path",
            ]
            if getattr(config, f, None) is not None
        )
        click.echo(
            f"  ✓ Config:    {config_path} — valid ({sections} sections)"
        )
        passed += 1
    except FileNotFoundError:
        click.echo(f"  ✗ Config:    {config_path} — file not found")
        warnings += 1
    except ValueError as exc:
        click.echo(f"  ✗ Config:    {config_path} — validation error:\n    {exc}")
        warnings += 1
    except yaml.YAMLError as exc:
        click.echo(f"  ✗ Config:    {config_path} — malformed YAML:\n    {exc}")
        warnings += 1
    except Exception as exc:
        click.echo(f"  ✗ Config:    {config_path} — unexpected error: {exc}")
        warnings += 1

    # --- 2. Database check ---
    try:
        from pinterest_agent.db.connection import ConnectionManager

        cm = ConnectionManager(db)
        cm.connect()

        # Count records
        record_count = 0
        for table in ["prompts", "images", "publications"]:
            try:
                row = cm.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                record_count += row[0] if row else 0
            except Exception:
                pass

        # Schema version
        schema_version = cm._get_schema_version()

        db_path_obj = Path(db)
        db_size = db_path_obj.stat().st_size if db_path_obj.exists() else 0

        size_str = f"{db_size / 1024:.1f}KB" if db_size < 1024 * 1024 else f"{db_size / (1024 * 1024):.1f}MB"
        click.echo(
            f"  ✓ Database:  {db} — {size_str}, schema v{schema_version}, "
            f"{record_count} records"
        )
        passed += 1
        cm.close()
    except Exception as exc:
        click.echo(f"  ✗ Database:  {db} — {exc}")
        warnings += 1

    # --- 3. Directories ---
    required_dirs = [
        "storage/images/raw",
        "storage/images/processed",
        "storage/images/failed",
        "storage/logs",
    ]
    click.echo("  Directories:")
    for d in required_dirs:
        d_path = Path(d)
        if d_path.is_dir():
            click.echo(f"    ✓ {d}/")
            passed += 1
        else:
            if fix:
                try:
                    d_path.mkdir(parents=True, exist_ok=True)
                    click.echo(f"    ✓ {d}/ (created)")
                    passed += 1
                except OSError as exc:
                    click.echo(f"    ✗ {d}/ — could not create: {exc}")
                    warnings += 1
            else:
                click.echo(f"    ✗ {d}/ — not found (use --fix to create)")
                warnings += 1

    # --- 4. Environment variables ---
    click.echo("")
    env_checks = {
        "PINTEREST_TOKEN": "Pinterest API",
        "OPENAI_API_KEY": "OpenAI API",
        "HF_TOKEN": "Hugging Face",
    }
    for env_var, label in env_checks.items():
        if os.environ.get(env_var):
            click.echo(f"  ✓ {label:<16} {env_var} set")
            passed += 1
        else:
            click.echo(f"  ✗ {label:<16} {env_var} not set")
            warnings += 1

    # --- 5. Provider imports ---
    click.echo("")
    providers_to_check = [
        ("local_diffusers", "local_diffusers", "torch"),
        ("huggingface", "hf_inference", "huggingface_hub"),
    ]
    for name, module, dep in providers_to_check:
        try:
            import importlib

            importlib.import_module(f"pinterest_agent.generators.{module}")
            # Check if the dependency is importable
            dep_ok = True
            try:
                importlib.import_module(dep)
            except ImportError:
                dep_ok = False

            if dep_ok:
                click.echo(f"  ✓ Provider:  {name:<20} — available")
                passed += 1
            else:
                click.echo(
                    f"  ⚠ Provider:  {name:<20} — module found, but '{dep}' not installed"
                )
                warnings += 1
        except ImportError:
            click.echo(
                f"  ✗ Provider:  {name:<20} — not available (import failed)"
            )
            warnings += 1

    # --- 6. Pinterest API connectivity (optional) ---
    click.echo("")
    pinterest_token = os.environ.get("PINTEREST_TOKEN")
    if pinterest_token:
        try:
            from pinterest_agent.publishers.pinterest_client import PinterestClient

            client = PinterestClient(access_token=pinterest_token)
            boards = client.get_boards()
            click.echo(
                f"  ✓ Pinterest: API reachable ({len(boards)} board(s) found)"
            )
            passed += 1
        except Exception as exc:
            click.echo(f"  ✗ Pinterest: API error — {exc}")
            warnings += 1
    else:
        click.echo("  - Pinterest: skipped (no token set)")

    # --- Summary ---
    click.echo("")
    if warnings == 0:
        click.echo(
            f"Diagnostics complete: {passed} checks passed, all good."
        )
    else:
        click.echo(
            f"Diagnostics complete: {passed} passed, {warnings} warnings"
        )
        raise click.ClickException(
            f"{warnings} issue(s) found. Review the warnings above."
        )
