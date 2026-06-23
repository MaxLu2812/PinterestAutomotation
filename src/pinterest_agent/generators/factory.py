"""GeneratorFactory — creates ImageGenerator instances from config and priority chains."""

from __future__ import annotations

from typing import Optional

from pinterest_agent.generators.base import (
    ImageGenerator,
    get_provider_class,
    list_registered_providers,
)


class GeneratorFactory:
    """Creates :class:`ImageGenerator` instances from config key names.

    Provider selection priority:
    1. Explicit provider name in config
    2. First available provider in a configured priority list

    Usage::

        factory = GeneratorFactory()

        # Single provider by name
        gen = factory.create("local_diffusers", device="cpu")

        # Priority chain — tries each until one is available
        chain = factory.create_priority_chain(
            ["local_diffusers", "huggingface"]
        )
        for gen in chain:
            if gen.is_available():
                result = gen.generate(prompt, seed=42)
                break
    """

    def create(self, name: str, **kwargs: object) -> ImageGenerator:
        """Instantiate a single provider by config key name.

        Args:
            name: Provider config key (e.g. 'local_diffusers', 'huggingface').
            **kwargs: Provider-specific constructor arguments.

        Returns:
            An initialized ImageGenerator instance.

        Raises:
            KeyError: If the provider name is not registered.
        """
        cls = get_provider_class(name)
        return cls(**kwargs)  # type: ignore[call-arg]

    def create_priority_chain(
        self,
        priority: list[str],
        **kwargs: object,
    ) -> list[ImageGenerator]:
        """Create a list of providers in priority order.

        Args:
            priority: Ordered list of provider config keys.
            **kwargs: Shared constructor arguments (passed to all providers).

        Returns:
            List of ImageGenerator instances in the given priority order.
        """
        return [self.create(name, **kwargs) for name in priority]

    @staticmethod
    def first_available(
        generators: list[ImageGenerator],
    ) -> Optional[ImageGenerator]:
        """Return the first available generator from a priority chain.

        Args:
            generators: Ordered list of generators to try.

        Returns:
            The first generator whose ``is_available()`` returns True,
            or None if none are available.
        """
        for gen in generators:
            if gen.is_available():
                return gen
        return None

    @staticmethod
    def list_providers() -> list[str]:
        """List all registered provider names."""
        return list_registered_providers()
