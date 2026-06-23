"""CLI commands for prompt generation and management.

Commands
--------
generate-prompts    Generate prompt batches from YAML templates.
list-prompts        Query prompts by status and/or niche.
retry-prompts       Reset failed prompts to pending for retry.
generate-images     Generate images from queued prompts.
list-images         Query generated images by status and/or niche.
retry-images        Reset failed images for regeneration.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from pinterest_agent.cli.main import cli
from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.prompt_repo import SqlitePromptRepository
from pinterest_agent.domain.models import ImageStatus, PromptStatus
from pinterest_agent.generators.factory import GeneratorFactory
from pinterest_agent.prompts.engine import PromptEngine

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _build_engine(db_path: str) -> PromptEngine:
    """Build a PromptEngine with a fresh SQLite repository."""
    cm = ConnectionManager(db_path)
    cm.connect()
    repo = SqlitePromptRepository(cm)
    return PromptEngine(repo=repo)


# ------------------------------------------------------------------
# generate-prompts
# ------------------------------------------------------------------

@cli.command()
@click.option(
    "--niche",
    default=None,
    help="Template name (e.g. 'old_money'). If omitted, lists available templates.",
)
@click.option("--count", default=10, type=int, help="Number of prompts to generate.")
@click.option("--seed", default=1, type=int, help="Starting seed for variable selection.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def generate_prompts(niche: str, count: int, seed: int, db: str) -> None:
    """Generate prompts from YAML templates and enqueue them."""
    engine = _build_engine(db)

    if niche is None:
        templates = engine.list_templates()
        if templates:
            click.echo("Available templates:\n")
            for t in templates:
                click.echo(f"  - {t}")
            click.echo(
                "\nUse --niche to generate prompts for a specific template."
            )
        else:
            click.echo("No templates found.")
        return

    click.echo(f"Generating {count} prompt(s) for niche '{niche}' (seed={seed}) ...")
    results = engine.generate_batch(niche, count=count, start_seed=seed)
    click.echo(f"Done. Generated {len(results)} prompt(s).")


# ------------------------------------------------------------------
# list-prompts
# ------------------------------------------------------------------

@cli.command()
@click.option("--niche", default=None, help="Filter by aesthetic/niche.")
@click.option(
    "--status",
    default=None,
    type=click.Choice(["pending", "generated", "failed"], case_sensitive=False),
    help="Filter by status.",
)
@click.option("--limit", default=50, type=int, help="Max rows to return.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def list_prompts(niche: str, status: str, limit: int, db: str) -> None:
    """List prompts filtered by optional status and/or niche."""
    engine = _build_engine(db)
    repo = engine._repo  # type: ignore[attr-defined]

    status_enum = PromptStatus(status) if status else None
    prompts = repo.query(status=status_enum, niche=niche, limit=limit)

    if not prompts:
        click.echo("No prompts found.")
        return

    click.echo(
        f"{'ID':>4}  {'Status':<10}  {'Niche':<20}  {'Template':<20}  {'Seed':>4}  {'Text Preview':<50}"
    )
    click.echo("-" * 120)
    for p in prompts:
        preview = p.text[:47] + "..." if len(p.text) > 50 else p.text
        click.echo(
            f"{p.id:>4}  {p.status.value:<10}  {p.aesthetic:<20}  {p.template_id:<20}  {p.variable_seed:>4}  {preview:<50}"
        )


# ------------------------------------------------------------------
# retry-prompts
# ------------------------------------------------------------------

@cli.command()
@click.option("--niche", default=None, help="Only retry prompts for this niche.")
@click.option("--max-retries", default=3, type=int, help="Not used in V1 — kept for compatibility.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def retry_prompts(niche: str, max_retries: int, db: str) -> None:
    """Reset failed prompts to pending so they can be retried."""
    engine = _build_engine(db)
    repo = engine._repo  # type: ignore[attr-defined]

    failures = repo.query(status=PromptStatus.FAILED, niche=niche, limit=5000)

    if not failures:
        click.echo("No failed prompts to retry.")
        return

    with click.progressbar(failures, label="Resetting prompts") as bar:
        for p in bar:
            repo.mark_done.cache_clear() if hasattr(repo.mark_done, "cache_clear") else None
            # Reset: set status back to pending, clear error
            repo._cm.execute(
                "UPDATE prompts SET status = ?, error = NULL WHERE id = ?",
                (PromptStatus.PENDING.value, p.id),
            )

    click.echo(f"Reset {len(failures)} failed prompt(s) to pending.")


# ------------------------------------------------------------------
# Helpers for image commands
# ------------------------------------------------------------------


def _build_image_pipeline(
    db: str,
    provider: str,
    storage: str,
    generator_config: object = None,
    retry_config: object = None,
):
    """Build an ImagePipeline with the configured providers."""
    cm = ConnectionManager(db)
    cm.connect()
    prompt_repo = SqlitePromptRepository(cm)
    image_repo = SqliteImageRepository(cm)

    factory = GeneratorFactory()

    if provider:
        # Single explicit provider
        try:
            gen = factory.create(provider)
            generators = [gen]
        except KeyError:
            available = factory.list_providers()
            raise click.BadParameter(
                f"Unknown provider '{provider}'. Available: {', '.join(available)}"
            )
    else:
        # Priority chain: local → huggingface
        generators = factory.create_priority_chain(
            ["local_diffusers", "huggingface"]
        )

    from pinterest_agent.config.loader import GeneratorConfig, RetryConfig
    from pinterest_agent.generators.pipeline import ImagePipeline

    kwargs = {
        "prompt_repo": prompt_repo,
        "image_repo": image_repo,
        "generators": generators,
        "storage_root": Path(storage),
    }

    # Pass config objects if provided (they override individual params)
    if generator_config is not None:
        kwargs["generator_config"] = generator_config
    if retry_config is not None:
        kwargs["retry_config"] = retry_config

    return ImagePipeline(**kwargs)


# ------------------------------------------------------------------
# generate-images
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--prompt-ids",
    default=None,
    type=str,
    help="Comma-separated list of prompt IDs to process.",
)
@click.option("--count", default=10, type=int, help="Number of prompts to process.")
@click.option(
    "--provider",
    default=None,
    type=str,
    help="Provider name (e.g. 'local_diffusers', 'huggingface'). Auto-priority if omitted.",
)
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
@click.option(
    "--storage",
    default="storage",
    show_default=True,
    help="Root directory for image storage.",
)
def generate_images(
    prompt_ids: str,
    count: int,
    provider: str,
    db: str,
    storage: str,
) -> None:
    """Generate images from queued prompts.

    Processes pending prompts through the configured provider chain.
    Use --prompt-ids to process specific prompts, or omit to dequeue.
    """
    pipeline = _build_image_pipeline(db, provider, storage)

    ids: list[int] | None = None
    if prompt_ids:
        try:
            ids = [int(x.strip()) for x in prompt_ids.split(",")]
        except ValueError:
            raise click.BadParameter(
                "prompt-ids must be a comma-separated list of integers"
            )

    click.echo(
        f"Generating images for {'prompt(s) ' + str(ids) if ids else f'{count} pending prompt(s)'} ..."
    )
    stats = pipeline.run(prompt_ids=ids, max_count=count)

    click.echo(
        f"Done. {stats.succeeded} generated, "
        f"{stats.skipped_already_generated + stats.skipped_duplicate} skipped, "
        f"{stats.failed} failed."
    )


# ------------------------------------------------------------------
# list-images
# ------------------------------------------------------------------


@cli.command()
@click.option("--niche", default=None, help="Filter by aesthetic niche.")
@click.option(
    "--status",
    default=None,
    type=click.Choice(["pending", "generated", "failed"], case_sensitive=False),
    help="Filter by status.",
)
@click.option("--limit", default=50, type=int, help="Max rows to return.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def list_images(niche: str, status: str, limit: int, db: str) -> None:
    """List generated images filtered by optional status and/or niche."""
    cm = ConnectionManager(db)
    cm.connect()
    repo = SqliteImageRepository(cm)

    images = repo.query(status=status, niche=niche, limit=limit)

    if not images:
        click.echo("No images found.")
        return

    click.echo(
        f"{'ID':>4}  {'Prompt':>7}  {'Status':<10}  {'Niche':<20}  "
        f"{'Provider':<16}  {'Seed':>4}  {'Size':>8}  {'File':<40}"
    )
    click.echo("-" * 130)
    for img in images:
        fname = Path(img.file_path).name if img.file_path else "-"
        size_str = f"{img.width}×{img.height}" if img.width else "-"
        click.echo(
            f"{img.id:>4}  {img.prompt_id:>7}  {img.status.value:<10}  "
            f"{img.niche:<20}  {img.backend:<16}  {img.seed:>4}  "
            f"{size_str:>8}  {fname:<40}"
        )


# ------------------------------------------------------------------
# retry-images
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--prompt-ids",
    default=None,
    type=str,
    help="Comma-separated list of prompt IDs to retry.",
)
@click.option("--max-retries", default=3, type=int, help="Not used in V1 — kept for compatibility.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def retry_images(prompt_ids: str, max_retries: int, db: str) -> None:
    """Reset failed image records so they can be regenerated.

    Also resets the associated prompt status back to 'pending'.
    """
    cm = ConnectionManager(db)
    cm.connect()
    image_repo = SqliteImageRepository(cm)
    prompt_repo = SqlitePromptRepository(cm)

    if prompt_ids:
        ids = [int(x.strip()) for x in prompt_ids.split(",")]
        click.echo(f"Resetting {len(ids)} failed image(s) for retry ...")
        for pid in ids:
            image_repo._cm.execute(
                "UPDATE images SET status = ? WHERE prompt_id = ? AND status = ?",
                (ImageStatus.PENDING.value, pid, ImageStatus.FAILED.value),
            )
            prompt_repo._cm.execute(
                "UPDATE prompts SET status = ?, error = NULL WHERE id = ?",
                (PromptStatus.PENDING.value, pid),
            )
        click.echo(f"Reset {len(ids)} prompt(s) for retry.")
    else:
        # Reset all failed images
        image_repo._cm.execute(
            "UPDATE images SET status = ? WHERE status = ?",
            (ImageStatus.PENDING.value, ImageStatus.FAILED.value),
        )
        prompt_repo._cm.execute(
            "UPDATE prompts SET status = ?, error = NULL WHERE status = ?",
            (PromptStatus.PENDING.value, PromptStatus.FAILED.value),
        )
        click.echo("Reset all failed images for retry.")
