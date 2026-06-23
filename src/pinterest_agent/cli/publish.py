"""CLI commands for publishing pins and managing the scheduler.

Commands
--------
publish-pins          Publish images to Pinterest immediately.
list-publications     Query publication records by status.
retry-publications    Reset failed publications for retry.
scheduler-run         Start the APScheduler daemon or run a dry cycle.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

from pinterest_agent.cli.main import cli
from pinterest_agent.config.loader import ConfigLoader
from pinterest_agent.db.connection import ConnectionManager
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import (
    ImageStatus,
    PublicationStatus,
)
from pinterest_agent.publishers.pin_publisher import PinPublisher
from pinterest_agent.publishers.pinterest_client import PinterestClient
from pinterest_agent.scheduler.scheduler import SchedulerService

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_publisher(
    db: str,
    config_path: str,
    account_name: str = "main",
) -> tuple[PinPublisher, SqliteImageRepository, SqlitePublicationRepository]:
    """Build a fully-wired PinPublisher from config and database.

    Returns the (publisher, image_repo, publication_repo) tuple so
    callers can also access repos directly.
    """
    loader = ConfigLoader()
    config = loader.load(config_path)

    # Find the matching account
    account = None
    for acct in config.accounts:
        if acct.name == account_name:
            account = acct
            break
    if account is None:
        raise click.BadParameter(
            f"Account '{account_name}' not found in config. "
            f"Available: {[a.name for a in config.accounts]}"
        )

    cm = ConnectionManager(db)
    cm.connect()
    image_repo = SqliteImageRepository(cm)
    publication_repo = SqlitePublicationRepository(cm)

    # Build PinterestClient
    access_token = account.tokens.get("access_token", "")
    refresh_token = account.tokens.get("refresh_token")
    pinterest_client = PinterestClient(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    publisher = PinPublisher(
        pinterest_client=pinterest_client,
        image_repo=image_repo,
        publication_repo=publication_repo,
        board_mapping=account.board_mapping,
    )
    return publisher, image_repo, publication_repo


def _build_scheduler(
    db: str,
    config_path: str,
    account_name: str = "main",
) -> SchedulerService:
    """Build a fully-wired SchedulerService from config and database."""
    loader = ConfigLoader()
    config = loader.load(config_path)

    account = None
    for acct in config.accounts:
        if acct.name == account_name:
            account = acct
            break
    if account is None:
        raise click.BadParameter(
            f"Account '{account_name}' not found in config."
        )

    cm = ConnectionManager(db)
    cm.connect()
    image_repo = SqliteImageRepository(cm)
    publication_repo = SqlitePublicationRepository(cm)

    access_token = account.tokens.get("access_token", "")
    refresh_token = account.tokens.get("refresh_token")
    pinterest_client = PinterestClient(
        access_token=access_token,
        refresh_token=refresh_token,
    )

    publisher = PinPublisher(
        pinterest_client=pinterest_client,
        image_repo=image_repo,
        publication_repo=publication_repo,
        board_mapping=account.board_mapping,
    )

    # Use publishing config from global config, with account-level override
    publishing_config = config.publishing
    if account.pins_per_day is not None:
        publishing_config = publishing_config.model_copy(
            update={"pins_per_day": account.pins_per_day}
        )

    return SchedulerService(
        publisher=publisher,
        image_repo=image_repo,
        publication_repo=publication_repo,
        publishing_config=publishing_config,
    )


# ------------------------------------------------------------------
# publish-pins
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--image-ids",
    default=None,
    type=str,
    help="Comma-separated list of image IDs to publish.",
)
@click.option("--count", default=5, type=int, help="Number of images to publish.")
@click.option(
    "--account",
    default="main",
    show_default=True,
    help="Account name from config.",
)
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
def publish_pins(
    image_ids: str | None,
    count: int,
    account: str,
    db: str,
    config_path: str,
) -> None:
    """Publish images to Pinterest immediately."""
    publisher, image_repo, _ = _build_publisher(db, config_path, account)

    if image_ids:
        ids = [int(x.strip()) for x in image_ids.split(",")]
        click.echo(f"Publishing {len(ids)} specific image(s) ...")
        images = []
        for img_id in ids:
            results = image_repo.query(status=ImageStatus.GENERATED.value, limit=5000)
            match = [img for img in results if img.id == img_id]
            if match:
                images.append(match[0])
            else:
                click.echo(f"Warning: image {img_id} not found or not in GENERATED status.")
    else:
        click.echo(f"Fetching up to {count} unpublished image(s) ...")
        images = image_repo.query(status=ImageStatus.GENERATED.value, limit=count)

    if not images:
        click.echo("No images available to publish.")
        return

    results = publisher.publish_batch(images)
    success_count = sum(1 for r in results if r.success)
    fail_count = sum(1 for r in results if not r.success)

    click.echo(f"Published {success_count}/{len(results)} image(s).")
    for r in results:
        if r.success:
            click.echo(f"  ✓ Image {r.image_id} → pin_id={r.pinterest_pin_id}")
        else:
            click.echo(f"  ✗ Image {r.image_id} failed: {r.error}")

    if fail_count:
        raise click.ClickException(f"{fail_count} publication(s) failed.")


# ------------------------------------------------------------------
# list-publications
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--status",
    default=None,
    type=click.Choice(["pending", "published", "failed"], case_sensitive=False),
    help="Filter by publication status.",
)
@click.option("--limit", default=50, type=int, help="Max rows to return.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def list_publications(status: str | None, limit: int, db: str) -> None:
    """List publication records filtered by optional status."""
    cm = ConnectionManager(db)
    cm.connect()
    pub_repo = SqlitePublicationRepository(cm)

    status_enum = PublicationStatus(status) if status else None
    records = pub_repo.query(status=status_enum, limit=limit)

    if not records:
        click.echo("No publication records found.")
        return

    click.echo(
        f"{'ID':>4}  {'Image':>6}  {'Status':<10}  {'Board':<20}  "
        f"{'Pin ID':<20}  {'Published At':<22}"
    )
    click.echo("-" * 100)
    for r in records:
        pub_at = r.published_at.isoformat() if r.published_at else "-"
        pin_id = r.pinterest_pin_id or "-"
        click.echo(
            f"{r.id:>4}  {r.image_id:>6}  {r.status.value:<10}  "
            f"{r.board_id:<20}  {pin_id:<20}  {pub_at:<22}"
        )


# ------------------------------------------------------------------
# retry-publications
# ------------------------------------------------------------------


@cli.command()
@click.option(
    "--publication-ids",
    default=None,
    type=str,
    help="Comma-separated list of publication IDs to retry.",
)
@click.option("--max-retries", default=3, type=int, help="Not used in V1.")
@click.option(
    "--db",
    default="data/pinterest_agent.db",
    show_default=True,
    help="Path to SQLite database.",
)
def retry_publications(publication_ids: str | None, max_retries: int, db: str) -> None:
    """Reset failed publication records to pending for retry.

    Also resets the associated image status back to 'generated'.
    """
    cm = ConnectionManager(db)
    cm.connect()
    pub_repo = SqlitePublicationRepository(cm)
    image_repo = SqliteImageRepository(cm)

    if publication_ids:
        ids = [int(x.strip()) for x in publication_ids.split(",")]
        click.echo(f"Resetting {len(ids)} failed publication(s) for retry ...")
        for pid in ids:
            pub_repo._cm.execute(
                "UPDATE publications SET status = ?, error = NULL WHERE id = ?",
                (PublicationStatus.PENDING.value, pid),
            )
        click.echo(f"Reset {len(ids)} publication(s).")
    else:
        pub_repo._cm.execute(
            "UPDATE publications SET status = ?, error = NULL WHERE status = ?",
            (PublicationStatus.PENDING.value, PublicationStatus.FAILED.value),
        )
        click.echo("Reset all failed publications to pending.")

    # Also reset images linked to those publications
    image_repo._cm.execute(
        "UPDATE images SET status = ?, error = NULL WHERE status = ?",
        (ImageStatus.GENERATED.value, ImageStatus.PUBLISHED.value),
    )


# ------------------------------------------------------------------
# scheduler-run
# ------------------------------------------------------------------


@cli.command()
@click.option("--daemon", is_flag=True, help="Run the scheduler as a daemon.")
@click.option("--dry-run", "dry_run", is_flag=True, help="Log what would be published without publishing.")
@click.option(
    "--account",
    default="main",
    show_default=True,
    help="Account name from config.",
)
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
def scheduler_run(
    daemon: bool,
    dry_run: bool,
    account: str,
    db: str,
    config_path: str,
) -> None:
    """Run the publishing scheduler.

    Without --daemon, runs a single publishing cycle and exits.
    With --daemon, starts the APScheduler daemon (blocks forever).

    Use --dry-run to preview what would be published.
    """
    scheduler = _build_scheduler(db, config_path, account)

    if daemon:
        click.echo("Starting scheduler daemon (Ctrl+C to stop) ...")
        scheduler.start()
    else:
        click.echo(
            f"Running single publishing cycle "
            f"{'(dry-run)' if dry_run else ''} ..."
        )
        count = scheduler.run_once(dry_run=dry_run)
        if dry_run:
            click.echo(f"Dry-run complete. Would publish {count} image(s).")
        else:
            click.echo(f"Published {count} image(s).")
