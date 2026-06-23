"""Abstract repository interfaces for Pinterest Aesthetic Automation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from pinterest_agent.domain.models import ImageRecord, Pin, Prompt, PromptStatus, PublicationRecord, PublicationStatus


class PromptRepository(ABC):
    """Repository for prompt queue operations."""

    @abstractmethod
    def enqueue(self, prompt: Prompt) -> int:
        """Insert a new prompt into the queue and return its row ID."""
        ...

    @abstractmethod
    def dequeue(self, limit: int = 10) -> list[Prompt]:
        """Fetch next batch of pending prompts in FIFO order."""
        ...

    @abstractmethod
    def mark_done(self, prompt_id: int) -> None:
        """Mark a prompt as successfully generated."""
        ...

    @abstractmethod
    def mark_failed(self, prompt_id: int, error: str) -> None:
        """Mark a prompt as failed with an error message."""
        ...

    @abstractmethod
    def count_by_status(self, status: PromptStatus) -> int:
        """Return count of prompts with the given status."""
        ...

    @abstractmethod
    def find_by_hash(self, prompt_hash: str) -> Optional[Prompt]:
        """Look up a prompt by its hash for dedup.

        Returns the prompt if found, None otherwise.
        """
        ...

    @abstractmethod
    def find_by_template_and_seed(
        self, template_id: str, variable_seed: int
    ) -> Optional[Prompt]:
        """Look up a prompt by template_id + variable_seed for dedup.

        Returns the prompt if found, None otherwise.
        """
        ...

    @abstractmethod
    def query(
        self,
        status: Optional[PromptStatus] = None,
        niche: Optional[str] = None,
        limit: int = 100,
    ) -> list[Prompt]:
        """Query prompts by optional status and niche filters."""
        ...


class ImageRepository(ABC):
    """Repository for generated image metadata."""

    @abstractmethod
    def save(self, image: ImageRecord) -> int:
        """Store a new image record and return its row ID."""
        ...

    @abstractmethod
    def find_by_prompt_hash(self, prompt_hash: str) -> Optional[ImageRecord]:
        """Look up an image by the source prompt hash."""
        ...

    @abstractmethod
    def find_by_perceptual_hash(self, phash: str) -> Optional[ImageRecord]:
        """Look up an image by its perceptual hash for dedup."""
        ...

    @abstractmethod
    def find_by_prompt_id(self, prompt_id: int) -> Optional[ImageRecord]:
        """Look up an image by its source prompt ID.

        Returns the most recent image for the given prompt, or None.
        """
        ...

    @abstractmethod
    def find_by_sha256(self, sha256: str) -> Optional[ImageRecord]:
        """Look up an image by its SHA256 content hash for exact dedup."""
        ...

    @abstractmethod
    def query(
        self,
        status: Optional[str] = None,
        niche: Optional[str] = None,
        limit: int = 100,
    ) -> list[ImageRecord]:
        """Query images by optional status and niche filters.

        Args:
            status: Filter by status string ('pending', 'generated', 'failed').
            niche: Filter by aesthetic niche.
            limit: Maximum rows to return.

        Returns images ordered by id ASC.
        """
        ...

    @abstractmethod
    def find_unpublished(self, limit: int = 10) -> list[ImageRecord]:
        """Fetch next batch of unpublished images in FIFO order."""
        ...

    @abstractmethod
    def mark_published(self, image_id: int, pin_id: str) -> None:
        """Mark an image as published with its Pinterest pin ID."""
        ...

    @abstractmethod
    def count_by_status(self, status: str) -> int:
        """Return count of images with the given status string."""
        ...


class AnalyticsRepository(ABC):
    """Repository for analytics event tracking."""

    @abstractmethod
    def record_pin_event(self, pin_id: str, event_type: str) -> None:
        """Record an analytics event for a pin (save, click, etc.)."""
        ...

    @abstractmethod
    def get_top_templates(self, limit: int = 10) -> list[dict]:
        """Return top-performing templates by engagement metrics.

        Each dict contains template_id and aggregate metrics.
        """
        ...

    @abstractmethod
    def get_niche_performance(self, niche: str) -> dict:
        """Return performance metrics for a specific niche.

        Returns a dict with keys like total_pins, total_saves, total_clicks.
        """
        ...


class PublicationRepository(ABC):
    """Repository for pin publication records."""

    @abstractmethod
    def save(self, record: PublicationRecord) -> int:
        """Insert a new publication record and return its row ID."""
        ...

    @abstractmethod
    def find_by_image_id(self, image_id: int) -> Optional[PublicationRecord]:
        """Find a publication record by image ID."""
        ...

    @abstractmethod
    def find_by_pinterest_pin_id(self, pin_id: str) -> Optional[PublicationRecord]:
        """Find a publication record by Pinterest pin ID."""
        ...

    @abstractmethod
    def query(
        self,
        status: Optional[PublicationStatus] = None,
        limit: int = 100,
    ) -> list[PublicationRecord]:
        """Query publication records by optional status filter."""
        ...

    @abstractmethod
    def count_by_status(self, status: PublicationStatus) -> int:
        """Return count of records with the given status."""
        ...

    @abstractmethod
    def count_published_today(self) -> int:
        """Return number of successful publications today."""
        ...

    @abstractmethod
    def mark_failed(self, record_id: int, error: str) -> None:
        """Mark a publication record as failed with error message."""
        ...
