"""APScheduler-based daily publishing scheduler.

Responsible ONLY for:
- Deciding WHEN to publish (time windows, rate limits)
- Picking the next unpublished image (oldest-first)
- Calling PinPublisher

Does NOT contain Pinterest logic. Does NOT know about tokens,
boards, or API endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from pinterest_agent.config.loader import PublishingConfig
from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import ImageStatus
from pinterest_agent.publishers.pin_publisher import PinPublisher

logger = logging.getLogger(__name__)


@dataclass
class WindowConfig:
    """Configuration for a single publishing time window."""

    hour: int
    minute: int = 0
    label: str = ""


@dataclass
class SchedulerConfig:
    """Configuration for the scheduler (internal representation)."""

    windows: list[WindowConfig] = field(default_factory=lambda: [
        WindowConfig(hour=9, minute=0, label="morning"),
        WindowConfig(hour=14, minute=0, label="afternoon"),
        WindowConfig(hour=20, minute=0, label="evening"),
    ])
    pins_per_day: int = 10
    min_interval_minutes: int = 30
    max_pins_per_window: int = 4


class SchedulerService:
    """APScheduler-based publishing scheduler.

    Manages daily publishing schedules per Pinterest account. Picks
    the oldest unpublished image from the image store and publishes
    it through the provided PinPublisher.

    A failed publication does NOT stop the scheduler — errors are
    logged and the next scheduled window continues normally.
    """

    def __init__(
        self,
        publisher: PinPublisher,
        image_repo: SqliteImageRepository,
        publication_repo: SqlitePublicationRepository,
        config: Optional[SchedulerConfig] = None,
        publishing_config: Optional[PublishingConfig] = None,
    ) -> None:
        self._publisher = publisher
        self._image_repo = image_repo
        self._publication_repo = publication_repo
        self._paused = False

        # Resolve scheduler config from publishing_config or fallback
        if config is not None:
            self._config = config
        elif publishing_config is not None:
            windows = [
                WindowConfig(hour=w["hour"], minute=w.get("minute", 0), label=w.get("label", ""))
                for w in publishing_config.publish_windows
            ]
            self._config = SchedulerConfig(
                windows=windows,
                pins_per_day=publishing_config.pins_per_day,
                min_interval_minutes=publishing_config.minimum_interval_minutes,
                max_pins_per_window=max(1, publishing_config.pins_per_day // max(len(windows), 1)),
            )
        else:
            self._config = SchedulerConfig()

        self._scheduler = BlockingScheduler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Register all daily jobs and start the scheduler.

        This call blocks until the scheduler is stopped.
        """
        self._register_jobs()
        logger.info(
            "Scheduler started: %d pins/day across %d window(s)",
            self._config.pins_per_day,
            len(self._config.windows),
        )
        try:
            self._scheduler.start()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user.")
            self._scheduler.shutdown(wait=False)

    def run_once(self, dry_run: bool = False) -> int:
        """Run a single publishing cycle immediately.

        Picks the oldest unpublished images and publishes them within
        the configured per-window limit.

        Args:
            dry_run: If True, log what would be published but don't publish.

        Returns:
            Number of images published (or would be published in dry-run).
        """
        published_count = 0

        # Check daily limit
        today_count = self._publication_repo.count_published_today()
        remaining = self._config.pins_per_day - today_count
        if remaining <= 0:
            logger.info("Daily pin limit reached (%d/%d). Skipping.", today_count, self._config.pins_per_day)
            return 0

        # Limit to window max
        window_limit = min(remaining, self._config.max_pins_per_window)

        # Pick oldest unpublished images with status GENERATED
        images = self._image_repo.query(
            status=ImageStatus.GENERATED.value,
            limit=window_limit,
        )

        if not images:
            logger.warning("No unpublished images found. Skipping window.")
            return 0

        logger.info(
            "Publishing cycle: %d image(s) available, limit=%d, remaining_today=%d",
            len(images), window_limit, remaining,
        )

        if dry_run:
            for img in images[:window_limit]:
                logger.info(
                    "[DRY-RUN] Would publish image %d (niche=%s, file=%s)",
                    img.id, img.niche, img.file_path,
                )
            return min(len(images), window_limit)

        results = self._publisher.publish_batch(images[:window_limit])
        for result in results:
            if result.success:
                published_count += 1

        logger.info(
            "Publishing cycle complete: %d/%d published.",
            published_count, len(results),
        )
        return published_count

    def pause(self) -> None:
        """Pause all scheduled publishing. Queued items are preserved."""
        if self._paused:
            return
        if self._scheduler.running:
            self._scheduler.pause()
        self._paused = True
        logger.info("Scheduler paused.")

    def resume(self) -> None:
        """Resume paused publishing."""
        if not self._paused:
            return
        if self._scheduler.running:
            self._scheduler.resume()
        self._paused = False
        logger.info("Scheduler resumed.")

    @property
    def is_paused(self) -> bool:
        """Check if the scheduler is currently paused."""
        return self._paused

    @property
    def is_running(self) -> bool:
        """Check if the underlying APScheduler is running."""
        return self._scheduler.running

    # ------------------------------------------------------------------
    # Internal: job registration
    # ------------------------------------------------------------------

    def _register_jobs(self) -> None:
        """Register cron jobs for each configured time window."""
        pins_per_window = self._distribute_pins()

        for i, window in enumerate(self._config.windows):
            count = pins_per_window[i]
            if count <= 0:
                continue

            # Schedule multiple pins within the window with 30-min spacing
            for offset in range(count):
                minute = window.minute + offset * self._config.min_interval_minutes
                if minute >= 60:
                    logger.warning(
                        "Pin offset %d for window %s exceeds hour boundary. Skipping.",
                        offset, window.label,
                    )
                    continue

                trigger = CronTrigger(
                    hour=window.hour,
                    minute=minute,
                )
                self._scheduler.add_job(
                    self._publish_job,
                    trigger=trigger,
                    id=f"{window.label}_{window.hour:02d}{minute:02d}",
                    replace_existing=True,
                    name=f"Publish at {window.hour:02d}:{minute:02d} ({window.label})",
                )
                logger.debug(
                    "Registered job: %s at %02d:%02d",
                    window.label, window.hour, minute,
                )

    def _distribute_pins(self) -> list[int]:
        """Distribute daily pin limit across configured windows.

        Distributes evenly, with remainders going to earlier windows.
        Example: 10 pins across 3 windows → [4, 3, 3].
        """
        num_windows = len(self._config.windows)
        if num_windows == 0:
            return []

        base = self._config.pins_per_day // num_windows
        remainder = self._config.pins_per_day % num_windows

        distribution = [base] * num_windows
        for i in range(remainder):
            distribution[i] += 1

        return distribution

    def _publish_job(self) -> None:
        """APScheduler job callback — publishes one image.

        This is called by APScheduler for each scheduled slot.
        It picks the oldest unpublished image and publishes it.
        """
        if self._paused:
            logger.debug("Scheduler paused — skipping publish job.")
            return

        logger.debug("Publish job triggered.")
        result = self.run_once(dry_run=False)
        if result > 0:
            logger.info("Publish job completed: %d image(s) published.", result)
