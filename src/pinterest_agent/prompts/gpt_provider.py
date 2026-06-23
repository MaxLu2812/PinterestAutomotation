"""GPT-4o-mini provider for prompt refinement with retry logic."""

from __future__ import annotations

import logging
import time
from typing import Optional

from pinterest_agent.config.loader import RetryConfig
from pinterest_agent.prompts.provider import PromptProvider

logger = logging.getLogger(__name__)

_DEFAULT_RETRIES = 3
_BASE_DELAY = 1.0  # seconds
_MAX_DELAY = 30.0


class GPT4MiniProvider(PromptProvider):
    """Provider that sends prompts to OpenAI GPT-4o-mini for refinement.

    Supports a **passthrough** mode (no API key) that returns the prompt
    as-is — useful for local testing and V1 development.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        max_retries: int = _DEFAULT_RETRIES,
        retry_config: Optional[RetryConfig] = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

        # Resolve retry parameters: explicit arg > retry_config > default
        if retry_config is not None:
            self._max_retries = retry_config.max_generation_retries
            self._base_delay = retry_config.base_delay_seconds
            self._exponential_backoff = retry_config.exponential_backoff
        else:
            self._max_retries = max_retries
            self._base_delay = _BASE_DELAY
            self._exponential_backoff = True

    # ------------------------------------------------------------------
    # PromptProvider interface
    # ------------------------------------------------------------------

    def generate(self, prompt_text: str, seed: Optional[int] = None, **kwargs) -> str:  # type: ignore[override]
        """Send *prompt_text* to GPT-4o-mini for refinement.

        Args:
            prompt_text: The base prompt to send.
            seed: Optional seed for deterministic results.
            **kwargs: Passed through to the API call (temperature, etc.).

        Returns:
            Refined prompt text from the model.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        if not self.is_available():
            logger.info("GPT-4o-mini unavailable — returning passthrough prompt")
            return prompt_text

        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                return self._call_api(prompt_text, seed=seed, **kwargs)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "GPT-4o-mini attempt %d/%d failed: %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
                if attempt < self._max_retries:
                    delay = (
                        self._base_delay * (2 ** (attempt - 1))
                        if self._exponential_backoff
                        else self._base_delay
                    )
                    delay = min(delay, _MAX_DELAY)
                    time.sleep(delay)

        raise RuntimeError(
            f"GPT-4o-mini failed after {self._max_retries} retries: {last_error}"
        ) from last_error

    def is_available(self) -> bool:
        """Available when an API key is set and the openai package is installed."""
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401
        except ImportError:
            logger.warning("openai package not installed — provider unavailable")
            return False
        return True

    def name(self) -> str:
        return "gpt-4o-mini"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_api(self, prompt_text: str, seed: Optional[int] = None, **kwargs) -> str:
        """Execute one API call. Broken out so tests can mock it easily."""
        import openai

        client = openai.OpenAI(api_key=self._api_key)

        params = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a prompt engineer specialized in aesthetic image "
                        "generation. Refine the following prompt to be more vivid, "
                        "detailed, and Pinterest-optimized. Keep it under 200 words."
                    ),
                },
                {"role": "user", "content": prompt_text},
            ],
            "max_tokens": 300,
            "temperature": kwargs.get("temperature", 0.7),
        }

        if seed is not None:
            params["seed"] = seed

        response = client.chat.completions.create(**params)
        return response.choices[0].message.content or prompt_text
