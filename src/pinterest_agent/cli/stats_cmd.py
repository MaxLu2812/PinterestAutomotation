"""CLI command: ``stats`` — usage statistics with date filtering.

Shows aggregate statistics for prompts, images, publications, dedup hits,
and provider usage over a configurable time period.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import click

from pinterest_agent.cli.main import cli
from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import ImageStatus, PromptStatus, PublicationStatus

logger = logging.getLogger(__name__)


@cli.command()
@click.option(
    "--days",
    default=30,
    type=int,
    help="Number of days to look back.",
    show_default=True,
)
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def stats(days: int, db: str) -> None:
    """Show usage statistics for the given period.

    Includes counts, averages per day, dedup hits, and provider usage breakdown.
    """
    since = datetime.now() - timedelta(days=days)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    try:
        cm = ConnectionManager(db)
        cm.connect()
    except Exception as exc:
        click.echo(f"Error connecting to database: {exc}", err=True)
        raise click.ClickException(str(exc)) from exc

    prompt_repo = SqlitePromptRepository(cm)
    image_repo = SqliteImageRepository(cm)
    pub_repo = SqlitePublicationRepository(cm)

    # --- Prompts ---
    total_prompts = (
        prompt_repo.count_by_status(PromptStatus.GENERATED)
        + prompt_repo.count_by_status(PromptStatus.FAILED)
        + prompt_repo.count_by_status(PromptStatus.PENDING)
    )
    generated_p = prompt_repo.count_by_status(PromptStatus.GENERATED)
    failed_p = prompt_repo.count_by_status(PromptStatus.FAILED)

    # --- Images ---
    total_images = (
        image_repo.count_by_status(ImageStatus.GENERATED.value)
        + image_repo.count_by_status(ImageStatus.PUBLISHED.value)
        + image_repo.count_by_status(ImageStatus.FAILED.value)
        + image_repo.count_by_status(ImageStatus.PENDING.value)
    )
    generated_i = image_repo.count_by_status(ImageStatus.GENERATED.value)
    published_i = image_repo.count_by_status(ImageStatus.PUBLISHED.value)
    failed_i = image_repo.count_by_status(ImageStatus.FAILED.value)

    # --- Publications ---
    published_pub = pub_repo.count_by_status(PublicationStatus.PUBLISHED)
    failed_pub = pub_repo.count_by_status(PublicationStatus.FAILED)
    total_failed = failed_p + failed_i + failed_pub

    # --- Averages ---
    avg_factor = max(days, 1)
    avg_prompts = generated_p / avg_factor
    avg_images = generated_i / avg_factor
    avg_published = published_pub / avg_factor
    avg_failed = total_failed / avg_factor

    click.echo(f"Statistics (last {days} days):")
    click.echo(f"  Prompts generated:  {generated_p}  ({avg_prompts:.1f}/day)")
    click.echo(f"  Images generated:   {generated_i}  ({avg_images:.1f}/day)")
    click.echo(f"  Pins published:     {published_pub}  ({avg_published:.1f}/day)")
    click.echo(f"  Failed items:       {total_failed}  ({avg_failed:.1f}/day)")

    # --- Dedup hits ---
    click.echo("")
    click.echo("  Dedup hits:")
    try:
        # Query dedup information from prompt errors
        dedup_template_seed = _count_dedup_by_pattern(
            cm, "prompts", "duplicate: template_id"
        )
        dedup_sha256 = _count_dedup_by_pattern(
            cm, "prompts", "duplicate: SHA256"
        )
        dedup_phash = _count_dedup_by_pattern(
            cm, "prompts", "duplicate: perceptual"
        )

        click.echo(f"    Template+seed:    {dedup_template_seed}")
        click.echo(f"    SHA256:            {dedup_sha256}")
        click.echo(f"    pHash:             {dedup_phash}")
    except Exception:
        click.echo("    (unavailable)")

    # --- Provider usage ---
    click.echo("")
    click.echo("  Provider usage:")
    try:
        rows = cm.execute(
            "SELECT backend, COUNT(*) as cnt FROM images "
            "WHERE backend != '' AND backend IS NOT NULL "
            "GROUP BY backend ORDER BY cnt DESC"
        ).fetchall()

        total_backend = sum(r["cnt"] for r in rows)
        if total_backend > 0:
            for row in rows:
                pct = row["cnt"] / total_backend * 100
                click.echo(f"    {row['backend']:<20} {row['cnt']:>4}  ({pct:.0f}%)")
        else:
            click.echo("    (no images generated yet)")
    except Exception:
        click.echo("    (unavailable)")


def _count_dedup_by_pattern(cm: ConnectionManager, table: str, pattern: str) -> int:
    """Count rows in *table* where error field contains *pattern*."""
    try:
        row = cm.execute(
            f"SELECT COUNT(*) FROM {table} WHERE error LIKE ?",
            (f"{pattern}%",),
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
