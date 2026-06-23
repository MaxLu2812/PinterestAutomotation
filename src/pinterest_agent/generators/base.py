"""Abstract base class for image generation providers."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from pinterest_agent.config.loader import RetryConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry utility
# ---------------------------------------------------------------------------

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[..., T],
    retry_config: RetryConfig,
    context: str = "",
    *args,
    **kwargs,
) -> T:
    """Execute *fn* with exponential backoff retry logic.

    Args:
        fn: The callable to execute.
        retry_config: Retry/backoff parameters.
        context: Optional context string for log messages.
        *args: Passed through to *fn*.
        **kwargs: Passed through to *fn*.

    Returns:
        The return value of *fn*.

    Raises:
        The last exception raised by *fn* if all retries are exhausted.
    """
    last_exc: Optional[Exception] = None
    max_retries = retry_config.max_generation_retries
    base_delay = retry_config.base_delay_seconds
    use_backoff = retry_config.exponential_backoff

    label = f" [{context}]" if context else ""

    for attempt in range(1, max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Attempt %d/%d failed%s: %s",
                attempt,
                max_retries,
                label,
                exc,
            )
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1)) if use_backoff else base_delay
                logger.debug("Retrying in %.2fs ...", delay)
                time.sleep(delay)

    raise RuntimeError(
        f"Operation failed after {max_retries} retries{label}: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    """Result of a single image generation attempt.

    Attributes:
        success: Whether the generation succeeded.
        image: PIL Image if successful, None otherwise.
        image_path: Path to the generated image on disk (set after saving).
        width: Width of the generated image in pixels.
        height: Height of the generated image in pixels.
        generation_time: Time taken to generate in seconds.
        error: Error message if generation failed.
        provider: Name of the provider that generated the image.
        seed: Seed used for generation.
    """

    success: bool = False
    image: object = None  # PIL.Image — avoid type import in base
    image_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    generation_time: Optional[float] = None
    error: Optional[str] = None
    provider: Optional[str] = None
    seed: Optional[int] = None


class ImageGenerator(ABC):
    """Abstract interface for image generation providers.

    Each provider implements ``generate``, ``is_available``, and ``name``.
    The factory uses these to select and instantiate backends.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        seed: Optional[int] = None,
        **kwargs: object,
    ) -> GenerationResult:
        """Generate an image from a text prompt.

        Must be deterministic when a seed is provided — the same prompt + seed
        should produce the same image.

        Args:
            prompt: The text prompt to generate from.
            seed: Optional seed for deterministic generation.
            **kwargs: Provider-specific overrides (e.g. negative_prompt, num_inference_steps).

        Returns:
            A GenerationResult with the image (if successful) or error details.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether this provider can run in the current environment.

        Checks dependencies (imports), hardware (GPU), and configuration (API keys).

        Returns:
            True if the provider is ready to use, False otherwise.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier string used in config and metadata.

        Returns:
            Short provider name, e.g. 'local_diffusers', 'huggingface'.
        """
        ...


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDER_REGISTRY: dict[str, type[ImageGenerator]] = {}


def register_provider(name: str, cls: type[ImageGenerator]) -> None:
    """Register an ImageGenerator class under a config key name.

    Args:
        name: Config key (e.g. 'local_diffusers', 'huggingface').
        cls: The ImageGenerator subclass to register.
    """
    _PROVIDER_REGISTRY[name] = cls


def get_provider_class(name: str) -> type[ImageGenerator]:
    """Look up a registered provider class by name.

    Args:
        name: Config key for the provider.

    Returns:
        The registered ImageGenerator subclass.

    Raises:
        KeyError: If the provider name is not registered.
    """
    if name not in _PROVIDER_REGISTRY:
        raise KeyError(
            f"Unknown provider '{name}'. "
            f"Registered providers: {list(_PROVIDER_REGISTRY)}"
        )
    return _PROVIDER_REGISTRY[name]


def list_registered_providers() -> list[str]:
    """Return all registered provider names."""
    return list(_PROVIDER_REGISTRY)
