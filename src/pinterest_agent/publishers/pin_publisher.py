"""High-level pin publishing orchestrator.

Takes an ImageRecord, resolves the board from niche config,
generates metadata, publishes via PinterestClient, and stores
a PublicationRecord in the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from pinterest_agent.db.repositories.image_repo import SqliteImageRepository
from pinterest_agent.db.repositories.publication_repo import (
    SqlitePublicationRepository,
)
from pinterest_agent.domain.models import ImageRecord, ImageStatus, PublicationStatus
from pinterest_agent.publishers.pinterest_client import PinterestClient

logger = logging.getLogger(__name__)


@dataclass
class PublicationResult:
    """Result of a single pin publication attempt."""

    success: bool
    image_id: int
    pinterest_pin_id: Optional[str] = None
    pin_url: Optional[str] = None
    error: Optional[str] = None
    published_at: Optional[datetime] = None


class PinPublisher:
    """Orchestrates pin publication for a single account.

    Flow:
        1. Validate image is in GENERATED status.
        2. Resolve board_id from niche mapping.
        3. Generate title and description from prompt metadata.
        4. Call PinterestClient.create_pin().
        5. Store publication record in SQLite.
        6. Update image status to published/failed.

    All errors are caught and returned as structured ``PublicationResult``
    — never throws.
    """

    def __init__(
        self,
        pinterest_client: PinterestClient,
        image_repo: SqliteImageRepository,
        publication_repo: SqlitePublicationRepository,
        board_mapping: dict[str, str] | None = None,
        niche_settings: dict[str, dict] | None = None,
    ) -> None:
        self._client = pinterest_client
        self._image_repo = image_repo
        self._publication_repo = publication_repo
        self._board_mapping = board_mapping or {}
        self._niche_settings = niche_settings or {}

    def publish(self, image: ImageRecord) -> PublicationResult:
        """Publish a single image to Pinterest.

        Args:
            image: An ImageRecord with status GENERATED.

        Returns:
            A PublicationResult indicating success or failure.
        """
        try:
            return self._do_publish(image)
        except Exception as exc:
            logger.exception("Unexpected error publishing image %d", image.id)
            return PublicationResult(
                success=False,
                image_id=image.id,
                error=f"Unexpected error: {exc}",
            )

    def publish_batch(self, images: list[ImageRecord]) -> list[PublicationResult]:
        """Publish multiple images sequentially.

        A failure for one image does NOT stop subsequent publications.

        Args:
            images: List of ImageRecord instances to publish.

        Returns:
            List of PublicationResult instances, one per image.
        """
        results: list[PublicationResult] = []
        for img in images:
            result = self.publish(img)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _do_publish(self, image: ImageRecord) -> PublicationResult:
        """Internal publish logic with all steps."""
        # Step 1: Validate image status
        if image.status != ImageStatus.GENERATED:
            return PublicationResult(
                success=False,
                image_id=image.id,
                error=(
                    f"Cannot publish image {image.id}: "
                    f"status is '{image.status.value}', expected 'generated'"
                ),
            )

        # Step 2: Resolve board
        board_id = self._resolve_board_id(image)
        if board_id is None:
            return PublicationResult(
                success=False,
                image_id=image.id,
                error=f"No board mapping found for niche '{image.niche}'",
            )

        # Step 3: Generate title and description
        title = self._generate_title(image)
        description = self._generate_description(image)
        tags = self._generate_tags(image)

        # Step 4: Create a pending publication record
        record_id = self._publication_repo.save(
            self._make_record(image, board_id, title, description, tags)
        )

        # Step 5: Publish via Pinterest API
        result = self._client.create_pin(
            board_id=board_id,
            image_path=image.file_path,
            title=title,
            description=description,
            alt_text=description[:500],
        )

        if "error" in result:
            # Mark publication as failed
            error_msg = result["error"]
            self._publication_repo.mark_failed(record_id, error_msg)
            self._image_repo._cm.execute(
                "UPDATE images SET error = ? WHERE id = ?",
                (error_msg, image.id),
            )
            logger.error("Publication failed for image %d: %s", image.id, error_msg)
            return PublicationResult(
                success=False,
                image_id=image.id,
                error=error_msg,
            )

        # Step 6: Success — update records
        pin_id = result.get("id", "")
        pin_url = result.get("link", "")
        now = datetime.now()

        # Update publication record
        self._publication_repo._cm.execute(
            """UPDATE publications
               SET status = ?, pinterest_pin_id = ?, published_at = ?
               WHERE id = ?""",
            (PublicationStatus.PUBLISHED.value, pin_id, now.isoformat(), record_id),
        )

        # Update image record
        self._image_repo.mark_published(image.id, pin_id)

        logger.info(
            "[PUBLISHED] image_id=%d pin_id=%s url=%s board=%s",
            image.id, pin_id, pin_url, board_id,
        )

        return PublicationResult(
            success=True,
            image_id=image.id,
            pinterest_pin_id=pin_id,
            pin_url=pin_url,
            published_at=now,
        )

    def _resolve_board_id(self, image: ImageRecord) -> Optional[str]:
        """Resolve a Pinterest board ID from the image's niche.

        First checks the configured board_mapping, then falls back
        to resolving the board name via PinterestClient.
        """
        board_name_or_id = self._board_mapping.get(image.niche)
        if board_name_or_id is None:
            return None

        # Try to use as-is (may already be a board ID or a name)
        board_id = self._client.resolve_board_id(board_name_or_id)
        if board_id:
            return board_id

        # If resolve_board_id fails, assume the value IS the board ID
        # (for users who configure IDs directly)
        return board_name_or_id

    @staticmethod
    def _generate_title(image: ImageRecord) -> str:
        """Generate a pin title from image metadata."""
        if image.niche:
            niche_title = image.niche.replace("_", " ").title()
            return f"{niche_title} Aesthetic — Pin #{image.id}"
        return f"Aesthetic Pin #{image.id}"

    @staticmethod
    def _generate_description(image: ImageRecord) -> str:
        """Generate a pin description from image metadata."""
        parts = [f"Aesthetic inspiration — {image.niche.replace('_', ' ').title()}"]
        if image.seed:
            parts.append(f"Style seed: {image.seed}")
        return ". ".join(parts)

    @staticmethod
    def _generate_tags(image: ImageRecord) -> str:
        """Generate comma-separated tags from niche metadata."""
        base_tags = image.niche.replace("_", " ")
        return f"{base_tags}, aesthetic, pinterest, interior design"

    @staticmethod
    def _make_record(
        image: ImageRecord,
        board_id: str,
        title: str,
        description: str,
        tags: str,
    ) -> "PublicationRecord":
        """Create a pending PublicationRecord."""
        from pinterest_agent.domain.models import PublicationRecord

        return PublicationRecord(
            image_id=image.id,
            board_id=board_id,
            title=title,
            description=description,
            tags=tags,
            status=PublicationStatus.PENDING,
        )
