"""Domain dataclasses for Pinterest Aesthetic Automation."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class PromptStatus(enum.Enum):
    """Status lifecycle for a prompt in the generation queue."""

    PENDING = "pending"
    GENERATED = "generated"
    FAILED = "failed"


class ImageStatus(enum.Enum):
    """Status lifecycle for a generated image."""

    PENDING = "pending"
    GENERATED = "generated"
    PUBLISHED = "published"
    FAILED = "failed"


class PublicationStatus(enum.Enum):
    """Status lifecycle for a pin publication attempt."""

    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class Prompt:
    """A prompt queued for image generation.

    Attributes:
        id: Database row ID (assigned on insert).
        aesthetic: The aesthetic/niche this prompt belongs to.
        template_id: Identifier of the YAML template used.
        variables: Variable substitutions applied to the template.
        variable_seed: Seed integer used for deterministic variable selection.
        text: The rendered prompt text (output of GPT-4o-mini).
        status: Current status in the pipeline.
        created_at: Timestamp when the prompt was created.
        error: Error message if status is FAILED.
    """

    id: int = 0
    aesthetic: str = ""
    template_id: str = ""
    variables: dict = field(default_factory=dict)
    variable_seed: int = 0
    text: str = ""
    status: PromptStatus = PromptStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


@dataclass
class ImageRecord:
    """A generated image stored on disk with metadata.

    Attributes:
        id: Database row ID (assigned on insert).
        prompt_id: Foreign key to the source prompt.
        prompt_hash: Hash of the prompt text for dedup.
        phash: Perceptual hash of the image for dedup.
        sha256: SHA256 hash of the image bytes for exact dedup.
        file_path: Path to the image file on local filesystem.
        status: Current status in the pipeline.
        pin_id: Pinterest pin ID once published.
        niche: The aesthetic niche this image belongs to.
        backend: Which generation backend produced this image.
        seed: Seed used for deterministic generation.
        width: Image width in pixels.
        height: Image height in pixels.
        file_size: Size of the image file in bytes.
        generation_time: Time taken to generate the image in seconds.
        negative_prompt: Optional negative prompt used during generation.
        error: Error message if status is FAILED.
        created_at: Timestamp when the image was stored.
        published_at: Timestamp when the image was published (if applicable).
    """

    id: int = 0
    prompt_id: int = 0
    prompt_hash: str = ""
    phash: str = ""
    sha256: str = ""
    file_path: str = ""
    status: ImageStatus = ImageStatus.PENDING
    pin_id: Optional[str] = None
    niche: str = ""
    backend: str = ""
    seed: int = 0
    width: int = 0
    height: int = 0
    file_size: int = 0
    generation_time: float = 0.0
    negative_prompt: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    published_at: Optional[datetime] = None


@dataclass
class Pin:
    """Record of a published Pinterest pin.

    Attributes:
        pinterest_pin_id: The pin ID returned by Pinterest API.
        image_id: Foreign key to the ImageRecord.
        board_id: The Pinterest board this pin was published to.
        url: Public URL of the pin.
        created_at: Timestamp when the pin was created.
        saves: Number of saves (updated by analytics).
        clicks: Number of clicks (updated by analytics).
    """

    pinterest_pin_id: str = ""
    image_id: int = 0
    board_id: str = ""
    url: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    saves: int = 0
    clicks: int = 0


@dataclass
class PublicationRecord:
    """Record of a pin publication attempt.

    Attributes:
        id: Database row ID (assigned on insert).
        image_id: Foreign key to the source ImageRecord.
        board_id: The Pinterest board ID or name this was published to.
        title: Pin title used during publication.
        description: Pin description used during publication.
        tags: Comma-separated tags used during publication.
        published_at: Timestamp when the pin was successfully published.
        pinterest_pin_id: The pin ID returned by Pinterest API on success.
        status: Current status of the publication attempt.
        error: Error message if status is FAILED.
        created_at: Timestamp when the record was created.
    """

    id: int = 0
    image_id: int = 0
    board_id: str = ""
    title: str = ""
    description: str = ""
    tags: str = ""
    published_at: Optional[datetime] = None
    pinterest_pin_id: Optional[str] = None
    status: PublicationStatus = PublicationStatus.PENDING
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AccountConfig:
    """Per-account configuration.

    Attributes:
        name: Account display name (also used for env-var resolution).
        tokens: API tokens loaded from environment variables.
        pins_per_day: Maximum pins to publish per day for this account.
        niches: List of niche names this account manages.
        enabled_backends: Ordered list of image generation backends.
    """

    name: str = ""
    tokens: dict = field(default_factory=dict)
    pins_per_day: int = 10
    niches: list = field(default_factory=list)
    enabled_backends: list = field(default_factory=list)
    board_mapping: dict = field(default_factory=dict)


@dataclass
class NicheConfig:
    """Per-niche configuration.

    Attributes:
        name: Niche identifier (e.g. 'cozy-living-room').
        board_id: Pinterest board ID for this niche.
        template_dir: Path to YAML template directory.
        gen_settings: Generation parameters (steps, guidance_scale, etc.).
    """

    name: str = ""
    board_id: str = ""
    template_dir: str = ""
    gen_settings: dict = field(default_factory=dict)
