"""ImagePipeline — orchestrates end-to-end image generation.

Flows:
1. Dequeue pending prompts or filter by prompt IDs
2. For each prompt, try providers in priority order (local → HF)
3. Process image (crop, resize to 1000×1500)
4. Compute SHA256, check for duplicates
5. Save as WEBP with proper naming
6. Store metadata in image_repo
7. Update prompt status

Failures are isolated — one failing prompt does not crash the batch.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from pinterest_agent.config.loader import GeneratorConfig, RetryConfig
from pinterest_agent.dedup.perceptual_hash import compute_phash, hamming_distance
from pinterest_agent.domain.models import ImageRecord, ImageStatus, Prompt
from pinterest_agent.domain.repositories import ImageRepository, PromptRepository
from pinterest_agent.generators.base import (
    GenerationResult,
    ImageGenerator,
    retry_with_backoff,
)
from pinterest_agent.utils.image_utils import process_image, save_image

logger = logging.getLogger(__name__)

# Default phash threshold (Hamming distance)
_PHASH_THRESHOLD = 5


@dataclass
class PipelineStats:
    """Accumulated statistics for a pipeline run."""

    total: int = 0
    skipped_already_generated: int = 0
    skipped_duplicate: int = 0
    succeeded: int = 0
    failed: int = 0


class ImagePipeline:
    """Orchestrates image generation from queued prompts.

    Attributes:
        prompt_repo: Repository for prompt queue operations.
        image_repo: Repository for image metadata.
        generators: Ordered list of ImageGenerator instances (priority chain).
        storage_root: Root directory for image storage.
        target_width: Output image width in pixels.
        target_height: Output image height in pixels.
        image_quality: WEBP quality (1-100).
    """

    def __init__(
        self,
        prompt_repo: PromptRepository,
        image_repo: ImageRepository,
        generators: list[ImageGenerator],
        storage_root: str | Path = "storage",
        target_width: int = 1000,
        target_height: int = 1500,
        image_quality: int = 90,
        generator_config: Optional[GeneratorConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        phash_threshold: int = _PHASH_THRESHOLD,
    ) -> None:
        self.prompt_repo = prompt_repo
        self.image_repo = image_repo
        self.generators = generators
        self.retry_config = retry_config or RetryConfig()
        self.phash_threshold = phash_threshold

        # Resolve from generator_config if provided (overrides individual params)
        if generator_config is not None:
            self.storage_root = Path(generator_config.output_directory).parent.parent  # e.g. "storage"
            self.target_width = generator_config.target_width
            self.target_height = generator_config.target_height
            self.image_quality = generator_config.image_quality
        else:
            self.storage_root = Path(storage_root)
            self.target_width = target_width
            self.target_height = target_height
            self.image_quality = image_quality

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        prompt_ids: Optional[list[int]] = None,
        max_count: Optional[int] = None,
    ) -> PipelineStats:
        """Run the image generation pipeline.

        Args:
            prompt_ids: Optional list of specific prompt IDs to process.
            max_count: Maximum number of prompts to process (None = unlimited).

        Returns:
            PipelineStats with counts of what happened.
        """
        stats = PipelineStats()

        if prompt_ids:
            prompts = self._fetch_prompts_by_ids(prompt_ids)
        else:
            prompts = self.prompt_repo.dequeue(limit=max_count or 100)

        if not prompts:
            logger.info("No pending prompts to process.")
            return stats

        stats.total = len(prompts)
        logger.info("Pipeline processing %d prompt(s)", stats.total)

        for prompt in prompts:
            self._process_single_prompt(prompt, stats)

        logger.info(
            "Pipeline complete: %d total, %d generated, %d skipped "
            "(already_generated=%d, duplicate=%d), %d failed",
            stats.total,
            stats.succeeded,
            stats.skipped_already_generated + stats.skipped_duplicate,
            stats.skipped_already_generated,
            stats.skipped_duplicate,
            stats.failed,
        )
        return stats

    # ------------------------------------------------------------------
    # Internal — single prompt processing
    # ------------------------------------------------------------------

    def _process_single_prompt(
        self,
        prompt: Prompt,
        stats: PipelineStats,
    ) -> None:
        """Process a single prompt through the entire pipeline."""
        logger.info(
            "Processing prompt %d (niche=%s, seed=%d)",
            prompt.id,
            prompt.aesthetic,
            prompt.variable_seed,
        )

        # Dedup check 1: already has a generated image?
        existing = self.image_repo.find_by_prompt_id(prompt.id)
        if existing and existing.status == ImageStatus.GENERATED:
            logger.info(
                "Prompt %d already has a generated image (id=%d), skipping",
                prompt.id,
                existing.id,
            )
            stats.skipped_already_generated += 1
            return

        # Try providers in priority order
        generation_result = self._try_providers(prompt)
        if not generation_result or not generation_result.success:
            self._handle_generation_failure(prompt, generation_result)
            stats.failed += 1
            return

        # Process image (crop, resize)
        processed = self._process_generated_image(generation_result)
        if processed is None:
            self._handle_generation_failure(
                prompt,
                GenerationResult(
                    success=False,
                    error="Image processing failed (crop/resize)",
                    provider=generation_result.provider,
                ),
            )
            stats.failed += 1
            return

        # Dedup check 2: SHA256 already exists?
        sha256 = compute_sha256(processed)
        duplicate = self.image_repo.find_by_sha256(sha256)
        if duplicate:
            logger.info(
                "SHA256 duplicate detected (prompt %d → existing image %d), skipping",
                prompt.id,
                duplicate.id,
            )
            self.prompt_repo.mark_failed(prompt.id, "duplicate: SHA256 match")
            stats.skipped_duplicate += 1
            return

        # Dedup check 3: Perceptual hash (near-duplicate detection)
        phash = compute_phash(processed)
        if phash:
            # Check exact phash match first
            phash_dup = self.image_repo.find_by_perceptual_hash(phash)
            if phash_dup:
                logger.info(
                    "Perceptual hash duplicate (exact) detected (prompt %d → existing image %d), skipping",
                    prompt.id,
                    phash_dup.id,
                )
                self.prompt_repo.mark_failed(prompt.id, "duplicate: perceptual hash match")
                stats.skipped_duplicate += 1
                return

            # Broader check: compare against recent images for the same niche
            if self.phash_threshold > 0:
                recent = self.image_repo.query(status="generated", niche=prompt.aesthetic, limit=100)
                for candidate in recent:
                    if candidate.phash:
                        distance = hamming_distance(phash, candidate.phash)
                        if distance <= self.phash_threshold:
                            logger.info(
                                "Perceptual hash near-duplicate detected (prompt %d, distance=%d, existing image %d), skipping",
                                prompt.id,
                                distance,
                                candidate.id,
                            )
                            self.prompt_repo.mark_failed(
                                prompt.id, f"duplicate: perceptual hash near-match (distance={distance})"
                            )
                            stats.skipped_duplicate += 1
                            return

        # Save as WEBP
        today = date.today()
        date_str = today.strftime("%Y-%m-%d")
        short_hash = sha256[:8]
        seed = generation_result.seed or prompt.variable_seed

        output_path = save_image(
            image=processed,
            output_dir=self.storage_root / "images" / "processed",
            niche=prompt.aesthetic,
            date_str=date_str,
            seed=seed,
            short_hash=short_hash,
            quality=self.image_quality,
        )

        # Determine file size
        file_size = output_path.stat().st_size if output_path.exists() else 0

        # Store metadata
        record = ImageRecord(
            prompt_id=prompt.id,
            prompt_hash=prompt.text,  # using prompt text as the hash key
            phash=phash or "",
            sha256=sha256,
            file_path=str(output_path),
            status=ImageStatus.GENERATED,
            niche=prompt.aesthetic,
            backend=generation_result.provider or "",
            seed=seed,
            width=processed.width,
            height=processed.height,
            file_size=file_size,
            generation_time=generation_result.generation_time or 0.0,
        )
        image_id = self.image_repo.save(record)
        logger.info("Saved image record %d → %s", image_id, output_path)

        # Mark prompt as generated
        self.prompt_repo.mark_done(prompt.id)

        stats.succeeded += 1

    def _try_providers(self, prompt: Prompt) -> Optional[GenerationResult]:
        """Try each generator in priority order (with per-provider retry)."""
        last_error: Optional[str] = None
        for generator in self.generators:
            if not generator.is_available():
                logger.debug("Provider %s not available, skipping", generator.name)
                continue

            seed = prompt.variable_seed

            # Wrap each provider call with retry logic
            def _attempt(g=generator, txt=prompt.text, sd=seed) -> GenerationResult:
                logger.info("Trying provider %s (seed=%d)", g.name, sd)
                if not g.is_available():
                    return GenerationResult(
                        success=False,
                        error=f"Provider {g.name} not available",
                        provider=g.name,
                    )
                return g.generate(txt, seed=sd)

            try:
                result = retry_with_backoff(
                    _attempt,
                    retry_config=self.retry_config,
                    context=f"provider={generator.name}, prompt={prompt.id}",
                )
            except Exception as exc:
                logger.exception(
                    "Provider %s exhausted retries for prompt %d", generator.name, prompt.id
                )
                last_error = str(exc)
                continue

            if result.success:
                return result

            last_error = result.error
            logger.warning(
                "Provider %s failed (seed=%d): %s",
                generator.name,
                seed,
                result.error,
            )

        # All providers exhausted
        return GenerationResult(
            success=False,
            error=f"All providers exhausted. Last error: {last_error}",
            provider="none",
        )

    def _process_generated_image(
        self,
        result: GenerationResult,
    ) -> object:
        """Crop and resize the generated image to target dimensions.

        Returns the processed PIL.Image, or None on failure.
        """
        try:
            image = result.image
            if image is None:
                return None
            return process_image(
                image,
                target_width=self.target_width,
                target_height=self.target_height,
            )
        except Exception as exc:
            logger.exception("Image processing failed: %s", exc)
            return None

    def _handle_generation_failure(
        self,
        prompt: Prompt,
        result: Optional[GenerationResult],
    ) -> None:
        """Mark a prompt as failed and record the error."""
        error_msg = result.error if result and result.error else "Unknown error"
        logger.error(
            "Generation failed for prompt %d: %s", prompt.id, error_msg
        )
        # Save failed image record
        record = ImageRecord(
            prompt_id=prompt.id,
            prompt_hash=prompt.text,
            file_path="",
            status=ImageStatus.FAILED,
            niche=prompt.aesthetic,
            backend=result.provider if result and result.provider else "",
            seed=prompt.variable_seed,
            error=error_msg,
        )
        self.image_repo.save(record)
        self.prompt_repo.mark_failed(prompt.id, error_msg)

    def _fetch_prompts_by_ids(self, prompt_ids: list[int]) -> list[Prompt]:
        """Fetch specific prompts by their IDs.

        Queries all prompts and filters by the requested IDs.
        """
        all_prompts = self.prompt_repo.query(limit=5000)
        id_set = set(prompt_ids)
        return [p for p in all_prompts if p.id in id_set]


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def compute_sha256(image: object) -> str:
    """Compute the SHA256 hex digest of a PIL Image's bytes.

    Args:
        image: A PIL.Image instance.

    Returns:
        Hex string of the SHA256 hash.
    """
    buf = io.BytesIO()
    image.save(buf, format="PNG")  # type: ignore[union-attr]
    return hashlib.sha256(buf.getvalue()).hexdigest()
