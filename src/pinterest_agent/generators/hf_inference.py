"""HuggingFaceProvider — generates images via the Hugging Face Inference API.

Uses ``huggingface_hub.InferenceClient`` for serverless inference.
Requires an HF API token set in the ``HF_API_TOKEN`` environment variable.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from pinterest_agent.generators.base import (
    GenerationResult,
    ImageGenerator,
    register_provider,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "black-forest-labs/FLUX.1-dev"
_HF_TOKEN_ENV = "HF_API_TOKEN"


class HuggingFaceProvider(ImageGenerator):
    """Cloud-based image generation via the Hugging Face Inference API.

    Uses the free tier of the HF Inference API. Rate limits apply.
    Configure the API token via the ``HF_API_TOKEN`` environment variable.

    Falls back to SD 3.5 if FLUX.1-dev is unavailable on the free tier.
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_token: Optional[str] = None,
        fallback_model: str = "stabilityai/stable-diffusion-3.5-large",
        timeout: int = 120,
    ) -> None:
        """Initialize the Hugging Face provider.

        Args:
            model: HF model ID for image generation.
            api_token: HF API token. Falls back to ``HF_API_TOKEN`` env var.
            fallback_model: Model to try if the primary is rate-limited.
            timeout: Request timeout in seconds.
        """
        self._model = model
        self._api_token = api_token or os.environ.get(_HF_TOKEN_ENV, "")
        self._fallback_model = fallback_model
        self._timeout = timeout
        self._client: object = None  # InferenceClient — lazy-loaded

    # ------------------------------------------------------------------
    # ImageGenerator interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "huggingface"

    def is_available(self) -> bool:
        """Check whether ``huggingface_hub`` is installed and an API token is set."""
        try:
            import huggingface_hub  # noqa: F401
        except ImportError:
            logger.warning(
                "huggingface_hub not installed. "
                "Install with: pip install huggingface_hub"
            )
            return False

        if not self._api_token:
            logger.warning(
                "HF_API_TOKEN not set. "
                "Set the HF_API_TOKEN environment variable or pass api_token."
            )
            return False

        return True

    def generate(
        self,
        prompt: str,
        seed: Optional[int] = None,
        **kwargs: object,
    ) -> GenerationResult:
        """Generate an image via the HF Inference API.

        Args:
            prompt: Text prompt for generation.
            seed: Seed for deterministic output (if supported by the model).
            **kwargs: Override defaults (negative_prompt, num_inference_steps, etc.).

        Returns:
            GenerationResult with the PIL image on success.
        """
        if not self.is_available():
            return GenerationResult(
                success=False,
                error="HuggingFace dependencies not available or HF_API_TOKEN not set",
                provider=self.name,
            )

        start = time.time()

        try:
            client = self._get_client()
            gen_seed = seed if seed is not None else 0

            # Prepare inference parameters
            params: dict[str, object] = {
                "seed": gen_seed,
            }
            if "negative_prompt" in kwargs:
                params["negative_prompt"] = kwargs["negative_prompt"]

            # Try primary model
            try:
                image = client.text_to_image(
                    prompt,
                    model=self._model,
                    **params,  # type: ignore[arg-type]
                )
            except Exception as primary_exc:
                # On rate-limit or model-load failure, try fallback
                exc_str = str(primary_exc).lower()
                if "rate limit" in exc_str or "loading" in exc_str:
                    logger.warning(
                        "Primary model %s failed (%s), trying fallback %s",
                        self._model,
                        primary_exc,
                        self._fallback_model,
                    )
                    image = client.text_to_image(
                        prompt,
                        model=self._fallback_model,
                        **params,  # type: ignore[arg-type]
                    )
                else:
                    raise

            elapsed = time.time() - start
            logger.info(
                "Generated image via HF Inference in %.2fs (model=%s, seed=%s)",
                elapsed,
                self._model,
                gen_seed,
            )

            return GenerationResult(
                success=True,
                image=image,
                width=image.width,
                height=image.height,
                generation_time=elapsed,
                provider=self.name,
                seed=gen_seed,
            )

        except Exception as exc:
            elapsed = time.time() - start
            logger.exception(
                "HuggingFace generation failed after %.2fs", elapsed
            )
            return GenerationResult(
                success=False,
                error=str(exc),
                generation_time=elapsed,
                provider=self.name,
                seed=seed,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> object:
        """Lazy-load and return the HF InferenceClient."""
        if self._client is not None:
            return self._client

        from huggingface_hub import InferenceClient

        self._client = InferenceClient(
            token=self._api_token,
            timeout=self._timeout,
        )
        return self._client


# Auto-register on import
register_provider("huggingface", HuggingFaceProvider)
