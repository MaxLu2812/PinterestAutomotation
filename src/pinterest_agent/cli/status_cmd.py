"""CLI command: ``status`` — comprehensive system overview.

Shows counts from all repositories, scheduler state, provider availability,
database and file system stats.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import click

from pinterest_agent.cli.main import cli
from pinterest_agent.config.loader import ConfigLoader
from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import ImageStatus, PromptStatus, PublicationStatus
from pinterest_agent.generators.factory import GeneratorFactory

logger = logging.getLogger(__name__)


def _format_bytes(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"


def _build_box_line(text: str, width: int = 52) -> str:
    """Build a box-drawing line with text, padded to width."""
    # Account for the "║  " prefix (3 chars) and " ║" suffix (2 chars)
    inner = width - 5
    if len(text) > inner:
        text = text[: inner - 3] + "..."
    return f"║  {text:<{inner}} ║"


def _build_box_separator(width: int = 52) -> str:
    """Build a horizontal separator for the box."""
    return f"╠{'═' * (width - 2)}╣"


@cli.command()
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
@click.option(
    "--config",
    "config_path",
    default="config.yaml",
    show_default=True,
    help="Path to YAML config file.",
)
def status(db: str, config_path: str) -> None:
    """Display comprehensive system overview.

    Shows counts for prompts, images, publications, scheduler windows,
    provider availability, and file system stats.
    """
    box_w = 52

    click.echo(f"╔{'═' * (box_w - 2)}╗")
    click.echo(_build_box_line("Pinterest Agent — Status", box_w))
    click.echo(f"╠{'═' * (box_w - 2)}╣")

    # --- Prompts ---
    try:
        cm = ConnectionManager(db)
        cm.connect()
        prompt_repo = SqlitePromptRepository(cm)

        total_prompts = (
            prompt_repo.count_by_status(PromptStatus.PENDING)
            + prompt_repo.count_by_status(PromptStatus.GENERATED)
            + prompt_repo.count_by_status(PromptStatus.FAILED)
        )
        generated_p = prompt_repo.count_by_status(PromptStatus.GENERATED)
        failed_p = prompt_repo.count_by_status(PromptStatus.FAILED)

        click.echo(_build_box_line(f"Prompts:    {total_prompts} total", box_w))
        click.echo(_build_box_line(f"  Generated: {generated_p}", box_w))
        click.echo(_build_box_line(f"  Failed:    {failed_p}", box_w))
    except Exception as exc:
        click.echo(_build_box_line(f"Prompts:    Error — {exc}", box_w))
        cm = None  # type: ignore[assignment]

    click.echo(_build_box_line("", box_w))

    # --- Images ---
    try:
        if cm is not None:
            image_repo = SqliteImageRepository(cm)

            pending_i = image_repo.count_by_status(ImageStatus.PENDING.value)
            generated_i = image_repo.count_by_status(ImageStatus.GENERATED.value)
            published_i = image_repo.count_by_status(ImageStatus.PUBLISHED.value)
            failed_i = image_repo.count_by_status(ImageStatus.FAILED.value)

            total_images = pending_i + generated_i + published_i + failed_i

            click.echo(_build_box_line(f"Images:     {total_images} total", box_w))
            click.echo(_build_box_line(f"  Generated: {generated_i}", box_w))
            click.echo(_build_box_line(f"  Published: {published_i}", box_w))
            click.echo(_build_box_line(f"  Failed:    {failed_i}", box_w))
        else:
            click.echo(_build_box_line("Images:     DB unavailable", box_w))
    except Exception as exc:
        click.echo(_build_box_line(f"Images:     Error — {exc}", box_w))

    click.echo(_build_box_line("", box_w))

    # --- Publications ---
    try:
        if cm is not None:
            pub_repo = SqlitePublicationRepository(cm)

            published_pub = pub_repo.count_by_status(PublicationStatus.PUBLISHED)
            failed_pub = pub_repo.count_by_status(PublicationStatus.FAILED)
            today_pub = pub_repo.count_published_today()

            total_pub = published_pub + failed_pub

            click.echo(_build_box_line(f"Publications: {total_pub} total", box_w))
            click.echo(_build_box_line(f"  Published:  {published_pub}", box_w))
            click.echo(_build_box_line(f"  Failed:     {failed_pub}", box_w))
            click.echo(_build_box_line(f"  Today:      {today_pub}", box_w))
        else:
            click.echo(_build_box_line("Publications: DB unavailable", box_w))
    except Exception as exc:
        click.echo(_build_box_line(f"Publications: Error — {exc}", box_w))

    click.echo(_build_box_line("", box_w))

    # --- Scheduler Info ---
    try:
        if cm is not None:
            loader = ConfigLoader()
            config = loader.load(config_path)
            publishing = config.publishing
            windows = publishing.publish_windows
            pins_per_day = publishing.pins_per_day

            click.echo(
                _build_box_line(
                    f"Scheduler:   {len(windows)} window(s), {pins_per_day} pins/day",
                    box_w,
                )
            )
            for w in windows:
                label = w.get("label", f"{w['hour']:02d}:{w.get('minute', 0):02d}")
                # Estimate pins per window
                per_win = max(1, pins_per_day // max(len(windows), 1))
                click.echo(
                    _build_box_line(
                        f"  {label.capitalize():<12} {w['hour']:02d}:{w.get('minute', 0):02d} ({per_win} pins)",
                        box_w,
                    )
                )
        else:
            click.echo(_build_box_line("Scheduler:   Config unavailable", box_w))
    except Exception as exc:
        click.echo(_build_box_line(f"Scheduler:   Error — {exc}", box_w))

    click.echo(_build_box_line("", box_w))

    # --- Providers ---
    try:
        factory = GeneratorFactory()
        providers = factory.list_providers()
        click.echo(_build_box_line("Providers:", box_w))
        for pname in providers:
            try:
                gen = factory.create(pname)
                available = gen.is_available()
                status_icon = "✓" if available else "✗"
                status_text = "Available" if available else "Not available"
                click.echo(
                    _build_box_line(f"  {pname:<20} {status_icon} {status_text}", box_w)
                )
            except Exception as gen_exc:
                click.echo(
                    _build_box_line(f"  {pname:<20} ✗ {gen_exc}", box_w)
                )
    except Exception as exc:
        click.echo(_build_box_line(f"Providers:   Error — {exc}", box_w))

    click.echo(_build_box_line("", box_w))

    # --- File system ---
    try:
        # DB size
        db_path_obj = Path(db)
        db_size = db_path_obj.stat().st_size if db_path_obj.exists() else 0
        click.echo(_build_box_line(f"Database: {db} ({_format_bytes(db_size)})", box_w))

        # Config
        config_path_obj = Path(config_path)
        config_status = (
            f"{config_path} ({_format_bytes(config_path_obj.stat().st_size)})"
            if config_path_obj.exists()
            else f"{config_path} (not found)"
        )
        click.echo(_build_box_line(f"Config:  {config_status}", box_w))

        # Storage
        storage_root = Path("storage")
        if storage_root.is_dir():
            file_count = sum(1 for _ in storage_root.rglob("*") if _.is_file())
            total_size = sum(
                _.stat().st_size for _ in storage_root.rglob("*") if _.is_file()
            )
            click.echo(
                _build_box_line(
                    f"Storage: storage/ ({file_count} files, {_format_bytes(total_size)})",
                    box_w,
                )
            )
        else:
            click.echo(_build_box_line("Storage: storage/ (not found)", box_w))

        # Log level
        click.echo(
            _build_box_line(
                f"Log level: {logging.getLevelName(logging.getLogger().getEffectiveLevel())}",
                box_w,
            )
        )
    except Exception as exc:
        click.echo(_build_box_line(f"File system: Error — {exc}", box_w))

    click.echo(f"╚{'═' * (box_w - 2)}╝")
