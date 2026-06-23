"""Abstract prompt provider interface.

All prompt backends (GPT-4o-mini, local, passthrough) implement this ABC
so the PromptEngine can swap providers without coupling to the API details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class PromptProvider(ABC):
    """Interface for prompt generation/refinement backends."""

    @abstractmethod
    def generate(self, prompt_text: str, **kwargs) -> str:
        """Generate or refine a prompt. Returns finalized prompt text.

        Args:
            prompt_text: Base prompt text (e.g. a template with substitutions).
            **kwargs: Provider-specific options (seed, temperature, etc.).

        Returns:
            The finalized prompt string.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether this provider is ready to accept requests."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. 'gpt-4o-mini', 'passthrough')."""
        ...
