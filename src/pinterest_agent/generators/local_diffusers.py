"""LocalDiffusersProvider — runs Stable Diffusion locally via the ``diffusers`` library.

Supports AMD DirectML (Windows), ROCm (Linux), and CPU fallback.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from pinterest_agent.generators.base import (
    GenerationResult,
    ImageGenerator,
    register_provider,
)

logger = logging.getLogger(__name__)

# Default model: lightweight SD 1.5 for lower VRAM; swap to SDXL for quality.
_DEFAULT_MODEL = "runwayml/stable-diffusion-v1-5"
_DEFAULT_NEGATIVE_PROMPT = (
    "nsfw, lowres, bad anatomy, bad hands, extra fingers, blurry, "
    "畸形的, 丑陋的, 低质量"
)


class LocalDiffusersProvider(ImageGenerator):
    """On-device image generation using Hugging Face ``diffusers``.

    Requires ``torch``, ``diffusers``, and ``transformers`` to be installed
    (see ``[project.optional-dependencies] local`` in ``pyproject.toml``).

    Hardware detection priority:
    1. ``torch-directml`` (Windows AMD)
    2. ``torch.cuda`` (NVIDIA)
    3. CPU fallback
    """

    def __init__(
        self,
        model_id: str = _DEFAULT_MODEL,
        device: Optional[str] = None,
        dtype: object = None,
        safety_checker: bool = True,
        negative_prompt: str = _DEFAULT_NEGATIVE_PROMPT,
        num_inference_steps: int = 30,
        guidance_scale: float = 7.5,
    ) -> None:
        """Initialize the local diffusers provider.

        Args:
            model_id: Hugging Face model ID for the Stable Diffusion pipeline.
            device: Override device ('cpu', 'cuda', 'directml'). Auto-detected if None.
            dtype: Torch dtype override (e.g. ``torch.float16``).
            safety_checker: Enable NSFW safety checker.
            negative_prompt: Default negative prompt text.
            num_inference_steps: Number of denoising steps.
            guidance_scale: Classifier-free guidance scale.
        """
        self._model_id = model_id
        self._device_override = device
        self._dtype = dtype
        self._safety_checker = safety_checker
        self._negative_prompt = negative_prompt
        self._num_inference_steps = num_inference_steps
        self._guidance_scale = guidance_scale

        self._pipe: object = None  # StableDiffusionPipeline — lazy-loaded
        self._device: str = "cpu"
        self._is_available_cache: Optional[bool] = None

    # ------------------------------------------------------------------
    # ImageGenerator interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "local_diffusers"

    def is_available(self) -> bool:
        """Check whether torch + diffusers are importable.

        Caches the result after the first check.
        """
        if self._is_available_cache is not None:
            return self._is_available_cache

        try:
            import diffusers  # noqa: F401
            import torch  # noqa: F401
            import transformers  # noqa: F401
            self._is_available_cache = True
        except ImportError as exc:
            logger.warning("LocalDiffusers not available: %s", exc)
            self._is_available_cache = False

        return self._is_available_cache

    def generate(
        self,
        prompt: str,
        seed: Optional[int] = None,
        **kwargs: object,
    ) -> GenerationResult:
        """Generate an image using the local diffusion pipeline.

        Args:
            prompt: Text prompt for generation.
            seed: Seed for deterministic output.
            **kwargs: Override defaults (negative_prompt, num_inference_steps, etc.).

        Returns:
            GenerationResult with the PIL image on success.
        """
        if not self.is_available():
            return GenerationResult(
                success=False,
                error="LocalDiffusers dependencies not installed",
                provider=self.name,
            )

        start = time.time()

        try:
            pipe = self._get_pipeline()
            gen_seed = seed if seed is not None else 0

            import torch

            # Deterministic generation
            torch.manual_seed(gen_seed)
            if self._device == "cuda":
                torch.cuda.manual_seed_all(gen_seed)

            negative = kwargs.get("negative_prompt", self._negative_prompt)
            steps = int(kwargs.get("num_inference_steps", self._num_inference_steps))
            guidance = float(kwargs.get("guidance_scale", self._guidance_scale))

            # Generate
            result = pipe(  # type: ignore[call-arg]
                prompt=prompt,
                negative_prompt=negative if negative else None,
                num_inference_steps=steps,
                guidance_scale=guidance,
                generator=None,  # seed set via torch.manual_seed
            )
            image = result.images[0]

            elapsed = time.time() - start
            logger.info(
                "Generated image in %.2fs (seed=%s, model=%s)",
                elapsed,
                gen_seed,
                self._model_id,
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
            logger.exception("LocalDiffusers generation failed after %.2fs", elapsed)
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

    def _get_pipeline(self) -> object:
        """Lazy-load and return the Stable Diffusion pipeline."""
        if self._pipe is not None:
            return self._pipe

        import torch
        from diffusers import StableDiffusionPipeline

        # Detect device
        device = self._resolve_device()

        try:
            pipe = StableDiffusionPipeline.from_pretrained(
                self._model_id,
                torch_dtype=self._dtype or torch.float32,
                safety_checker=self._get_safety_checker(),
            )
            pipe = pipe.to(device)
            # Enable memory efficient attention if available
            if hasattr(pipe, "enable_attention_slicing"):
                pipe.enable_attention_slicing()
        except Exception:
            logger.exception("Failed to load model %s on %s", self._model_id, device)
            raise

        self._pipe = pipe
        self._device = device
        return pipe

    def _resolve_device(self) -> str:
        """Determine the best available compute device."""
        if self._device_override:
            return self._device_override

        import torch

        # 1. DirectML (Windows AMD)
        try:
            import torch_directml  # type: ignore[import-untyped]
            device = torch_directml.device()
            # Verify it works
            _ = torch.tensor([1.0], device=device)
            logger.info("Using DirectML device: %s", device)
            self._device = str(device)
            return str(device)
        except ImportError:
            pass
        except Exception:
            pass

        # 2. CUDA (NVIDIA)
        if torch.cuda.is_available():
            logger.info("Using CUDA device: %s", torch.cuda.get_device_name(0))
            return "cuda"

        # 3. CPU fallback
        logger.info("No GPU detected, falling back to CPU")
        return "cpu"

    def _get_safety_checker(self) -> object:
        """Return safety checker config based on the safety_checker flag."""
        if not self._safety_checker:
            return None
        # Use default safety checker from diffusers
        return True  # diffusers uses default when True


# Auto-register on import
register_provider("local_diffusers", LocalDiffusersProvider)
